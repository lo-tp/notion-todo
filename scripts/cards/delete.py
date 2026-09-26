"""delete subcommand: archive a task card (Notion soft delete)."""

from cards import common


def cmd_delete(args, env: dict[str, str]) -> None:
    common.require(env, "NOTION_TOKEN")
    conn = common.connect(env)
    try:
        task_id, task_name = common.find_task(conn, args.task)
        notion = common.Client(auth=env["NOTION_TOKEN"])
        try:
            notion.pages.update(page_id=task_id, archived=True)
        finally:
            notion.close()
    finally:
        conn.close()

    print(f"Archived task: {task_name} (id={task_id})")
    common.auto_sync(env)
