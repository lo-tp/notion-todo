"""start / end subcommands: time tracking.

Invariant: at most one open (running) time tracker — `start` stops every
open tracker before opening a new one; `end` stops every open tracker.

Open trackers are discovered by querying the live Notion Time Tracking
database (Status = "Ing") rather than the local mirror, so a stale mirror
can't leave a tracker running or let `start` open a duplicate.
"""

from datetime import datetime
from typing import Any, cast

import sync
from cards import common


def _name_of(properties: dict) -> str | None:
    """Extract the tracker's Name (title) text, if present."""
    prop = properties.get("Name")
    if not prop or prop.get("type") != "title":
        return None
    return "".join(t.get("plain_text", "") for t in prop.get("title", []))


def open_trackers(notion, env: dict[str, str]) -> list[tuple[str, str | None]]:
    """Query Notion for every open tracker; return (page_id, task_name)."""
    ds_id = sync.data_source_id(notion, env["NOTION_DB_TIME_TRACKING"])
    rows: list[tuple[str, str | None]] = []
    start_cursor = None
    while True:
        body: dict[str, Any] = {
            "page_size": 100,
            "filter": {"property": "Status", "select": {"equals": "Ing"}},
        }
        if start_cursor:
            body["start_cursor"] = start_cursor
        data = cast(dict, notion.data_sources.query(data_source_id=ds_id, **body))
        for record in data["results"]:
            rows.append((record["id"], _name_of(record["properties"])))
        if data["has_more"]:
            start_cursor = data["next_cursor"]
        else:
            break
    return rows


def stop_all_running(notion, env: dict[str, str], description: str | None = None) -> list[str]:
    """Stop every open tracker in Notion; return the stopped page ids.

    ``description`` (optional) updates the stopped records' Description property.
    """
    now = common.local_now().isoformat()
    properties: dict[str, Any] = {
        "End Time": {"date": {"start": now}},
        "Status": {"select": {"name": "Stopped"}},
    }
    if description:
        properties["Description"] = {"rich_text": [{"text": {"content": description}}]}
    stopped: list[str] = []
    for page_id, task_name in open_trackers(notion, env):
        notion.pages.update(page_id=page_id, properties=properties)
        print(f"  Stopped: {task_name or page_id}")
        stopped.append(page_id)
    return stopped


def start_tracking(
    notion,
    env: dict[str, str],
    task_id: str,
    task_name: str,
    description: str | None = None,
) -> tuple[str, datetime]:
    """Create a new open tracker for task_id; return (page_id, start_time).

    ``description`` (optional) is stored on the tracker's Description property.
    """
    now = common.local_now()
    properties: dict[str, Any] = {
        "Name": {"title": [{"text": {"content": task_name}}]},
        "Tasks": {"relation": [{"id": task_id}]},
        "Start Time": {"date": {"start": now.isoformat()}},
        "Status": {"select": {"name": "Ing"}},
    }
    if description:
        properties["Description"] = {"rich_text": [{"text": {"content": description}}]}
    resp = cast(
        dict[str, Any],
        notion.pages.create(
            parent={"database_id": env["NOTION_DB_TIME_TRACKING"]},
            properties=properties,
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
            stopped = stop_all_running(notion, env)
            page_id, now = start_tracking(notion, env, task_id, task_name, args.description)
        finally:
            notion.close()
    finally:
        conn.close()

    print(f"  Started at {now.isoformat()} (id={page_id})")
    if stopped:
        print(f"  (stopped {len(stopped)} previously open tracker(s))")
    common.auto_sync(env)


def cmd_end(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN", "NOTION_DB_TIME_TRACKING")
    notion = common.Client(auth=env["NOTION_TOKEN"])
    try:
        stopped = stop_all_running(notion, env, args.description)
    finally:
        notion.close()

    if not stopped:
        print("No open time trackers to stop.")
        return
    print(f"Done. Stopped {len(stopped)} tracker(s).")
    common.auto_sync(env)
