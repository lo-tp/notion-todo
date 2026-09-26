"""create subcommand: create a new task card."""

from typing import Any, cast

from cards import common


def cmd_create(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN", "NOTION_DB_TASKS")
    conn = common.connect(env)
    try:
        project_id = None
        if args.project is not None:
            project_id = common.find_project(conn, args.project) if args.project else None
        tags = common.parse_tags(args.tags)

        properties = common.build_properties(
            args.name,
            status=args.status,
            due=args.due,
            project_id=project_id,
            tags=tags,
            priority=args.priority,
            description=args.description,
        )

        notion = common.Client(auth=env["NOTION_TOKEN"])
        try:
            ds_id = common.sync.data_source_id(notion, env["NOTION_DB_TASKS"])
            common.validate_selects(notion, ds_id, properties)
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
    common.auto_sync(env)
