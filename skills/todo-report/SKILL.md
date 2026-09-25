---
name: todo-report
description: Generate summaries and reports from the local task data. Use when the user asks for a weekly review, time breakdown, productivity summary, or overview of their workload.
---

# Todo Report

> Follow shared conventions: `../conventions.md`

Generate summaries from the local Postgres mirror.

## Connection

See `../conventions.md` (Connection) for the Postgres boilerplate.

## Shared Queries

For raw time queries (time logged today, time by project this week, total per task) see the `time-tracker` skill; for the canonical project status query see `todo-query` ("Project status overview").

## Reports

### Daily Summary
"What did I do today?"
```sql
-- Active tasks today
SELECT name, status, priority FROM tasks
WHERE status = 'Today' AND deleted_at IS NULL;
```

For time logged today, see the `time-tracker` skill.

### Weekly Review
"What was my week like?"
```sql
-- Tasks completed this week
SELECT name FROM tasks
WHERE status = 'Done'
  AND notion_updated_at >= NOW() - INTERVAL '7 days'
  AND deleted_at IS NULL;

-- Backlog size
SELECT count(*) FROM tasks WHERE status = 'Backlog' AND deleted_at IS NULL;
```

For time by project this week, see the `time-tracker` skill.

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

Use the `todo-query` skill ("Project status overview") for the canonical project query.

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
