"""#1283: auto-close and reconciliation never found the PAT connected in the web UI.

Integrations → Connect stores the PAT in the connecting user's own credential
store (#790), and since #963 every principal has a user_id, even with auth off.
Auto-close and reconciliation run with no request, so they read only the
machine-wide store. They found nothing, logged at INFO and did nothing. The
advertised "Close GitHub issue when task is DONE" never worked for a
web-connected repo unless GITHUB_TOKEN was exported as well.

The connect route now records the owning user_id beside the repo (non-secret),
and both background paths resolve that user's PAT before falling back.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import credentials as creds_mod
from codeframe.core import tasks
from codeframe.core.credentials import CredentialManager, CredentialProvider, CredentialStore
from codeframe.core.github_integration_config import (
    clear_github_integration_config,
    connection_owner,
    record_connection_owner,
    resolve_background_pat,
    save_github_integration_config,
)
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

OWNER_PAT = "ghp_owner_connected_in_the_ui_fake_0000"
MACHINE_PAT = "ghp_machine_wide_fake_0000"
OWNER = 7


@pytest.fixture
def ws(tmp_path, monkeypatch):
    # Isolated credential store: no keyring, no ~/.codeframe, no ambient token.
    monkeypatch.setattr(creds_mod, "DEFAULT_STORAGE_DIR", tmp_path / "creds")
    monkeypatch.setattr(CredentialStore, "_check_keyring", lambda self: False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


def _store(user_id, pat):
    CredentialManager(user_id=user_id, migrate=False).set_credential(
        CredentialProvider.GIT_GITHUB, pat
    )


def _connect_config(ws, owner=OWNER):
    save_github_integration_config(ws, {"repo": "acme/app", "owner_login": "acme", "owner_avatar_url": ""})
    record_connection_owner(ws, owner)


class TestTheResolver:
    def test_the_owner_is_recorded_and_forgotten_on_disconnect(self, ws):
        _connect_config(ws)
        assert connection_owner(ws) == OWNER
        clear_github_integration_config(ws)
        assert connection_owner(ws) is None

    def test_an_owner_forged_in_the_workspace_is_ignored(self, ws, tmp_path):
        """`.codeframe/` is writable by whatever runs in the workspace; an owner
        id written there must not unlock another account's PAT (codex P1)."""
        import json

        _store(99, "ghp_victim_fake_0000")
        save_github_integration_config(ws, {"repo": "acme/app", "owner_login": "acme", "owner_avatar_url": ""})
        cfg = ws.state_dir / "github_integration.json"
        cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "owner_user_id": 99}))

        assert resolve_background_pat(ws) is None

    def test_the_owners_pat_is_used(self, ws):
        _connect_config(ws)
        _store(OWNER, OWNER_PAT)
        _store(None, MACHINE_PAT)
        assert resolve_background_pat(ws) == OWNER_PAT

    def test_the_owners_pat_beats_an_ambient_github_token(self, ws, monkeypatch):
        """The operator's environment must not act on the user's behalf (#900)."""
        _connect_config(ws)
        _store(OWNER, OWNER_PAT)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_operator_env_fake")
        assert resolve_background_pat(ws) == OWNER_PAT

    def test_an_unreadable_owner_store_still_falls_back(self, ws, monkeypatch):
        """One broken per-user store must not disable the machine-wide path."""
        _connect_config(ws)
        _store(None, MACHINE_PAT)
        real = creds_mod.CredentialManager

        def manager(*args, user_id=None, **kwargs):
            if user_id == OWNER:
                raise creds_mod.CredentialStoreUnreadableError("corrupt users/7 store")
            return real(*args, user_id=user_id, **kwargs)

        monkeypatch.setattr(creds_mod, "CredentialManager", manager)
        assert resolve_background_pat(ws) == MACHINE_PAT

    def test_hosted_mode_never_uses_the_operators_github_token(self, ws, monkeypatch):
        """No connection of the user's own: the operator's env is not theirs (#900)."""
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_operator_env_fake")
        assert resolve_background_pat(ws) is None

    def test_self_hosted_still_falls_back_to_github_token(self, ws, monkeypatch):
        monkeypatch.delenv("CODEFRAME_DEPLOYMENT_MODE", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_operator_env_fake")
        assert resolve_background_pat(ws) == "ghp_operator_env_fake"

    def test_falls_back_to_the_machine_wide_store(self, ws):
        _connect_config(ws)  # the owner has no stored PAT
        _store(None, MACHINE_PAT)
        assert resolve_background_pat(ws) == MACHINE_PAT

    def test_no_connection_uses_the_machine_wide_store(self, ws):
        _store(None, MACHINE_PAT)
        assert resolve_background_pat(ws) == MACHINE_PAT


class TestBackgroundPaths:
    def test_auto_close_uses_the_owners_pat(self, ws, monkeypatch):
        _connect_config(ws)
        _store(OWNER, OWNER_PAT)
        closed: list = []
        monkeypatch.setattr(tasks, "_close_issue_background", lambda *a: closed.append(a))
        task = tasks.create(
            ws, title="Imported", status=TaskStatus.IN_PROGRESS, github_issue_number=99,
            external_url="https://github.com/acme/app/issues/99", auto_close_github_issue=True,
        )

        tasks.update_status(ws, task.id, TaskStatus.DONE)

        assert closed == [(OWNER_PAT, "acme/app", 99)]

    def test_reconciliation_uses_the_owners_pat(self, ws):
        from codeframe.core.reconciliation import GitHubIssueState

        _connect_config(ws)
        _store(OWNER, OWNER_PAT)
        seen: list = []
        state = GitHubIssueState(workspace=ws, fetch=lambda pat, repo, n: seen.append(pat) or "open")
        task = tasks.create(
            ws, title="Imported", status=TaskStatus.READY, github_issue_number=5,
            external_url="https://github.com/acme/app/issues/5",
        )

        state.is_closed(task)

        assert seen == [OWNER_PAT]


class TestThroughTheRouterWithAuthOn:
    def test_connect_then_done_attempts_the_close(self, ws, monkeypatch):
        """End to end, as the issue asks: a real per-user principal connects in
        the UI, and completing an imported task attempts the close."""
        from codeframe.auth.dependencies import require_auth
        from codeframe.ui.dependencies import get_v2_workspace
        from codeframe.ui.routers import github_integrations_v2

        async def valid(pat, repo, **kwargs):
            return {"repo_full_name": repo, "owner_login": "acme", "owner_avatar_url": ""}

        monkeypatch.setattr(github_integrations_v2, "validate_connection", valid)
        app = FastAPI()
        app.include_router(github_integrations_v2.router)
        app.dependency_overrides[get_v2_workspace] = lambda: ws
        app.dependency_overrides[require_auth] = lambda: {
            "user_id": OWNER, "scopes": ["read", "write", "admin"], "auth_type": "jwt",
        }

        r = TestClient(app).post(
            "/api/v2/integrations/github/connect", json={"pat": OWNER_PAT, "repo": "acme/app"}
        )
        assert r.status_code == 200, r.text

        closed: list = []
        monkeypatch.setattr(tasks, "_close_issue_background", lambda *a: closed.append(a))
        task = tasks.create(
            ws, title="Imported", status=TaskStatus.IN_PROGRESS, github_issue_number=99,
            external_url="https://github.com/acme/app/issues/99", auto_close_github_issue=True,
        )
        tasks.update_status(ws, task.id, TaskStatus.DONE)

        assert closed == [(OWNER_PAT, "acme/app", 99)]


class TestOwnerMapPersistence:
    """codex re-review: lost updates across workers, incomplete rollback, and a
    Unix-only permission call."""

    def test_concurrent_processes_do_not_lose_owners(self, tmp_path):
        import subprocess
        import sys
        import textwrap

        home = tmp_path / "home"
        home.mkdir()
        script = tmp_path / "writer.py"
        script.write_text(textwrap.dedent("""
            import sys
            from pathlib import Path
            from types import SimpleNamespace
            from codeframe.core.github_integration_config import record_connection_owner
            worker = int(sys.argv[1])
            for i in range(15):
                ws = SimpleNamespace(repo_path=Path(sys.argv[2]) / f"w{worker}-{i}")
                record_connection_owner(ws, worker * 100 + i)
        """))
        env = {**__import__("os").environ, "HOME": str(home)}
        procs = [
            subprocess.Popen([sys.executable, str(script), str(w), str(tmp_path)], env=env)
            for w in range(8)
        ]
        for p in procs:
            assert p.wait(timeout=120) == 0

        import json

        owners = json.loads((home / ".codeframe" / "github_connection_owners.json").read_text())
        assert len(owners) == 8 * 15, "a concurrent writer dropped another's entry"

    def test_recording_works_without_fchmod(self, ws, monkeypatch):
        import os

        monkeypatch.delattr(os, "fchmod", raising=False)
        record_connection_owner(ws, OWNER)
        assert connection_owner(ws) == OWNER
        owners = creds_mod.DEFAULT_STORAGE_DIR / "github_connection_owners.json"
        if os.name == "posix":  # private to the operator, as the credential store is
            assert owners.stat().st_mode & 0o777 == 0o600

    def test_concurrent_connects_never_cross_a_repo_with_another_owner(self, ws, monkeypatch):
        """GLM review: the config and the owner were written separately, so a
        connect landing between them left one admin's repo with the other's
        PAT. Deterministic: connect B is fired right after A saves its repo."""
        import threading

        from codeframe.core import github_integration_config as gic

        real_save = gic.save_github_integration_config
        fired = {"done": False}
        b_thread: list = []

        def save_then_race(workspace, config):
            saved = real_save(workspace, config)
            if not fired["done"]:
                fired["done"] = True
                t = threading.Thread(target=gic.save_connection, args=(
                    ws, {"repo": "acme/r2", "owner_login": "acme", "owner_avatar_url": ""}, 2,
                ))
                t.start()
                t.join(timeout=1.0)  # with the lock B waits for A; without it, B finishes here
                b_thread.append(t)
            return saved

        monkeypatch.setattr(gic, "save_github_integration_config", save_then_race)
        gic.save_connection(ws, {"repo": "acme/r1", "owner_login": "acme", "owner_avatar_url": ""}, 1)
        b_thread[0].join(timeout=30)

        repo = gic.load_github_integration_config(ws)["repo"]
        assert repo == f"acme/r{connection_owner(ws)}", "a repo was paired with another admin"

    def test_a_failed_owner_record_restores_the_previous_repo(self, ws, monkeypatch):
        from codeframe.auth.dependencies import require_auth
        from codeframe.core.github_integration_config import load_github_integration_config
        from codeframe.ui.dependencies import get_v2_workspace
        from codeframe.ui.routers import github_integrations_v2

        save_github_integration_config(ws, {"repo": "acme/old", "owner_login": "acme", "owner_avatar_url": ""})

        async def valid(pat, repo, **kwargs):
            return {"repo_full_name": repo, "owner_login": "acme", "owner_avatar_url": ""}

        def broken(*a, **k):
            raise OSError("disk full")

        from codeframe.core import github_integration_config as gic

        monkeypatch.setattr(github_integrations_v2, "validate_connection", valid)
        monkeypatch.setattr(gic, "_write_owner", broken)  # after the repo is saved
        app = FastAPI()
        app.include_router(github_integrations_v2.router)
        app.dependency_overrides[get_v2_workspace] = lambda: ws
        app.dependency_overrides[require_auth] = lambda: {
            "user_id": OWNER, "scopes": ["read", "write", "admin"], "auth_type": "jwt",
        }

        r = TestClient(app).post(
            "/api/v2/integrations/github/connect", json={"pat": OWNER_PAT, "repo": "acme/new"}
        )

        assert r.status_code == 500
        assert load_github_integration_config(ws)["repo"] == "acme/old"

    def test_the_rollback_restores_the_previous_owner_with_the_repo(self, ws, monkeypatch):
        """GLM: the restore ran outside the lock and without the owner, so it
        could pair the old repo with another admin's owner record."""
        from codeframe.auth.dependencies import require_auth
        from codeframe.core import github_integration_config as gic
        from codeframe.ui.dependencies import get_v2_workspace
        from codeframe.ui.routers import github_integrations_v2

        gic.save_connection(ws, {"repo": "acme/old", "owner_login": "acme", "owner_avatar_url": ""}, 5)
        real_write = gic._write_owner
        calls = {"n": 0}

        def fail_once(workspace, user_id):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("disk full")
            real_write(workspace, user_id)

        async def valid(pat, repo, **kwargs):
            return {"repo_full_name": repo, "owner_login": "acme", "owner_avatar_url": ""}

        monkeypatch.setattr(github_integrations_v2, "validate_connection", valid)
        monkeypatch.setattr(gic, "_write_owner", fail_once)
        # Another admin connects in the window between the failure and the
        # rollback (fired from the rollback's own first statement).
        real_error = github_integrations_v2.logger.error

        def error_then_concurrent_connect(*a, **k):
            real_error(*a, **k)
            gic.save_connection(ws, {"repo": "acme/r3", "owner_login": "acme", "owner_avatar_url": ""}, 3)

        monkeypatch.setattr(github_integrations_v2.logger, "error", error_then_concurrent_connect)
        app = FastAPI()
        app.include_router(github_integrations_v2.router)
        app.dependency_overrides[get_v2_workspace] = lambda: ws
        app.dependency_overrides[require_auth] = lambda: {
            "user_id": OWNER, "scopes": ["read", "write", "admin"], "auth_type": "jwt",
        }

        r = TestClient(app).post(
            "/api/v2/integrations/github/connect", json={"pat": OWNER_PAT, "repo": "acme/new"}
        )

        assert r.status_code == 500
        # Whatever the final state, the repo and its owner belong together.
        repo = gic.load_github_integration_config(ws)["repo"]
        assert (repo, connection_owner(ws)) in {("acme/old", 5), ("acme/r3", 3)}

    def test_a_disconnect_racing_a_connect_never_leaves_a_repo_without_its_owner(
        self, ws, monkeypatch
    ):
        """GLM: the disconnect unlinked the config before taking the lock, so a
        connect landing in between kept its repo while its owner was erased."""
        import pathlib
        import threading

        from codeframe.core import github_integration_config as gic

        gic.save_connection(ws, {"repo": "acme/old", "owner_login": "acme", "owner_avatar_url": ""}, 5)
        config_path = gic._config_path(ws)
        real_unlink = pathlib.Path.unlink
        racers: list = []

        def unlink_then_race(self, *a, **k):
            real_unlink(self, *a, **k)
            if self == config_path and not racers:
                t = threading.Thread(target=gic.save_connection, args=(
                    ws, {"repo": "acme/new", "owner_login": "acme", "owner_avatar_url": ""}, OWNER,
                ))
                t.start()
                t.join(timeout=1.0)  # a locked disconnect makes the connect wait
                racers.append(t)

        monkeypatch.setattr(pathlib.Path, "unlink", unlink_then_race)
        gic.clear_github_integration_config(ws)
        racers[0].join(timeout=30)

        config = gic.load_github_integration_config(ws)
        if config is not None:
            assert connection_owner(ws) == OWNER, "a connected repo was left with no owner"

