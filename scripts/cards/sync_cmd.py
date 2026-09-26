"""sync subcommand: sync Notion databases into the local mirror."""

from cards import common


def cmd_sync(args, env: dict[str, str]) -> None:
    common.require(
        env,
        "NOTION_TOKEN",
        "NOTION_DB_PROJECTS",
        "NOTION_DB_RECORDS",
        "NOTION_DB_TASKS",
        "NOTION_DB_TIME_TRACKING",
    )
    notion = common.Client(auth=env["NOTION_TOKEN"])
    try:
        conn = common.connect(env)
        try:
            common.sync.init_schema(conn)
            common.sync.sync_all(notion, env, conn, full=args.full)
            conn.commit()
        finally:
            conn.close()
    finally:
        notion.close()
