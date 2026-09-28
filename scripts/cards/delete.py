"""delete subcommand: archive a task card (Notion soft delete)."""

from datetime import UTC, datetime

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

        # Mark deleted immediately (O(1)). The post-mutation incremental sync
        # won't resurrect it: archived pages never appear in query results,
        # and upsert only clears deleted_at for ids it actually fetches.
        conn.execute(
            "UPDATE tasks SET deleted_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), task_id),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"Archived task: {task_name} (id={task_id})")
    common.auto_sync(env)
