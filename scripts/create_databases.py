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

One deliberate deviation from a live schema: the three `Status` columns are
created as `select` (Notion's API cannot create `status` columns). Same options,
no groups; sync.py reads them identically.
"""

import sys
from pathlib import Path

import requests

# --- Config ---

NOTION_VERSION = "2022-06-28"
NOTION_API = "https://api.notion.com/v1"

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


def main():
    env = load_env()
    missing = [k for k in ("NOTION_TOKEN", "NOTION_PARENT_PAGE") if k not in env]
    if missing:
        sys.exit(f"Missing required .env keys: {', '.join(missing)}")

    headers = {
        "Authorization": f"Bearer {env['NOTION_TOKEN']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    parent_id = env["NOTION_PARENT_PAGE"]

    def api(method, path, json=None):
        resp = requests.request(method, f"{NOTION_API}{path}", headers=headers, json=json)
        if resp.status_code >= 400:
            sys.exit(f"Notion API {method} {path} -> {resp.status_code}\n{resp.text}")
        return resp.json()

    # --- Validate parent page ---
    page = api("GET", f"/pages/{parent_id}")
    if page.get("archived"):
        sys.exit(f"Parent page {parent_id} is archived.")
    print(f"Parent page: {parent_id}")

    # --- Guard: refuse if a "Tasks" database already exists under the parent ---
    children, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = api("GET", f"/blocks/{parent_id}/children", params=body)
        children.extend(data["results"])
        if data["has_more"]:
            cursor = data["next_cursor"]
        else:
            break
    child_db_ids = [b["id"] for b in children if b["type"] in ("table", "board", "list", "timeline", "gallery")]
    titles = {}
    # Fetch titles for database children.
    for db_id in child_db_ids:
        db = api("GET", f"/databases/{db_id}")
        titles[db_id] = "".join(t.get("plain_text", "") for t in db.get("title", []))
    if "Tasks" in titles.values():
        present = sorted(t for t in titles.values() if t in ("Tasks", "Projects", "Records", "Time Tracking DB"))
        sys.exit(
            "Already provisioned: a 'Tasks' database exists under the parent page.\n"
            f"  Existing matching databases: {present or 'none'}\n"
            "  Clean them up (archive) and re-run, or point NOTION_PARENT_PAGE at an empty page."
        )

    def create_db(title, properties):
        resp = api("POST", "/databases", json={"parent": {"page_id": parent_id}, "title": [{"text": {"content": title}}], "properties": properties})
        print(f"  Created database: {title} ({resp['id']})")
        return resp["id"]

    def add_properties(db_id, properties):
        api("PATCH", f"/databases/{db_id}", json={"properties": properties})

    # --- Step 1: Create the four databases with independent properties only ---
    # Relations/rollups/formulas are added afterward (Notion requires their
    # referenced relations/databases to exist first).
    projects_id = create_db("Projects", {
        "Name": {"type": "title", "title": {}},
        "Status": {"type": "select", "select": {"options": [
            {"name": "Not started", "color": "gray"},
            {"name": "Active", "color": "blue"},
            {"name": "Paused", "color": "yellow"},
            {"name": "Done", "color": "green"},
        ]}},
    })

    records_id = create_db("Records", {
        "Name": {"type": "title", "title": {}},
        "Tags": {"type": "multi_select", "multi_select": {}},
        "Created time": {"type": "created_time", "created_time": {}},
        "Summary": {"type": "rich_text", "rich_text": {}},
    })

    tasks_id = create_db("Tasks", {
        "Name": {"type": "title", "title": {}},
        "Tags": {"type": "multi_select", "multi_select": {}},
        "Status": {"type": "select", "select": {"options": [
            {"name": "Backlog", "color": "gray"},
            {"name": "This Week", "color": "blue"},
            {"name": "This Month", "color": "purple"},
            {"name": "Today", "color": "orange"},
            {"name": "Blocked", "color": "red"},
            {"name": "In progress", "color": "yellow"},
            {"name": "Finished", "color": "green"},
        ]}},
        "Due Date": {"type": "date", "date": {}},
        "Priority": {"type": "select", "select": {"options": [{"name": "5", "color": "default"}]}},
        "Description": {"type": "rich_text", "rich_text": {}},
        "Created time": {"type": "created_time", "created_time": {}},
    })

    time_tracking_id = create_db("Time Tracking DB", {
        "Name": {"type": "title", "title": {}},
        "Start Time": {"type": "date", "date": {}},
        "End Time": {"type": "date", "date": {}},
        "Status": {"type": "select", "select": {"options": [
            {"name": "Stopped", "color": "gray"},
            {"name": "Ing", "color": "yellow"},
        ]}},
    })

    # --- Step 2: Relations ---
    # Projects links are one-way (single_property) so Projects stays clean.
    add_properties(records_id, {"Projects": {"type": "relation", "relation": {"database_id": projects_id, "type": "single_property"}}})
    add_properties(tasks_id, {"Projects": {"type": "relation", "relation": {"database_id": projects_id, "type": "single_property"}}})
    # Time Tracking <-> Tasks is bidirectional; reverse auto-named "Time Tracking DB" on Tasks.
    add_properties(time_tracking_id, {"Tasks": {"type": "relation", "relation": {"database_id": tasks_id, "type": "dual_property", "dual_property": {"synced_property_name": "Time Tracking DB"}}}})

    # --- Step 3: Time Tracking rollup + formulas (before Tasks rollups, which sum these) ---
    add_properties(time_tracking_id, {
        "Project": {"type": "rollup", "rollup": {"relation_property_name": "Tasks", "rollup_property_name": "Projects", "function": "show_original"}},
    })
    add_properties(time_tracking_id, {
        "Duration": {"type": "formula", "formula": {"expression": 'dateBetween(prop("End Time"),prop("Start Time"),"minutes")'}},
        "Weekly Duration": {"type": "formula", "formula": {"expression": (
            'if(or(dateBetween(prop("End Time"),now(),"weeks") == 0, '
            'dateBetween(prop("Start Time"),now(),"weeks") == 0), '
            'dateBetween(prop("End Time"),prop("Start Time"),"minutes"), 0)'
        )}},
        "Hidden Project": {"type": "formula", "formula": {"expression": 'prop("Project").first()'}},
    })

    # --- Step 4: Tasks rollups over the Time Tracking DB relation ---
    add_properties(tasks_id, {
        "Time Spent": {"type": "rollup", "rollup": {"relation_property_name": "Time Tracking DB", "rollup_property_name": "Duration", "function": "sum"}},
        "Weekly Time Spent": {"type": "rollup", "rollup": {"relation_property_name": "Time Tracking DB", "rollup_property_name": "Weekly Duration", "function": "sum"}},
    })

    # --- Write IDs to .env ---
    ids = {
        "projects": projects_id,
        "records": records_id,
        "tasks": tasks_id,
        "time_tracking": time_tracking_id,
    }
    updates = {DB_ENV_KEYS[k]: v for k, v in ids.items()}
    write_env_keys(updates)

    env_block = "\n".join(f"{k}={v}" for k, v in updates.items())
    print("\nCreated and wired all databases.")
    print("\n.env updated with:\n" + env_block)
    print("\nNext: run a full sync to seed the local mirror:")
    print("  uv run python sync/sync.py --full")


if __name__ == "__main__":
    main()
