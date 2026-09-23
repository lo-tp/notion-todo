---
name: todo-mutate
description: Create, update, complete, or delete tasks in Notion via the API. Use when the user wants to add a task, change status, set priority, add tags, or remove a task.
---

# Todo Mutate

Create and update tasks in Notion directly via the API. After mutations, the local Postgres mirror will be stale until the next sync — remind the user if relevant.

## Connection

Read `NOTION_TOKEN` from the project's `.env` file.

```python
import requests
from pathlib import Path

env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
token = env['NOTION_TOKEN']
headers = {
    "Authorization": f"Bearer {token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}
NOTION_API = "https://api.notion.com/v1"
TASKS_DB = "1c7613a9-7933-80b5-833d-d1eb31797ac9"
```

## Operations

### Create a task

```python
resp = requests.post(
    f"{NOTION_API}/pages",
    headers=headers,
    json={
        "parent": {"database_id": TASKS_DB},
        "properties": {
            "Name": {"title": [{"text": {"content": "Task name"}}]},
            # Optional fields — include only if specified:
            # "Status": {"status": {"name": "Today"}},
            # "Priority": {"select": {"name": "5"}},
            # "Due Date": {"date": {"start": "2026-09-25"}},
            # "Tags": {"multi_select": [{"name": "Reading"}]},
            # "Description": {"rich_text": [{"text": {"content": "details"}}]},
            # "Projects": {"relation": [{"id": "<project-uuid>"}]},
        }
    }
)
```

### Update a task

```python
resp = requests.patch(
    f"{NOTION_API}/pages/{task_id}",
    headers=headers,
    json={"properties": {
        "Status": {"status": {"name": "Done"}},
        # ...only include fields being changed
    }}
)
```

### "Delete" a task (archive)

Notion doesn't support hard delete via API. Archive instead:
```python
resp = requests.patch(
    f"{NOTION_API}/pages/{task_id}",
    headers=headers,
    json={"archived": True}
)
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
Backlog, This Week, This Month, Today, Blocked, In progress, Done

## Priority options
5 (only option currently)

## Rules

- Always confirm with the user before creating or deleting tasks unless the request is unambiguous
- When the user says "complete" or "done" → set status to "Done"
- When the user says "delete" → archive (Notion limitation)
- After mutations, suggest running a sync: `uv run python sync/sync.py`
- If the user mentions a project name, look it up in the `projects` table first
