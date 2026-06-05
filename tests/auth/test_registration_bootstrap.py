"""Registration bootstrap gating (issue #336).

/auth/register is allowed only while ZERO users exist. Once any user exists,
it returns 403. Implemented via a dependency on the register router include.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth import router as auth_router
from codeframe.auth.manager import reset_auth_engine
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    db.close()

    app = FastAPI()
    app.include_router(auth_router.router)
    client = TestClient(app, raise_server_exceptions=False)
    client.db_path = db_path
    yield client
    reset_auth_engine()


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
        resp = auth_client.post(
            "/auth/register",
            json={"email": "first@example.com", "password": "secret123"},
        )
        # Bootstrap allowed: registration proceeds (not gated with 403).
        assert resp.status_code != 403, resp.text
        assert resp.status_code in (200, 201), resp.text

    def test_register_forbidden_once_a_real_user_exists(self, auth_client):
        _add_real_user(auth_client.db_path)
        resp = auth_client.post(
            "/auth/register",
            json={"email": "second@example.com", "password": "secret123"},
        )
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

        async def _register(client, email):
            resp = await client.post(
                "/auth/register",
                json={"email": email, "password": "secret123"},
            )
            statuses.append(resp.status_code)

        async def _run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                async with anyio.create_task_group() as tg:
                    tg.start_soon(_register, client, "racer-a@example.com")
                    tg.start_soon(_register, client, "racer-b@example.com")

        anyio.run(_run)

        assert sorted(statuses) == [201, 403] or sorted(statuses) == [200, 403], (
            f"expected exactly one success and one 403, got {statuses}"
        )
