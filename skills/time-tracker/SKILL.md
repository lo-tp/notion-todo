---
name: time-tracker
description: Log time entries against tasks and summarize time spent. Use when the user wants to log time, track hours on a task, or get time reports.
---

# Time Tracker

> Follow shared conventions: `../conventions.md`

Manage time entries in Notion (Time Tracking DB) and query local Postgres for summaries.

## Connection

Read `NOTION_TOKEN` and `DATABASE_URL` from the project's `.env` file.

```python
from notion_client import Client
import psycopg
from pathlib import Path
from datetime import datetime, timedelta

env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
notion = Client(auth=env['NOTION_TOKEN'])   # one client per run; call notion.close() when done
TIME_TRACKING_DB = env['NOTION_DB_TIME_TRACKING']
```

## Logging Time

### Log a time entry against a task

```python
def log_time(task_id: str, start_time: str, end_time: str, name: str = None):
    """start_time and end_time are ISO format, e.g. '2026-09-22T09:00:00+08:00'"""
    properties = {
        "Name": {"title": [{"text": {"content": name or "Time entry"}}]},
        "Start Time": {"date": {"start": start_time}},
        "End Time": {"date": {"start": end_time}},
        "Status": {"select": {"name": "Stopped"}},
        "Tasks": {"relation": [{"id": task_id}]},
    }
    resp = notion.pages.create(
        parent={"database_id": TIME_TRACKING_DB}, properties=properties
    )
    return resp
```

### Common log patterns

- "Log 30 minutes on X" → find task, create entry with start=now-30min, end=now
- "Log 1 hour on X this morning" → start=9am today, end=10am today
- "I worked on X for 45 min" → start=now-45min, end=now

## Querying (local Postgres)

### Time spent today
```sql
SELECT t.name as task, sum(EXTRACT(EPOCH FROM (end_time - start_time))/3600) as hours
FROM time_tracking tt
JOIN tasks t ON tt.task_id = t.id
WHERE tt.start_time::date = CURRENT_DATE AND tt.deleted_at IS NULL
GROUP BY t.name
ORDER BY hours DESC
```

### Time spent this week per project
```sql
SELECT p.name as project,
       sum(EXTRACT(EPOCH FROM (tt.end_time - tt.start_time))/3600) as hours
FROM time_tracking tt
JOIN tasks t ON tt.task_id = t.id
LEFT JOIN projects p ON t.project_id = p.id
WHERE tt.start_time >= CURRENT_DATE - INTERVAL '7 days'
  AND tt.deleted_at IS NULL
GROUP BY p.name
ORDER BY hours DESC
```

### Total time per task (all time)
```sql
SELECT t.name, count(*) as entries,
       sum(EXTRACT(EPOCH FROM (tt.end_time - tt.start_time))/3600) as total_hours
FROM time_tracking tt
JOIN tasks t ON tt.task_id = t.id
WHERE tt.deleted_at IS NULL AND t.deleted_at IS NULL
GROUP BY t.name
HAVING sum(EXTRACT(EPOCH FROM (tt.end_time - tt.start_time))/3600) > 0
ORDER BY total_hours DESC
LIMIT 20
```

## Finding Task IDs

```python
with psycopg.connect(url) as conn:
    row = conn.execute(
        "SELECT id, name FROM tasks WHERE name ILIKE %s AND deleted_at IS NULL LIMIT 1",
        (f"%{name}%",)
    ).fetchone()
```

## Rules

- Time format: ISO 8601 with timezone (user is likely +08:00 based on context)
- Always confirm the time range before logging if it's ambiguous
- After logging, suggest a sync to update local data
- Present time summaries in hours (1 decimal) for readability
- "How long did I spend on X?" → query, don't create anything
