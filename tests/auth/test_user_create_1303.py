"""``cf auth user-create`` (#1303): the only way to add a second account.

HTTP registration closes after the first user, so without this a deployment
could never have more than one login.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi_users.password import PasswordHelper
from typer.testing import CliRunner

from codeframe.auth import router as auth_router
from codeframe.auth.manager import reset_auth_engine
from codeframe.cli import auth_commands
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

EMAIL = "second@example.com"
PASSWORD = "correct-horse-battery"


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.delenv("CODEFRAME_BOOTSTRAP_TOKEN", raising=False)
    reset_auth_engine()
    database = Database(db_path)
    database.initialize()
    monkeypatch.setattr(auth_commands, "get_db_for_cli", lambda: database)
    yield database
    reset_auth_engine()


def _create(*args, password=PASSWORD, email=EMAIL):
    return CliRunner().invoke(
        auth_commands.auth_app, ["user-create", email, "--password", password, *args]
    )


def _row(db, email=EMAIL):
    return db.conn.execute(
        "SELECT hashed_password, is_active, is_superuser, is_verified, name "
        "FROM users WHERE email = ?",
        (email,),
    ).fetchone()


def test_creates_a_regular_active_user(db):
    result = _create("--name", "Second User")
    assert result.exit_code == 0, result.output
    hashed, active, superuser, verified, name = _row(db)
    assert PasswordHelper().verify_and_update(PASSWORD, hashed)[0]
    assert (active, superuser, verified, name) == (1, 0, 0, "Second User")
    assert "admin" not in result.output.lower().replace("administrator", "")


def test_admin_flag_makes_a_superuser(db):
    result = _create("--admin")
    assert result.exit_code == 0, result.output
    assert _row(db)[2] == 1
    assert "admin" in result.output.lower()


def test_email_is_normalized(db):
    assert _create(email="  Second@Example.COM ").exit_code == 0
    assert _row(db, EMAIL) is not None


@pytest.mark.parametrize("dup", [EMAIL, "SECOND@example.com"])
def test_duplicate_email_is_refused_case_insensitively(db, dup):
    assert _create().exit_code == 0
    result = _create(email=dup)
    assert result.exit_code == 1
    assert db.conn.execute("SELECT COUNT(*) FROM users WHERE lower(email) = ?", (EMAIL,)).fetchone()[0] == 1


def test_weak_password_is_refused_and_nothing_is_written(db):
    result = _create(password="short")
    assert result.exit_code == 1
    assert "12" in result.output
    assert _row(db) is None


@pytest.mark.parametrize("email", ["not-an-email", "@", "a@", "@b"])
def test_invalid_email_is_refused(db, email):
    assert _create(email=email).exit_code == 1


def test_created_user_can_log_in_through_the_real_router(db):
    assert _create().exit_code == 0
    app = FastAPI()
    app.include_router(auth_router.router)
    client = TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 40000))
    resp = client.post("/auth/jwt/login", data={"username": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    bad = client.post("/auth/jwt/login", data={"username": EMAIL, "password": "wrong-password-xx"})
    assert bad.status_code == 400
