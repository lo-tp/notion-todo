---
name: todo-mutate
description: Create, update, complete, or delete tasks in Notion via the API. Use when the user wants to add a task, change status, set priority, add tags, or remove a task.
---

# Todo Mutate

> Follow shared conventions: `../conventions.md`

Create and update tasks in Notion directly via the API. After a mutation succeeds, trigger an incremental sync so the local Postgres mirror stays up to date (see Rules).

## Connection

See `../conventions.md` (Connection) for the Notion + Postgres boilerplate.

## Operations

### Create a task

Use the dedicated script — it formats the properties, validates Status/Priority
against the live database options, and resolves `--project` against the local
mirror:

```
uv run python scripts/create_task.py <name> \
    [--status STATUS] [--due YYYY-MM-DD] [--project NAME] \
    [--tags a,b] [--priority 5] [--description TEXT]
```

Only the fields you pass are set. `--project` links an existing project (by name,
unique substring, or UUID); it never creates a project. A successful run counts as
a successful mutation, so trigger the incremental sync (see Rules).

### Update a task

```python
resp = notion.pages.update(
    page_id=task_id,
    properties={
        "Status": {"status": {"name": "Done"}},
        # ...only include fields being changed
    },
)
notion.close()
```

### "Delete" a task (archive)

Notion doesn't support hard delete via API. Archive instead:
```python
resp = notion.pages.update(page_id=task_id, archived=True)
notion.close()
```

### Start / Stop a task (time tracking)

Use the dedicated scripts — they resolve the task against the local mirror, set
`Start Time`/`End Time` = now, and enforce the single-running-tracker invariant:

```
# Start: stops every open tracker first, then starts a new one for the task
uv run python scripts/start_tracking.py <task-name-or-id>

# Stop: stops every open tracker; idempotent (no-op if none is open)
uv run python scripts/stop_tracking.py
```

Task resolution: exact UUID, exact name, or unique substring — ambiguous names are
rejected. A successful run counts as a successful mutation, so trigger the
incremental sync (see Rules).
## Status options
Backlog, This Week, This Month, Today, Blocked, In progress, Done, Finished, Repetitive

`Finished` is the terminal status (cards marked complete are typically moved to it; `Done` is legacy).

## Priority options
5 (only option currently)

## Rules

- Always confirm with the user before creating or deleting tasks unless the request is unambiguous
- When the user says "complete" or "done" → set status to "Done"
- When the user says "delete" → archive (Notion limitation)
- If a mutation request returns success (HTTP 2xx), immediately trigger an incremental sync for the affected database: `uv run python sync/sync.py`
- **Single running tracker invariant:** at any moment there must be at most one open (running) time tracker. The start/stop scripts enforce it — never start a new tracker without first stopping all open ones. Never allow two open trackers to coexist.
- If the user mentions a project name, look it up in the `projects` table first
- You are never allowed to create a new project
