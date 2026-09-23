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

## Page content (on-demand)

Page body content (paragraphs, headings, links, embeds) is **not** synced locally — the `description` property is the only stored text. When the user asks for a card's page content, fetch it from the Notion API on demand. Never add page blocks to the sync.

```python
import requests

headers = {
    "Authorization": f"Bearer {env['NOTION_TOKEN']}",
    "Notion-Version": "2022-06-28",
}

# Resolve the page id from the local db (e.g. tasks.id for a task card)
resp = requests.get(
    f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100",
    headers=headers,
)
resp.raise_for_status()

for block in resp.json()['results']:
    btype, obj = block['type'], block[block['type']]
    text = ''.join(t['plain_text'] for t in obj.get('rich_text', []))
    # print per type: paragraph, heading_1/2/3, bulleted_list_item,
    # numbered_list_item, to_do, toggle, callout, divider,
    # child_database (embedded db title), column_list, etc.
```

## Rules

- When listing tasks, always exclude `Done` status cards — unless the user explicitly asks to see all cards or the done cards
- Always run queries via `uv run python` with inline scripts
- Present results in a concise table or list format
- If the user asks for something that doesn't map to a simple query, compose the SQL accordingly
- If a query returns no results, say so rather than showing an empty table
- Page content: on-demand API fetch only (see above); keep the local mirror to database properties
