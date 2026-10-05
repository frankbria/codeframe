"""`cf init` migrates a serve-first legacy state.db to platform.db (#1376).

Before #1287, `cf serve` with no DATABASE_PATH wrote the control plane
(accounts, API keys) into `.codeframe/state.db`, the workspace's own file.
#1287 keeps such an install on state.db and warns, but `cf init` there still
failed with "Workspace database exists but contains no workspace record" until
the operator renamed the file by hand. Init now does that move itself, once,
consistently (sqlite backup, WAL included), and the accounts stay reachable.
"""

import re
import sqlite3

import pytest

from codeframe.core.workspace import create_or_load_workspace
from codeframe.platform_store.database import Database, default_database_path

pytestmark = pytest.mark.v2

REAL_HASH = "$argon2id$v=19$m=65536,t=3,p=4$real"


def _legacy_control_plane(repo):
    """What the old default left behind: the control plane in state.db."""
    state = repo / ".codeframe" / "state.db"
    state.parent.mkdir(parents=True)
    db = Database(state)
    db.initialize()
    db.conn.execute(
        "INSERT INTO users (id, email, name, hashed_password, is_active, is_superuser, is_verified, email_verified) "
        "VALUES (7, 'op@x.co', 'Op', ?, 1, 1, 1, 1)",
        (REAL_HASH,),
    )
    db.conn.commit()
    db.close()
    return state


