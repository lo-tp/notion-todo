"""Stop all running time-tracking records.

A "running" time-tracking record is one with no End Time (an open tracker).
This sets `End Time` = now and `Status` = "Stopped" on every open record in
Notion. It does not touch the task's own Status and does not refresh the
local Postgres mirror (run `uv run python sync/sync.py` to refresh).

Usage:
    uv run python scripts/stop_tracking.py

Idempotent: if nothing is open, it does nothing.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from notion_client import Client

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env() -> dict[str, str]:
    """Read KEY=VALUE pairs from .env (project root)."""
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def db_url(env: dict[str, str]) -> str:
    """Postgres URL with a driver prefix psycopg understands."""
    return env["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)


def open_trackers(env: dict[str, str]) -> list[tuple[str, str | None]]:
    """Return (page_id, task_name) for every open time-tracking record."""
    sql = (
        "SELECT tt.id, t.name "
        "FROM time_tracking tt "
        "LEFT JOIN tasks t ON t.id = tt.task_id "
        "WHERE tt.end_time IS NULL AND tt.deleted_at IS NULL "
        "ORDER BY tt.start_time"
    )
    with psycopg.connect(db_url(env)) as conn:
        return [(str(row[0]), row[1]) for row in conn.execute(sql).fetchall()]


def stop_all_running(env: dict[str, str]) -> list[str]:
    """Stop every open tracker in Notion; return the stopped page ids."""
    notion = Client(auth=env["NOTION_TOKEN"])
    now = datetime.now(UTC)
    stopped: list[str] = []
    try:
        for page_id, task_name in open_trackers(env):
            notion.pages.update(
                page_id=page_id,
                properties={
                    "End Time": {"date": {"start": now.isoformat()}},
                    "Status": {"select": {"name": "Stopped"}},
                },
            )
            print(f"  Stopped: {task_name or page_id}")
            stopped.append(page_id)
    finally:
        notion.close()
    return stopped


def main() -> None:
    env = load_env()
    if "NOTION_TOKEN" not in env:
        sys.exit("Missing NOTION_TOKEN in .env")

    stopped = stop_all_running(env)
    if not stopped:
        print("No open time trackers to stop.")
        return

    print(f"Done. Stopped {len(stopped)} tracker(s).")


if __name__ == "__main__":
    main()
