"""Manage Notion cards from the command line (the surface agent skills drive).

All Notion interactions go through the notion-client library. After every
mutation the local SQLite mirror is refreshed with an incremental sync, so a
single command always leaves the mirror consistent.

Usage:
    uv run python scripts/notion_cards.py <command> ...

Commands:
    create   Create a new task card.
    modify   Modify a task card's fields (empty value clears a field).
    delete   Archive a task card.
    start    Start a time tracker for a task (stops any open trackers first).
    end      Stop every open time tracker (idempotent).
    recent   Print the most recently used card titles.
    sync     Sync Notion databases into the local mirror (--full for full).

Task resolution: an exact UUID is used as-is; otherwise the name is matched
exactly, then by unique substring. Ambiguous matches are rejected.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

# Make the sync engine importable (sync/sync.py is the `sync` module).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sync"))

from notion_client import Client

import sync

UUID_RE = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)

DEFAULT_RECENT_LIMIT = 20
RECENT_CARDS_LIMIT_KEY = "RECENT_CARDS_LIMIT"


# --- Shared helpers --------------------------------------------------------


def load_env() -> dict[str, str]:
    """Read KEY=VALUE pairs from the nearest .env (cwd or an ancestor)."""
    here = Path.cwd()
    env_file = next(
        (d / ".env" for d in [here, *here.parents] if (d / ".env").is_file()),
        None,
    )
    if env_file is None:
        raise FileNotFoundError(f"No .env found in {here} or any parent directory")
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def local_now() -> datetime:
    """Current time in the system's local time zone (tz-aware, correct offset/DST)."""
    return datetime.now().astimezone()


def require(env: dict[str, str], *keys: str) -> None:
    missing = [k for k in keys if k not in env]
    if missing:
        sys.exit(f"Missing {', '.join(missing)} in .env")


def connect(env: dict[str, str]):
    """Open the mirror (schema initialized idempotently)."""
    conn = sync.connect(sync.db_path(env))
    sync.init_schema(conn)
    return conn


def auto_sync(env: dict[str, str]) -> None:
    """Incremental in-process sync after a mutation, so the mirror stays consistent."""
    client = Client(auth=env["NOTION_TOKEN"])
    try:
        conn = connect(env)
        try:
            sync.sync_all(client, env, conn)
            conn.commit()
        finally:
            conn.close()
    finally:
        client.close()
    print("Mirror synced.")


# --- Task / project resolution ---------------------------------------------


def find_task(conn, query: str) -> tuple[str, str]:
    """Resolve a task to (page_id, name) by UUID, exact name, then unique substring."""
    if UUID_RE.match(query):
        row = conn.execute(
            "SELECT id, name FROM tasks WHERE id = ? AND deleted_at IS NULL", (query,)
        ).fetchone()
        if row:
            return row[0], row[1]
        sys.exit(f"No task with id {query}.")

    exact = conn.execute(
        "SELECT id, name FROM tasks WHERE name = ? AND deleted_at IS NULL", (query,)
    ).fetchall()
    if len(exact) == 1:
        return exact[0][0], exact[0][1]
    if len(exact) > 1:
        sys.exit(f"Ambiguous task name '{query}': {[r[1] for r in exact]}")

    like = conn.execute(
        "SELECT id, name FROM tasks WHERE lower(name) LIKE lower(?) AND deleted_at IS NULL ORDER BY name",
        (f"%{query}%",),
    ).fetchall()
    if len(like) == 1:
        return like[0][0], like[0][1]
    if not like:
        sys.exit(f"No task matching '{query}'.")
    sys.exit(f"Ambiguous task name '{query}': {[r[1] for r in like]}")


