---
name: todo-mutate
description: Create, update, complete, or delete tasks in Notion via the API. Use when the user wants to add a task, change status, set priority, add tags, or remove a task.
---

# Todo Mutate

Create and update tasks in Notion directly via the API. After a mutation succeeds, trigger an incremental sync so the local Postgres mirror stays up to date (see Rules).

## Connection

Read `NOTION_TOKEN` from the project's `.env` file.

```python
from notion_client import Client
from pathlib import Path

env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
notion = Client(auth=env['NOTION_TOKEN'])   # one client per run; call notion.close() when done
TIME_TRACKING_DB = env['NOTION_DB_TIME_TRACKING']
```

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

"Starting" and "stopping" a task means creating or updating a row in the **time tracking** database (`TIME_TRACKING_DB`) that references the task. Time-tracking fields: `Name`, `Tasks` (relation to the task), `Start Time`, `End Time`, `Status`, `Duration`.

**Start a task** — create a new time-tracking row with `Start Time` = now, linked to the task:
```python
resp = notion.pages.create(
    parent={"database_id": TIME_TRACKING_DB},
    properties={
        "Name": {"title": [{"text": {"content": "<task name>"}}]},
        "Tasks": {"relation": [{"id": task_id}]},
        "Start Time": {"date": {"start": "2026-09-23T09:00:00.000Z"}},
    },
)
```

**Stop a task** — find the matching open time-tracking row (linked to the task, no `End Time`) and set `End Time` = now:
```python
resp = notion.pages.update(
    page_id=time_tracking_id,
    properties={"End Time": {"date": {"start": "2026-09-23T10:30:00.000Z"}}},
)
notion.close()
```
## Finding Task IDs

To find a task by name, query the local Postgres first:
```python
import psycopg
env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
url = env['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1)
with psycopg.connect(url) as conn:
    row = conn.execute(
        "SELECT id, name FROM tasks WHERE name ILIKE %s AND deleted_at IS NULL LIMIT 1",
        (f"%{query}%",)
    ).fetchone()
```

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
- If the user says **start** a task → add a new row to the time tracking database for that task (`Start Time` = now). Before adding the new row, you need to stop all existing rows that are ongoing.
- If the user says **stop** a task → update the matching open time tracking row for that task (`End Time` = now)
- **Single running tracker invariant:** at any moment there must be at most one open (running) time tracker. Before starting a new time tracker for any card, first stop ALL existing open time trackers (set `End Time` = now for every row with `End Time` IS NULL), even if they belong to a different card. Then start the new one. Never allow two open trackers to coexist.
- When the user says **stop**, stop the time tracker for the card they referenced (the matching open row for that task). It does not stop unrelated trackers on its own — only do it as part of the start sequence above if that is what's needed to keep a single tracker running.
- If the user mentions a project name, look it up in the `projects` table first
- You are never allowed to create a new project
