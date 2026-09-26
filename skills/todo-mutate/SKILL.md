---
name: todo-mutate
description: Create, update, complete, or delete tasks in Notion via the API. Use when the user wants to add a task, change status, set priority, add tags, or remove a task.
---

# Todo Mutate

> Follow shared conventions: `../conventions.md`

Create and update tasks in Notion through the card CLI. The CLI auto-syncs the local mirror after every mutation — no extra sync step.

## Connection

See `../conventions.md` (Connection) for the Notion + SQLite boilerplate.

## Operations

### Create a task

Use the CLI — it formats the properties, validates Status/Priority against the
live database options, and resolves `--project` against the local mirror:

```
uv run python scripts/notion_cards.py create <name> \
    [--status STATUS] [--due YYYY-MM-DD] [--project NAME] \
    [--tags a,b] [--priority 5] [--description TEXT]
```

Only the fields you pass are set. `--project` links an existing project (by name,
unique substring, or UUID); it never creates a project.

### Modify a task

```
uv run python scripts/notion_cards.py modify <task> \
    [--name NEW] [--status STATUS] [--due YYYY-MM-DD] [--project NAME] \
    [--tags a,b] [--priority 5] [--description TEXT]
```

Only the fields you pass are touched. An empty value clears a field (e.g.
`--status ""` unsets the status). Tags and project are replaced wholesale.

### Delete a task (archive)

Notion doesn't support hard delete via API. Archive instead:

```
uv run python scripts/notion_cards.py delete <task>
```

### Start / End a task (time tracking)

```
# Start: stops every open tracker first, then starts a new one for the task
uv run python scripts/notion_cards.py start <task>

# End: stops every open tracker; idempotent (no-op if none is open)
uv run python scripts/notion_cards.py end
```

Task resolution: exact UUID, exact name, or unique substring — ambiguous names are
rejected.

### Direct API updates (ad hoc)

For field sets the CLI doesn't cover, update via the API and sync afterwards:

```python
resp = notion.pages.update(
    page_id=task_id,
    properties={
        "Status": {"select": {"name": "Today"}},
        # ...only include fields being changed
    },
)
notion.close()
```

```bash
uv run python scripts/notion_cards.py sync
```

## Status options
Backlog, This Week, This Month, Today, Blocked, In progress, Finished

`Finished` is the terminal status (cards marked complete are typically moved to it; `Done` is legacy).

## Priority options
5 (only option currently)

## Rules

- Always confirm with the user before creating or deleting tasks unless the request is unambiguous
- When the user says "complete" or "done" → set status to "Finished" (or `Done` if that's the card's existing convention)
- When the user says "delete" → archive (Notion limitation)
- **Single running tracker invariant:** at any moment there must be at most one open (running) time tracker. The start command enforces it — never start a new tracker without first stopping all open ones. Never allow two open trackers to coexist.
- If the user mentions a project name, look it up in the `projects` table first
- You are never allowed to create a new project
