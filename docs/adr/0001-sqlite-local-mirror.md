# SQLite for the local mirror

The local mirror of the Notion databases is a single-process, single-user read cache whose only job is fast name lookup and reporting for the agent CLI. It was on Postgres (via `py-pglite`); it is now stdlib **SQLite** at `.notion-sync/mirror.sqlite` (overridable via `MIRROR_PATH` in `.env`), chosen because a local embedded DB with zero server, zero extra dependencies, and zero provisioning cost satisfies the workload — and it removes `psycopg` and `py-pglite` from the dependency tree.

**Consequences:** `tags` is a JSON list in a `TEXT` column (no `TEXT[]`/GIN); timestamps are ISO-8601 strings (no `timestamptz`); the soft-delete query no longer uses `unnest`. The schema lives in `sync/schema.sql` and is initialized idempotently by the sync.
