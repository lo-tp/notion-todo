"""start / end subcommands: time tracking.

Invariant: at most one open (running) time tracker — `start` stops every
open tracker before opening a new one; `end` stops every open tracker.
"""

from datetime import datetime
from typing import Any, cast

from cards import common


def open_trackers(conn) -> list[tuple[str, str | None]]:
    """Return (page_id, task_name) for every open time-tracking record."""
    rows = conn.execute(
        "SELECT tt.id, t.name "
        "FROM time_tracking tt "
        "LEFT JOIN tasks t ON t.id = tt.task_id "
        "WHERE tt.end_time IS NULL AND tt.deleted_at IS NULL "
        "ORDER BY tt.start_time"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def stop_all_running(notion, conn) -> list[str]:
    """Stop every open tracker in Notion; return the stopped page ids."""
    now = common.local_now().isoformat()
    stopped: list[str] = []
    for page_id, task_name in open_trackers(conn):
        notion.pages.update(
            page_id=page_id,
            properties={
                "End Time": {"date": {"start": now}},
                "Status": {"select": {"name": "Stopped"}},
            },
        )
        print(f"  Stopped: {task_name or page_id}")
        stopped.append(page_id)
    return stopped


def start_tracking(
    notion, env: dict[str, str], task_id: str, task_name: str
) -> tuple[str, datetime]:
    """Create a new open tracker for task_id; return (page_id, start_time)."""
    now = common.local_now()
    resp = cast(
        dict[str, Any],
        notion.pages.create(
            parent={"database_id": env["NOTION_DB_TIME_TRACKING"]},
            properties={
                "Name": {"title": [{"text": {"content": task_name}}]},
                "Tasks": {"relation": [{"id": task_id}]},
                "Start Time": {"date": {"start": now.isoformat()}},
                "Status": {"select": {"name": "Ing"}},
            },
        ),
    )
    return resp["id"], now


def cmd_start(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN", "NOTION_DB_TIME_TRACKING")
    conn = common.connect(env)
    try:
        task_id, task_name = common.find_task(conn, args.task)
        notion = common.Client(auth=env["NOTION_TOKEN"])
        try:
            print(f"Starting tracker for: {task_name} (id={task_id})")
            stopped = stop_all_running(notion, conn)
            page_id, now = start_tracking(notion, env, task_id, task_name)
        finally:
            notion.close()
    finally:
        conn.close()

    print(f"  Started at {now.isoformat()} (id={page_id})")
    if stopped:
        print(f"  (stopped {len(stopped)} previously open tracker(s))")
    common.auto_sync(env)


def cmd_end(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN")
    conn = common.connect(env)
    try:
        notion = common.Client(auth=env["NOTION_TOKEN"])
        try:
            stopped = stop_all_running(notion, conn)
        finally:
            notion.close()
    finally:
        conn.close()

    if not stopped:
        print("No open time trackers to stop.")
        return
    print(f"Done. Stopped {len(stopped)} tracker(s).")
    common.auto_sync(env)
