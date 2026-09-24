"""Provision a new Notion workspace with the four task-management databases.

Usage:
    uv run python scripts/create_databases.py

Reads NOTION_TOKEN and NOTION_PARENT_PAGE from .env (project root).
Creates Projects, Records, Tasks, and Time Tracking DB under the parent page,
with all relations, rollups, and formulas wired so that sync/sync.py's
EXPECTED_SCHEMA is satisfied on first sync.

After creating, writes NOTION_DB_PROJECTS / NOTION_DB_RECORDS / NOTION_DB_TASKS /
NOTION_DB_TIME_TRACKING into .env and prints the IDs + the .env block.

Notion-only: the Postgres mirror is initialized by the first `sync/sync.py` run.

Uses the `notion-client` SDK (ramnes/notion-sdk-py), pinned to Notion API
version 2025-09-03. In that version a database's property schemas live on its
data source, so each database is created with an `initial_data_source` carrying
its base properties, and relations/rollups/formulas are added afterward via
`data_sources.update` (Notion requires the referenced relations/databases to
exist first).

One deliberate deviation from a live schema: the three `Status` columns are
created as `select` (Notion's API cannot create `status` columns). Same options,
no groups; sync.py reads them identically.
"""

import sys
from pathlib import Path

from notion_client import APIResponseError, Client, collect_paginated_api

# --- Config ---

NOTION_VERSION = "2025-09-03"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# The four new DB IDs get these keys in .env.
DB_ENV_KEYS = {
    "projects": "NOTION_DB_PROJECTS",
    "records": "NOTION_DB_RECORDS",
    "tasks": "NOTION_DB_TASKS",
    "time_tracking": "NOTION_DB_TIME_TRACKING",
}


def load_env():
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def write_env_keys(updates):
    """Insert or replace `key=value` lines in .env, preserving order and comments."""
    lines = ENV_PATH.read_text().splitlines()
    for key, value in updates.items():
        new_line = f"{key}={value}"
        replaced = False
        for i, existing in enumerate(lines):
            if existing.strip().split("=")[0].strip() == key:
                lines[i] = new_line
                replaced = True
                break
        if not replaced:
            lines.append(new_line)
    # Keep a single trailing newline; join without an extra blank if file ended with one.
    ENV_PATH.write_text("\n".join(lines) + "\n")


def normalize_page_id(value):
    """Accept a raw Notion page ID or a pasted page URL; return the 32-char hex ID."""
    v = value.strip().replace("-", "")
    if "/" in v:  # e.g. https://www.notion.so/.../3e5db18bdc5f808c9f6ae60a6cb8f95f
        v = v.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    return v


