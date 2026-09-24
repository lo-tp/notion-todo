"""Unit tests for sync/sync.py.

Pure functions are tested directly. Database-touching functions run against a
real throwaway Postgres database (see the ``test_db`` fixture). Notion API
calls are exercised by mocking the module-level ``client``.
"""

import uuid
from datetime import datetime, timezone
from unittest import mock

import pytest

import sync
from sync import SchemaMismatchError


def _make_record(**props):
    return {"properties": props}


# --- parse_properties ------------------------------------------------------

def test_parse_title_joins_segments():
    rec = _make_record(Name={"type": "title", "title": [
        {"plain_text": "Hello"}, {"plain_text": " World"}]})
    gt, *_ = sync.parse_properties(rec)
    assert gt("Name") == "Hello World"


def test_parse_rich_text():
    rec = _make_record(Description={"type": "rich_text", "rich_text": [{"plain_text": "abc"}]})
    gt, *_ = sync.parse_properties(rec)
    assert gt("Description") == "abc"


def test_parse_select():
    rec = _make_record(Status={"type": "select", "select": {"name": "Today"}})
    _, gs, *_ = sync.parse_properties(rec)
    assert gs("Status") == "Today"


def test_parse_status():
    rec = _make_record(Status={"type": "status", "status": {"name": "Done"}})
    _, gs, *_ = sync.parse_properties(rec)
    assert gs("Status") == "Done"


def test_parse_multi_select():
    rec = _make_record(Tags={"type": "multi_select", "multi_select": [
        {"name": "a"}, {"name": "b"}]})
    _, _, gm, *_ = sync.parse_properties(rec)
    assert gm("Tags") == ["a", "b"]


def test_parse_multi_select_empty():
    rec = _make_record(Tags={"type": "multi_select", "multi_select": []})
    _, _, gm, *_ = sync.parse_properties(rec)
    assert gm("Tags") == []


def test_parse_date():
    rec = _make_record(**{"Due Date": {"type": "date", "date": {"start": "2026-01-01"}}})
    _, _, _, gd, _ = sync.parse_properties(rec)
    assert gd("Due Date") == "2026-01-01"


def test_parse_relation():
    rec = _make_record(Projects={"type": "relation", "relation": [{"id": "abc"}]})
    _, _, _, _, gr = sync.parse_properties(rec)
    assert gr("Projects") == "abc"


def test_parse_empty_select_is_none():
    rec = _make_record(Status={"type": "select", "select": None})
    _, gs, *_ = sync.parse_properties(rec)
    assert gs("Status") is None


# --- upserts (against a real Postgres) -------------------------------------

def test_upsert_projects(test_db):
    pid = str(uuid.uuid4())
    rec = {
        "id": pid,
        "last_edited_time": "2026-01-01T00:00:00.000Z",
        "created_time": "2025-12-31T00:00:00.000Z",
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "P1"}]},
            "Status": {"type": "select", "select": {"name": "Active"}},
        },
    }
    sync.upsert_projects(test_db, [rec])
    test_db.commit()

    row = test_db.execute(
        "SELECT name, status, deleted_at FROM projects WHERE id=%s", (pid,)
    ).fetchone()
    assert row[0] == "P1"
    assert row[1] == "Active"
    assert row[2] is None


def test_upsert_projects_clears_deleted_on_conflict(test_db):
    pid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO projects (id, name, notion_updated_at, deleted_at) VALUES (%s, 'old', now(), now())",
        (pid,),
    )
    test_db.commit()

    sync.upsert_projects(test_db, [{
        "id": pid,
        "last_edited_time": "2026-01-02T00:00:00.000Z",
        "created_time": "2025-12-31T00:00:00.000Z",
        "properties": {"Name": {"type": "title", "title": [{"plain_text": "new"}]},
                       "Status": {"type": "select", "select": None}},
    }])
    test_db.commit()

    row = test_db.execute("SELECT name, deleted_at FROM projects WHERE id=%s", (pid,)).fetchone()
    assert row[0] == "new"
    assert row[1] is None  # revived


