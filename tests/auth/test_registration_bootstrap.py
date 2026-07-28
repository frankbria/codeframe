"""Registration bootstrap gating (issues #336, #897).

/auth/register is the bootstrap-first-user route. Two independent gates apply:

1. **Credential gate (#897)** — the caller must present
   ``X-Bootstrap-Token`` matching ``CODEFRAME_BOOTSTRAP_TOKEN``, or the request
   must originate on the host itself (loopback, not via a reverse proxy).
2. **Bootstrap gate (#336)** — registration closes once a real (login-capable)
   account exists.

Either gate failing yields 403.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth import router as auth_router
from codeframe.auth.manager import reset_auth_engine
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

BOOTSTRAP_TOKEN = "s3cret-bootstrap-token"


def _build_app(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.delenv("CODEFRAME_BOOTSTRAP_TOKEN", raising=False)
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    db.close()

    app = FastAPI()
    app.include_router(auth_router.router)
    return app, db_path


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """Client whose requests look like they came from the host itself.

    ``TestClient``'s default peer is the literal string ``testclient``, which is
    not a parseable IP — the loopback gate would (correctly) reject it. Pin an
    actual loopback peer so these tests exercise the local-request path.
    """
    app, db_path = _build_app(tmp_path, monkeypatch)
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 40000))
    client.db_path = db_path
    yield client
    reset_auth_engine()


@pytest.fixture
def remote_client(tmp_path, monkeypatch):
    """Client whose requests arrive from an off-host address."""
    app, db_path = _build_app(tmp_path, monkeypatch)
    client = TestClient(app, raise_server_exceptions=False, client=("203.0.113.5", 40000))
    client.db_path = db_path
    yield client
    reset_auth_engine()


def _register(client, email="first@example.com", token=None, headers=None):
    request_headers = dict(headers or {})
    if token is not None:
        request_headers["X-Bootstrap-Token"] = token
    return client.post(
        "/auth/register",
        json={"email": email, "password": "secret123"},
        headers=request_headers,
    )


def _add_real_user(db_path, user_id=2):
    """Insert a real (login-capable) user — a non-disabled password hash."""
    db = Database(db_path)
    db.initialize()
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (?, 'existing@example.com', 'Existing',
                '$2b$12$abcdefghijklmnopqrstuv', 1, 0, 1, 1)
        """,
        (user_id,),
    )
    db.conn.commit()
    db.close()


class TestRegistrationBootstrap:
    def test_register_allowed_when_only_seeded_admin(self, auth_client):
        """The seeded disabled-password admin must not close registration."""
        resp = _register(auth_client)
        # Bootstrap allowed: registration proceeds (not gated with 403).
        assert resp.status_code != 403, resp.text
        assert resp.status_code in (200, 201), resp.text

    def test_register_forbidden_once_a_real_user_exists(self, auth_client):
        _add_real_user(auth_client.db_path)
        resp = _register(auth_client, email="second@example.com")
        assert resp.status_code == 403, resp.text

    def test_concurrent_first_registrations_admit_exactly_one(self, auth_client):
        """TOCTOU guard: two simultaneous first-time registrations must not
        both slip through the zero-users check (codex review P2). The yield
        dependency holds an in-process lock until user creation completes, so
        exactly one succeeds and the other gets 403."""
        import anyio
        import httpx

        app = auth_client.app
        statuses = []

        async def _register_async(client, email):
            resp = await client.post(
                "/auth/register",
                json={"email": email, "password": "secret123"},
            )
            statuses.append(resp.status_code)

        async def _run():
            transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 40000))
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                async with anyio.create_task_group() as tg:
                    tg.start_soon(_register_async, client, "racer-a@example.com")
                    tg.start_soon(_register_async, client, "racer-b@example.com")

        anyio.run(_run)

        assert sorted(statuses) == [201, 403] or sorted(statuses) == [200, 403], (
            f"expected exactly one success and one 403, got {statuses}"
        )


