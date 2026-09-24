"""Start a new time-tracking record for a task.

Per the single-running-tracker invariant, this first stops every currently
open time tracker, then creates a new open tracker for the target task with
`Start Time` = now. It does not refresh the local Postgres mirror (run
`uv run python sync/sync.py` to refresh).

Usage:
    uv run python scripts/start_tracking.py <task-name-or-id>

Examples:
    uv run python scripts/start_tracking.py "Grandma Care"
    uv run python scripts/start_tracking.py 3e5db18b-dc5f-81af-bbba-f1e3f73910ff

Task resolution: an exact UUID is used as-is; otherwise the name is matched
exactly, then by unique substring. Ambiguous matches are rejected.
"""

import re
import sys
from datetime import UTC, datetime

import psycopg
from notion_client import Client
from stop_tracking import db_url, load_env, stop_all_running

UUID_RE = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)


def find_task(env, query: str) -> tuple[str, str]:
    """Resolve a task to (page_id, name) by UUID or name."""
    with psycopg.connect(db_url(env)) as conn:
        if UUID_RE.match(query):
            row = conn.execute(
                "SELECT id, name FROM tasks WHERE id = %s AND deleted_at IS NULL",
                (query,),
            ).fetchone()
            if row:
                return str(row[0]), row[1]
            sys.exit(f"No task with id {query}.")

        exact = conn.execute(
            "SELECT id, name FROM tasks WHERE name = %s AND deleted_at IS NULL",
            (query,),
        ).fetchall()
        if len(exact) == 1:
            return str(exact[0][0]), exact[0][1]
        if len(exact) > 1:
            sys.exit(f"Ambiguous task name '{query}': {[r[1] for r in exact]}")

        like = conn.execute(
            "SELECT id, name FROM tasks WHERE name ILIKE %s AND deleted_at IS NULL ORDER BY name",
            (f"%{query}%",),
        ).fetchall()
        if len(like) == 1:
            return str(like[0][0]), like[0][1]
        if not like:
            sys.exit(f"No task matching '{query}'.")
        sys.exit(f"Ambiguous task name '{query}': {[r[1] for r in like]}")


def start_tracking(env, task_id: str, task_name: str) -> tuple[str, datetime]:
    """Create a new open tracker for task_id; return (page_id, start_time)."""
    notion = Client(auth=env["NOTION_TOKEN"])
    now = datetime.now(UTC)
    try:
        resp = notion.pages.create(
            parent={"database_id": env["NOTION_DB_TIME_TRACKING"]},
            properties={
                "Name": {"title": [{"text": {"content": task_name}}]},
                "Tasks": {"relation": [{"id": task_id}]},
                "Start Time": {"date": {"start": now.isoformat()}},
                "Status": {"select": {"name": "Ing"}},
            },
        )
    finally:
        notion.close()
    return resp["id"], now


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: uv run python scripts/start_tracking.py <task-name-or-id>")
    query = " ".join(sys.argv[1:])

    env = load_env()
    for key in ("NOTION_TOKEN", "NOTION_DB_TIME_TRACKING"):
        if key not in env:
            sys.exit(f"Missing {key} in .env")

    task_id, task_name = find_task(env, query)
    print(f"Starting tracker for: {task_name} (id={task_id})")

    stopped = stop_all_running(env)
    page_id, now = start_tracking(env, task_id, task_name)
    print(f"  Started at {now.isoformat()} (id={page_id})")
    if stopped:
        print(f"  (stopped {len(stopped)} previously open tracker(s))")

    print("Done.")


if __name__ == "__main__":
    main()