def find_project(conn, query: str) -> str:
    """Resolve a project to a page id against the local mirror."""
    if UUID_RE.match(query):
        row = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL", (query,)
        ).fetchone()
        if row:
            return row[0]
        sys.exit(f"No project with id {query}.")

    exact = conn.execute(
        "SELECT id, name FROM projects WHERE name = ? AND deleted_at IS NULL", (query,)
    ).fetchall()
    if len(exact) == 1:
        return exact[0][0]
    if len(exact) > 1:
        sys.exit(f"Ambiguous project name '{query}': {[r[1] for r in exact]}")

    like = conn.execute(
        "SELECT id, name FROM projects WHERE lower(name) LIKE lower(?) AND deleted_at IS NULL ORDER BY name",
        (f"%{query}%",),
    ).fetchall()
    if len(like) == 1:
        return like[0][0]
    if not like:
        sys.exit(f"No project matching '{query}'. (Projects must already exist.)")
    sys.exit(f"Ambiguous project name '{query}': {[r[1] for r in like]}")


# --- Notion property helpers -------------------------------------------------


def build_properties(
    name: str,
    status: str | None = None,
    due: str | None = None,
    project_id: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
    description: str | None = None,
) -> dict:
    """Assemble the Notion `properties` payload.

    ``None`` means "not passed" (field omitted); an empty string clears the
    field. Tags/project are replaced wholesale.
    """
    props: dict = {"Name": {"title": [{"text": {"content": name}}]}}
    if status is not None:
        props["Status"] = {"select": {"name": status} if status else None}
    if due is not None:
        props["Due Date"] = {"date": {"start": due} if due else None}
    if project_id is not None:
        props["Projects"] = {"relation": [] if not project_id else [{"id": project_id}]}
    if tags is not None:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    if priority is not None:
        props["Priority"] = {"select": {"name": priority} if priority else None}
    if description is not None:
        props["Description"] = {
            "rich_text": [{"text": {"content": description}}] if description else []
        }
    return props


def validate_selects(notion: Client, ds_id: str, properties: dict) -> None:
    """Exit if a provided Status/Priority value is not a valid option for the DB."""
    schema = cast(dict[str, Any], notion.data_sources.retrieve(data_source_id=ds_id))["properties"]
    for prop in ("Status", "Priority"):
        select = properties.get(prop, {}).get("select")
        name = select.get("name") if select else None
        if not name:
            continue
        options = [o["name"] for o in schema.get(prop, {}).get("select", {}).get("options", [])]
        if options and name not in options:
            sys.exit(f"Unknown {prop.lower()} '{name}'. Options: {options}")


def parse_tags(value: str | None) -> list[str] | None:
    """Split a comma-separated tags value; None means "not passed"."""
    if value is None:
        return None
    return [t.strip() for t in value.split(",") if t.strip()]


# --- Mutations ---------------------------------------------------------------


def cmd_create(args, env: dict[str, str]) -> None:
    require(env, "NOTION_TOKEN", "NOTION_DB_TASKS")
    conn = connect(env)
    try:
        project_id = None
        if args.project is not None:
            project_id = find_project(conn, args.project) if args.project else None
        tags = parse_tags(args.tags)

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
            ds_id = sync.data_source_id(notion, env["NOTION_DB_TASKS"])
            validate_selects(notion, ds_id, properties)
            resp = cast(
                dict[str, Any],
                notion.pages.create(
                    parent={"database_id": env["NOTION_DB_TASKS"]}, properties=properties
                ),
            )
        finally:
            notion.close()
    finally:
        conn.close()

    print(f"Created task: {args.name} (id={resp['id']})")
    auto_sync(env)


