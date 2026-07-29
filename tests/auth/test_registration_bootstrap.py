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


def _superuser_flag(db_path, email):
    db = Database(db_path)
    db.initialize()
    row = db.conn.execute(
        "SELECT is_superuser FROM users WHERE email = ?", (email,)
    ).fetchone()
    db.close()
    return None if row is None else bool(row[0])


class TestBootstrapUserBecomesSuperuser:
    """#898 / P0.4 — admin scope now derives from ``users.is_superuser``.

    ``fastapi_users.get_register_router`` forces ``is_superuser=False`` on every
    registration, so without this promotion no principal would ever hold admin
    and credential storage / PAT storage / PR merge would be permanently 403.
    The bootstrap route admits exactly one login-capable account (#336/#897), so
    that account is the operator.
    """

    def test_bootstrap_user_is_promoted_to_superuser(self, auth_client):
        resp = _register(auth_client)
        assert resp.status_code in (200, 201), resp.text
        assert _superuser_flag(auth_client.db_path, "first@example.com") is True

    def test_seeded_disabled_admin_does_not_block_promotion(self, auth_client):
        """The seeded id=1 placeholder is already is_superuser=1 but cannot log
        in, so it must not be mistaken for an existing admin."""
        _register(auth_client)
        assert _superuser_flag(auth_client.db_path, "first@example.com") is True

    def test_registration_alongside_an_existing_real_user_does_not_promote(
        self, auth_client, monkeypatch
    ):
        """Belt-and-braces: if a second registration path ever opens, only a
        genuinely-sole account is promoted."""
        from codeframe.auth import router as auth_router_module

        _add_real_user(auth_client.db_path)
        # Bypass the closed-registration gate to exercise the promotion guard
        # itself rather than the route gate that normally precedes it.
        async def _allow_anything():
            yield

        auth_client.app.dependency_overrides[auth_router_module.allow_registration] = (
            _allow_anything
        )
        try:
            resp = _register(auth_client, email="second@example.com")
            assert resp.status_code in (200, 201), resp.text
        finally:
            auth_client.app.dependency_overrides.clear()

        assert _superuser_flag(auth_client.db_path, "second@example.com") is False


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

    def test_non_ascii_token_header_is_rejected_not_crashed(
        self, auth_client, monkeypatch
    ):
        """A hostile header must 403, not 500.

        Header bytes above 0x7F are legal on the wire and Starlette decodes them
        as latin-1, so the dependency sees a non-ASCII ``str``.
        ``hmac.compare_digest`` raises ``TypeError`` on non-ASCII ``str``
        operands, so comparing strings directly would turn this into a 500.
        """
        monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
        resp = _register(
            auth_client, headers={"X-Bootstrap-Token": b"caf\xe9-\xfcnicode"}
        )
        assert resp.status_code == 403, resp.text

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

    def test_repeated_forwarded_for_headers_all_inspected(self, auth_client):
        """``Headers.get`` returns only the FIRST match. A proxy that emits its
        own ``X-Forwarded-For`` header instead of appending to the client's
        would otherwise let an attacker-supplied loopback value mask the real
        address sitting in the second header."""
        resp = auth_client.post(
            "/auth/register",
            json={"email": "a@example.com", "password": "secret123"},
            headers=[
                ("X-Forwarded-For", "127.0.0.1"),
                ("X-Forwarded-For", "203.0.113.5"),
            ],
        )
        assert resp.status_code == 403, resp.text

    def test_x_real_ip_public_client_forbidden(self, auth_client):
        """nginx-style proxies set ``X-Real-IP``, sometimes without any
        ``X-Forwarded-For`` at all."""
        resp = _register(auth_client, headers={"X-Real-IP": "203.0.113.5"})
        assert resp.status_code == 403, resp.text

    def test_x_real_ip_loopback_allowed(self, auth_client):
        resp = _register(auth_client, headers={"X-Real-IP": "127.0.0.1"})
        assert resp.status_code in (200, 201), resp.text

    def test_header_casing_is_ignored(self, auth_client):
        """HTTP headers are case-insensitive — the gate must not be evadable by
        sending ``x-FoRwArDeD-fOr``."""
        resp = _register(auth_client, headers={"x-FoRwArDeD-fOr": "203.0.113.5"})
        assert resp.status_code == 403, resp.text

    def test_forwarded_proto_and_host_do_not_block(self, auth_client):
        """These describe the request, not who made it, and the local Next.js
        `/auth/*` rewrite sets them in ordinary development."""
        resp = _register(
            auth_client,
            headers={"X-Forwarded-Proto": "http", "X-Forwarded-Host": "localhost:3000"},
        )
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

    def test_ipv4_mapped_ipv6_loopback_peer_allowed(self, tmp_path, monkeypatch):
        """A dual-stack listener reports a loopback IPv4 peer as
        ``::ffff:127.0.0.1``, which ``IPv6Address.is_loopback`` calls False."""
        app, _ = _build_app(tmp_path, monkeypatch)
        with TestClient(
            app, raise_server_exceptions=False, client=("::ffff:127.0.0.1", 40000)
        ) as client:
            resp = _register(client)
            assert resp.status_code in (200, 201), resp.text
        reset_auth_engine()

    def test_ipv4_mapped_ipv6_public_peer_forbidden(self, tmp_path, monkeypatch):
        """The mapped-address unwrapping must not turn into a bypass."""
        app, _ = _build_app(tmp_path, monkeypatch)
        with TestClient(
            app, raise_server_exceptions=False, client=("::ffff:203.0.113.5", 40000)
        ) as client:
            resp = _register(client)
            assert resp.status_code == 403, resp.text
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
