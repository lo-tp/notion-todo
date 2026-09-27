"""Notion → SQLite sync engine.

Imported by ``scripts/notion_cards.py`` (its ``sync`` subcommand is the only
sync entry point). The local mirror is a SQLite database at
``sync.db_path(env)`` — ``mirror.sqlite`` under the project root
by default, overridable via ``MIRROR_PATH`` in ``.env``.

First run (or ``full=True``): full sync of all databases.
Subsequent runs: incremental sync based on ``last_edited_time`` watermark.
"""

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from notion_client import Client

# --- Config ---

# Expected fields per database (must match sync/schema.sql and sync/sync.py)
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
        "Description",
        "Duration",
        "Weekly Duration",
        "Project",
    },
}

# Databases in dependency order (projects before its referencers).
DATABASES = ("projects", "tasks", "records", "time_tracking")

ENV_KEYS = {
    "projects": "NOTION_DB_PROJECTS",
    "tasks": "NOTION_DB_TASKS",
    "records": "NOTION_DB_RECORDS",
    "time_tracking": "NOTION_DB_TIME_TRACKING",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("sync")


# --- SQLite connection ---


def db_path(env: dict[str, str]) -> Path:
    """Path to the local mirror database (``MIRROR_PATH`` in .env, else
    ``mirror.sqlite`` under the project root)."""
    if env.get("MIRROR_PATH"):
        return Path(env["MIRROR_PATH"])
    return PROJECT_ROOT / "mirror.sqlite"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the mirror database, creating the parent directory if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the mirror tables/indexes (idempotent) and apply column migrations."""
    conn.executescript((Path(__file__).parent / "schema.sql").read_text())
    _migrate_columns(conn)


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """Add columns created after a mirror's initial creation (idempotent)."""
    columns = {r[1] for r in conn.execute("PRAGMA table_info(time_tracking)")}
    if "description" not in columns:
        conn.execute("ALTER TABLE time_tracking ADD COLUMN description TEXT")


# --- Notion API ---


def data_source_id(client: Client, db_id: str) -> str:
    """Resolve the (single) data-source id for a database.

    The current Notion API splits a database into data sources; record
    queries and properties live on the data source.
    """
    db = cast(dict, client.databases.retrieve(database_id=db_id))
    return db["data_sources"][0]["id"]


def fetch_all_records(client: Client, ds_id: str, last_edited_after: str | None = None):
    """Fetch all (or recently updated) records from a data source.

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

        data = cast(dict, client.data_sources.query(data_source_id=ds_id, **body))

        records.extend(data["results"])
        if data["has_more"]:
            start_cursor = data["next_cursor"]
        else:
            break
    return records


def fetch_all_ids(client: Client, ds_id: str):
    """Fetch all record IDs from a data source (for soft-delete detection)."""
    ids = set()
    start_cursor = None
    while True:
        body: dict[str, Any] = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        data = cast(dict, client.data_sources.query(data_source_id=ds_id, **body))
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
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                status = excluded.status,
                notion_updated_at = excluded.notion_updated_at,
                deleted_at = NULL
            """,
            (r["id"], gt("Name"), gs("Status"), r["last_edited_time"], r["created_time"]),
        )


