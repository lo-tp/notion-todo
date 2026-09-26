"""page subcommand: read/create/update/delete page content blocks on a card.

Page content lives only in Notion — no mirror sync is needed.
"""

import sys
from typing import Any, cast

from cards import common

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


def _latest_block_id(notion, card_id: str) -> str:
    resp = cast(dict[str, Any], notion.blocks.children.list(block_id=card_id))
    blocks = resp.get("results", [])
    if not blocks:
        sys.exit("No page content on this card.")
    return blocks[-1]["id"]


def cmd_page(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN")
    conn = common.connect(env)
    card_id, name = common.find_task(conn, args.card)
    conn.close()
    notion = common.Client(auth=env["NOTION_TOKEN"])
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
            block = {"type": "paragraph", "paragraph": {"rich_text": common.rich_text(args.text)}}
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
                block_id=block_id, **{btype: {"rich_text": common.rich_text(args.text)}}
            )
            print(f"Updated {btype} block {block_id} on {name}.")
        else:  # delete
            notion.blocks.delete(block_id=block_id)
            print(f"Deleted block {block_id} from {name}.")
    finally:
        notion.close()
