"""A key never grants more than its owner currently holds (issue #898 / P0.4).

The creation-time guard in ``api_key_router`` blocks a non-superuser from
*minting* an admin key, but that alone leaves two holes:

- keys already persisted with ``admin`` before the guard existed (every
  pre-#898 database — any signed-in user could mint one), and
- a key whose owner is later demoted, which would keep admin forever.

``get_api_key_auth`` therefore clamps the stored scopes against the owner's
live ``is_superuser`` on every request. That is continuous, needs no migration,
and makes a demotion take effect immediately.
"""

import pytest

from codeframe.auth.api_keys import SCOPE_ADMIN, SCOPE_READ, SCOPE_WRITE
from codeframe.auth.dependencies import (
    _scopes_within_owner_grant,
    get_api_key_auth,
)
from codeframe.core.api_key_service import ApiKeyService
from codeframe.platform_store.database import Database
from tests.conftest import setup_test_user

pytestmark = pytest.mark.v2


class _FakeState:
    pass


class _FakeApp:
    def __init__(self, db):
        self.state = _FakeState()
        self.state.db = db


class _FakeRequest:
    def __init__(self, db):
        self.app = _FakeApp(db)
        self.state = _FakeState()


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    database = Database(tmp_path / "state.db")
    database.initialize()
    setup_test_user(database, user_id=1)  # is_superuser = 0
    yield database
    database.close()


def _set_superuser(db, value):
    db.conn.execute("UPDATE users SET is_superuser = ? WHERE id = 1", (int(value),))
    db.conn.commit()


async def _resolve(db, key):
    return await get_api_key_auth(api_key=key, request=_FakeRequest(db))


class TestOwnerScopeClamp:
    @pytest.mark.asyncio
    async def test_admin_dropped_when_owner_is_not_superuser(self, db):
        key = ApiKeyService(db).create_api_key(
            user_id=1, name="legacy", scopes=[SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]
        )

        auth = await _resolve(db, key.key)

        assert auth is not None
        assert SCOPE_ADMIN not in auth["scopes"]
        # The rest of the key still works — it is clamped, not revoked.
        assert auth["scopes"] == [SCOPE_READ, SCOPE_WRITE]

    @pytest.mark.asyncio
    async def test_admin_honored_when_owner_is_superuser(self, db):
        key = ApiKeyService(db).create_api_key(
            user_id=1, name="legit", scopes=[SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]
        )
        _set_superuser(db, True)

        auth = await _resolve(db, key.key)

        assert SCOPE_ADMIN in auth["scopes"]

    @pytest.mark.asyncio
    async def test_demotion_takes_effect_immediately(self, db):
        """The case a one-time migration could never cover."""
        key = ApiKeyService(db).create_api_key(
            user_id=1, name="k", scopes=[SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]
        )
        _set_superuser(db, True)
        assert SCOPE_ADMIN in (await _resolve(db, key.key))["scopes"]

        _set_superuser(db, False)

        assert SCOPE_ADMIN not in (await _resolve(db, key.key))["scopes"]

    @pytest.mark.asyncio
    async def test_non_admin_key_is_untouched(self, db):
        key = ApiKeyService(db).create_api_key(
            user_id=1, name="rw", scopes=[SCOPE_READ, SCOPE_WRITE]
        )

        assert (await _resolve(db, key.key))["scopes"] == [SCOPE_READ, SCOPE_WRITE]


class TestClampFailsClosed:
    """The clamp is exercised directly here: an *orphan* key is unreachable (a
    foreign key on ``api_keys.user_id`` guarantees the owner row exists), so the
    branches worth pinning are the ones a real DB can still produce."""

    def _key_record(self):
        return {
            "id": "k1",
            "user_id": 1,
            "scopes": [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
        }

    def test_unreadable_owner_drops_admin(self):
        """A transient read failure must drop admin, not grant it."""

        class _Boom:
            class conn:
                @staticmethod
                def execute(*_a, **_k):
                    raise RuntimeError("transient DB failure")

        scopes = _scopes_within_owner_grant(_Boom(), self._key_record())

        assert scopes == [SCOPE_READ, SCOPE_WRITE]

    def test_absent_owner_row_drops_admin(self):
        class _NoRow:
            class conn:
                @staticmethod
                def execute(*_a, **_k):
                    return type("C", (), {"fetchone": staticmethod(lambda: None)})()

        scopes = _scopes_within_owner_grant(_NoRow(), self._key_record())

        assert SCOPE_ADMIN not in scopes