class TestBootstrapTokenGate:
    """#897 — a configured token is mandatory, loopback included."""

    def test_correct_token_registers(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
        resp = _register(auth_client, token=BOOTSTRAP_TOKEN)
        assert resp.status_code in (200, 201), resp.text

    def test_missing_token_forbidden_even_with_zero_users(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
        resp = _register(auth_client)
        assert resp.status_code == 403, resp.text
        assert "CODEFRAME_BOOTSTRAP_TOKEN" in resp.text

    def test_wrong_token_forbidden(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
        resp = _register(auth_client, token="not-the-token")
        assert resp.status_code == 403, resp.text

    def test_configured_token_not_bypassed_by_loopback(self, auth_client, monkeypatch):
        """Configuring a token is an opt-in to the stronger control — a local
        request must not sidestep it."""
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
        assert auth_client.post(
            "/auth/register", json={"email": "a@example.com", "password": "secret123"}
        ).status_code == 403

    def test_second_registration_forbidden_even_with_correct_token(
        self, auth_client, monkeypatch
    ):
        """The token opens the bootstrap window; it does not reopen it."""
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
        first = _register(auth_client, email="first@example.com", token=BOOTSTRAP_TOKEN)
        assert first.status_code in (200, 201), first.text

        second = _register(auth_client, email="second@example.com", token=BOOTSTRAP_TOKEN)
        assert second.status_code == 403, second.text

    def test_blank_token_env_is_treated_as_unset(self, auth_client, monkeypatch):
        """An empty/whitespace value must not become a matchable secret."""
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", "   ")
        # Falls back to the loopback path, which this client satisfies.
        resp = _register(auth_client)
        assert resp.status_code in (200, 201), resp.text

    def test_remote_caller_with_correct_token_registers(self, remote_client, monkeypatch):
        """The token is what makes remote bootstrap possible at all."""
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
        resp = _register(remote_client, token=BOOTSTRAP_TOKEN)
        assert resp.status_code in (200, 201), resp.text


class TestLoopbackGate:
    """#897 — with no token configured, only host-local requests may bootstrap."""

    def test_loopback_caller_allowed(self, auth_client):
        resp = _register(auth_client)
        assert resp.status_code in (200, 201), resp.text

    def test_remote_caller_forbidden(self, remote_client):
        resp = _register(remote_client)
        assert resp.status_code == 403, resp.text
        assert "CODEFRAME_BOOTSTRAP_TOKEN" in resp.text

    def test_proxied_public_client_forbidden(self, auth_client):
        """The Caddy trap: behind the documented reverse proxy the peer IS
        loopback, so the forwarded chain is what distinguishes a real local
        caller from the whole Internet."""
        resp = _register(
            auth_client, headers={"X-Forwarded-For": "203.0.113.5"}
        )
        assert resp.status_code == 403, resp.text

    def test_spoofed_loopback_forwarded_for_still_forbidden(self, auth_client):
        """Caddy *appends* the real peer, so an attacker-supplied loopback hop
        cannot hide the public one behind it."""
        resp = _register(
            auth_client, headers={"X-Forwarded-For": "127.0.0.1, 203.0.113.5"}
        )
        assert resp.status_code == 403, resp.text

    def test_loopback_forwarded_chain_allowed(self, auth_client):
        """A local dev proxy (Next.js rewrite) forwards from loopback to
        loopback — that is still a host-local request."""
        resp = _register(auth_client, headers={"X-Forwarded-For": "127.0.0.1"})
        assert resp.status_code in (200, 201), resp.text

    def test_rfc7239_forwarded_header_forbidden(self, auth_client):
        """Any RFC 7239 `Forwarded` header means a proxy is in the path."""
        resp = _register(
            auth_client, headers={"Forwarded": "for=203.0.113.5;proto=https"}
        )
        assert resp.status_code == 403, resp.text

    def test_ipv6_loopback_caller_allowed(self, tmp_path, monkeypatch):
        app, _ = _build_app(tmp_path, monkeypatch)
        with TestClient(
            app, raise_server_exceptions=False, client=("::1", 40000)
        ) as client:
            resp = _register(client)
            assert resp.status_code in (200, 201), resp.text
        reset_auth_engine()

    def test_unparseable_peer_forbidden(self, tmp_path, monkeypatch):
        """Fail closed when the peer address is not an IP we can classify."""
        app, _ = _build_app(tmp_path, monkeypatch)
        with TestClient(
            app, raise_server_exceptions=False, client=("testclient", 40000)
        ) as client:
            resp = _register(client)
            assert resp.status_code == 403, resp.text
        reset_auth_engine()
