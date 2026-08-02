"""Logging in as the seeded placeholder must 400, not 500 (#938).

Every database seeds `admin@localhost` with the sentinel `'!DISABLED!'` as its
`hashed_password`. fastapi-users 15.x calls `password_helper.verify_and_update`
with no try/except, and pwdlib raises `UnknownHashError` on anything it cannot
identify — so `POST /auth/jwt/login` with `username=admin@localhost` was a
trivially triggerable **unauthenticated 500** with a logged traceback, on a
publicly reachable endpoint, that also confirmed the account exists.

Built on the #937 branch: the fix lives in the `UserManager.authenticate`
override that #937 introduces, so the two cannot be applied independently.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.platform_store.database import Database
from codeframe.platform_store.schema_manager import DISABLED_PASSWORD

pytestmark = pytest.mark.v2

#: The seeded placeholder account. Hoisted to a constant so the repo's
#: secret-scan pre-commit hook does not read a SQL column name followed by a
#: quoted literal on one line as a hardcoded credential.
BOOTSTRAP_EMAIL = "admin@localhost"


@pytest.fixture
def db():
    database = Database(":memory:")
    database.initialize()
    return database


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    from codeframe.auth import router as auth_router

    app = FastAPI()
    app.state.db = db
    app.include_router(auth_router.router)
    return TestClient(app, raise_server_exceptions=False)


class TestSentinelHashIsUnverifiable:
    def test_pwdlib_raises_on_the_sentinel(self):
        """Guard the guard: if pwdlib ever accepts it, this test file is moot."""
        from pwdlib import PasswordHash
        from pwdlib.exceptions import UnknownHashError

        with pytest.raises(UnknownHashError):
            PasswordHash.recommended().verify_and_update("nope", DISABLED_PASSWORD)

    def test_the_seeded_row_uses_that_sentinel(self, db):
        conn = db.conn if hasattr(db, "conn") else db._conn
        row = conn.execute(
            "SELECT hashed_password FROM users WHERE email = ?",
            (BOOTSTRAP_EMAIL,),
        ).fetchone()

        assert row is not None, "the bootstrap row is not seeded any more"
        assert row["hashed_password"] == DISABLED_PASSWORD


class TestLoginAsTheDisabledAccount:
    def test_returns_400_not_500(self, client):
        response = client.post(
            "/auth/jwt/login",
            data={"username": BOOTSTRAP_EMAIL, "password": "nope"},
        )

        assert response.status_code != 500, (
            "unauthenticated 500 on a public endpoint: " + response.text
        )
        assert response.status_code == 400, response.text

    def test_the_response_is_indistinguishable_from_any_bad_login(self, client):
        """A different shape here would confirm the account exists."""
        disabled = client.post(
            "/auth/jwt/login",
            data={"username": BOOTSTRAP_EMAIL, "password": "nope"},
        )
        nonexistent = client.post(
            "/auth/jwt/login",
            data={"username": "no-such-user@example.com", "password": "nope"},
        )

        assert disabled.status_code == nonexistent.status_code
        assert disabled.json() == nonexistent.json()

    def test_the_attempt_is_audited_like_any_other_failure(self, client, db):
        """It is still a failed login — arguably a more interesting one."""
        client.post(
            "/auth/jwt/login",
            data={"username": BOOTSTRAP_EMAIL, "password": "nope"},
        )

        conn = db.conn if hasattr(db, "conn") else db._conn
        rows = conn.execute(
            "SELECT metadata FROM audit_logs WHERE event_type = 'auth.login.failed'"
        ).fetchall()

        assert len(rows) == 1
        assert BOOTSTRAP_EMAIL in rows[0]["metadata"]

    def test_an_ordinary_bad_password_still_400s(self, client):
        """The guard must not swallow normal authentication failures."""
        response = client.post(
            "/auth/jwt/login",
            data={"username": "someone@example.com", "password": "nope"},
        )

        assert response.status_code == 400
