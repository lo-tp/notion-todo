---
name: time-tracker
description: Log time entries against tasks and summarize time spent. Use when the user wants to log time, track hours on a task, or get time reports.
---

# Time Tracker

> Follow shared conventions: `../conventions.md`

Manage time entries in Notion (Time Tracking DB) and query the local SQLite mirror for summaries.

## Connection

See `../conventions.md` (Connection) for the Notion + SQLite boilerplate.

## Logging Time

### Live tracking (start / stop)

```bash
uv run python scripts/notion_cards.py start <task>   # stops any open tracker first
uv run python scripts/notion_cards.py end            # stops every open tracker
```

### Log a past time entry against a task

Create the entry via the API (start_time and end_time are ISO 8601 with the
user's local timezone, e.g. '2026-09-22T09:00:00+08:00'), then sync:

```python
def log_time(task_id: str, start_time: str, end_time: str, name: str = None):
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

```bash
uv run python scripts/notion_cards.py sync
```

### Common log patterns

- "Log 30 minutes on X" → find task, create entry with start=now-30min, end=now
- "Log 1 hour on X this morning" → start=9am today, end=10am today
- "I worked on X for 45 min" → start=now-45min, end=now

## Querying (local SQLite)

SQLite has no `EXTRACT`; compute hours as
`round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1)`.

### Time spent today
```sql
SELECT t.name AS task,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS hours
FROM time_tracking tt
JOIN tasks t ON t.id = tt.task_id
WHERE date(tt.start_time) = date('now')
  AND tt.deleted_at IS NULL AND tt.end_time IS NOT NULL
GROUP BY t.name
ORDER BY hours DESC
```

### Time spent this week per project
```sql
SELECT p.name AS project,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS hours
FROM time_tracking tt
JOIN tasks t ON t.id = tt.task_id
LEFT JOIN projects p ON p.id = t.project_id
WHERE tt.start_time >= datetime('now', '-7 days')
  AND tt.deleted_at IS NULL AND tt.end_time IS NOT NULL
GROUP BY p.name
ORDER BY hours DESC
```

### Total time per task (all time)
```sql
SELECT t.name, count(*) AS entries,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS total_hours
FROM time_tracking tt
JOIN tasks t ON t.id = tt.task_id
WHERE tt.deleted_at IS NULL AND t.deleted_at IS NULL AND tt.end_time IS NOT NULL
GROUP BY t.name
HAVING sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24) > 0
ORDER BY total_hours DESC
LIMIT 20
```

## Rules

- Time format: ISO 8601 with the user's local timezone (detect at runtime — see Time Display in conventions)
- Always confirm the time range before logging if it's ambiguous
- After logging via the API, run the incremental sync (see above)
- Present time summaries in hours (1 decimal) for readability
- "How long did I spend on X?" → query, don't create anything
