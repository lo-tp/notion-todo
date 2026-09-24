"""Notion → Postgres sync engine.

Usage:
    uv run python sync/sync.py [--full]

First run (or --full): full sync of all databases.
Subsequent runs: incremental sync based on last_edited_time watermark.
"""

import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import psycopg
from notion_client import Client

# --- Config ---

# Database IDs loaded from .env (see env loading below)

# Expected fields per database (must match sync/schema.py and sync.py)
EXPECTED_SCHEMA = {
    "tasks": {
        "Name",
        "Tags",
        "Status",
        "Due Date",
        "Projects",
        "Priority",
        "Description",
        "Created time",
        "Time Tracking DB",
        "Time Spent",
        "Weekly Time Spent",
    },
    "projects": {"Name", "Status"},
    "records": {"Name", "Tags", "Created time", "Projects", "Summary"},
    "time_tracking": {
        "Name",
        "Tasks",
        "Start Time",
        "End Time",
        "Status",
        "Duration",
        "Weekly Duration",
        "Project",
    },
}

# Load .env
env_path = Path(__file__).parent.parent / ".env"
env = {}
for line in env_path.read_text().splitlines():
    if line and not line.startswith("#"):
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()

NOTION_TOKEN = env["NOTION_TOKEN"]
DATABASE_URL = env["DATABASE_URL"]

DATABASES = {
    "tasks": env["NOTION_DB_TASKS"],
    "projects": env["NOTION_DB_PROJECTS"],
    "records": env["NOTION_DB_RECORDS"],
    "time_tracking": env["NOTION_DB_TIME_TRACKING"],
}
client = Client(auth=NOTION_TOKEN)
# Strip SQLAlchemy-style prefix if present
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("sync")


# --- Notion API ---

# Cache of data-source IDs resolved from database IDs. The current Notion API
# splits a database into data sources; record queries and properties live on
# the data source, so we resolve that ID once per database.
_DATA_SOURCE_IDS = {}


def _data_source_id(db_key):
    if db_key not in _DATA_SOURCE_IDS:
        db = cast(dict, client.databases.retrieve(database_id=DATABASES[db_key]))
        _DATA_SOURCE_IDS[db_key] = db["data_sources"][0]["id"]
    return _DATA_SOURCE_IDS[db_key]


def fetch_all_records(db_key, last_edited_after=None):
    """Fetch all (or recently updated) records from a Notion database.

    Uses server-side last_edited_time filtering when a watermark is provided.
    """
    records = []
    start_cursor = None
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        if last_edited_after:
            body["filter"] = {
                "timestamp": "last_edited_time",
                "last_edited_time": {"after": last_edited_after},
            }

        data = cast(dict, client.data_sources.query(data_source_id=_data_source_id(db_key), **body))

        records.extend(data["results"])
        if data["has_more"]:
            start_cursor = data["next_cursor"]
        else:
            break
    return records


def fetch_all_ids(db_key):
    """Fetch all record IDs from a database (for soft-delete detection)."""
    ids = set()
    start_cursor = None
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        data = cast(dict, client.data_sources.query(data_source_id=_data_source_id(db_key), **body))
        for r in data["results"]:
            ids.add(r["id"])
        if data["has_more"]:
            start_cursor = data["next_cursor"]
        else:
            break
    return ids


# --- Record parsing ---


def parse_properties(record):
    props = record["properties"]

    def get_text(prop_name):
        p = props.get(prop_name, {})
        if p["type"] == "title":
            return "".join(t["plain_text"] for t in p["title"])
        if p["type"] == "rich_text":
            return "".join(t["plain_text"] for t in p["rich_text"])
        return None

    def get_select(prop_name):
        p = props.get(prop_name, {})
        if p["type"] == "select" and p["select"]:
            return p["select"]["name"]
        if p["type"] == "status" and p["status"]:
            return p["status"]["name"]
        return None

    def get_multi_select(prop_name):
        p = props.get(prop_name, {})
        if p["type"] == "multi_select":
            return [opt["name"] for opt in p["multi_select"]]
        return []

    def get_date(prop_name):
        p = props.get(prop_name, {})
        if p["type"] == "date" and p["date"]:
            return p["date"]["start"]
        return None

    def get_relation(prop_name):
        p = props.get(prop_name, {})
        if p["type"] == "relation" and p["relation"]:
            return p["relation"][0]["id"]
        return None

    return get_text, get_select, get_multi_select, get_date, get_relation