def cmd_modify(args, env: dict[str, str]) -> None:
    require(env, "NOTION_TOKEN", "NOTION_DB_TASKS")
    conn = connect(env)
    try:
        task_id, task_name = find_task(conn, args.task)

        properties = build_properties(
            args.name if args.name is not None else task_name,
            status=args.status,
            due=args.due,
            project_id=find_project(conn, args.project) if args.project else None,
            tags=parse_tags(args.tags),
            priority=args.priority,
            description=args.description,
        )
        # Only the fields the user actually passed get touched.
        touched = {
            "Name": args.name is not None,
            "Status": args.status is not None,
            "Due Date": args.due is not None,
            "Projects": args.project is not None,
            "Tags": args.tags is not None,
            "Priority": args.priority is not None,
            "Description": args.description is not None,
        }
        properties = {k: v for k, v in properties.items() if touched.get(k, False)}
        if not properties:
            sys.exit("Nothing to modify (pass at least one field).")

        notion = Client(auth=env["NOTION_TOKEN"])
        try:
            ds_id = sync.data_source_id(notion, env["NOTION_DB_TASKS"])
            validate_selects(notion, ds_id, properties)
            notion.pages.update(page_id=task_id, properties=properties)
        finally:
            notion.close()
    finally:
        conn.close()

    print(f"Modified task: {task_name} (id={task_id})")
    auto_sync(env)


def cmd_delete(args, env: dict[str, str]) -> None:
    require(env, "NOTION_TOKEN")
    conn = connect(env)
    try:
        task_id, task_name = find_task(conn, args.task)
        notion = Client(auth=env["NOTION_TOKEN"])
        try:
            notion.pages.update(page_id=task_id, archived=True)
        finally:
            notion.close()
    finally:
        conn.close()

    print(f"Archived task: {task_name} (id={task_id})")
    auto_sync(env)


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


def stop_all_running(notion: Client, conn) -> list[str]:
    """Stop every open tracker in Notion; return the stopped page ids."""
    now = local_now().isoformat()
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
    notion: Client, env: dict[str, str], task_id: str, task_name: str
) -> tuple[str, datetime]:
    """Create a new open tracker for task_id; return (page_id, start_time)."""
    now = local_now()
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
    require(env, "NOTION_TOKEN", "NOTION_DB_TIME_TRACKING")
    conn = connect(env)
    try:
        task_id, task_name = find_task(conn, args.task)
        notion = Client(auth=env["NOTION_TOKEN"])
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
    auto_sync(env)


def cmd_end(args, env: dict[str, str]) -> None:
    require(env, "NOTION_TOKEN")
    conn = connect(env)
    try:
        notion = Client(auth=env["NOTION_TOKEN"])
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
    auto_sync(env)


def recent_titles(conn, limit: int) -> list[tuple[str, str]]:
    """Return (id, name) for the most recently used, non-deleted tasks.

    "Last used" is approximated by the most recent Notion edit, falling back
    to creation order.
    """
    rows = conn.execute(
        "SELECT id, name FROM tasks "
        "WHERE deleted_at IS NULL "
        "ORDER BY notion_updated_at DESC, created_at DESC "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def cmd_recent(args, env: dict[str, str]) -> None:
    limit = args.limit or int(env.get(RECENT_CARDS_LIMIT_KEY, DEFAULT_RECENT_LIMIT))
    conn = connect(env)
    try:
        for i, (_card_id, name) in enumerate(recent_titles(conn, limit), 1):
            print(f"{i}. {name}")
    finally:
        conn.close()


def cmd_frequent(args, env: dict[str, str]) -> None:
    """Print the most recently used tasks and projects, with their ids."""
    conn = connect(env)
    try:
        for table, label in (("tasks", "Tasks"), ("projects", "Projects")):
            rows = conn.execute(
                f"SELECT id, name FROM {table} "
                f"WHERE deleted_at IS NULL "
                f"ORDER BY notion_updated_at DESC LIMIT ?",
                (args.limit,),
            ).fetchall()
            print(f"{label} (top {args.limit} by recent use):")
            for card_id, name in rows:
                print(f"  {card_id}  {name}")
    finally:
        conn.close()


def _rich_text(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text}}]


# Block types whose content is a replaceable rich_text list.
BLOCK_TEXT_TYPES = (
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "callout",
    "quote",
)


def _block_text(block: dict) -> str:
    obj = block.get(block["type"], {})
    return "".join(t.get("plain_text", "") for t in obj.get("rich_text", []))