def upsert_tasks(conn, records):
    for r in records:
        gt, gs, gm, gd, gr = parse_properties(r)
        conn.execute(
            """
            INSERT INTO tasks (id, name, tags, status, due_date, project_id, priority, description, created_at, notion_updated_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                tags = excluded.tags,
                status = excluded.status,
                due_date = excluded.due_date,
                project_id = excluded.project_id,
                priority = excluded.priority,
                description = excluded.description,
                notion_updated_at = excluded.notion_updated_at,
                deleted_at = NULL
            """,
            (
                r["id"],
                gt("Name"),
                json.dumps(gm("Tags")),
                gs("Status"),
                gd("Due Date"),
                gr("Projects"),
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
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                tags = excluded.tags,
                project_id = excluded.project_id,
                summary = excluded.summary,
                notion_updated_at = excluded.notion_updated_at,
                deleted_at = NULL
            """,
            (
                r["id"],
                gt("Name"),
                json.dumps(gm("Tags")),
                gr("Projects"),
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
            INSERT INTO time_tracking (id, name, task_id, start_time, end_time, status, description, notion_updated_at, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                task_id = excluded.task_id,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                status = excluded.status,
                description = excluded.description,
                notion_updated_at = excluded.notion_updated_at,
                deleted_at = NULL
            """,
            (
                r["id"],
                gt("Name"),
                gr("Tasks"),
                gd("Start Time"),
                gd("End Time"),
                gs("Status"),
                gt("Description"),
                r["last_edited_time"],
            ),
        )


# --- Soft delete ---


def soft_delete_missing(conn, table, live_ids):
    """Mark local rows that no longer exist in Notion as deleted."""
    now = datetime.now(UTC).isoformat()
    if live_ids:
        placeholders = ",".join("?" for _ in live_ids)
        conn.execute(
            f"UPDATE {table} SET deleted_at = ? "
            f"WHERE id NOT IN ({placeholders}) AND deleted_at IS NULL",
            [now, *sorted(live_ids)],
        )
    else:
        conn.execute(f"UPDATE {table} SET deleted_at = ? WHERE deleted_at IS NULL", (now,))


# --- Schema validation ---


class SchemaMismatchError(Exception):
    def __init__(self, db_key, issues):
        self.db_key = db_key
        self.issues = issues
        super().__init__(
            f"Schema mismatch for '{db_key}'\n  "
            + "\n  ".join(issues)
            + "\nRefusing to sync. Update sync/schema.sql and sync/sync.py to match, then re-run."
        )


def check_schema(client: Client, db_key: str, ds_id: str) -> None:
    """Verify Notion database schema matches expected. Raise if mismatch."""
    ds = cast(dict, client.data_sources.retrieve(data_source_id=ds_id))
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


# --- Sync orchestration ---


def get_watermark(conn, db_key: str) -> str | None:
    row = conn.execute(
        "SELECT last_synced_at FROM sync_state WHERE db_id = ?", (db_key,)
    ).fetchone()
    return row[0] if row else None


def next_watermark(conn, db_key: str, records) -> datetime:
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


def set_watermark(conn, db_key: str, value: datetime) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (db_id, last_synced_at)
        VALUES (?, ?)
        ON CONFLICT(db_id) DO UPDATE SET last_synced_at = excluded.last_synced_at
        """,
        (db_key, value.isoformat()),
    )


def sync_database(
    client: Client, env: dict[str, str], conn, db_key: str, full: bool = False
) -> int:
    """Sync one Notion database into the mirror; return the record count."""
    ds_id = data_source_id(client, env[ENV_KEYS[db_key]])

    # Validate schema before syncing data
    check_schema(client, db_key, ds_id)

    log.info(f"Syncing {db_key}...")

    watermark = None if full else get_watermark(conn, db_key)
    records = fetch_all_records(client, ds_id, last_edited_after=watermark)
    log.info(f"  Fetched {len(records)} records")

    upsert = {
        "projects": upsert_projects,
        "tasks": upsert_tasks,
        "records": upsert_records,
        "time_tracking": upsert_time_tracking,
    }[db_key]
    upsert(conn, records)

    # Soft-delete: only on full sync (incremental can't detect deletes)
    if full:
        live_ids = fetch_all_ids(client, ds_id)
        soft_delete_missing(conn, db_key, live_ids)
        log.info("  Soft-deleted records no longer in Notion")

    set_watermark(conn, db_key, next_watermark(conn, db_key, records))
    return len(records)


def sync_all(client: Client, env: dict[str, str], conn, full: bool = False) -> None:
    """Sync all databases in dependency order. Raises SchemaMismatchError."""
    for key in DATABASES:
        sync_database(client, env, conn, key, full=full)

    log.info("Sync complete.")