# --- Database upserts ---


def upsert_projects(conn, records):
    for r in records:
        gt, gs, gm, gd, gr = parse_properties(r)
        conn.execute(
            """
            INSERT INTO projects (id, name, status, notion_updated_at, notion_created_at, deleted_at)
            VALUES (%s, %s, %s, %s, %s, NULL)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                status = EXCLUDED.status,
                notion_updated_at = EXCLUDED.notion_updated_at,
                deleted_at = NULL
            """,
            (
                uuid.UUID(r["id"]),
                gt("Name"),
                gs("Status"),
                r["last_edited_time"],
                r["created_time"],
            ),
        )


def upsert_tasks(conn, records):
    for r in records:
        gt, gs, gm, gd, gr = parse_properties(r)
        conn.execute(
            """
            INSERT INTO tasks (id, name, tags, status, due_date, project_id, priority, description, created_at, notion_updated_at, deleted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                tags = EXCLUDED.tags,
                status = EXCLUDED.status,
                due_date = EXCLUDED.due_date,
                project_id = EXCLUDED.project_id,
                priority = EXCLUDED.priority,
                description = EXCLUDED.description,
                notion_updated_at = EXCLUDED.notion_updated_at,
                deleted_at = NULL
            """,
            (
                uuid.UUID(r["id"]),
                gt("Name"),
                gm("Tags"),
                gs("Status"),
                gd("Due Date"),
                uuid.UUID(gr("Projects")) if gr("Projects") else None,
                gs("Priority"),
                gt("Description"),
                r["created_time"],
                r["last_edited_time"],
            ),
        )


def upsert_records(conn, records):
    for r in records:
        gt, gs, gm, gd, gr = parse_properties(r)
        conn.execute(
            """
            INSERT INTO records (id, name, tags, project_id, summary, created_at, notion_updated_at, deleted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                tags = EXCLUDED.tags,
                project_id = EXCLUDED.project_id,
                summary = EXCLUDED.summary,
                notion_updated_at = EXCLUDED.notion_updated_at,
                deleted_at = NULL
            """,
            (
                uuid.UUID(r["id"]),
                gt("Name"),
                gm("Tags"),
                uuid.UUID(gr("Projects")) if gr("Projects") else None,
                gt("Summary"),
                r["created_time"],
                r["last_edited_time"],
            ),
        )


def upsert_time_tracking(conn, records):
    for r in records:
        gt, gs, gm, gd, gr = parse_properties(r)
        conn.execute(
            """
            INSERT INTO time_tracking (id, name, task_id, start_time, end_time, status, notion_updated_at, deleted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                task_id = EXCLUDED.task_id,
                start_time = EXCLUDED.start_time,
                end_time = EXCLUDED.end_time,
                status = EXCLUDED.status,
                notion_updated_at = EXCLUDED.notion_updated_at,
                deleted_at = NULL
            """,
            (
                uuid.UUID(r["id"]),
                gt("Name"),
                uuid.UUID(gr("Tasks")) if gr("Tasks") else None,
                gd("Start Time"),
                gd("End Time"),
                gs("Status"),
                r["last_edited_time"],
            ),
        )


# --- Soft delete ---


def soft_delete_missing(conn, table, db_id, live_ids):
    """Mark local rows that no longer exist in Notion as deleted."""
    conn.execute(
        f"""
        UPDATE {table}
        SET deleted_at = %s
        WHERE id NOT IN (SELECT unnest(%s::uuid[]))
          AND deleted_at IS NULL
        """,
        (datetime.now(UTC), [str(i) for i in live_ids]),
    )


