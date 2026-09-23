---
name: todo-report
description: Generate summaries and reports from the local task data. Use when the user asks for a weekly review, time breakdown, productivity summary, or overview of their workload.
---

# Todo Report

Generate summaries from the local Postgres mirror.

## Connection

Read `DATABASE_URL` from the project's `.env` file.

```python
import psycopg
from pathlib import Path

env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
url = env['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1)
conn = psycopg.connect(url)
```

## Reports

### Daily Summary
"What did I do today?"
```sql
-- Active tasks today
SELECT name, status, priority FROM tasks
WHERE status = 'Today' AND deleted_at IS NULL;

-- Time logged today
SELECT t.name,
       EXTRACT(EPOCH FROM (tt.end_time - tt.start_time))/3600 as hours
FROM time_tracking tt
JOIN tasks t ON tt.task_id = t.id
WHERE tt.start_time::date = CURRENT_DATE AND tt.deleted_at IS NULL
ORDER BY tt.start_time;
```

### Weekly Review
"What was my week like?"
```sql
-- Tasks completed this week
SELECT name FROM tasks
WHERE status = 'Done'
  AND notion_updated_at >= NOW() - INTERVAL '7 days'
  AND deleted_at IS NULL;

-- Time by project this week
SELECT p.name,
       sum(EXTRACT(EPOCH FROM (tt.end_time - tt.start_time))/3600) as hours
FROM time_tracking tt
JOIN tasks t ON tt.task_id = t.id
LEFT JOIN projects p ON t.project_id = p.id
WHERE tt.start_time >= NOW() - INTERVAL '7 days'
  AND tt.deleted_at IS NULL
GROUP BY p.name
ORDER BY hours DESC;

-- Backlog size
SELECT count(*) FROM tasks WHERE status = 'Backlog' AND deleted_at IS NULL;
```

### Workload Overview
"Show me what's on my plate"
```sql
SELECT
  status,
  count(*) as count
FROM tasks
WHERE deleted_at IS NULL AND status != 'Done'
GROUP BY status
ORDER BY
  CASE status
    WHEN 'Today' THEN 1
    WHEN 'This Week' THEN 2
    WHEN 'This Month' THEN 3
    WHEN 'Blocked' THEN 4
    WHEN 'In progress' THEN 5
    ELSE 6
  END;
```

### Project Health
"Status of all my projects"
```sql
SELECT p.name, p.status,
       count(t.id) as open_tasks,
       count(t.id) FILTER (WHERE t.status = 'Done') as done_tasks
FROM projects p
LEFT JOIN tasks t ON t.project_id = p.id
  AND t.deleted_at IS NULL AND t.status != 'Done'
WHERE p.deleted_at IS NULL
GROUP BY p.name, p.status
ORDER BY p.status, p.name;
```

## Output Format

- Use tables for structured data
- Use bullet points for narrative summaries
- Include totals (e.g., "Total: 6.5 hours this week")
- Flag anomalies: tasks stuck in "Today" for >1 week, blocked items with no update, etc.
- Keep reports scannable — bold key numbers, group by priority

## Rules

- Always query local Postgres (never hit Notion API for reports)
- If data looks stale (>1 day since last sync), suggest running sync first
- Adapt the report to what the user specifically asked for — don't dump everything
