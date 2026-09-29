# Query recipes

Local SQLite mirror queries. Run via the template in `SKILL.md` (ad-hoc snippet) or adapt into one.

## Tables

- `tasks` — id, name, tags (JSON list), status, due_date, project_id, priority, description, created_at, notion_updated_at
- `records` — id, name, tags (JSON list), project_id, summary, created_at, notion_updated_at
- `projects` — id, name, status, notion_updated_at
- `time_tracking` — id, name, task_id, start_time, end_time, status, notion_updated_at

Conventions: filter `deleted_at IS NULL` on everything. Cards tagged `hidden` are excluded from all lists by default (`tags NOT LIKE '%"hidden"%'`) — include only when the user explicitly asks.

Hours (SQLite has no `EXTRACT`):
`round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1)`

## Common queries

**"What's on my plate today?"**
```sql
SELECT t.name, t.priority, t.due_date, p.name AS project
FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
WHERE t.status = 'Today' AND t.deleted_at IS NULL
ORDER BY CAST(t.priority AS INTEGER) DESC
```

**"What's due this week?"**
```sql
SELECT t.name, t.due_date, t.status, p.name AS project
FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
WHERE t.due_date BETWEEN date('now') AND date('now', '+7 days')
  AND t.deleted_at IS NULL AND t.status != 'Done'
ORDER BY t.due_date
```

**"Show high-priority backlog"**
```sql
SELECT name, tags, due_date FROM tasks
WHERE status = 'Backlog' AND priority IS NOT NULL AND deleted_at IS NULL
ORDER BY CAST(priority AS INTEGER) DESC
```

**"Show records tagged X"**
```sql
SELECT name, summary FROM records
WHERE tags LIKE '%"x"%' AND deleted_at IS NULL
```

**Project status overview**
```sql
SELECT p.name, p.status,
       count(t.id) AS task_count,
       sum(CASE WHEN t.status = 'Done' THEN 1 ELSE 0 END) AS done_count
FROM projects p
LEFT JOIN tasks t ON t.project_id = p.id AND t.deleted_at IS NULL
WHERE p.deleted_at IS NULL
GROUP BY p.name, p.status
ORDER BY p.status
```

**Default card list** (Title, Project, Status, Total Time — top 10, show total count)
```sql
SELECT t.name, p.name, t.status,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS total_hours
FROM tasks t
LEFT JOIN projects p ON p.id = t.project_id
LEFT JOIN time_tracking tt ON tt.task_id = t.id AND tt.deleted_at IS NULL AND tt.end_time IS NOT NULL
WHERE t.deleted_at IS NULL
GROUP BY t.id, p.name
ORDER BY t.created_at
LIMIT 10
```

## Time summaries

**Time spent today**
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

**Time spent this week per project**
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

**Total time per task (all time)**
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

## Reports

**Daily summary** ("what did I do today?") — tasks with `status = 'Today'` (name, status, priority) plus "Time spent today".

**Weekly review** ("what was my week like?") — tasks `status = 'Done'` with `notion_updated_at >= datetime('now', '-7 days')`; count of `status = 'Backlog'`; plus "Time spent this week per project".

**Workload overview** ("what's on my plate?")
```sql
SELECT status, count(*) AS count
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

**Project health** — the "Project status overview" query.

### Output format

- Tables for structured data, bullets for narrative; include totals ("Total: 6.5 hours this week")
- Flag anomalies: tasks stuck in "Today" >1 week, blocked items with no update
- Bold key numbers, group by priority