def _latest_block_id(notion: Client, card_id: str) -> str:
    resp = cast(dict[str, Any], notion.blocks.children.list(block_id=card_id))
    blocks = resp.get("results", [])
    if not blocks:
        sys.exit("No page content on this card.")
    return blocks[-1]["id"]


def _latest_comment_id(notion: Client, card_id: str) -> str:
    resp = cast(dict[str, Any], notion.comments.list(block_id=card_id))
    comments = resp.get("results", [])
    if not comments:
        sys.exit("No comments on this card.")
    return comments[-1]["id"]


def cmd_comment(args, env: dict[str, str]) -> None:
    """Read, create, update, or delete comments on a card."""
    require(env, "NOTION_TOKEN")
    conn = connect(env)
    card_id, name = find_task(conn, args.card)
    conn.close()
    notion = Client(auth=env["NOTION_TOKEN"])
    try:
        if args.action == "read":
            resp = cast(dict[str, Any], notion.comments.list(block_id=card_id))
            comments = resp.get("results", [])
            if not comments:
                print(f"No comments on {name}.")
                return
            for c in comments:
                author = c["created_by"][0].get("name", "(unknown)")
                text = "".join(rt["plain_text"] for rt in c["rich_text"])
                print(f"{c['id']}  {c['created_time'][:19]}  {author}  {text}")
            return

        if args.action in ("create", "update") and not args.text:
            sys.exit(f"{args.action} requires a comment text.")

        if args.action == "create":
            resp = cast(
                dict[str, Any],
                notion.comments.create(
                    parent={"page_id": card_id}, rich_text=_rich_text(args.text)
                ),
            )
            print(f"Added comment {resp['id']} on {name}.")
        elif args.action == "update":
            comment_id = args.comment_id or _latest_comment_id(notion, card_id)
            notion.comments.update(
                comment_id=comment_id, rich_text=_rich_text(args.text)
            )
            print(f"Updated comment {comment_id} on {name}.")
        else:  # delete
            comment_id = args.comment_id or _latest_comment_id(notion, card_id)
            notion.comments.delete(comment_id=comment_id)
            print(f"Deleted comment {comment_id} on {name}.")
    finally:
        notion.close()


def cmd_page(args, env: dict[str, str]) -> None:
    """Read, create, update, or delete page content blocks on a card."""
    require(env, "NOTION_TOKEN")
    conn = connect(env)
    card_id, name = find_task(conn, args.card)
    conn.close()
    notion = Client(auth=env["NOTION_TOKEN"])
    try:
        if args.action == "read":
            resp = cast(dict[str, Any], notion.blocks.children.list(block_id=card_id))
            blocks = resp.get("results", [])
            if not blocks:
                print(f"No page content on {name}.")
                return
            for i, block in enumerate(blocks, 1):
                print(f"{i}. {block['id']}  {block['type']}  {_block_text(block)}")
            return

        if args.action in ("create", "update") and not args.text:
            sys.exit(f"{args.action} requires text.")

        if args.action == "create":
            block = {"type": "paragraph", "paragraph": {"rich_text": _rich_text(args.text)}}
            resp = cast(
                dict[str, Any],
                notion.blocks.children.append(block_id=card_id, children=[block]),
            )
            print(f"Added paragraph to {name} ({resp['results'][0]['id']}).")
            return

        block_id = args.block_id or _latest_block_id(notion, card_id)
        if args.action == "update":
            block = cast(dict[str, Any], notion.blocks.retrieve(block_id=block_id))
            btype = block["type"]
            if btype not in BLOCK_TEXT_TYPES:
                sys.exit(f"Block {block_id} is a {btype}; only text blocks can be updated.")
            notion.blocks.update(
                block_id=block_id, **{btype: {"rich_text": _rich_text(args.text)}}
            )
            print(f"Updated {btype} block {block_id} on {name}.")
        else:  # delete
            notion.blocks.delete(block_id=block_id)
            print(f"Deleted block {block_id} from {name}.")
    finally:
        notion.close()


