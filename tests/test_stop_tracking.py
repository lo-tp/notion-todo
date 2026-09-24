"""Unit tests for scripts/stop_tracking.py.

Pure functions are tested directly. Database-touching helpers run against the
shared in-memory Postgres (see the ``test_db`` fixture) by pointing
``psycopg.connect`` at that connection. Notion calls are exercised by mocking
the module-level :class:`~notion_client.Client`.
"""

import uuid
from unittest import mock

import pytest
import stop_tracking


def _ctx(value):
    class _Ctx:
        def __enter__(self):
            return value

        def __exit__(self, *exc):
            return False

    return _Ctx()


def _point_connect_at(test_db, monkeypatch):
    """Make ``stop_tracking.psycopg.connect`` return the shared test connection.

    ``stop_tracking.psycopg`` and the top-level ``psycopg`` are the same object,
    so ``monkeypatch`` restores the real ``connect`` after each test.
    """
    monkeypatch.setattr(
        stop_tracking.psycopg, "connect", mock.Mock(side_effect=lambda url: _ctx(test_db))
    )


# --- load_env --------------------------------------------------------------


def test_load_env(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("NOTION_TOKEN=tok\n# a comment\nDATABASE_URL=postgresql+psycopg://h/db\n\n")
    monkeypatch.setattr(stop_tracking, "ENV_PATH", p)
    assert stop_tracking.load_env() == {
        "NOTION_TOKEN": "tok",
        "DATABASE_URL": "postgresql+psycopg://h/db",
    }


# --- db_url ----------------------------------------------------------------


def test_db_url_rewrites_driver_prefix():
    assert stop_tracking.db_url({"DATABASE_URL": "postgresql+psycopg://h/db"}) == "postgresql://h/db"


def test_db_url_leaves_plain_url_untouched():
    assert stop_tracking.db_url({"DATABASE_URL": "postgresql://h/db"}) == "postgresql://h/db"


# --- open_trackers ---------------------------------------------------------


def test_open_trackers_returns_only_open_rows(test_db, monkeypatch):
    task = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO tasks (id, name, notion_updated_at) VALUES (%s, 'open task', now())", (task,)
    )
    open_tt = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO time_tracking (id, name, task_id, start_time, notion_updated_at) "
        "VALUES (%s, 'open', %s, now(), now())",
        (open_tt, task),
    )
    # A closed tracker (end_time set) must be excluded.
    closed_task = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO tasks (id, name, notion_updated_at) VALUES (%s, 'done task', now())",
        (closed_task,),
    )
    closed_tt = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO time_tracking (id, name, task_id, start_time, end_time, notion_updated_at) "
        "VALUES (%s, 'closed', %s, now(), now(), now())",
        (closed_tt, closed_task),
    )
    test_db.commit()

    _point_connect_at(test_db, monkeypatch)

    rows = stop_tracking.open_trackers({"DATABASE_URL": "x"})
    assert rows == [(open_tt, "open task")]


def test_open_trackers_orders_by_start_time(test_db, monkeypatch):
    task = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO tasks (id, name, notion_updated_at) VALUES (%s, 't', now())", (task,)
    )
    first = str(uuid.uuid4())
    second = str(uuid.uuid4())
    # Inserted out of order; start_time decides the order.
    test_db.execute(
        "INSERT INTO time_tracking (id, task_id, start_time, notion_updated_at) "
        "VALUES (%s, %s, '2026-01-02T00:00:00Z', now())",
        (second, task),
    )
    test_db.execute(
        "INSERT INTO time_tracking (id, task_id, start_time, notion_updated_at) "
        "VALUES (%s, %s, '2026-01-01T00:00:00Z', now())",
        (first, task),
    )
    test_db.commit()

    _point_connect_at(test_db, monkeypatch)

    rows = stop_tracking.open_trackers({"DATABASE_URL": "x"})
    assert [row[0] for row in rows] == [first, second]


def test_open_trackers_empty(test_db, monkeypatch):
    _point_connect_at(test_db, monkeypatch)
    assert stop_tracking.open_trackers({"DATABASE_URL": "x"}) == []


# --- stop_all_running ------------------------------------------------------


def test_stop_all_running_updates_each_and_returns_ids(monkeypatch):
    mock_client = mock.MagicMock()
    monkeypatch.setattr(stop_tracking, "Client", lambda **k: mock_client)
    monkeypatch.setattr(stop_tracking, "open_trackers", lambda env: [("a", "Task A"), ("b", None)])

    stopped = stop_tracking.stop_all_running({"NOTION_TOKEN": "tok"})

    assert stopped == ["a", "b"]
    assert mock_client.pages.update.call_count == 2
    mock_client.close.assert_called_once()


def test_stop_all_running_sets_end_time_and_status(monkeypatch):
    mock_client = mock.MagicMock()
    monkeypatch.setattr(stop_tracking, "Client", lambda **k: mock_client)
    monkeypatch.setattr(stop_tracking, "open_trackers", lambda env: [("a", "Task A")])

    stop_tracking.stop_all_running({"NOTION_TOKEN": "tok"})

    call = mock_client.pages.update.call_args
    assert call.kwargs["page_id"] == "a"
    props = call.kwargs["properties"]
    assert props["Status"] == {"select": {"name": "Stopped"}}
    assert "start" in props["End Time"]["date"]


def test_stop_all_running_is_empty_when_nothing_open(monkeypatch):
    mock_client = mock.MagicMock()
    monkeypatch.setattr(stop_tracking, "Client", lambda **k: mock_client)
    monkeypatch.setattr(stop_tracking, "open_trackers", lambda env: [])

    assert stop_tracking.stop_all_running({"NOTION_TOKEN": "tok"}) == []
    mock_client.pages.update.assert_not_called()


# --- main ------------------------------------------------------------------


def test_main_missing_token_exits(monkeypatch):
    monkeypatch.setattr(stop_tracking, "load_env", lambda: {"DATABASE_URL": "x"})
    with pytest.raises(SystemExit):
        stop_tracking.main()


def test_main_nothing_open_prints_message(monkeypatch, capsys):
    monkeypatch.setattr(stop_tracking, "load_env", lambda: {"NOTION_TOKEN": "tok"})
    monkeypatch.setattr(stop_tracking, "stop_all_running", lambda env: [])
    stop_tracking.main()
    assert "No open" in capsys.readouterr().out


def test_main_stops_and_prints(monkeypatch, capsys):
    monkeypatch.setattr(stop_tracking, "load_env", lambda: {"NOTION_TOKEN": "tok"})
    monkeypatch.setattr(stop_tracking, "stop_all_running", lambda env: ["a", "b"])
    stop_tracking.main()
    assert "Stopped 2 tracker(s)" in capsys.readouterr().out
