"""API-key scope enforcement across the v2 API (issue #717 / P0.6).

Before this, every v2 router mounted a blanket ``require_auth`` that proved
*authentication* only — a read-scoped key could POST/PUT/DELETE and even store
credentials or merge PRs. Now:

- safe methods (GET) need ``read``
- mutating methods (POST/PUT/PATCH/DELETE) need ``write``
- credential storage/deletion and PR-merge need ``admin``

JWT principals and the auth-disabled synthetic principal carry all scopes, so
this only constrains scoped API keys.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from codeframe.auth.api_keys import SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN
from codeframe.auth.manager import reset_auth_engine
from codeframe.core.api_key_service import ApiKeyService
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def scoped_app(tmp_path, monkeypatch):
    """Real server app with auth ON and three API keys (read/write/admin)."""
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        ) VALUES (1, 'test@example.com', 'Test', '!DISABLED!', 1, 0, 1, 1)
        """
    )
    db.conn.commit()

    svc = ApiKeyService(db)
    keys = {
        "read": svc.create_api_key(user_id=1, name="r", scopes=[SCOPE_READ]).key,
        "write": svc.create_api_key(user_id=1, name="w", scopes=[SCOPE_READ, SCOPE_WRITE]).key,
        "admin": svc.create_api_key(user_id=1, name="a", scopes=[SCOPE_ADMIN]).key,
    }
    db.close()

    from codeframe.ui import server

    importlib.reload(server)

    # Isolate the credential store: with auth ON, requests carry user_id=1 and
    # the per-user CredentialManager (#790) would otherwise probe — and migrate
    # entries out of — the developer's real ~/.codeframe store.
    from codeframe.core.credentials import CredentialManager, CredentialStore
    from codeframe.ui.routers import github_integrations_v2, settings_v2

    cred_store = CredentialStore(storage_dir=tmp_path / "creds")
    cred_store._keyring_available = False
    cred_manager = CredentialManager.__new__(CredentialManager)
    cred_manager._store = cred_store
    cred_deps = (
        settings_v2.get_credential_manager,
        settings_v2.get_credential_manager_readonly,
        github_integrations_v2.get_credential_manager,
        github_integrations_v2.get_credential_manager_readonly,
    )
    for dep in cred_deps:
        server.app.dependency_overrides[dep] = lambda: cred_manager

    yield server.app, keys
    for dep in cred_deps:
        server.app.dependency_overrides.pop(dep, None)
    reset_auth_engine()


def _hdr(key: str) -> dict:
    return {"X-API-Key": key}


class TestMethodScope:
    def test_read_key_allowed_on_get(self, scoped_app):
        app, keys = scoped_app
        r = TestClient(app).get("/api/v2/settings", headers=_hdr(keys["read"]))
        assert r.status_code != 403  # read scope satisfies a GET
        assert r.status_code != 401

    def test_read_key_forbidden_on_write(self, scoped_app):
        app, keys = scoped_app
        # PUT /api/v2/settings mutates → needs write; read key must 403 before
        # any body validation (router-level dependency fires first).
        r = TestClient(app).put("/api/v2/settings", headers=_hdr(keys["read"]), json={})
        assert r.status_code == 403

    def test_write_key_allowed_on_write(self, scoped_app):
        app, keys = scoped_app
        r = TestClient(app).put("/api/v2/settings", headers=_hdr(keys["write"]), json={})
        assert r.status_code != 403  # write scope passes the method guard
        assert r.status_code != 401


class TestAdminScope:
    def test_read_key_forbidden_on_credential_storage(self, scoped_app):
        app, keys = scoped_app
        r = TestClient(app).put(
            "/api/v2/settings/keys/openai", headers=_hdr(keys["read"]), json={"value": "sk-x"}
        )
        assert r.status_code == 403

    def test_write_key_forbidden_on_credential_storage(self, scoped_app):
        app, keys = scoped_app
        # write is not enough — credential storage is admin-only.
        r = TestClient(app).put(
            "/api/v2/settings/keys/openai", headers=_hdr(keys["write"]), json={"value": "sk-x"}
        )
        assert r.status_code == 403

    def test_admin_key_allowed_on_credential_storage(self, scoped_app):
        app, keys = scoped_app
        r = TestClient(app).put(
            "/api/v2/settings/keys/openai", headers=_hdr(keys["admin"]), json={"value": "sk-x"}
        )
        # admin passes the scope gate; may 400 on value format, but never 403.
        assert r.status_code != 403
        assert r.status_code != 401

    def test_write_key_forbidden_on_pr_merge(self, scoped_app):
        app, keys = scoped_app
        r = TestClient(app).post(
            "/api/v2/pr/1/merge", headers=_hdr(keys["write"]), json={}
        )
        assert r.status_code == 403

    def test_admin_key_allowed_on_pr_merge(self, scoped_app):
        app, keys = scoped_app
        r = TestClient(app).post(
            "/api/v2/pr/1/merge", headers=_hdr(keys["admin"]), json={}
        )
        # admin passes the scope gate; may 400/404/422 on body/logic, never 403.
        assert r.status_code != 403
        assert r.status_code != 401


class TestPatchIsMutating:
    def test_read_key_forbidden_on_patch(self, scoped_app):
        app, keys = scoped_app
        # PATCH is not a safe method → needs write; a read key must 403.
        r = TestClient(app).patch(
            "/api/v2/tasks/abc", headers=_hdr(keys["read"]), json={}
        )
        assert r.status_code == 403
