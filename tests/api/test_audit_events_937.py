"""Security events actually reach audit_logs (#937).

`AuditLogger` documented "all security-relevant events ... for compliance,
security monitoring, and incident investigation" and defined AUTH_*, AUTHZ_* and
USER_* types; the store created `audit_logs` plus three indexes. The only call
site in the whole package was the rate-limit handler, wrapped in
`except Exception: logger.debug`. No test referenced AuditLogger or
AuditRepository at all.

So the schema implied controls that were not in force: a failed login, a logout,
a bootstrap registration and every API-key mint or revocation wrote nothing.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.lib.audit_logger import AuditEventType, AuditLogger, audit_from_request
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def db():
    database = Database(":memory:")
    database.initialize()
    return database


def _seeded_user_id(database):
    """The bootstrap account's id. audit_logs.user_id is a foreign key."""
    conn = database.conn if hasattr(database, "conn") else database._conn
    return conn.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]


def _rows(database, event_type=None):
    conn = database.conn if hasattr(database, "conn") else database._conn
    sql = "SELECT event_type, user_id, ip_address, metadata FROM audit_logs"
    params = ()
    if event_type:
        sql += " WHERE event_type = ?"
        params = (event_type,)
    return conn.execute(sql, params).fetchall()


class TestAuditRepositoryDirectly:
    """AC2 — create_audit_log had no direct test."""

    def test_create_audit_log_persists_a_row(self, db):
        from datetime import UTC, datetime

        row_id = db.create_audit_log(
            event_type="auth.login.failed",
            user_id=None,
            resource_type="auth",
            resource_id=None,
            ip_address="203.0.113.7",
            metadata={"email": "someone@example.com"},
            timestamp=datetime.now(UTC),
        )

        assert row_id
        rows = _rows(db, "auth.login.failed")
        assert len(rows) == 1
        assert rows[0]["ip_address"] == "203.0.113.7"

    def test_metadata_round_trips_as_json(self, db):
        from datetime import UTC, datetime
        import json

        db.create_audit_log(
            event_type="api_key.created",
            user_id=1,
            resource_type="api_key",
            resource_id=None,
            ip_address=None,
            metadata={"scopes": ["read", "write"], "name": "ci"},
            timestamp=datetime.now(UTC),
        )

        stored = json.loads(_rows(db, "api_key.created")[0]["metadata"])
        assert stored["scopes"] == ["read", "write"]
        assert stored["name"] == "ci"

    def test_null_user_is_allowed(self, db):
        """A failed login has no user id — the row must still be writable."""
        from datetime import UTC, datetime

        assert db.create_audit_log(
            event_type="auth.login.failed",
            user_id=None,
            resource_type="auth",
            resource_id=None,
            ip_address=None,
            metadata=None,
            timestamp=datetime.now(UTC),
        )


class TestAuditWriteFailureIsLoud:
    """AC3 — the failure path logged at debug, so a missing trail was invisible."""

    def test_write_failure_logs_at_warning(self, caplog):
        import logging

        class BrokenDb:
            def create_audit_log(self, **_kwargs):
                raise RuntimeError("audit table is gone")

        with caplog.at_level(logging.WARNING):
            AuditLogger(BrokenDb())._log_event(
                event_type=AuditEventType.AUTH_LOGIN_FAILED,
                user_id=None,
                resource_type="auth",
                resource_id=None,
                ip_address=None,
                metadata=None,
            )

        assert any(r.levelno >= logging.WARNING for r in caplog.records)
        assert "auth.login.failed" in caplog.text

    def test_write_failure_does_not_raise(self):
        """Refusing a login because auditing broke would be a self-inflicted outage."""

        class BrokenDb:
            def create_audit_log(self, **_kwargs):
                raise RuntimeError("boom")

        AuditLogger(BrokenDb())._log_event(
            event_type=AuditEventType.AUTH_LOGOUT,
            user_id=1,
            resource_type="auth",
            resource_id=None,
            ip_address=None,
            metadata=None,
        )


