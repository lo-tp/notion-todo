"""comment subcommand: read/create/update/delete comments on a card.

Comments live only in Notion — the local mirror is never touched, so no
sync step follows these mutations.
"""

import sys
from typing import Any, cast

from cards import common


def _latest_comment_id(notion, card_id: str) -> str:
    resp = cast(dict[str, Any], notion.comments.list(block_id=card_id))
    comments = resp.get("results", [])
    if not comments:
        sys.exit("No comments on this card.")
    return comments[-1]["id"]


def cmd_comment(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN")
    conn = common.connect(env)
    card_id, name = common.find_task(conn, args.card)
    conn.close()
    notion = common.Client(auth=env["NOTION_TOKEN"])
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
                    parent={"page_id": card_id}, rich_text=common.rich_text(args.text)
                ),
            )
            print(f"Added comment {resp['id']} on {name}.")
        elif args.action == "update":
            comment_id = args.comment_id or _latest_comment_id(notion, card_id)
            notion.comments.update(comment_id=comment_id, rich_text=common.rich_text(args.text))
            print(f"Updated comment {comment_id} on {name}.")
        else:  # delete
            comment_id = args.comment_id or _latest_comment_id(notion, card_id)
            notion.comments.delete(comment_id=comment_id)
            print(f"Deleted comment {comment_id} on {name}.")
    finally:
        notion.close()
