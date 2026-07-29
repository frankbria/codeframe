"""API-key auth stops writing to the database on every request (#902 / P0.8).

Every API-key request did a SELECT *and* an UPDATE+COMMIT of ``last_used_at``,
against a lock with ``busy_timeout=5000`` — a database **writer** per
authenticated call, on the event loop, purely to refresh a timestamp nothing
reads at per-request resolution.

Resolution now runs on a worker thread, and the timestamp refresh is coalesced
to at most once per key per window.
"""

import pytest

from codeframe.auth import dependencies as deps
from codeframe.auth.api_keys import SCOPE_READ, SCOPE_WRITE
from codeframe.core.api_key_service import ApiKeyService
from codeframe.platform_store.database import Database
from tests.conftest import setup_test_user

pytestmark = pytest.mark.v2


class _State:
    pass


class _App:
    def __init__(self, db):
        self.state = _State()
        self.state.db = db


class _Request:
    def __init__(self, db):
        self.app = _App(db)
        self.state = _State()


@pytest.fixture(autouse=True)
def clean_coalesce_state():
    deps._last_used_writes.clear()
    yield
    deps._last_used_writes.clear()


@pytest.fixture
def db_and_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    db = Database(tmp_path / "state.db")
    db.initialize()
    setup_test_user(db, user_id=1)
    key = ApiKeyService(db).create_api_key(
        user_id=1, name="k", scopes=[SCOPE_READ, SCOPE_WRITE]
    )
    yield db, key
    db.close()


class TestLastUsedCoalescing:
    @pytest.mark.asyncio
    async def test_repeat_requests_write_once(self, db_and_key, monkeypatch):
        db, key = db_and_key
        writes = []
        real = db.api_keys.update_last_used
        monkeypatch.setattr(
            db.api_keys,
            "update_last_used",
            lambda key_id: (writes.append(key_id), real(key_id))[1],
        )

        for _ in range(5):
            auth = await deps.get_api_key_auth(api_key=key.key, request=_Request(db))
            assert auth is not None

        assert len(writes) == 1, (
            f"{len(writes)} database writes for 5 authenticated requests"
        )

    @pytest.mark.asyncio
    async def test_the_window_expires(self, db_and_key, monkeypatch):
        db, key = db_and_key
        writes = []
        real = db.api_keys.update_last_used
        monkeypatch.setattr(
            db.api_keys,
            "update_last_used",
            lambda key_id: (writes.append(key_id), real(key_id))[1],
        )

        await deps.get_api_key_auth(api_key=key.key, request=_Request(db))
        # Age the recorded write past the window rather than sleeping for it.
        for key_id in list(deps._last_used_writes):
            deps._last_used_writes[key_id] -= deps._LAST_USED_COALESCE_SECONDS + 1
        await deps.get_api_key_auth(api_key=key.key, request=_Request(db))

        assert len(writes) == 2, "the timestamp must still refresh once per window"

    @pytest.mark.asyncio
    async def test_the_timestamp_is_still_recorded(self, db_and_key):
        """Coalescing must not mean 'never write'."""
        db, key = db_and_key

        await deps.get_api_key_auth(api_key=key.key, request=_Request(db))

        assert db.api_keys.get_by_id(key.id)["last_used_at"] is not None

    @pytest.mark.asyncio
    async def test_distinct_keys_are_tracked_separately(self, db_and_key, monkeypatch):
        db, key = db_and_key
        second = ApiKeyService(db).create_api_key(
            user_id=1, name="k2", scopes=[SCOPE_READ]
        )
        writes = []
        real = db.api_keys.update_last_used
        monkeypatch.setattr(
            db.api_keys,
            "update_last_used",
            lambda key_id: (writes.append(key_id), real(key_id))[1],
        )

        await deps.get_api_key_auth(api_key=key.key, request=_Request(db))
        await deps.get_api_key_auth(api_key=second.key, request=_Request(db))

        assert sorted(writes) == sorted([key.id, second.id])


class TestResolutionIsOffloaded:
    @pytest.mark.asyncio
    async def test_the_blocking_half_runs_on_a_worker_thread(
        self, db_and_key, monkeypatch
    ):
        """The bcrypt verify plus SQLite reads must not sit on the event loop."""
        import threading

        db, key = db_and_key
        seen = {}
        real = deps._resolve_api_key

        def _record(api_key, request):
            seen["thread"] = threading.current_thread()
            return real(api_key, request)

        monkeypatch.setattr(deps, "_resolve_api_key", _record)

        loop_thread = threading.current_thread()
        auth = await deps.get_api_key_auth(api_key=key.key, request=_Request(db))

        assert auth is not None
        assert seen["thread"] is not loop_thread