class TestAuditFromRequest:
    def test_writes_using_the_app_database(self, db):
        app = FastAPI()
        app.state.db = db

        class FakeRequest:
            def __init__(self, application):
                self.app = application
                self.client = type("C", (), {"host": "198.51.100.9"})()

        audit_from_request(
            FakeRequest(app),
            AuditEventType.AUTH_LOGIN_FAILED,
            email="attacker@example.com",
        )

        rows = _rows(db, "auth.login.failed")
        assert len(rows) == 1
        assert rows[0]["ip_address"] == "198.51.100.9"

    def test_no_database_is_a_quiet_no_op(self):
        """Routers built without app state (unit tests) must not blow up."""
        app = FastAPI()

        class FakeRequest:
            def __init__(self, application):
                self.app = application
                self.client = None

        audit_from_request(FakeRequest(app), AuditEventType.AUTH_LOGOUT)


class TestFailedLoginProducesAnAuditRow:
    """AC2 — the router-level assertion the issue asks for."""

    @pytest.fixture
    def client(self, db, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        from codeframe.auth import router as auth_router

        app = FastAPI()
        app.state.db = db
        app.include_router(auth_router.router)
        return TestClient(app, raise_server_exceptions=False)

    def test_bad_credentials_are_recorded(self, client, db):
        response = client.post(
            "/auth/jwt/login",
            data={"username": "nobody@example.com", "password": "nope"},
        )

        assert response.status_code in (400, 401), response.text
        rows = _rows(db, "auth.login.failed")
        assert len(rows) == 1, "a failed login wrote no audit row"

    def test_the_recorded_row_names_the_attempted_identity(self, client, db):
        client.post(
            "/auth/jwt/login",
            data={"username": "target@example.com", "password": "wrong"},
        )

        import json

        rows = _rows(db, "auth.login.failed")
        assert rows, "no audit row"
        assert "target@example.com" in json.loads(rows[0]["metadata"])["email"]

    def test_repeated_failures_each_produce_a_row(self, client, db):
        """One row per attempt is what makes credential stuffing visible."""
        for _ in range(3):
            client.post(
                "/auth/jwt/login",
                data={"username": "target@example.com", "password": "wrong"},
            )

        assert len(_rows(db, "auth.login.failed")) == 3


class TestForeignKeyOnUserId:
    """Found while writing the inactive-account test: a user_id with no `users`
    row fails the INSERT outright, and the guard then swallows it — so the event
    is lost rather than partially recorded. Worth pinning so the behaviour is a
    known constraint on call sites, not a surprise."""

    def test_an_unknown_user_id_loses_the_row_and_warns(self, db, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            AuditLogger(db)._log_event(
                event_type=AuditEventType.AUTH_LOGIN_FAILED,
                user_id=999999,  # no such users row
                resource_type="auth",
                resource_id=None,
                ip_address=None,
                metadata=None,
            )

        assert _rows(db, "auth.login.failed") == []
        assert "foreign key" in caplog.text.lower()

    def test_a_null_user_id_always_works(self, db):
        """Which is why the bad-credentials path passes None."""
        AuditLogger(db)._log_event(
            event_type=AuditEventType.AUTH_LOGIN_FAILED,
            user_id=None,
            resource_type="auth",
            resource_id=None,
            ip_address=None,
            metadata=None,
        )

        assert len(_rows(db, "auth.login.failed")) == 1


class TestInactiveAccountLoginIsAudited:
    """Raised by the PR bot.

    fastapi-users' route rejects an inactive account with the same 400
    BAD_CREDENTIALS *after* authenticate() returns the user. Auditing only the
    None case made repeated correct-password attempts against a disabled or
    compromised account invisible — the exact credential-stuffing signal this
    feature exists to capture.
    """

    @pytest.mark.asyncio
    async def test_an_inactive_user_with_the_right_password_is_audited(self, db):
        from unittest.mock import AsyncMock, patch

        from fastapi_users import BaseUserManager

        from codeframe.auth.manager import UserManager
        from codeframe.lib.audit_logger import _current_request

        # A REAL user row: audit_logs.user_id is a foreign key, so a fabricated
        # id would make the write fail and the guard would swallow it — the test
        # would then pass for the wrong reason once the code was fixed.
        real_id = _seeded_user_id(db)
        inactive = type(
            "U", (), {"id": real_id, "is_active": False, "email": "x@y.z"}
        )()

        class FakeRequest:
            def __init__(self):
                self.app = type("A", (), {"state": type("S", (), {"db": db})()})()
                self.client = None

        manager = UserManager.__new__(UserManager)
        token = _current_request.set(FakeRequest())
        try:
            with patch.object(
                BaseUserManager, "authenticate", AsyncMock(return_value=inactive)
            ):
                result = await manager.authenticate(
                    type("C", (), {"username": "x@y.z", "password": "pw"})()
                )
        finally:
            _current_request.reset(token)

        assert result is inactive, "authenticate must still return what it returned"
        rows = _rows(db, "auth.login.failed")
        assert len(rows) == 1, "an inactive-account login wrote no audit row"

        import json

        assert json.loads(rows[0]["metadata"])["reason"] == "inactive_account"

    @pytest.mark.asyncio
    async def test_an_active_user_is_not_audited_as_a_failure(self, db):
        """on_after_login records the success; a duplicate failure row would lie."""
        from unittest.mock import AsyncMock, patch

        from fastapi_users import BaseUserManager

        from codeframe.auth.manager import UserManager
        from codeframe.lib.audit_logger import _current_request

        active = type(
            "U", (), {"id": _seeded_user_id(db), "is_active": True, "email": "x@y.z"}
        )()

        class FakeRequest:
            def __init__(self):
                self.app = type("A", (), {"state": type("S", (), {"db": db})()})()
                self.client = None

        manager = UserManager.__new__(UserManager)
        token = _current_request.set(FakeRequest())
        try:
            with patch.object(
                BaseUserManager, "authenticate", AsyncMock(return_value=active)
            ):
                await manager.authenticate(
                    type("C", (), {"username": "x@y.z", "password": "pw"})()
                )
        finally:
            _current_request.reset(token)

        assert _rows(db, "auth.login.failed") == []


class TestWritesAreDeferredPastTheAuthSession:
    """Raised by `codex review` as a P1.

    fastapi-users' async SQLAlchemy session and app.state.db are two connections
    to the SAME SQLite file, and authenticate() can leave a write open (it
    rewrites a legacy password hash). An inline audit write would queue behind
    that transaction on busy_timeout=5000 — a 5s stall on every failed login,
    and a LOST audit row once the wait expires.
    """

    def test_events_are_queued_not_written_during_the_request(self, db):
        from codeframe.lib.audit_logger import _pending

        class FakeRequest:
            def __init__(self):
                self.app = type("A", (), {"state": type("S", (), {"db": db})()})()
                self.client = None

        token = _pending.set([])
        try:
            audit_from_request(FakeRequest(), AuditEventType.AUTH_LOGIN_FAILED)
            assert _rows(db) == [], "the row was written inline, not deferred"
            assert len(_pending.get()) == 1, "the event was not queued"
        finally:
            _pending.reset(token)

    def test_without_a_capture_context_the_write_is_immediate(self, db):
        """Call sites outside a captured route must still work."""

        class FakeRequest:
            def __init__(self):
                self.app = type("A", (), {"state": type("S", (), {"db": db})()})()
                self.client = None

        audit_from_request(FakeRequest(), AuditEventType.AUTH_LOGOUT)

        assert len(_rows(db, "auth.logout")) == 1

    def test_the_context_is_reset_even_if_a_flush_fails(self):
        """A stranded ContextVar would leak one request's identity into the next."""
        import asyncio

        from codeframe.lib.audit_logger import _pending, capture_audit_request

        class BrokenDb:
            def create_audit_log(self, **_kwargs):
                raise RuntimeError("boom")

        async def drive():
            gen = capture_audit_request(
                type("R", (), {"app": None, "client": None})()
            )
            await gen.asend(None)
            _pending.get().append((BrokenDb(), {
                "event_type": AuditEventType.AUTH_LOGOUT,
                "user_id": None, "resource_type": "auth",
                "resource_id": None, "ip_address": None, "metadata": None,
            }))
            try:
                await gen.asend(None)
            except StopAsyncIteration:
                pass

        asyncio.run(drive())

        assert _pending.get() is None, "the pending buffer leaked past the request"


class TestTaxonomyCoversTheWiredEvents:
    @pytest.mark.parametrize(
        "name",
        [
            "AUTH_LOGIN_SUCCESS",
            "AUTH_LOGIN_FAILED",
            "AUTH_LOGOUT",
            "USER_CREATED",
            "API_KEY_CREATED",
            "API_KEY_REVOKED",
        ],
    )
    def test_event_type_exists(self, name):
        assert hasattr(AuditEventType, name)
