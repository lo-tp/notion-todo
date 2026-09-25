"""Create a new task in Notion.

Only the fields you pass are set; everything else is left blank. This does not
refresh the local Postgres mirror (run `uv run python sync/sync.py` to
refresh).

Usage:
    uv run python scripts/create_task.py <name> [options]

Options:
    --status STATUS        A task Status option (e.g. "This Week").
    --due YYYY-MM-DD       Due date.
    --project NAME         Link to an existing project (resolved via the
                           local mirror). Projects cannot be created here.
    --tags a,b,c           Comma-separated tags (options are created on demand).
    --priority 5           Priority option (only "5" is defined).
    --description TEXT     Free-form description.

Examples:
    uv run python scripts/create_task.py "Book dentist appointment"
    uv run python scripts/create_task.py "营业执照变更" \\
        --status "This Week" --due 2026-10-01 --project Life
"""

import argparse
import re
import sys
from typing import Any, cast

import psycopg
from notion_client import Client
from stop_tracking import db_url, load_env

UUID_RE = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)


def find_project(env: dict[str, str], query: str) -> str:
    """Resolve a project to a page id against the local mirror."""
    with psycopg.connect(db_url(env)) as conn:
        if UUID_RE.match(query):
            row = conn.execute(
                "SELECT id, name FROM projects WHERE id = %s AND deleted_at IS NULL",
                (query,),
            ).fetchone()
            if row:
                return str(row[0])
            sys.exit(f"No project with id {query}.")

        exact = conn.execute(
            "SELECT id, name FROM projects WHERE name = %s AND deleted_at IS NULL",
            (query,),
        ).fetchall()
        if len(exact) == 1:
            return str(exact[0][0])
        if len(exact) > 1:
            sys.exit(f"Ambiguous project name '{query}': {[r[1] for r in exact]}")

        like = conn.execute(
            "SELECT id, name FROM projects WHERE name ILIKE %s AND deleted_at IS NULL ORDER BY name",
            (f"%{query}%",),
        ).fetchall()
        if len(like) == 1:
            return str(like[0][0])
        if not like:
            sys.exit(f"No project matching '{query}'. (Projects must already exist.)")
        sys.exit(f"Ambiguous project name '{query}': {[r[1] for r in like]}")


def build_properties(
    name: str,
    status: str | None = None,
    due: str | None = None,
    project_id: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
    description: str | None = None,
) -> dict:
    """Assemble the Notion `properties` payload, omitting any field that is not set."""
    props: dict = {"Name": {"title": [{"text": {"content": name}}]}}
    if status is not None:
        props["Status"] = {"select": {"name": status}}
    if due is not None:
        props["Due Date"] = {"date": {"start": due}}
    if project_id is not None:
        props["Projects"] = {"relation": [{"id": project_id}]}
    if tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    if priority is not None:
        props["Priority"] = {"select": {"name": priority}}
    if description is not None:
        props["Description"] = {"rich_text": [{"text": {"content": description}}]}
    return props


def data_source_id(notion: Client, db_id: str) -> str:
    """Resolve the (single) data-source id for a database."""
    db = cast(dict[str, Any], notion.databases.retrieve(database_id=db_id))
    return db["data_sources"][0]["id"]


def validate_selects(notion: Client, ds_id: str, properties: dict) -> None:
    """Exit if a provided Status/Priority value is not a valid option for the DB."""
    schema = cast(dict[str, Any], notion.data_sources.retrieve(data_source_id=ds_id))["properties"]
    for prop in ("Status", "Priority"):
        name = properties.get(prop, {}).get("select", {}).get("name")
        if not name:
            continue
        options = [
            o["name"] for o in schema.get(prop, {}).get("select", {}).get("options", [])
        ]
        if options and name not in options:
            sys.exit(f"Unknown {prop.lower()} '{name}'. Options: {options}")


def create_task(notion: Client, db_id: str, properties: dict) -> str:
    """Create the page; return its id."""
    resp = cast(dict[str, Any], notion.pages.create(parent={"database_id": db_id}, properties=properties))
    return resp["id"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a new task in Notion. Only the fields you pass are set."
    )
    parser.add_argument("name", help="Task name (title).")
    parser.add_argument("--status", help="Status option (e.g. 'This Week').")
    parser.add_argument("--due", help="Due date, YYYY-MM-DD.")
    parser.add_argument("--project", help="Project name or id to link.")
    parser.add_argument("--tags", help="Comma-separated tags.")
    parser.add_argument("--priority", help="Priority option (e.g. '5').")
    parser.add_argument("--description", help="Free-form description.")
    args = parser.parse_args()

    env = load_env()
    for key in ("NOTION_TOKEN", "NOTION_DB_TASKS"):
        if key not in env:
            sys.exit(f"Missing {key} in .env")

    project_id = find_project(env, args.project) if args.project else None
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None

    properties = build_properties(
        args.name,
        status=args.status,
        due=args.due,
        project_id=project_id,
        tags=tags,
        priority=args.priority,
        description=args.description,
    )

    notion = Client(auth=env["NOTION_TOKEN"])
    try:
        ds_id = data_source_id(notion, env["NOTION_DB_TASKS"])
        validate_selects(notion, ds_id, properties)
        page_id = create_task(notion, env["NOTION_DB_TASKS"], properties)
    finally:
        notion.close()

    print(f"Created task: {args.name} (id={page_id})")
    print("Done.")


if __name__ == "__main__":
    main()
