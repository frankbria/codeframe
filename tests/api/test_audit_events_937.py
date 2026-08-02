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
