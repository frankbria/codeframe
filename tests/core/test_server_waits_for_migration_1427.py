"""A server starting mid-migration waits for it and opens platform.db (#1427).

`migrate_legacy_control_plane` refuses a state.db a server already has open,
but its check ran once: a `cf serve` that opened state.db after the check and
before the move wrote accounts into the file being moved aside, and the next
start preferred platform.db without them. The migration lock only serialised
`cf init` processes; the server's first open now takes it too.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from codeframe.platform_store import database as db_mod
from tests.core.test_legacy_control_plane_migration_1376 import _emails, _legacy_control_plane

pytestmark = pytest.mark.v2


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_a_server_starting_mid_migration_waits_and_opens_platform_db(repo, monkeypatch):
    _legacy_control_plane(repo)
    checked, release = threading.Event(), threading.Event()
    real_check = db_mod._refuse_unsafe_move

    def check_then_pause(state_dir, legacy):
        real_check(state_dir, legacy)
        checked.set()      # the window: checks passed, nothing moved yet
        release.wait(10)

    monkeypatch.setattr(db_mod, "_refuse_unsafe_move", check_then_pause)
    migration = threading.Thread(target=db_mod.migrate_legacy_control_plane, args=(repo / ".codeframe",))
    migration.start()
    assert checked.wait(10)

    opened = {}
    server = threading.Thread(target=lambda: opened.setdefault("db", db_mod.open_control_plane_db()))
    server.start()
    server.join(0.5)
    assert server.is_alive(), "the server opened the DB while the migration was mid-move"

    release.set()
    migration.join(10)
    server.join(10)
    db = opened["db"]
    try:
        assert db.db_path == repo / ".codeframe" / "platform.db"
        assert _emails(db.db_path) == ["op@x.co"]
    finally:
        db.close()


def test_without_a_legacy_state_db_no_lock_file_is_created(repo):
    """A normal start pays nothing and leaves nothing behind."""
    db = db_mod.open_control_plane_db()
    db.close()
    assert not (repo / ".codeframe" / ".control-plane-migration.lock").exists()


def test_database_path_is_opened_as_given(repo, monkeypatch):
    target = repo / "elsewhere.db"
    monkeypatch.setenv("DATABASE_PATH", str(target))
    db = db_mod.open_control_plane_db()
    db.close()
    assert db.db_path == target
    tables = {r[0] for r in sqlite3.connect(target).execute("SELECT name FROM sqlite_master")}
    assert "users" in tables  # the control-plane schema, at the given path


def _lock_calls(monkeypatch) -> list:
    """Every acquisition of the migration lock. Not the lock file: filelock
    deletes it on release, so its absence proves nothing (review)."""
    from codeframe.core import atomic_io

    calls: list = []
    real = atomic_io.read_modify_write_lock
    monkeypatch.setattr(atomic_io, "read_modify_write_lock", lambda p: calls.append(p) or real(p))
    return calls


@pytest.mark.parametrize("kind", ["workspace", "shared"])
def test_a_state_db_that_can_never_be_moved_takes_no_lock(repo, monkeypatch, kind):
    """Every `cf init`ed workspace keeps its domain DB in state.db, and a
    "shared" legacy file (accounts plus a workspace) is never moved; neither
    can race a migration, so a serve there must not take the lock (review)."""
    from codeframe.core.workspace import create_or_load_workspace

    create_or_load_workspace(repo)
    if kind == "shared":
        shared = db_mod.Database(repo / ".codeframe" / "state.db")
        shared.initialize()
        shared.conn.execute(
            "INSERT INTO users (id, email, name, hashed_password, is_active, is_superuser, is_verified, email_verified) "
            "VALUES (7, 'op@x.co', 'Op', 'real', 1, 1, 1, 1)"
        )
        shared.conn.commit()
        shared.close()
        assert db_mod._legacy_kind(repo / ".codeframe" / "state.db") == "shared"
    calls = _lock_calls(monkeypatch)

    db_mod.open_control_plane_db().close()

    assert calls == []


def test_a_legacy_control_plane_state_db_does_take_the_lock(repo, monkeypatch):
    _legacy_control_plane(repo)
    calls = _lock_calls(monkeypatch)

    db_mod.open_control_plane_db().close()

    assert calls == [repo / ".codeframe" / ".control-plane-migration.lock"]