def test_upsert_tasks_with_relation(test_db):
    proj = str(uuid.uuid4())
    test_db.execute("INSERT INTO projects (id, name, notion_updated_at) VALUES (%s, 'proj', now())", (proj,))
    test_db.commit()

    tid = str(uuid.uuid4())
    rec = {
        "id": tid,
        "last_edited_time": "2026-01-02T00:00:00.000Z",
        "created_time": "2026-01-01T00:00:00.000Z",
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "T1"}]},
            "Tags": {"type": "multi_select", "multi_select": [{"name": "x"}]},
            "Status": {"type": "select", "select": {"name": "Today"}},
            "Due Date": {"type": "date", "date": {"start": "2026-02-01"}},
            "Projects": {"type": "relation", "relation": [{"id": proj}]},
            "Priority": {"type": "select", "select": {"name": "5"}},
            "Description": {"type": "rich_text", "rich_text": [{"plain_text": "desc"}]},
        },
    }
    sync.upsert_tasks(test_db, [rec])
    test_db.commit()

    row = test_db.execute("SELECT name, tags, project_id, priority, due_date FROM tasks WHERE id=%s", (tid,)).fetchone()
    assert row[0] == "T1"
    assert row[1] == ["x"]
    assert row[2] == uuid.UUID(proj)
    assert row[3] == "5"
    assert row[4].isoformat() == "2026-02-01"


def test_upsert_time_tracking(test_db):
    task = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO tasks (id, name, notion_updated_at) VALUES (%s, 'task', now())", (task,)
    )
    test_db.commit()

    tid = str(uuid.uuid4())
    rec = {
        "id": tid,
        "last_edited_time": "2026-01-02T00:00:00.000Z",
        "created_time": "2026-01-01T00:00:00.000Z",
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "entry"}]},
            "Tasks": {"type": "relation", "relation": [{"id": task}]},
            "Start Time": {"type": "date", "date": {"start": "2026-01-02T09:00:00.000Z"}},
            "End Time": {"type": "date", "date": {"start": "2026-01-02T10:00:00.000Z"}},
            "Status": {"type": "select", "select": {"name": "Stopped"}},
        },
    }
    sync.upsert_time_tracking(test_db, [rec])
    test_db.commit()

    row = test_db.execute("SELECT name, task_id, start_time, end_time, status FROM time_tracking WHERE id=%s", (tid,)).fetchone()
    assert row[0] == "entry"
    assert row[1] == uuid.UUID(task)
    assert row[2].isoformat() == "2026-01-02T09:00:00+00:00"
    assert row[3].isoformat() == "2026-01-02T10:00:00+00:00"
    assert row[4] == "Stopped"


# --- soft delete ------------------------------------------------------------

def test_soft_delete_missing(test_db):
    live_a = str(uuid.uuid4())
    live_c = str(uuid.uuid4())
    gone = str(uuid.uuid4())
    for pid in (live_a, live_c, gone):
        test_db.execute("INSERT INTO projects (id, name, notion_updated_at) VALUES (%s, 'x', now())", (pid,))
    test_db.commit()

    sync.soft_delete_missing(test_db, "projects", None, {live_a, live_c})
    test_db.commit()

    deleted = {str(r[0]) for r in test_db.execute(
        "SELECT id FROM projects WHERE deleted_at IS NOT NULL"
    ).fetchall()}
    assert deleted == {gone}


def test_soft_delete_missing_empty_live_marks_all(test_db):
    a = str(uuid.uuid4())
    test_db.execute("INSERT INTO projects (id, name, notion_updated_at) VALUES (%s, 'x', now())", (a,))
    test_db.commit()

    sync.soft_delete_missing(test_db, "projects", None, set())
    test_db.commit()

    row = test_db.execute("SELECT deleted_at FROM projects WHERE id=%s", (a,)).fetchone()
    assert row[0] is not None


# --- watermarks -------------------------------------------------------------

def test_get_watermark_none(test_db):
    assert sync.get_watermark(test_db, "projects") is None


def test_set_and_get_watermark(test_db):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sync.set_watermark(test_db, "projects", ts)
    test_db.commit()
    assert sync.get_watermark(test_db, "projects") == ts.isoformat()


def test_next_watermark_advances_to_max_edited(test_db):
    recs = [
        {"last_edited_time": "2026-01-05T00:00:00.000Z"},
        {"last_edited_time": "2026-01-03T00:00:00.000Z"},
    ]
    wm = sync.next_watermark(test_db, "projects", recs)
    assert wm == datetime(2026, 1, 5, tzinfo=timezone.utc)


def test_next_watermark_falls_back_to_previous(test_db):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sync.set_watermark(test_db, "projects", ts)
    test_db.commit()
    assert sync.next_watermark(test_db, "projects", []) == ts


