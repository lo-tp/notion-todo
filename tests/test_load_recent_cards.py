"""Unit tests for scripts/load_recent_cards.py."""

import sys
import uuid
from datetime import UTC, datetime
from unittest import mock

import load_recent_cards
import pytest


def _ctx(value):
    class _Ctx:
        def __enter__(self):
            return value

        def __exit__(self, *exc):
            return False

    return _Ctx()


def _point_connect_at(test_db, monkeypatch):
    monkeypatch.setattr(
        load_recent_cards.psycopg, "connect", mock.Mock(side_effect=lambda url: _ctx(test_db))
    )


def _insert(test_db, name, updated=None, deleted=False):
    cid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO tasks (id, name, notion_updated_at, deleted_at) "
        "VALUES (%s, %s, %s, %s)",
        (cid, name, updated, datetime.now(UTC) if deleted else None),
    )
    test_db.commit()
    return cid


def test_recent_titles_returns_most_recent_first(test_db, monkeypatch):
    _insert(test_db, "old", updated=datetime(2020, 1, 1, tzinfo=UTC))
    _insert(test_db, "new", updated=datetime(2024, 1, 1, tzinfo=UTC))
    _point_connect_at(test_db, monkeypatch)

    titles = load_recent_cards.recent_titles({"DATABASE_URL": "x"}, 20)

    assert [name for _, name in titles] == ["new", "old"]


def test_recent_titles_respects_limit(test_db, monkeypatch):
    for i in range(5):
        _insert(test_db, f"card-{i}", updated=datetime(2024, 1, 1 + i, tzinfo=UTC))
    _point_connect_at(test_db, monkeypatch)

    titles = load_recent_cards.recent_titles({"DATABASE_URL": "x"}, 3)

    assert len(titles) == 3
    # Most recent (card-4, card-3, card-2) come first.
    assert [name for _, name in titles] == ["card-4", "card-3", "card-2"]


def test_recent_titles_excludes_deleted(test_db, monkeypatch):
    _insert(test_db, "kept", updated=datetime(2024, 1, 5, tzinfo=UTC))
    _insert(test_db, "gone", updated=datetime(2025, 1, 1, tzinfo=UTC), deleted=True)
    _point_connect_at(test_db, monkeypatch)

    titles = load_recent_cards.recent_titles({"DATABASE_URL": "x"}, 20)

    assert [name for _, name in titles] == ["kept"]


def test_recent_titles_returns_id_and_name(test_db, monkeypatch):
    cid = _insert(test_db, "solo", updated=datetime(2024, 1, 1, tzinfo=UTC))
    _point_connect_at(test_db, monkeypatch)

    titles = load_recent_cards.recent_titles({"DATABASE_URL": "x"}, 20)

    assert titles == [(cid, "solo")]


# --- main ------------------------------------------------------------------


def test_main_missing_env_key_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["load_recent_cards.py"])
    monkeypatch.setattr(load_recent_cards, "load_env", lambda: {})
    with pytest.raises(SystemExit):
        load_recent_cards.main()


def test_main_prints_numbered_titles(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["load_recent_cards.py"])
    monkeypatch.setattr(
        load_recent_cards, "load_env", lambda: {"DATABASE_URL": "x"}
    )
    monkeypatch.setattr(
        load_recent_cards,
        "recent_titles",
        lambda env, limit: [("id-1", "breakfast"), ("id-2", "sleep")],
    )

    load_recent_cards.main()

    out = capsys.readouterr().out
    assert "1. breakfast  (id-1)" in out
    assert "2. sleep  (id-2)" in out


def test_main_uses_custom_limit(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["load_recent_cards.py", "5"])
    monkeypatch.setattr(load_recent_cards, "load_env", lambda: {"DATABASE_URL": "x"})
    captured = {}

    def _capture(env, limit):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(load_recent_cards, "recent_titles", _capture)

    load_recent_cards.main()

    assert captured["limit"] == 5


def test_main_uses_env_limit(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["load_recent_cards.py"])
    monkeypatch.setattr(
        load_recent_cards, "load_env", lambda: {"DATABASE_URL": "x", "RECENT_CARDS_LIMIT": "7"}
    )
    captured = {}

    def _capture(env, limit):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(load_recent_cards, "recent_titles", _capture)

    load_recent_cards.main()

    assert captured["limit"] == 7


def test_main_cli_overrides_env(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["load_recent_cards.py", "3"])
    monkeypatch.setattr(
        load_recent_cards, "load_env", lambda: {"DATABASE_URL": "x", "RECENT_CARDS_LIMIT": "7"}
    )
    captured = {}

    def _capture(env, limit):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(load_recent_cards, "recent_titles", _capture)

    load_recent_cards.main()

    assert captured["limit"] == 3


def test_main_defaults_when_no_env_key(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["load_recent_cards.py"])
    monkeypatch.setattr(load_recent_cards, "load_env", lambda: {"DATABASE_URL": "x"})
    captured = {}

    def _capture(env, limit):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(load_recent_cards, "recent_titles", _capture)

    load_recent_cards.main()

    assert captured["limit"] == 20
