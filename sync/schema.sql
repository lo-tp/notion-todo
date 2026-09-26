-- Schema for local Notion mirror (SQLite)
--
-- IDs are Notion page IDs stored as TEXT. Timestamps are ISO-8601 strings
-- exactly as returned by the Notion API (or local ISO for `deleted_at`).
-- `tags` is a JSON list of strings, e.g. ["a", "b"] or [].

CREATE TABLE IF NOT EXISTS projects (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    status            TEXT,
    notion_updated_at TEXT NOT NULL,
    notion_created_at TEXT,
    deleted_at        TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    tags              TEXT NOT NULL DEFAULT '[]',
    status            TEXT,
    due_date          TEXT,
    project_id        TEXT REFERENCES projects(id),
    priority          TEXT,
    description       TEXT,
    created_at        TEXT,
    notion_updated_at TEXT NOT NULL,
    deleted_at        TEXT
);

CREATE TABLE IF NOT EXISTS records (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    tags              TEXT NOT NULL DEFAULT '[]',
    project_id        TEXT REFERENCES projects(id),
    summary           TEXT,
    created_at        TEXT,
    notion_updated_at TEXT NOT NULL,
    deleted_at        TEXT
);

CREATE TABLE IF NOT EXISTS time_tracking (
    id                TEXT PRIMARY KEY,
    name              TEXT,
    task_id           TEXT REFERENCES tasks(id),
    start_time        TEXT,
    end_time          TEXT,
    status            TEXT,
    notion_updated_at TEXT NOT NULL,
    deleted_at        TEXT
);

-- Track sync watermark per database
CREATE TABLE IF NOT EXISTS sync_state (
    db_id           TEXT PRIMARY KEY,
    last_synced_at  TEXT NOT NULL
);

-- Indexes for common queries (partial indexes carry over from the Postgres
-- schema; the GIN indexes on tags are gone — tags are JSON text now).
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_time_tracking_task ON time_tracking(task_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_time_tracking_start ON time_tracking(start_time) WHERE deleted_at IS NULL;
