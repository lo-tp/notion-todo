-- Schema for local Notion mirror

CREATE TABLE IF NOT EXISTS projects (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,
    status          TEXT,
    notion_updated_at TIMESTAMPTZ NOT NULL,
    notion_created_at TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,
    tags            TEXT[] DEFAULT '{}',
    status          TEXT,
    due_date        DATE,
    project_id      UUID REFERENCES projects(id),
    priority        TEXT,
    description     TEXT,
    created_at      TIMESTAMPTZ,
    notion_updated_at TIMESTAMPTZ NOT NULL,
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS records (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,
    tags            TEXT[] DEFAULT '{}',
    project_id      UUID REFERENCES projects(id),
    summary         TEXT,
    created_at      TIMESTAMPTZ,
    notion_updated_at TIMESTAMPTZ NOT NULL,
    deleted_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS time_tracking (
    id              UUID PRIMARY KEY,
    name            TEXT,
    task_id         UUID REFERENCES tasks(id),
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    status          TEXT,
    notion_updated_at TIMESTAMPTZ NOT NULL,
    deleted_at      TIMESTAMPTZ
);

-- Track sync watermark per database
CREATE TABLE IF NOT EXISTS sync_state (
    db_id           TEXT PRIMARY KEY,
    last_synced_at  TIMESTAMPTZ NOT NULL
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_time_tracking_task ON time_tracking(task_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_time_tracking_start ON time_tracking(start_time) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_records_tags ON records USING gin(tags) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_tags ON tasks USING gin(tags) WHERE deleted_at IS NULL;
