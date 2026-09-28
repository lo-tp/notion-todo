# Notion Sync

A local mirror of personal Notion databases (Tasks, Records, Projects, Time Tracking) synced to SQLite for fast local querying and agent-driven task management.

## Language

**Task**:
A unit of work tracked in the Tasks database. Has a status lifecycle (Backlog → This Week/This Month/Today → In progress → Done) and optional due date, priority, and project.
_Avoid_: todo, item, entry

**Project**:
A named grouping container that tasks and records can be associated with. Has a status lifecycle (Not started → Active → Done/Paused).
_Avoid_: category, folder

**Record**:
A general-purpose reference/note entry (contacts, places, reading notes, etc.) tagged for categorization. Not a task — no status lifecycle.
_Avoid_: note, log, entry

**Time Entry**:
A single start/end time interval logged against a task. Duration is computed, not stored.
_Avoid_: log, session, timesheet

**Sync**:
The operation of pulling changes from Notion into local SQLite. First sync is full; subsequent syncs are incremental (by `last_edited_time`).
_Avoid_: pull, fetch, backup

**Soft Delete**:
A Notion record that no longer appears in the API is marked `deleted_at` in SQLite rather than removed. Keeps the local copy honest.
_Avoid_: tombstone, ghost