def test_next_watermark_first_sync_returns_now(test_db):
    wm = sync.next_watermark(test_db, "projects", [])
    assert wm.tzinfo is not None


# --- schema validation (mocked Notion client) -------------------------------

def test_check_schema_ok(monkeypatch):
    fake = mock.MagicMock()
    fake.data_sources.retrieve.return_value = {"properties": {"Name": {}, "Status": {}}}
    monkeypatch.setattr(sync, "client", fake)
    monkeypatch.setitem(sync._DATA_SOURCE_IDS, "projects", "ds")
    sync.check_schema("projects")  # should not raise


def test_check_schema_missing_field(monkeypatch):
    fake = mock.MagicMock()
    fake.data_sources.retrieve.return_value = {"properties": {"Name": {}}}
    monkeypatch.setattr(sync, "client", fake)
    monkeypatch.setitem(sync._DATA_SOURCE_IDS, "projects", "ds")
    with pytest.raises(SchemaMismatchError) as ei:
        sync.check_schema("projects")
    assert any("MISSING" in i for i in ei.value.issues)


def test_check_schema_new_field(monkeypatch):
    fake = mock.MagicMock()
    fake.data_sources.retrieve.return_value = {
        "properties": {"Name": {}, "Status": {}, "Extra": {}}}
    monkeypatch.setattr(sync, "client", fake)
    monkeypatch.setitem(sync._DATA_SOURCE_IDS, "projects", "ds")
    with pytest.raises(SchemaMismatchError) as ei:
        sync.check_schema("projects")
    assert any("NEW" in i for i in ei.value.issues)


# --- data-source ID resolution ---------------------------------------------

def test_data_source_id_is_cached(monkeypatch):
    fake = mock.MagicMock()
    fake.databases.retrieve.return_value = {"data_sources": [{"id": "ds-real"}]}
    monkeypatch.setattr(sync, "client", fake)
    monkeypatch.setitem(sync._DATA_SOURCE_IDS, "tasks", "seed")  # pre-seeded

    assert sync._data_source_id("tasks") == "seed"
    fake.databases.retrieve.assert_not_called()

    # Unseeded key resolves via the client.
    del sync._DATA_SOURCE_IDS["tasks"]
    assert sync._data_source_id("tasks") == "ds-real"
    fake.databases.retrieve.assert_called_once()


# --- record fetching (mocked Notion client, pagination) --------------------

def test_fetch_all_records_paginates(monkeypatch):
    fake = mock.MagicMock()
    fake.data_sources.query.side_effect = [
        {"results": [{"id": "1"}], "has_more": True, "next_cursor": "c2"},
        {"results": [{"id": "2"}, {"id": "3"}], "has_more": False, "next_cursor": None},
    ]
    monkeypatch.setattr(sync, "client", fake)
    monkeypatch.setitem(sync._DATA_SOURCE_IDS, "tasks", "ds")

    recs = sync.fetch_all_records("tasks")
    assert [r["id"] for r in recs] == ["1", "2", "3"]

    calls = fake.data_sources.query.call_args_list
    assert calls[0].kwargs == {"data_source_id": "ds", "page_size": 100}
    assert calls[1].kwargs == {"data_source_id": "ds", "page_size": 100, "start_cursor": "c2"}


def test_fetch_all_records_applies_watermark_filter(monkeypatch):
    fake = mock.MagicMock()
    fake.data_sources.query.return_value = {"results": [], "has_more": False, "next_cursor": None}
    monkeypatch.setattr(sync, "client", fake)
    monkeypatch.setitem(sync._DATA_SOURCE_IDS, "tasks", "ds")

    sync.fetch_all_records("tasks", last_edited_after="2026-01-01T00:00:00.000Z")
    assert fake.data_sources.query.call_args.kwargs["filter"] == {
        "timestamp": "last_edited_time",
        "last_edited_time": {"after": "2026-01-01T00:00:00.000Z"},
    }


def test_fetch_all_ids_collects_set(monkeypatch):
    fake = mock.MagicMock()
    fake.data_sources.query.side_effect = [
        {"results": [{"id": "a"}, {"id": "b"}], "has_more": True, "next_cursor": "c"},
        {"results": [{"id": "c"}], "has_more": False, "next_cursor": None},
    ]
    monkeypatch.setattr(sync, "client", fake)
    monkeypatch.setitem(sync._DATA_SOURCE_IDS, "projects", "ds")

    assert sync.fetch_all_ids("projects") == {"a", "b", "c"}
