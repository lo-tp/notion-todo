"""Shared pytest fixtures for the notion-sync test suite.

- Puts ``sync/`` and ``scripts/`` on the import path so their modules can be
  imported directly.
- Provides :func:`test_db`, a temporary SQLite database (fresh per test) with
  the project schema applied.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _sub in ("sync", "scripts"):
    _p = str(ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_SCHEMA = (ROOT / "sync" / "schema.sql").read_text()


@pytest.fixture
def test_db(tmp_path):
    """Yield a SQLite connection with the mirror schema applied, fresh per test."""
    conn = sqlite3.connect(tmp_path / "mirror.sqlite")
    conn.executescript(_SCHEMA)
    yield conn
    conn.close()