def _emails(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT email FROM users WHERE hashed_password = ?", (REAL_HASH,))]
    finally:
        conn.close()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_init_after_an_old_default_serve_succeeds_and_keeps_the_accounts(repo):
    _legacy_control_plane(repo)

    ws = create_or_load_workspace(repo)  # raised "contains no workspace record"

    platform = repo / ".codeframe" / "platform.db"
    assert _emails(platform) == ["op@x.co"]
    assert default_database_path() == str(platform)  # the server now finds them
    assert ws.db_path == repo / ".codeframe" / "state.db"
    assert (repo / ".codeframe" / "state.db.pre-1287").exists()  # the original, kept


def test_wal_only_data_left_by_a_crash_survives_the_move(repo):
    """A server that died mid-flight leaves rows only in the -wal; a file copy
    would miss them, the backup does not."""
    import subprocess as sp
    import sys
    import textwrap

    state = _legacy_control_plane(repo)
    sp.run([sys.executable, "-c", textwrap.dedent(f"""
        import os, sqlite3
        c = sqlite3.connect({str(state)!r})
        c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA wal_autocheckpoint=0")
        c.execute("INSERT INTO users (id,email,name,hashed_password,is_active,is_superuser,is_verified,email_verified) "
                  "VALUES (8,'late@x.co','Late',{REAL_HASH!r},1,0,1,1)")
        c.commit()
        os._exit(0)  # no close: the row stays in state.db-wal
    """)], check=True)
    assert (state.parent / "state.db-wal").exists()

    create_or_load_workspace(repo)

    assert sorted(_emails(repo / ".codeframe" / "platform.db")) == ["late@x.co", "op@x.co"]


def test_a_db_still_open_by_a_server_is_not_moved(repo):
    """A copy taken while a server writes would lose its later writes (codex)."""
    from codeframe.platform_store.database import LegacyControlPlaneError

    state = _legacy_control_plane(repo)
    live = sqlite3.connect(state)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("SELECT 1").fetchone()
    try:
        with pytest.raises(LegacyControlPlaneError, match="Stop it"):
            create_or_load_workspace(repo)
    finally:
        live.close()
    assert not (repo / ".codeframe" / "platform.db").exists()
    assert _emails(state) == ["op@x.co"]


def test_an_explicit_database_path_to_the_legacy_file_is_not_moved(repo, monkeypatch):
    """The server would restart on DATABASE_PATH, now a workspace DB (codex)."""
    from codeframe.platform_store.database import LegacyControlPlaneError

    state = _legacy_control_plane(repo)
    monkeypatch.setenv("DATABASE_PATH", str(state))
    with pytest.raises(LegacyControlPlaneError, match="DATABASE_PATH"):
        create_or_load_workspace(repo)
    assert _emails(state) == ["op@x.co"]
    assert not (repo / ".codeframe" / "platform.db").exists()


def test_an_existing_platform_db_is_never_overwritten(repo):
    _legacy_control_plane(repo)
    platform = repo / ".codeframe" / "platform.db"
    platform.write_bytes(b"")  # someone already set one up

    with pytest.raises(FileNotFoundError, match="no workspace record"):
        create_or_load_workspace(repo)
    assert platform.read_bytes() == b""


def test_a_workspace_db_is_left_alone(repo):
    ws = create_or_load_workspace(repo)
    again = create_or_load_workspace(repo)
    assert again.id == ws.id
    assert not (repo / ".codeframe" / "platform.db").exists()


def test_cf_init_reports_a_new_workspace_not_an_existing_one(repo):
    """The file existed, but no workspace did: say 'Initialized', not 'already'."""
    import subprocess as sp

    from typer.testing import CliRunner

    from codeframe.cli.app import app

    _legacy_control_plane(repo)
    sp.run(["git", "init", "-q"], cwd=repo, check=True)

    result = CliRunner().invoke(app, ["init", str(repo)])

    assert result.exit_code == 0, result.output
    assert "already initialized" not in result.output.lower(), result.output


def test_concurrent_migrations_move_the_file_once(repo):
    """Two inits racing must not replace each other's platform.db or the
    preserved original (codex review)."""
    from concurrent.futures import ThreadPoolExecutor

    from codeframe.platform_store.database import migrate_legacy_control_plane

    _legacy_control_plane(repo)
    state_dir = repo / ".codeframe"
    with ThreadPoolExecutor(max_workers=4) as pool:
        moved = list(pool.map(lambda _: migrate_legacy_control_plane(state_dir), range(4)))

    assert moved.count(True) == 1, moved
    assert _emails(state_dir / "platform.db") == ["op@x.co"]
    assert _emails(state_dir / "state.db.pre-1287") == ["op@x.co"]


def test_the_copy_keeps_the_original_permissions(repo):
    """Password hashes in a 0600 file must not land in a 0644 one (codex)."""
    import os
    import stat

    state = _legacy_control_plane(repo)
    os.chmod(state, 0o600)
    old = os.umask(0o022)
    try:
        create_or_load_workspace(repo)
    finally:
        os.umask(old)

    assert stat.S_IMODE(os.stat(repo / ".codeframe" / "platform.db").st_mode) == 0o600


def test_a_migration_interrupted_after_publishing_completes_on_retry(repo, monkeypatch):
    """Dying between publishing platform.db and moving state.db aside left a
    state no later init could leave (codex review)."""
    import os

    from codeframe.platform_store import database as db_mod

    _legacy_control_plane(repo)
    real_replace = os.replace

    def fail_moving_aside(src, dst, *a, **k):
        if str(dst).endswith(".pre-1287"):
            raise OSError("disk went away")
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(db_mod.os, "replace", fail_moving_aside)
    with pytest.raises(OSError):
        create_or_load_workspace(repo)
    assert (repo / ".codeframe" / "platform.db").exists()  # published, then stuck
    with pytest.raises(OSError):  # the first retry fails the same way (codex)
        create_or_load_workspace(repo)

    monkeypatch.setattr(db_mod.os, "replace", real_replace)
    ws = create_or_load_workspace(repo)  # the retry finishes the job

    assert ws.db_path.exists()
    assert _emails(repo / ".codeframe" / "platform.db") == ["op@x.co"]
    assert _emails(repo / ".codeframe" / "state.db.pre-1287") == ["op@x.co"]


def test_resuming_an_interrupted_migration_keeps_the_safety_checks(repo, monkeypatch):
    """DATABASE_PATH set between attempts must still stop the move (codex)."""
    import os

    from codeframe.platform_store import database as db_mod
    from codeframe.platform_store.database import LegacyControlPlaneError

    state = _legacy_control_plane(repo)
    real_replace = os.replace
    monkeypatch.setattr(
        db_mod.os, "replace",
        lambda s, d, *a, **k: (_ for _ in ()).throw(OSError("x")) if str(d).endswith(".pre-1287")
        else real_replace(s, d, *a, **k),
    )
    with pytest.raises(OSError):
        create_or_load_workspace(repo)
    monkeypatch.setattr(db_mod.os, "replace", real_replace)

    monkeypatch.setenv("DATABASE_PATH", str(state))
    with pytest.raises(LegacyControlPlaneError, match="DATABASE_PATH"):
        create_or_load_workspace(repo)
    assert _emails(state) == ["op@x.co"]  # still where DATABASE_PATH says


def test_a_failed_copy_leaves_no_temp_file_and_a_retry_succeeds(repo, monkeypatch):
    """A leftover copy of the accounts blocked the next attempt (codex)."""
    from codeframe.platform_store import database as db_mod

    _legacy_control_plane(repo)
    real_connect = sqlite3.connect
    calls = {"n": 0}

    def flaky_connect(path, *a, **k):
        if str(path).endswith(".tmp") and calls["n"] == 0:
            calls["n"] += 1
            raise sqlite3.OperationalError("disk I/O error")
        return real_connect(path, *a, **k)

    monkeypatch.setattr(db_mod.sqlite3, "connect", flaky_connect)
    with pytest.raises(sqlite3.OperationalError):
        create_or_load_workspace(repo)
    assert not list((repo / ".codeframe").glob("*.tmp"))

    create_or_load_workspace(repo)
    assert _emails(repo / ".codeframe" / "platform.db") == ["op@x.co"]


def test_the_marker_is_durable_before_platform_db_is_published(repo, monkeypatch):
    """A power loss must not keep platform.db and lose the marker (codex): the
    directory is fsynced with the marker in it before publication."""
    from codeframe.core import atomic_io

    _legacy_control_plane(repo)
    state_dir = repo / ".codeframe"
    synced_with_marker_before_publish = []
    real = atomic_io.fsync_directory

    def spy(path):
        if (state_dir / ".control-plane-migration.pending").exists() and not (state_dir / "platform.db").exists():
            synced_with_marker_before_publish.append(path)
        real(path)

    monkeypatch.setattr(atomic_io, "fsync_directory", spy)
    create_or_load_workspace(repo)

    assert synced_with_marker_before_publish == [state_dir]


def _schema_of(db_path):
    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    return version, tables


def _stale_and_stamped(repo):
    """A pre-#655 control plane (interactive_sessions without user_id) that
    main's failing ``cf init`` has already stamped with the workspace
    user_version, as every real #1376 directory is by the time it upgrades."""
    state = _legacy_control_plane(repo)
    conn = sqlite3.connect(state)
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'interactive_sessions'"
    ).fetchone()[0]
    conn.execute("DROP TABLE interactive_sessions")
    conn.execute(re.sub(r",\s*(--[^\n]*\n\s*)*user_id[^\n]*", "", ddl))  # pre-#655
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()
    return state


