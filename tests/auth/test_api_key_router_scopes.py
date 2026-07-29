"""The API-key management router enforces scope by method (issue #898 / P0.4).

The router was mounted with a bare ``require_auth``, so a ``scopes: ["read"]``
key could DELETE any of its owner's other keys — including the write/admin ones
— which is a privilege *reduction* attack (revoke the keys you can't use) and,
worse, an unscoped mutation from a credential that proved read access only.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth import router as auth_router
from codeframe.auth.api_keys import SCOPE_READ, SCOPE_WRITE
from codeframe.auth.manager import reset_auth_engine
from codeframe.core.api_key_service import ApiKeyService
from codeframe.platform_store.database import Database
from tests.conftest import setup_test_user

pytestmark = pytest.mark.v2


@pytest.fixture
def client_and_keys(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    setup_test_user(db, user_id=1)
    svc = ApiKeyService(db)
    keys = {
        "read": svc.create_api_key(user_id=1, name="r", scopes=[SCOPE_READ]),
        "write": svc.create_api_key(user_id=1, name="w", scopes=[SCOPE_READ, SCOPE_WRITE]),
    }
    db.close()

    app = FastAPI()
    app.include_router(auth_router.router)
    yield TestClient(app, raise_server_exceptions=False), keys
    reset_auth_engine()


def _hdr(key) -> dict:
    return {"X-API-Key": key.key}


class TestApiKeyRouterScopes:
    def test_read_key_may_list(self, client_and_keys):
        client, keys = client_and_keys
        resp = client.get("/api/auth/api-keys", headers=_hdr(keys["read"]))
        assert resp.status_code == 200, resp.text

    def test_read_key_forbidden_on_revoke(self, client_and_keys):
        """The core regression: a read-scope key must not revoke a key."""
        client, keys = client_and_keys
        resp = client.delete(
            f"/api/auth/api-keys/{keys['write'].id}", headers=_hdr(keys["read"])
        )
        assert resp.status_code == 403, resp.text

        # And the target key really is still active.
        listed = client.get("/api/auth/api-keys", headers=_hdr(keys["read"])).json()
        assert [k for k in listed if k["id"] == keys["write"].id][0]["is_active"] is True

    def test_write_key_may_revoke(self, client_and_keys):
        client, keys = client_and_keys
        resp = client.delete(
            f"/api/auth/api-keys/{keys['read'].id}", headers=_hdr(keys["write"])
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["revoked"] is True

    def test_read_key_forbidden_on_create(self, client_and_keys):
        """Creation already required a JWT; the method guard fires first and 403s."""
        client, keys = client_and_keys
        resp = client.post(
            "/api/auth/api-keys",
            headers=_hdr(keys["read"]),
            json={"name": "escalate", "scopes": ["admin"]},
        )
        assert resp.status_code in (401, 403), resp.text


class TestAdminKeyMintingRequiresSuperuser:
    """A key must not grant more than its creator holds (#898).

    Without this the JWT-scope derivation is a formality: any signed-in
    non-superuser could mint themselves an ``admin`` key and use it to store
    credentials or merge PRs.
    """

    def _jwt(self):
        from tests.conftest import create_test_jwt_token

        return {"Authorization": f"Bearer {create_test_jwt_token(user_id=1)}"}

    def _promote(self, tmp_path):
        db = Database(tmp_path / "state.db")
        db.initialize()
        db.conn.execute("UPDATE users SET is_superuser = 1 WHERE id = 1")
        db.conn.commit()
        db.close()

    def test_non_superuser_cannot_mint_admin_key(self, client_and_keys):
        client, _ = client_and_keys
        resp = client.post(
            "/api/auth/api-keys",
            headers=self._jwt(),
            json={"name": "escalate", "scopes": ["admin"]},
        )
        assert resp.status_code == 403, resp.text

    def test_non_superuser_may_mint_a_write_key(self, client_and_keys):
        client, _ = client_and_keys
        resp = client.post(
            "/api/auth/api-keys",
            headers=self._jwt(),
            json={"name": "ordinary", "scopes": ["read", "write"]},
        )
        assert resp.status_code == 201, resp.text

    def test_superuser_may_mint_admin_key(self, client_and_keys, tmp_path):
        client, _ = client_and_keys
        self._promote(tmp_path)
        resp = client.post(
            "/api/auth/api-keys",
            headers=self._jwt(),
            json={"name": "legit", "scopes": ["admin"]},
        )
        assert resp.status_code == 201, resp.text
