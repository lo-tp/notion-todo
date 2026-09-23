---
name: notion-sync
description: Sync Notion databases to local Postgres. Use when the user asks to sync, refresh, or update their local task data.
---

# Notion Sync

Run the sync to pull changes from Notion into local Postgres.

## Usage

```bash
# Incremental sync (default)
uv run python sync/sync.py

# Full sync (first run, or to detect deletions)
uv run python sync/sync.py --full
```

## Behavior

- **Incremental** (default): Only fetches records updated since last sync via Notion's `last_edited_time` filter. Fast.
- **Full** (`--full`): Fetches all records and soft-deletes any that no longer exist in Notion. Slower.

## Schema Mismatch

If the Notion database schema has changed (fields added/removed), the sync will refuse and list which fields are new or missing. In that case:

1. Tell the user what changed in Notion
2. Update `sync/schema.sql` (Postgres DDL) and `sync/sync.py` (field parsing) to match
3. Re-run the sync

## After Sync

- Suggest running a query skill if the user was about to do something with the data
- Report the number of records synced

## Rules

- Default to incremental unless the user explicitly says "full sync"
- If sync fails due to rate limiting (HTTP 429), wait and retry
- If schema mismatch occurs, do NOT attempt to sync — stop and report
