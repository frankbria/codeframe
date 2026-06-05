"""Central auth enforcement across the v2 API (issue #336).

With CODEFRAME_AUTH_REQUIRED=true, every v2 REST router must reject
unauthenticated requests with 401 (a 404/422 would mean the dependency did
NOT fire). A valid JWT (header) must get past auth (not 401). Public
endpoints (/, /health, docs, /auth/register) stay reachable.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_test_jwt_token

pytestmark = pytest.mark.v2


# One representative GET endpoint per mounted v2 REST router. Cheap paths;
# the goal is to confirm the router-level require_auth dependency fires.
# (router id, GET path)
V2_GET_ENDPOINTS = [
    ("batches", "/api/v2/batches"),
    ("blockers", "/api/v2/blockers"),
    ("checkpoints", "/api/v2/checkpoints"),
    ("costs", "/api/v2/costs/summary"),
    ("diagnose", "/api/v2/tasks/abc/diagnose"),
    ("discovery", "/api/v2/discovery/status"),
    ("environment", "/api/v2/env/check"),
    ("events", "/api/v2/events"),
    ("gates", "/api/v2/gates"),
    ("git", "/api/v2/git/status"),
    ("github_integrations", "/api/v2/integrations/github/status"),
    ("interactive_sessions", "/api/v2/sessions"),
    ("pr", "/api/v2/pr/status"),
    ("prd", "/api/v2/prd"),
    ("proof", "/api/v2/proof/requirements"),
    ("review", "/api/v2/review/diff"),
    ("schedule", "/api/v2/schedule"),
    # streaming_v2 holds SSE utilities only; the SSE route itself is mounted
    # under the tasks prefix — assert the auth dependency fires on it too.
    ("streaming-sse", "/api/v2/tasks/abc/stream"),
    ("settings", "/api/v2/settings"),
    ("tasks", "/api/v2/tasks"),
    ("templates", "/api/v2/templates"),
    ("workspace", "/api/v2/workspaces"),
]


@pytest.fixture
def auth_app(monkeypatch):
    """Import the real server app with auth enforcement enabled."""
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    # server module is import-time; the app object already exists. The
    # require_auth dependency reads the env at request time, so a freshly
    # constructed TestClient over the existing app honors the monkeypatch.
    from codeframe.ui import server

    importlib.reload(server)
    return server.app


@pytest.mark.parametrize("router_id,path", V2_GET_ENDPOINTS)
def test_unauthenticated_returns_401(auth_app, router_id, path):
    client = TestClient(auth_app, raise_server_exceptions=False)
    resp = client.get(path)
    assert resp.status_code == 401, (
        f"{router_id} {path} returned {resp.status_code}, expected 401 "
        f"(auth dependency did not fire)"
    )


@pytest.mark.parametrize("router_id,path", V2_GET_ENDPOINTS)
def test_valid_jwt_not_401(auth_app, router_id, path):
    client = TestClient(auth_app, raise_server_exceptions=False)
    token = create_test_jwt_token(user_id=1)
    resp = client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code != 401, (
        f"{router_id} {path} returned 401 with a valid JWT"
    )


def test_valid_api_key_not_401(auth_app, monkeypatch, tmp_path):
    """End-to-end X-API-Key path: a real key stored in the platform store
    must get past the router-level require_auth dependency."""
    from codeframe.auth.api_keys import generate_api_key
    from codeframe.platform_store.database import Database

    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    db = Database(db_path)
    db.initialize()
    full_key, key_hash, prefix = generate_api_key()
    db.api_keys.create(
        user_id=1,
        name="enforcement-test",
        key_hash=key_hash,
        prefix=prefix,
        scopes=["read", "write", "admin"],
    )
    db.close()

    # No lifespan (no `with`): get_api_key_auth falls back to DATABASE_PATH.
    client = TestClient(auth_app, raise_server_exceptions=False)
    resp = client.get("/api/v2/templates", headers={"X-API-Key": full_key})
    assert resp.status_code != 401, resp.text

    # And a bogus key must NOT pass.
    resp = client.get("/api/v2/templates", headers={"X-API-Key": "cf_live_" + "0" * 32})
    assert resp.status_code == 401


def test_test_broadcast_requires_auth(auth_app):
    client = TestClient(auth_app, raise_server_exceptions=False)
    resp = client.post("/test/broadcast", json={"message": {"x": 1}})
    assert resp.status_code == 401


class TestPublicEndpointsStayOpen:
    def test_root(self, auth_app):
        client = TestClient(auth_app, raise_server_exceptions=False)
        assert client.get("/").status_code == 200

    def test_health(self, auth_app):
        client = TestClient(auth_app, raise_server_exceptions=False)
        assert client.get("/health").status_code == 200

    def test_docs(self, auth_app):
        client = TestClient(auth_app, raise_server_exceptions=False)
        assert client.get("/docs").status_code == 200

    def test_openapi(self, auth_app):
        client = TestClient(auth_app, raise_server_exceptions=False)
        assert client.get("/openapi.json").status_code == 200

    def test_register_not_401(self, auth_app):
        """The register endpoint must remain reachable (not blanket-401'd)."""
        client = TestClient(auth_app, raise_server_exceptions=False)
        resp = client.post(
            "/auth/register",
            json={"email": "x@example.com", "password": "secret123"},
        )
        assert resp.status_code != 401
