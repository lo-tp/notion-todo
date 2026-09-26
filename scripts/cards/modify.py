"""modify subcommand: modify a task card's fields."""

import sys

from cards import common


def cmd_modify(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN", "NOTION_DB_TASKS")
    conn = common.connect(env)
    try:
        task_id, task_name = common.find_task(conn, args.task)

        properties = common.build_properties(
            args.name if args.name is not None else task_name,
            status=args.status,
            due=args.due,
            project_id=common.find_project(conn, args.project) if args.project else None,
            tags=common.parse_tags(args.tags),
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

        notion = common.Client(auth=env["NOTION_TOKEN"])
        try:
            ds_id = common.sync.data_source_id(notion, env["NOTION_DB_TASKS"])
            common.validate_selects(notion, ds_id, properties)
            notion.pages.update(page_id=task_id, properties=properties)
        finally:
            notion.close()
    finally:
        conn.close()

    print(f"Modified task: {task_name} (id={task_id})")
    common.auto_sync(env)
