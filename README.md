# notion-sync

Local mirror of your Notion task management system, synced to Postgres for fast querying and agent-driven interaction.

## Databases Synced

| Database | Purpose |
|----------|---------|
| Tasks | Your todo items with status, priority, due dates |
| Projects | Grouping containers for tasks and records |
| Records | General reference notes (contacts, places, reading, etc.) |
| Time Tracking | Time entries logged against tasks |

## Setup

1. **Dependencies** (managed by UV):
   ```bash
   uv sync
   ```

2. **Environment** (`.env`):
   ```
   NOTION_TOKEN=ntn_your_token
   DATABASE_URL=postgresql://postgres:postgres@localhost:5432/notion_sync
   ```

3. **Postgres**: Ensure your local instance is running. The `notion_sync` database is created on first sync.

## Sync

```bash
# Full sync (first run, or after major changes in Notion)
uv run python sync/sync.py --full

# Incremental sync (picks up changes since last sync)
uv run python sync/sync.py
```

Incremental sync uses Notion's `last_edited_time` filter. Soft-deletes are only detected on `--full` runs.

## Usage (via coding agent skills)

The `skills/` directory contains agent skill files that define how to interact with your data:

| Skill | What it does |
|-------|-------------|
| `notion-sync` | Sync Notion databases to local Postgres |
| `todo-query` | Query tasks, records, projects, time entries |
| `todo-mutate` | Create, update, complete tasks in Notion |
| `time-tracker` | Log time entries, get time summaries |
| `todo-report` | Weekly reviews, workload overviews, project health |

You interact with this project through your coding agent. Examples:

- "What's on my plate today?"
- "Add a task: fix the login bug, due tomorrow"
- "Log 30 minutes on 'Learn Rust'"
- "What did I spend time on this week?"
- "Show all records tagged 'Chengdu'"

After any mutations (creating/updating tasks in Notion), run a sync to refresh the local mirror.

## Schema

See `sync/schema.sql` for the full DDL. Key design decisions:

- Notion record IDs stored as UUID primary keys
- Formula/rollup fields (Duration, Time Spent, etc.) are computed in SQL, not stored
- Soft-delete via `deleted_at` column (records deleted in Notion are marked, not removed)
- `sync_state` table tracks the last-sync watermark per database

## Context

See `CONTEXT.md` for the domain glossary.
