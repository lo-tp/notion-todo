"""Load the most recently used card titles for in-context fuzzy matching.

Prints the N most recently updated card titles so the agent can capture them in
context and fuzzy-match a later command against them. Excludes deleted cards;
includes hidden cards (they are real cards the user refers to).

"Last used" is approximated by the most recent Notion edit, falling back to
creation order.

The number of cards is set by the ``RECENT_CARDS_LIMIT`` key in ``.env``
(default 20); a positional argument overrides both.

Usage:
    uv run python scripts/load_recent_cards.py [N]
"""

import sys

import psycopg
from stop_tracking import db_url, load_env

DEFAULT_LIMIT = 20
ENV_LIMIT_KEY = "RECENT_CARDS_LIMIT"


def recent_titles(env: dict[str, str], limit: int) -> list[tuple[str, str]]:
    """Return (id, name) for the most recently used, non-deleted cards."""
    with psycopg.connect(db_url(env)) as conn:
        rows = conn.execute(
            "SELECT id, name FROM tasks "
            "WHERE deleted_at IS NULL "
            "ORDER BY notion_updated_at DESC NULLS LAST, created_at DESC "
            "LIMIT %s",
            (limit,),
        ).fetchall()
    return [(str(r[0]), r[1]) for r in rows]


def main() -> None:
    env = load_env()
    if "DATABASE_URL" not in env:
        sys.exit("Missing DATABASE_URL in .env")

    # Precedence: CLI argument > RECENT_CARDS_LIMIT in .env > DEFAULT_LIMIT.
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else int(env.get(ENV_LIMIT_KEY, DEFAULT_LIMIT))

    for i, (card_id, name) in enumerate(recent_titles(env, limit), 1):
        print(f"{i}. {name}  ({card_id})")


if __name__ == "__main__":
    main()
