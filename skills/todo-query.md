---
name: todo-query
description: Query and list tasks, records, projects, and time entries from the local Postgres mirror. Use when the user asks about their tasks, what's due, time spent, records, or projects.
---

# Todo Query

Query the local Postgres mirror of Notion databases. All queries should filter `deleted_at IS NULL` unless the user explicitly asks about deleted items.

## Connection

Read `DATABASE_URL` from the project's `.env` file (same directory as `pyproject.toml`).

Use this pattern for all queries:

```python
import psycopg
from pathlib import Path

env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
url = env['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1)
conn = psycopg.connect(url)
```

## Tables

- `tasks` — id, name, tags[], status, due_date, project_id, priority, description, created_at, notion_updated_at
- `records` — id, name, tags[], project_id, summary, created_at, notion_updated_at
- `projects` — id, name, status, notion_updated_at
- `time_tracking` — id, name, task_id, start_time, end_time, status, notion_updated_at

## Common Queries

### "What's on my plate today?"
```sql
SELECT t.name, t.priority, t.due_date, p.name as project
FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
WHERE t.status = 'Today' AND t.deleted_at IS NULL
ORDER BY t.priority DESC NULLS LAST
```

### "What's due this week?"
```sql
SELECT t.name, t.due_date, t.status, p.name as project
FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
WHERE t.due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
  AND t.deleted_at IS NULL
  AND t.status != 'Done'
ORDER BY t.due_date
```

### "Show high-priority backlog"
```sql
SELECT name, tags, due_date FROM tasks
WHERE status = 'Backlog' AND priority IS NOT NULL AND deleted_at IS NULL
ORDER BY priority DESC
```

### "What time did I spend this week?"
```sql
SELECT tt.start_time, tt.name, t.name as task
FROM time_tracking tt
LEFT JOIN tasks t ON tt.task_id = t.id
WHERE tt.start_time >= NOW() - INTERVAL '7 days'
  AND tt.deleted_at IS NULL
ORDER BY tt.start_time DESC
```

### "Show records tagged X"
```sql
SELECT name, summary FROM records
WHERE %s = ANY(tags) AND deleted_at IS NULL
```

### "Project status overview"
```sql
SELECT p.name, p.status,
       count(t.id) as task_count,
       count(t.id) FILTER (WHERE t.status = 'Done') as done_count
FROM projects p
LEFT JOIN tasks t ON t.project_id = p.id AND t.deleted_at IS NULL
WHERE p.deleted_at IS NULL
GROUP BY p.name, p.status
ORDER BY p.status
```

## Rules

- Always run queries via `uv run python` with inline scripts
- Present results in a concise table or list format
- If the user asks for something that doesn't map to a simple query, compose the SQL accordingly
- If a query returns no results, say so rather than showing an empty table
