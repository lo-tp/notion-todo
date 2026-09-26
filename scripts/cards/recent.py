"""recent subcommand: print the most recently used card titles."""

from cards import common


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
    limit = args.limit or int(env.get(common.RECENT_CARDS_LIMIT_KEY, common.DEFAULT_RECENT_LIMIT))
    conn = common.connect(env)
    try:
        for i, (card_id, name) in enumerate(recent_titles(conn, limit), 1):
            print(f"{i}.  {card_id}  {name}")
    finally:
        conn.close()