def cmd_sync(args, env: dict[str, str]) -> None:
    require(
        env,
        "NOTION_TOKEN",
        "NOTION_DB_PROJECTS",
        "NOTION_DB_RECORDS",
        "NOTION_DB_TASKS",
        "NOTION_DB_TIME_TRACKING",
    )
    notion = Client(auth=env["NOTION_TOKEN"])
    try:
        conn = connect(env)
        try:
            sync.init_schema(conn)
            sync.sync_all(notion, env, conn, full=args.full)
            conn.commit()
        finally:
            conn.close()
    finally:
        notion.close()


# --- CLI wiring ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notion_cards.py",
        description="Manage Notion cards (tasks, time tracking) with an auto-synced local mirror.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="Create a new task card.")
    p.add_argument("name", help="Task name (title).")
    p.add_argument("--status", help="Status option (e.g. 'This Week'); empty clears.")
    p.add_argument("--due", help="Due date, YYYY-MM-DD; empty clears.")
    p.add_argument("--project", help="Project name or id to link (resolved via the mirror); empty clears.")
    p.add_argument("--tags", help="Comma-separated tags; replaces the tag list; empty clears.")
    p.add_argument("--priority", help="Priority option (e.g. '5'); empty clears.")
    p.add_argument("--description", help="Free-form description; empty clears.")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("modify", help="Modify a task card's fields.")
    p.add_argument("task", help="Task name or id.")
    p.add_argument("--name", help="New name (rename).")
    p.add_argument("--status", help="Status option; empty clears.")
    p.add_argument("--due", help="Due date, YYYY-MM-DD; empty clears.")
    p.add_argument("--project", help="Project name or id to link; empty clears.")
    p.add_argument("--tags", help="Comma-separated tags; replaces the tag list; empty clears.")
    p.add_argument("--priority", help="Priority option; empty clears.")
    p.add_argument("--description", help="Free-form description; empty clears.")
    p.set_defaults(func=cmd_modify)

    p = sub.add_parser("page", help="Read/create/update/delete page content on a card.")
    p.add_argument("card", help="Task name or id.")
    p.add_argument("action", choices=["read", "create", "update", "delete"])
    p.add_argument("text", nargs="?", help="Block text (create/update).")
    p.add_argument("block_id", nargs="?", help="Block id (update/delete; default: last block).")
    p.set_defaults(func=cmd_page)

    p = sub.add_parser("comment", help="Read/create/update/delete comments on a card.")
    p.add_argument("card", help="Task name or id.")
    p.add_argument("action", choices=["read", "create", "update", "delete"])
    p.add_argument("text", nargs="?", help="Comment text (create/update).")
    p.add_argument("comment_id", nargs="?", help="Comment id (update/delete; default: latest).")
    p.set_defaults(func=cmd_comment)

    p = sub.add_parser("frequent", help="List the most frequently used tasks and projects with their ids.")
    p.add_argument("--limit", type=int, default=15, help="How many to load per list (default: 15).")
    p.set_defaults(func=cmd_frequent)

    p = sub.add_parser("delete", help="Archive a task card.")
    p.add_argument("task", help="Task name or id.")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("start", help="Start a time tracker for a task.")
    p.add_argument("task", help="Task name or id.")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("end", help="Stop every open time tracker.")
    p.set_defaults(func=cmd_end)

    p = sub.add_parser("recent", help="Print the most recently used card titles.")
    p.add_argument("limit", nargs="?", type=int, help="How many cards (default from RECENT_CARDS_LIMIT, 20).")
    p.set_defaults(func=cmd_recent)

    p = sub.add_parser("sync", help="Sync Notion databases into the local mirror.")
    p.add_argument("--full", action="store_true", help="Full sync (soft-deletes missing rows).")
    p.set_defaults(func=cmd_sync)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args, load_env())
    except sync.SchemaMismatchError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