# --- Schema validation ---


def check_schema(db_key):
    """Verify Notion database schema matches expected. Raise if mismatch."""
    ds = cast(dict, client.data_sources.retrieve(data_source_id=_data_source_id(db_key)))
    actual_fields = set(ds["properties"].keys())
    expected = EXPECTED_SCHEMA[db_key]

    added = actual_fields - expected
    removed = expected - actual_fields

    if added or removed:
        issues = []
        if added:
            issues.append(f"NEW in Notion: {sorted(added)}")
        if removed:
            issues.append(f"MISSING in Notion (was expected): {sorted(removed)}")
        raise SchemaMismatchError(db_key, issues)


class SchemaMismatchError(Exception):
    def __init__(self, db_key, issues):
        self.db_key = db_key
        self.issues = issues
        super().__init__(
            f"Schema mismatch for '{db_key}\n  " + "\n  ".join(issues) + "\n"
            "Refusing to sync. Update sync/schema.sql and sync/sync.py to match, then re-run."
        )


# --- Sync orchestration ---


def get_watermark(conn, db_key):
    row = conn.execute(
        "SELECT last_synced_at FROM sync_state WHERE db_id = %s", (db_key,)
    ).fetchone()
    return row[0].isoformat() if row else None


def next_watermark(conn, db_key, records):
    """Advance the watermark to the max last_edited_time of the records fetched
    this pass, so it never jumps past what we actually upserted.

    Falls back to the previous watermark when nothing was fetched, and to now on
    the very first sync. Working in Notion's last_edited_time domain (instead of
    local wall-clock) keeps incremental syncs safe: an edit's last_edited_time
    can never land behind the watermark and be skipped on the next pass.
    """
    if records:
        max_edited = max(r["last_edited_time"] for r in records)
        return datetime.fromisoformat(max_edited.replace("Z", "+00:00"))
    prev = get_watermark(conn, db_key)
    return datetime.fromisoformat(prev) if prev else datetime.now(UTC)


def set_watermark(conn, db_key, value):
    conn.execute(
        """
        INSERT INTO sync_state (db_id, last_synced_at)
        VALUES (%s, %s)
        ON CONFLICT (db_id) DO UPDATE SET last_synced_at = EXCLUDED.last_synced_at
        """,
        (db_key, value),
    )


def sync(db_key, full=False):
    db_id = DATABASES[db_key]

    # Validate schema before syncing data
    check_schema(db_key)

    log.info(f"Syncing {db_key}...")

    with psycopg.connect(DATABASE_URL) as conn:
        # Get watermark
        watermark = None if full else get_watermark(conn, db_key)

        # Fetch records
        records = fetch_all_records(db_key, last_edited_after=watermark)
        log.info(f"  Fetched {len(records)} records")

        # Upsert
        upsert = {
            "projects": upsert_projects,
            "tasks": upsert_tasks,
            "records": upsert_records,
            "time_tracking": upsert_time_tracking,
        }[db_key]
        upsert(conn, records)

        # Soft-delete: only on full sync (incremental can't detect deletes)
        if full:
            live_ids = fetch_all_ids(db_key)
            table = {
                "projects": "projects",
                "tasks": "tasks",
                "records": "records",
                "time_tracking": "time_tracking",
            }[db_key]
            soft_delete_missing(conn, table, db_id, live_ids)
            log.info("  Soft-deleted records no longer in Notion")

        # Update watermark
        set_watermark(conn, db_key, next_watermark(conn, db_key, records))
        conn.commit()
        log.info("  Done.")


def main():
    full = "--full" in sys.argv

    # Initialize schema on first run
    schema_path = Path(__file__).parent / "schema.sql"
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(schema_path.read_text().encode())
        conn.commit()

    # Sync in dependency order
    for key in ["projects", "tasks", "records", "time_tracking"]:
        try:
            sync(key, full=full)
        except SchemaMismatchError as e:
            log.error(str(e))
            sys.exit(1)

    log.info("Sync complete.")


if __name__ == "__main__":
    main()
