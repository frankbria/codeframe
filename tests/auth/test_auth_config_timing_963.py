"""Auth configuration timing and auth-disabled degradations (issue #963).

Five defects:

1. ``JWT_LIFETIME_SECONDS`` was read at import time — before ``.env`` is
   loaded — so an operator who set it the documented way silently got the 24h
   default. A security control that does not apply and never says so.
2. ``get_async_session_maker`` cached a session maker that went stale after
   ``DATABASE_PATH`` changed: it never consulted the engine's path-change
   check, so it kept handing out a maker bound to the old database.
3. With ``CODEFRAME_AUTH_REQUIRED=false`` the synthetic principal carried
   ``user_id=None``, so ``/api/auth/api-keys`` returned an empty list, 404'd on
   revoke, and 401'd on create — the first thing a self-hosted evaluator tries,
   broken three ways.
4. The API-key auth fallback constructed and schema-initialised a brand-new
   ``Database`` under ``os.getcwd()`` per request, littering SQLite files.
5. Logout is a no-op. Documented as a known limitation (see the test at the
   bottom), which the acceptance criteria allow.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


# ─────────────────────────────────────────────────────────────────────────────
# 1. JWT lifetime is read when the strategy is built
# ─────────────────────────────────────────────────────────────────────────────


class TestJwtLifetimeIsReadLate:
    def test_env_set_after_import_is_observed(self, monkeypatch):
        from codeframe.auth import manager

        # The module is already imported — exactly the situation an operator
        # is in when .env is loaded during server startup.
        monkeypatch.setenv("JWT_LIFETIME_SECONDS", "3600")
        strategy = manager.get_jwt_strategy()

        assert strategy.lifetime_seconds == 3600

    def test_default_is_still_24h(self, monkeypatch):
        from codeframe.auth import manager

        monkeypatch.delenv("JWT_LIFETIME_SECONDS", raising=False)
        assert manager.get_jwt_strategy().lifetime_seconds == 86400

    def test_an_unparseable_value_falls_back_to_the_default(self, monkeypatch):
        from codeframe.auth import manager

        monkeypatch.setenv("JWT_LIFETIME_SECONDS", "not-a-number")
        assert manager.get_jwt_strategy().lifetime_seconds == 86400

    def test_no_module_level_constant_freezes_the_value(self):
        """A module-level int would be re-frozen at the next import."""
        from codeframe.auth import manager

        source = Path(manager.__file__).read_text()
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("JWT_LIFETIME_SECONDS ="):
                assert "getenv" not in stripped, (
                    "lifetime is still resolved at import time: " + stripped
                )


# ─────────────────────────────────────────────────────────────────────────────
# 2. The session maker follows DATABASE_PATH
# ─────────────────────────────────────────────────────────────────────────────


class TestSessionMakerFollowsDatabasePath:
    def test_changing_database_path_rebuilds_the_maker(self, tmp_path, monkeypatch):
        from codeframe.auth import manager

        manager.reset_auth_engine()

        first = tmp_path / "a.db"
        monkeypatch.setenv("DATABASE_PATH", str(first))
        maker_a = manager.get_async_session_maker()
        engine_a = manager.get_engine()

        second = tmp_path / "b.db"
        monkeypatch.setenv("DATABASE_PATH", str(second))
        maker_b = manager.get_async_session_maker()
        engine_b = manager.get_engine()

        assert maker_a is not maker_b, "stale session maker reused after path change"
        assert engine_a is not engine_b
        assert str(second) in str(engine_b.url)

        manager.reset_auth_engine()

    def test_same_path_reuses_the_maker(self, tmp_path, monkeypatch):
        from codeframe.auth import manager

        manager.reset_auth_engine()
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.db"))

        assert manager.get_async_session_maker() is manager.get_async_session_maker()

        manager.reset_auth_engine()


# ─────────────────────────────────────────────────────────────────────────────
# 3. With auth off, all three API-key operations work
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def auth_off_client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from codeframe.auth import router as auth_router
    from codeframe.auth.manager import reset_auth_engine
    from codeframe.platform_store.database import Database
    from tests.conftest import setup_test_user

    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    setup_test_user(db, user_id=1)

    app = FastAPI()
    app.include_router(auth_router.router)
    app.state.db = db
    yield TestClient(app, raise_server_exceptions=False)
    db.close()
    reset_auth_engine()


class TestApiKeysWorkWithAuthDisabled:
    """The first thing a self-hosted evaluator tries (#963)."""

    def test_create_succeeds(self, auth_off_client):
        resp = auth_off_client.post(
            "/api/auth/api-keys", json={"name": "local", "scopes": ["read"]}
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["key"].startswith("cf_")

    def test_list_returns_the_key_that_was_just_created(self, auth_off_client):
        auth_off_client.post(
            "/api/auth/api-keys", json={"name": "local", "scopes": ["read"]}
        )

        resp = auth_off_client.get("/api/auth/api-keys")
        assert resp.status_code == 200, resp.text
        names = [k["name"] for k in resp.json()]
        assert names == ["local"], f"list did not see the key: {resp.json()}"

    def test_revoke_succeeds(self, auth_off_client):
        created = auth_off_client.post(
            "/api/auth/api-keys", json={"name": "local", "scopes": ["read"]}
        ).json()

        resp = auth_off_client.delete(f"/api/auth/api-keys/{created['id']}")
        assert resp.status_code == 200, resp.text

        remaining = auth_off_client.get("/api/auth/api-keys").json()
        assert [k for k in remaining if k["is_active"]] == []

    def test_the_principal_is_stable_across_requests(self, auth_off_client):
        """Two creates must land under the same identity, or list breaks."""
        auth_off_client.post(
            "/api/auth/api-keys", json={"name": "one", "scopes": ["read"]}
        )
        auth_off_client.post(
            "/api/auth/api-keys", json={"name": "two", "scopes": ["read"]}
        )

        listed = auth_off_client.get("/api/auth/api-keys").json()
        assert sorted(k["name"] for k in listed) == ["one", "two"]

    def test_admin_key_creation_still_follows_the_resolved_account(
        self, auth_off_client
    ):
        """Admin is a property of the user row, not of auth being off (#898).

        The fixture's operator is is_superuser=0, so an admin-scoped key is
        refused — the same rule as with auth on. A real install resolves to the
        seeded admin@localhost row (is_superuser=1); covered below.
        """
        resp = auth_off_client.post(
            "/api/auth/api-keys", json={"name": "adm", "scopes": ["read", "admin"]}
        )
        assert resp.status_code == 403, resp.text

    def test_a_superuser_operator_may_mint_an_admin_key(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from codeframe.auth import router as auth_router
        from codeframe.auth.manager import reset_auth_engine
        from codeframe.platform_store.database import Database

        db_path = tmp_path / "state.db"
        monkeypatch.setenv("DATABASE_PATH", str(db_path))
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        reset_auth_engine()

        db = Database(db_path)
        db.initialize()
        db.conn.execute(
            "INSERT OR REPLACE INTO users (id, email, name, hashed_password, "
            "is_active, is_superuser, is_verified, email_verified) "
            "VALUES (1, 'admin@localhost', 'Admin', '!DISABLED!', 1, 1, 1, 1)"
        )
        db.conn.commit()

        app = FastAPI()
        app.include_router(auth_router.router)
        app.state.db = db
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/auth/api-keys", json={"name": "adm", "scopes": ["read", "admin"]}
        )
        db.close()
        reset_auth_engine()

        assert resp.status_code == 201, resp.text


class TestAuthOffKeysDoNotSurviveIntoAnExposedDeployment:
    """A key minted with auth off must not become a durable admin credential.

    Found in review of this issue: with auth off, key creation is attributed to
    the local operator, which on a fresh install is the seeded
    ``admin@localhost`` placeholder — is_active=1, is_superuser=1, and a
    password nobody can use. Turn auth on afterwards and that key kept working,
    because key auth otherwise checks only is_active/is_superuser. A durable
    admin credential created without anyone authenticating.
    """

    def _db_with(self, tmp_path, *, real_account: bool):
        from codeframe.auth.manager import DISABLED_PASSWORD, reset_auth_engine
        from codeframe.platform_store.database import Database

        db_path = tmp_path / "state.db"
        reset_auth_engine()
        db = Database(db_path)
        db.initialize()
        db.conn.execute(
            "INSERT OR REPLACE INTO users (id, email, name, hashed_password, "
            "is_active, is_superuser, is_verified, email_verified) "
            "VALUES (1, 'admin@localhost', 'Admin', ?, 1, 1, 1, 1)",
            (DISABLED_PASSWORD,),
        )
        if real_account:
            db.conn.execute(
                "INSERT OR REPLACE INTO users (id, email, name, hashed_password, "
                "is_active, is_superuser, is_verified, email_verified) "
                "VALUES (2, 'real@example.com', 'Real', '$2b$12$abcdefghij', 1, 1, 1, 1)"
            )
        db.conn.commit()
        return db, db_path

    @pytest.mark.asyncio
    async def test_a_placeholder_owned_key_is_refused_once_auth_is_on(
        self, tmp_path, monkeypatch
    ):
        from unittest.mock import MagicMock

        from codeframe.auth import dependencies
        from codeframe.core.api_key_service import ApiKeyService

        db, db_path = self._db_with(tmp_path, real_account=False)
        monkeypatch.setenv("DATABASE_PATH", str(db_path))
        created = ApiKeyService(db).create_api_key(
            user_id=1, name="local", scopes=["read", "admin"]
        )

        request = MagicMock()
        request.app.state.db = db
        request.state.db = db

        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        assert await dependencies.get_api_key_auth(
            request=request, api_key=created.key
        ) is not None, "the key must still work in the mode that created it"

        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        assert await dependencies.get_api_key_auth(
            request=request, api_key=created.key
        ) is None, "a placeholder-owned key survived into an authenticated deployment"

        db.close()

    @pytest.mark.asyncio
    async def test_a_real_accounts_key_is_unaffected(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock

        from codeframe.auth import dependencies
        from codeframe.core.api_key_service import ApiKeyService

        db, db_path = self._db_with(tmp_path, real_account=True)
        monkeypatch.setenv("DATABASE_PATH", str(db_path))
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        created = ApiKeyService(db).create_api_key(
            user_id=2, name="real", scopes=["read"]
        )

        request = MagicMock()
        request.app.state.db = db
        request.state.db = db

        assert await dependencies.get_api_key_auth(
            request=request, api_key=created.key
        ) is not None

        db.close()

    @pytest.mark.asyncio
    async def test_the_local_operator_prefers_a_login_capable_account(
        self, tmp_path, monkeypatch
    ):
        from codeframe.auth import dependencies
        from codeframe.auth.manager import reset_auth_engine

        db, db_path = self._db_with(tmp_path, real_account=True)
        db.close()
        monkeypatch.setenv("DATABASE_PATH", str(db_path))
        reset_auth_engine()

        operator = await dependencies._local_operator_user()
        assert operator is not None
        assert operator.id == 2, "resolved the disabled placeholder over a real account"

        reset_auth_engine()


# ─────────────────────────────────────────────────────────────────────────────
# 4. The API-key fallback never writes a database into cwd
# ─────────────────────────────────────────────────────────────────────────────


class TestApiKeyFallbackDoesNotLitter:
    def test_no_database_is_constructed_at_cwd(self):
        """The cwd-relative default is what created stray .codeframe dirs."""
        import inspect

        from codeframe.auth import dependencies

        source = inspect.getsource(dependencies)
        # Check executable lines only — the removal is explained in a comment
        # that necessarily names the old call (same trap as #962's jinja test).
        offenders = [
            line.strip()
            for line in source.splitlines()
            if "os.getcwd()" in line.split("#", 1)[0]
        ]
        assert offenders == [], (
            f"API-key auth still resolves a database path from the cwd: {offenders}"
        )

    @pytest.mark.asyncio
    async def test_request_without_an_app_database_creates_no_files(self, tmp_path):
        from unittest.mock import MagicMock

        from codeframe.auth import dependencies

        cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            request = MagicMock()
            request.app.state.db = None
            request.state.db = None
            # A syntactically valid key that cannot resolve to anything.
            await dependencies.get_api_key_auth(
                request=request, api_key="cf_deadbeefdeadbeefdeadbeef"
            )
        except Exception:
            pass  # Rejecting the key is fine; creating files is not.
        finally:
            os.chdir(cwd)

        stray = list(tmp_path.rglob("*.db"))
        assert stray == [], f"request created database files: {stray}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Logout's limitation is documented
# ─────────────────────────────────────────────────────────────────────────────


class TestLogoutLimitationIsDocumented:
    def test_the_no_op_is_stated_where_a_reader_will_find_it(self):
        from codeframe.auth import manager

        source = Path(manager.__file__).read_text().lower()
        assert "logout" in source
        # The mitigating control must be named alongside it, not left implicit.
        window = source[source.index("logout") - 2000 : source.index("logout") + 3000]
        assert "jwt_lifetime_seconds" in window or "lifetime" in window
