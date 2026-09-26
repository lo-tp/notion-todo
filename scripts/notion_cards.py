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

Implementation is split by subcommand in the ``cards`` package
(``scripts/cards/``); this file only wires the CLI.
"""

import argparse
import sys

from cards import (
    comment,
    common,
    create,
    delete,
    frequent,
    modify,
    page,
    recent,
    sync_cmd,
    tracking,
)


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
    p.add_argument(
        "--project", help="Project name or id to link (resolved via the mirror); empty clears."
    )
    p.add_argument("--tags", help="Comma-separated tags; replaces the tag list; empty clears.")
    p.add_argument("--priority", help="Priority option (e.g. '5'); empty clears.")
    p.add_argument("--description", help="Free-form description; empty clears.")
    p.set_defaults(func=create.cmd_create)

    p = sub.add_parser("modify", help="Modify a task card's fields.")
    p.add_argument("task", help="Task name or id.")
    p.add_argument("--name", help="New name (rename).")
    p.add_argument("--status", help="Status option; empty clears.")
    p.add_argument("--due", help="Due date, YYYY-MM-DD; empty clears.")
    p.add_argument("--project", help="Project name or id to link; empty clears.")
    p.add_argument("--tags", help="Comma-separated tags; replaces the tag list; empty clears.")
    p.add_argument("--priority", help="Priority option; empty clears.")
    p.add_argument("--description", help="Free-form description; empty clears.")
    p.set_defaults(func=modify.cmd_modify)

    p = sub.add_parser("page", help="Read/create/update/delete page content on a card.")
    p.add_argument("card", help="Task name or id.")
    p.add_argument("action", choices=["read", "create", "update", "delete"])
    p.add_argument("text", nargs="?", help="Block text (create/update).")
    p.add_argument("block_id", nargs="?", help="Block id (update/delete; default: last block).")
    p.set_defaults(func=page.cmd_page)

    p = sub.add_parser("comment", help="Read/create/update/delete comments on a card.")
    p.add_argument("card", help="Task name or id.")
    p.add_argument("action", choices=["read", "create", "update", "delete"])
    p.add_argument("text", nargs="?", help="Comment text (create/update).")
    p.add_argument("comment_id", nargs="?", help="Comment id (update/delete; default: latest).")
    p.set_defaults(func=comment.cmd_comment)

    p = sub.add_parser(
        "frequent", help="List the most frequently used tasks and projects with their ids."
    )
    p.add_argument("--limit", type=int, default=15, help="How many to load per list (default: 15).")
    p.set_defaults(func=frequent.cmd_frequent)

    p = sub.add_parser("delete", help="Archive a task card.")
    p.add_argument("task", help="Task name or id.")
    p.set_defaults(func=delete.cmd_delete)

    p = sub.add_parser("start", help="Start a time tracker for a task.")
    p.add_argument("task", help="Task name or id.")
    p.set_defaults(func=tracking.cmd_start)

    p = sub.add_parser("end", help="Stop every open time tracker.")
    p.set_defaults(func=tracking.cmd_end)

    p = sub.add_parser("recent", help="Print the most recently used card titles.")
    p.add_argument(
        "limit", nargs="?", type=int, help="How many cards (default from RECENT_CARDS_LIMIT, 20)."
    )
    p.set_defaults(func=recent.cmd_recent)

    p = sub.add_parser("sync", help="Sync Notion databases into the local mirror.")
    p.add_argument("--full", action="store_true", help="Full sync (soft-deletes missing rows).")
    p.set_defaults(func=sync_cmd.cmd_sync)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args, common.load_env())
    except common.sync.SchemaMismatchError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
