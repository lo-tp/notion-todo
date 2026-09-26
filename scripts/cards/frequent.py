"""frequent subcommand: list the most recently used tasks and projects with ids."""

from cards import common


def cmd_frequent(args, env: dict[str, str]) -> None:
    conn = common.connect(env)
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
