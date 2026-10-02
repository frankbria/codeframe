"""Tenant-owned LLM keys (#1303).

A non-admin user may store/delete their OWN LLM key (write scope, per-user
store). The GitHub PAT stays admin-only, and a non-admin's manager must never
run the machine-wide migration (it would copy the operator's keys into the
tenant's store). Real server, real auth, real per-user credential stores.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from codeframe.auth.api_keys import SCOPE_ADMIN, SCOPE_READ, SCOPE_WRITE
from codeframe.auth.manager import reset_auth_engine
from codeframe.core import credentials
from codeframe.core.api_key_service import ApiKeyService
from codeframe.core.credentials import CredentialManager, CredentialProvider
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

ANTHROPIC = "sk-ant-test-" + "a" * 20
OPENAI = "sk-" + "o" * 30
GITHUB = "ghp_test" + "g" * 20
USER_ID = 1


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CODEFRAME_DISABLE_KEYRING", "1")
    for p in CredentialProvider:
        monkeypatch.delenv(p.env_var, raising=False)
    store_dir = tmp_path / "creds"
    monkeypatch.setattr(credentials, "DEFAULT_STORAGE_DIR", store_dir)
    credentials._MIGRATION_COMPLETE.clear()
    reset_auth_engine()

    db = Database(tmp_path / "state.db")
    db.initialize()
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        ) VALUES
            (1, 'u@example.com', 'U', '$2b$12$testtesttesttesttesttestesttesttesttesttesttesttesttestte', 1, 0, 1, 1),
            (2, 'op@example.com', 'Op', '$2b$12$testtesttesttesttesttestesttesttesttesttesttesttesttestte', 1, 1, 1, 1)
        """
    )
    db.conn.commit()
    svc = ApiKeyService(db)
    keys = {
        "read": svc.create_api_key(user_id=1, name="r", scopes=[SCOPE_READ]).key,
        "write": svc.create_api_key(user_id=1, name="w", scopes=[SCOPE_READ, SCOPE_WRITE]).key,
        "admin": svc.create_api_key(user_id=2, name="a", scopes=[SCOPE_ADMIN]).key,
    }
    db.close()

    from codeframe.ui import server

    importlib.reload(server)
    yield TestClient(server.app), keys, store_dir
    credentials._MIGRATION_COMPLETE.clear()
    reset_auth_engine()


def _h(key):
    return {"X-API-Key": key}


def _user_store(store_dir, uid=USER_ID):
    return CredentialManager(storage_dir=store_dir, user_id=uid, migrate=False)


def _machine_store(store_dir):
    return CredentialManager(storage_dir=store_dir, user_id=None)


def test_non_admin_stores_own_llm_key_in_own_store(env):
    client, keys, store_dir = env
    r = client.put(
        "/api/v2/settings/keys/LLM_ANTHROPIC", headers=_h(keys["write"]), json={"value": ANTHROPIC}
    )
    assert r.status_code == 200, r.text
    assert _user_store(store_dir).get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC
    assert _machine_store(store_dir).get_credential(CredentialProvider.LLM_ANTHROPIC) is None


def test_non_admin_cannot_store_github_pat(env):
    client, keys, store_dir = env
    r = client.put(
        "/api/v2/settings/keys/GIT_GITHUB", headers=_h(keys["write"]), json={"value": GITHUB}
    )
    assert r.status_code == 403
    assert "admin" in r.json()["detail"]
    assert _user_store(store_dir).get_credential(CredentialProvider.GIT_GITHUB) is None


def test_non_admin_cannot_delete_github_pat(env):
    client, keys, _ = env
    r = client.delete("/api/v2/settings/keys/GIT_GITHUB", headers=_h(keys["write"]))
    assert r.status_code == 403


def test_non_admin_deletes_own_llm_key(env):
    client, keys, store_dir = env
    client.put(
        "/api/v2/settings/keys/LLM_ANTHROPIC", headers=_h(keys["write"]), json={"value": ANTHROPIC}
    )
    r = client.delete("/api/v2/settings/keys/LLM_ANTHROPIC", headers=_h(keys["write"]))
    assert r.status_code == 204
    assert _user_store(store_dir).get_credential(CredentialProvider.LLM_ANTHROPIC) is None


def test_read_only_principal_still_forbidden(env):
    client, keys, _ = env
    r = client.put(
        "/api/v2/settings/keys/LLM_ANTHROPIC", headers=_h(keys["read"]), json={"value": ANTHROPIC}
    )
    assert r.status_code == 403
    assert client.delete("/api/v2/settings/keys/LLM_ANTHROPIC", headers=_h(keys["read"])).status_code == 403


def test_admin_can_still_store_github_pat(env):
    client, keys, _ = env
    r = client.put(
        "/api/v2/settings/keys/GIT_GITHUB", headers=_h(keys["admin"]), json={"value": GITHUB}
    )
    assert r.status_code == 200, r.text


def test_non_admin_does_not_inherit_operator_keys(env):
    """The migration must not run for a non-admin: the operator's key stays out."""
    client, keys, store_dir = env
    _machine_store(store_dir).set_credential(CredentialProvider.LLM_OPENAI, OPENAI)

    r = client.put(
        "/api/v2/settings/keys/LLM_ANTHROPIC", headers=_h(keys["write"]), json={"value": ANTHROPIC}
    )
    assert r.status_code == 200, r.text
    mine = _user_store(store_dir)
    assert mine.get_credential(CredentialProvider.LLM_OPENAI) is None
    assert mine.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC


def test_non_admin_github_connect_does_not_copy_operator_keys(env, tmp_path):
    """The GitHub router built its manager before its admin check, so a refused
    non-admin connect still migrated the operator's keys into the tenant's
    store (internal review of #1303). One shared dependency now serves both."""
    from codeframe.core.workspace import create_or_load_workspace

    client, keys, store_dir = env
    _machine_store(store_dir).set_credential(CredentialProvider.LLM_OPENAI, OPENAI)
    repo = tmp_path / "repo"
    repo.mkdir()
    create_or_load_workspace(repo)

    r = client.post(
        f"/api/v2/integrations/github/connect?workspace_path={repo}",
        headers=_h(keys["write"]),
        json={"pat": "ghp_" + "x" * 36, "repo": "o/r"},
    )

    assert r.status_code == 403, r.text  # reached the admin check, past the workspace
    assert _user_store(store_dir).get_credential(CredentialProvider.LLM_OPENAI) is None
