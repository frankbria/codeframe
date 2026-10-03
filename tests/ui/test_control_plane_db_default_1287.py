"""The server's control-plane DB no longer defaults to the workspace DB (#1287).

``DATABASE_PATH`` used to default to ``<cwd>/.codeframe/state.db`` — the very
file ``create_or_load_workspace`` owns. Serve-then-init left a ``state.db`` with
no workspace row, so ``cf init`` refused it and the only recovery deleted the
operator's accounts too; init-then-serve wrote users and api_keys into the
repo's domain DB, and the two schemas' ``user_version`` stamps collided.
"""

import logging
import sqlite3
import subprocess

import pytest

pytestmark = pytest.mark.v2


def _tables(db_path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _serve(repo):
    from fastapi.testclient import TestClient

    from codeframe.ui.server import app

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_serve_then_init_in_the_same_directory(repo):
    from codeframe.core.workspace import create_or_load_workspace

    _serve(repo)
    create_or_load_workspace(repo)  # raised "contains no workspace record"

    assert "users" not in _tables(repo / ".codeframe" / "state.db")
    assert "users" in _tables(repo / ".codeframe" / "platform.db")


def test_init_then_serve_leaves_the_workspace_db_alone(repo):
    from codeframe.core.workspace import create_or_load_workspace

    create_or_load_workspace(repo)
    _serve(repo)

    assert "users" not in _tables(repo / ".codeframe" / "state.db")


def test_every_default_site_resolves_the_same_path(repo):
    from codeframe.auth.manager import _get_database_path
    from codeframe.cli.auth_commands import get_db_for_cli
    from codeframe.platform_store.database import default_database_path

    expected = str(repo / ".codeframe" / "platform.db")
    assert default_database_path() == expected
    assert _get_database_path() == expected
    get_db_for_cli().close()
    assert (repo / ".codeframe" / "platform.db").is_file()
    assert not (repo / ".codeframe" / "state.db").exists()


def test_database_path_still_wins(repo, monkeypatch):
    from codeframe.platform_store.database import default_database_path

    monkeypatch.setenv("DATABASE_PATH", str(repo / "elsewhere.db"))
    assert default_database_path() == str(repo / "elsewhere.db")


def test_a_legacy_install_keeps_its_accounts(repo, caplog):
    """Accounts already in ``state.db`` stay reachable, with a warning."""
    from codeframe.platform_store.database import default_database_path

    legacy = repo / ".codeframe" / "state.db"
    legacy.parent.mkdir()
    sqlite3.connect(legacy).execute("CREATE TABLE users (id INTEGER)").connection.commit()

    with caplog.at_level(logging.WARNING):
        assert default_database_path() == str(legacy)
    assert "DATABASE_PATH" in caplog.text


def test_a_workspace_db_without_accounts_is_not_legacy(repo):
    from codeframe.core.workspace import create_or_load_workspace
    from codeframe.platform_store.database import default_database_path

    create_or_load_workspace(repo)
    assert default_database_path() == str(repo / ".codeframe" / "platform.db")


def test_only_the_resolver_supplies_a_database_path_fallback():
    """Five sites each carried their own copy of the old default; one hid from a
    plain grep because the path was split across ``os.path.join`` arguments.
    Reading ``DATABASE_PATH`` with no fallback is fine (``cf stats``, API-key
    auth); supplying a fallback anywhere but the resolver is not."""
    import re
    from pathlib import Path

    with_fallback = re.compile(r"""(getenv|environ\.get)\(\s*["']DATABASE_PATH["']\s*,""")
    sites = sorted(
        str(p)
        for p in Path("codeframe").rglob("*.py")
        if with_fallback.search(p.read_text())
    )
    assert sites == []