def provision(notion, parent_id):
    """Create and wire the four databases; return their IDs keyed by name."""

    # --- Validate parent page ---
    page = notion.pages.retrieve(page_id=parent_id)
    if page.get("archived"):
        sys.exit(f"Parent page {parent_id} is archived.")
    print(f"Parent page: {parent_id}")

    # --- Guard: refuse if a "Tasks" database already exists under the parent ---
    children = collect_paginated_api(notion.blocks.children.list, block_id=parent_id)
    # A database under a page is a `child_database` block.
    child_db_ids = [b["id"] for b in children if b["type"] == "child_database"]
    titles = {}
    # Fetch titles for database children.
    # A database under a page is a `child_database` block.
    for db_id in child_db_ids:
        db = notion.databases.retrieve(database_id=db_id)
        titles[db_id] = "".join(t.get("plain_text", "") for t in db.get("title", []))
    if "Tasks" in titles.values():
        present = sorted(
            t for t in titles.values() if t in ("Tasks", "Projects", "Records", "Time Tracking DB")
        )
        sys.exit(
            "Already provisioned: a 'Tasks' database exists under the parent page.\n"
            f"  Existing matching databases: {present or 'none'}\n"
            "  Clean them up (archive) and re-run, or point NOTION_PARENT_PAGE at an empty page."
        )

    def create_db(title, properties):
        # In the 2025-09-03 API, property schemas live on the data source, so
        # they are supplied via `initial_data_source` at creation time.
        resp = notion.databases.create(
            parent={"type": "page_id", "page_id": parent_id},
            title=[{"text": {"content": title}}],
            initial_data_source={"properties": properties},
        )
        print(f"  Created database: {title} ({resp['id']})")
        # The data source id is needed for the subsequent property updates.
        ds_id = notion.databases.retrieve(database_id=resp["id"])["data_sources"][0]["id"]
        return resp["id"], ds_id

    def add_properties(ds_id, properties):
        # Property schemas live on the data source (2025-09-03 API).
        notion.data_sources.update(data_source_id=ds_id, properties=properties)

    # --- Step 1: Create the four databases with independent properties only ---
    # Relations/rollups/formulas are added afterward (Notion requires their
    # referenced relations/databases to exist first).
    projects_id, projects_ds = create_db(
        "Projects",
        {
            "Name": {"type": "title", "title": {}},
            "Status": {
                "type": "select",
                "select": {
                    "options": [
                        {"name": "Not started", "color": "gray"},
                        {"name": "Active", "color": "blue"},
                        {"name": "Paused", "color": "yellow"},
                        {"name": "Done", "color": "green"},
                    ]
                },
            },
        },
    )

    records_id, records_ds = create_db(
        "Records",
        {
            "Name": {"type": "title", "title": {}},
            "Tags": {"type": "multi_select", "multi_select": {}},
            "Created time": {"type": "created_time", "created_time": {}},
            "Summary": {"type": "rich_text", "rich_text": {}},
        },
    )

    tasks_id, tasks_ds = create_db(
        "Tasks",
        {
            "Name": {"type": "title", "title": {}},
            "Tags": {"type": "multi_select", "multi_select": {}},
            "Status": {
                "type": "select",
                "select": {
                    "options": [
                        {"name": "Backlog", "color": "gray"},
                        {"name": "This Week", "color": "blue"},
                        {"name": "This Month", "color": "purple"},
                        {"name": "Today", "color": "orange"},
                        {"name": "Blocked", "color": "red"},
                        {"name": "In progress", "color": "yellow"},
                        {"name": "Finished", "color": "green"},
                    ]
                },
            },
            "Due Date": {"type": "date", "date": {}},
            "Priority": {
                "type": "select",
                "select": {"options": [{"name": "5", "color": "default"}]},
            },
            "Description": {"type": "rich_text", "rich_text": {}},
            "Created time": {"type": "created_time", "created_time": {}},
        },
    )

    time_tracking_id, tt_ds = create_db(
        "Time Tracking DB",
        {
            "Name": {"type": "title", "title": {}},
            "Start Time": {"type": "date", "date": {}},
            "End Time": {"type": "date", "date": {}},
            "Status": {
                "type": "select",
                "select": {
                    "options": [
                        {"name": "Stopped", "color": "gray"},
                        {"name": "Ing", "color": "yellow"},
                    ]
                },
            },
        },
    )

    # --- Step 2: Relations ---
    # Projects links are one-way (single_property) so Projects stays clean.
    add_properties(
        records_ds,
        {
            "Projects": {
                "type": "relation",
                "relation": {"data_source_id": projects_ds, "single_property": {}},
            }
        },
    )
    add_properties(
        tasks_ds,
        {
            "Projects": {
                "type": "relation",
                "relation": {"data_source_id": projects_ds, "single_property": {}},
            }
        },
    )
    # Time Tracking <-> Tasks is bidirectional; reverse auto-named "Time Tracking DB" on Tasks.
    add_properties(
        tt_ds,
        {
            "Tasks": {
                "type": "relation",
                "relation": {
                    "data_source_id": tasks_ds,
                    "dual_property": {"synced_property_name": "Time Tracking DB"},
                },
            }
        },
    )

    # --- Step 3: Time Tracking rollup + formulas (before Tasks rollups, which sum these) ---
    add_properties(
        tt_ds,
        {
            "Project": {
                "type": "rollup",
                "rollup": {
                    "relation_property_name": "Tasks",
                    "rollup_property_name": "Projects",
                    "function": "show_original",
                },
            },
        },
    )
    add_properties(
        tt_ds,
        {
            "Duration": {
                "type": "formula",
                "formula": {
                    "expression": 'dateBetween(prop("End Time"),prop("Start Time"),"minutes")'
                },
            },
            "Weekly Duration": {
                "type": "formula",
                "formula": {
                    "expression": (
                        'if(or(dateBetween(prop("End Time"),now(),"weeks") == 0, '
                        'dateBetween(prop("Start Time"),now(),"weeks") == 0), '
                        'dateBetween(prop("End Time"),prop("Start Time"),"minutes"), 0)'
                    )
                },
            },
        },
    )

    # --- Step 4: Tasks rollups over the Time Tracking DB relation ---
    add_properties(
        tasks_ds,
        {
            "Time Spent": {
                "type": "rollup",
                "rollup": {
                    "relation_property_name": "Time Tracking DB",
                    "rollup_property_name": "Duration",
                    "function": "sum",
                },
            },
            "Weekly Time Spent": {
                "type": "rollup",
                "rollup": {
                    "relation_property_name": "Time Tracking DB",
                    "rollup_property_name": "Weekly Duration",
                    "function": "sum",
                },
            },
        },
    )

    return {
        "projects": projects_id,
        "records": records_id,
        "tasks": tasks_id,
        "time_tracking": time_tracking_id,
    }


def main():
    env = load_env()
    missing = [k for k in ("NOTION_TOKEN", "NOTION_PARENT_PAGE") if k not in env]
    if missing:
        sys.exit(f"Missing required .env keys: {', '.join(missing)}")

    notion = Client(auth=env["NOTION_TOKEN"], notion_version=NOTION_VERSION)
    parent_id = normalize_page_id(env["NOTION_PARENT_PAGE"])

    try:
        ids = provision(notion, parent_id)
    except APIResponseError as e:
        sys.exit(f"Notion API error: {e.code} (HTTP {e.status})\n{e}")
    finally:
        notion.close()

    updates = {DB_ENV_KEYS[k]: v for k, v in ids.items()}
    write_env_keys(updates)

    env_block = "\n".join(f"{k}={v}" for k, v in updates.items())
    print("\nCreated and wired all databases.")
    print("\n.env updated with:\n" + env_block)
    print("\nNext: run a full sync to seed the local mirror:")
    print("  uv run python sync/sync.py --full")


if __name__ == "__main__":
    main()