def _columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


@pytest.mark.parametrize("via", ["core", "cli"])
def test_the_migrated_db_still_gets_its_control_plane_migrations(repo, via):
    """A copy that kept the workspace user_version made SchemaManager skip
    every control-plane migration at or below it, forever (GLM review)."""
    import subprocess as sp

    from typer.testing import CliRunner

    from codeframe.cli.app import app
    from codeframe.platform_store.schema_manager import SchemaManager

    _stale_and_stamped(repo)
    if via == "core":
        create_or_load_workspace(repo)
    else:
        sp.run(["git", "init", "-q"], cwd=repo, check=True)
        assert CliRunner().invoke(app, ["init", str(repo)]).exit_code == 0

    platform = repo / ".codeframe" / "platform.db"
    db = Database(platform)
    db.initialize()  # what the server does on start
    db.close()

    assert "user_id" in _columns(platform, "interactive_sessions")
    assert _schema_of(platform)[0] == SchemaManager.SCHEMA_VERSION


def test_loading_a_control_plane_db_as_a_workspace_does_not_stamp_it(repo):
    """The v2 init route and the per-request cwd fallback call get_workspace on
    the legacy file directly; that must not write the workspace schema into it."""
    from codeframe.core.workspace import get_workspace

    state = _legacy_control_plane(repo)
    before = _schema_of(state)

    with pytest.raises(FileNotFoundError, match="no workspace record"):
        get_workspace(repo)

    assert _schema_of(state) == before


def test_a_relative_database_path_is_refused_from_another_cwd(repo, tmp_path_factory, monkeypatch):
    """The server resolves a relative DATABASE_PATH against its own cwd, the
    repo root; init run from elsewhere must still see it names this file (GLM)."""
    from codeframe.platform_store.database import LegacyControlPlaneError

    state = _legacy_control_plane(repo)
    monkeypatch.setenv("DATABASE_PATH", ".codeframe/state.db")
    monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))

    with pytest.raises(LegacyControlPlaneError, match="DATABASE_PATH"):
        create_or_load_workspace(repo)
    assert _emails(state) == ["op@x.co"]
