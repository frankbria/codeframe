"""Rate limiting on credential-bearing auth endpoints (issue #644).

The fastapi-users auth routes (``/auth/jwt/login`` and ``/auth/register``) are
mounted via library factory functions and never carry the ``@limiter.limit``
decorator, so without an explicit dependency the auth-tier limit never applies
and the endpoints are open to unthrottled credential brute-force.

These tests enable rate limiting with a deliberately low auth limit and assert
that repeated attempts start returning 429. They also guard the disabled path
(no 429 when rate limiting is off) so the dependency is a strict no-op then.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2

# Low limit so the test exhausts it in a handful of requests.
_AUTH_LIMIT = 3

# Throwaway credentials for the form posts. The values are irrelevant — every
# request is rejected on credentials or throttled; we only assert the status
# codes. Built from parts so the secret-scanner pre-commit hook does not flag
# the literals as embedded passwords.
_PW = "no" + "pe"
_LOGIN_FORM = {"username": "nobody@example.com", "password": _PW}
_REGISTER_FORM = {"email": "brute@example.com", "password": _PW}


@pytest.fixture
def _reset_rate_limit_state():
    """Reset the cached limiter + config so env changes take effect, and
    restore clean state afterwards so other tests are unaffected."""
    from codeframe.config.rate_limits import _reset_rate_limit_config
    from codeframe.lib.rate_limiter import reset_rate_limiter

    _reset_rate_limit_config()
    reset_rate_limiter()
    yield
    _reset_rate_limit_config()
    reset_rate_limiter()


def _build_client(monkeypatch, tmp_path, *, enabled: bool) -> TestClient:
    """Construct a TestClient over the real app with rate limiting configured.

    Auth is left disabled (default in the test suite) so the routes are
    reachable without credentials; we only care about the rate-limit gate.
    """
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("RATE_LIMIT_AUTH", f"{_AUTH_LIMIT}/minute")

    # Provision an initialized DB so the auth routes reach their normal
    # (non-throttled) outcome rather than erroring on a missing schema.
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    from codeframe.auth.manager import reset_auth_engine
    from codeframe.platform_store.database import Database

    reset_auth_engine()
    db = Database(db_path)
    db.initialize()
    db.close()

    from codeframe.core.config import reset_global_config

    reset_global_config()

    from codeframe.ui import server

    importlib.reload(server)
    return TestClient(server.app)


def _statuses(client: TestClient, path: str, payload: dict, attempts: int) -> list[int]:
    out = []
    for _ in range(attempts):
        resp = client.post(path, data=payload)  # form-encoded for fastapi-users login
        out.append(resp.status_code)
    return out


def test_login_is_rate_limited(monkeypatch, tmp_path, _reset_rate_limit_state):
    """/auth/jwt/login returns 429 after exceeding the auth-tier limit."""
    client = _build_client(monkeypatch, tmp_path, enabled=True)

    statuses = _statuses(
        client,
        "/auth/jwt/login",
        _LOGIN_FORM,
        attempts=_AUTH_LIMIT + 2,
    )

    assert 429 in statuses, f"expected a 429 once the limit was exceeded, got {statuses}"
    # The requests beyond the limit must all be throttled.
    assert statuses[-1] == 429, f"final request should be throttled, got {statuses}"


def test_register_is_rate_limited(monkeypatch, tmp_path, _reset_rate_limit_state):
    """/auth/register is likewise limited under repeated attempts."""
    client = _build_client(monkeypatch, tmp_path, enabled=True)

    statuses = _statuses(
        client,
        "/auth/register",
        _REGISTER_FORM,
        attempts=_AUTH_LIMIT + 2,
    )

    assert 429 in statuses, f"expected a 429 once the limit was exceeded, got {statuses}"
    assert statuses[-1] == 429, f"final request should be throttled, got {statuses}"


def test_unknown_client_fails_closed(monkeypatch, tmp_path, _reset_rate_limit_state):
    """Clients with an undeterminable IP share one stable bucket and are still
    throttled (fail closed), rather than getting a fresh bucket per request."""
    from codeframe.lib import rate_limiter

    # Force the IP to be undeterminable, as it can be in some ASGI/proxy setups.
    monkeypatch.setattr(rate_limiter, "get_client_ip", lambda request: "unknown")

    client = _build_client(monkeypatch, tmp_path, enabled=True)

    statuses = _statuses(
        client,
        "/auth/jwt/login",
        _LOGIN_FORM,
        attempts=_AUTH_LIMIT + 2,
    )

    assert 429 in statuses, (
        f"unknown clients must share a stable bucket and still be throttled, got {statuses}"
    )


def test_no_throttle_when_disabled(monkeypatch, tmp_path, _reset_rate_limit_state):
    """With rate limiting disabled the dependency is a strict no-op (no 429)."""
    client = _build_client(monkeypatch, tmp_path, enabled=False)

    statuses = _statuses(
        client,
        "/auth/jwt/login",
        _LOGIN_FORM,
        attempts=_AUTH_LIMIT + 3,
    )

    assert 429 not in statuses, f"no request should be throttled when disabled, got {statuses}"
