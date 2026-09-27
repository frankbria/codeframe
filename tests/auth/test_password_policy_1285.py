"""Password policy on the sole superuser (#1285).

The bootstrap account holds admin scope and terminal access, yet it could be
registered with "a", emptied via ``PATCH /users/me {"password": ""}``, and its
password or email changed with nothing but a (24h, unrevocable) JWT — so a
leaked token became a permanent takeover.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth import router as auth_router
from codeframe.auth.manager import reset_auth_engine
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

EMAIL = "operator@example.com"
PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "another-long-passphrase"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.delenv("CODEFRAME_BOOTSTRAP_TOKEN", raising=False)
    reset_auth_engine()
    db = Database(db_path)
    db.initialize()
    db.close()

    app = FastAPI()
    app.include_router(auth_router.router)
    yield TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 40000))
    reset_auth_engine()


def _register(client, password=PASSWORD, email=EMAIL):
    return client.post("/auth/register", json={"email": email, "password": password})


def _login(client, password=PASSWORD, email=EMAIL):
    return client.post("/auth/jwt/login", data={"username": email, "password": password})


@pytest.fixture
def session(client):
    """A registered bootstrap superuser: (client, auth headers, user id)."""
    reg = _register(client)
    assert reg.status_code == 201, reg.text
    token = _login(client).json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}, reg.json()["id"]


class TestRegistration:
    @pytest.mark.parametrize("password", ["a", "", "elevenchars"])
    def test_a_short_password_is_refused(self, client, password):
        resp = _register(client, password=password)
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"]["code"] == "REGISTER_INVALID_PASSWORD"

    def test_the_email_as_password_is_refused(self, client):
        resp = _register(client, password=EMAIL.upper())
        assert resp.status_code == 400, resp.text

    def test_twelve_characters_is_enough(self, client):
        resp = _register(client, password="twelve-chars")
        assert resp.status_code == 201, resp.text
        assert resp.json()["is_superuser"] is True


def _routes(user_id):
    return ["/users/me", f"/users/{user_id}"]


class TestPatchPasswordPolicy:
    @pytest.mark.parametrize("route_index", [0, 1], ids=["me", "by-id"])
    @pytest.mark.parametrize("password", ["", "short"])
    def test_a_short_password_is_refused(self, session, route_index, password):
        client, headers, uid = session
        resp = client.patch(
            _routes(uid)[route_index],
            json={"password": password, "current_password": PASSWORD},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert _login(client).status_code == 200, "the old password must still work"

    @pytest.mark.parametrize("route_index", [0, 1], ids=["me", "by-id"])
    def test_a_password_change_needs_the_current_password(self, session, route_index):
        client, headers, uid = session
        resp = client.patch(
            _routes(uid)[route_index], json={"password": NEW_PASSWORD}, headers=headers
        )
        assert resp.status_code == 400, resp.text
        assert _login(client, NEW_PASSWORD).status_code == 400

    @pytest.mark.parametrize("route_index", [0, 1], ids=["me", "by-id"])
    def test_a_wrong_current_password_is_refused(self, session, route_index):
        client, headers, uid = session
        resp = client.patch(
            _routes(uid)[route_index],
            json={"password": NEW_PASSWORD, "current_password": "not-the-password"},
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert _login(client, NEW_PASSWORD).status_code == 400

    def test_the_right_current_password_changes_it(self, session):
        client, headers, _ = session
        resp = client.patch(
            "/users/me",
            json={"password": NEW_PASSWORD, "current_password": PASSWORD},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert "current_password" not in resp.json()
        assert _login(client, NEW_PASSWORD).status_code == 200
        assert _login(client).status_code == 400


class TestPatchEmail:
    @pytest.mark.parametrize("route_index", [0, 1], ids=["me", "by-id"])
    def test_an_email_change_needs_the_current_password(self, session, route_index):
        client, headers, uid = session
        resp = client.patch(
            _routes(uid)[route_index], json={"email": "thief@example.com"}, headers=headers
        )
        assert resp.status_code == 400, resp.text
        assert _login(client).status_code == 200

    def test_the_right_current_password_changes_it(self, session):
        client, headers, _ = session
        resp = client.patch(
            "/users/me",
            json={"email": "moved@example.com", "current_password": PASSWORD},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert _login(client, email="moved@example.com").status_code == 200

    def test_resending_the_same_email_is_not_a_change(self, session):
        client, headers, _ = session
        resp = client.patch("/users/me", json={"email": EMAIL}, headers=headers)
        assert resp.status_code == 200, resp.text

    def test_other_fields_need_no_current_password(self, session):
        client, headers, _ = session
        resp = client.patch("/users/me", json={"name": "Operator"}, headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Operator"


class TestOfflineSetPassword:
    """``cf auth set-password`` writes the hash directly — the same policy applies."""

    def test_a_short_password_is_refused(self, monkeypatch):
        from typer.testing import CliRunner

        from codeframe.cli import auth_commands

        monkeypatch.setattr(
            auth_commands, "get_db_for_cli", lambda: pytest.fail("must refuse before the DB")
        )
        result = CliRunner().invoke(
            auth_commands.auth_app, ["set-password", EMAIL, "--password", "short"]
        )
        assert result.exit_code == 1
        assert "12" in result.output
