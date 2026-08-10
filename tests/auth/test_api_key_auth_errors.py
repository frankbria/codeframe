"""Error-path tests for get_api_key_auth (issue #760).

Two regressions are guarded here:
  1. An unexpected DB failure must be surfaced at warning+ (not swallowed at
     debug), so a valid key degrading to 401 leaves a visible root cause.
  2. The per-request fallback Database connection must be closed — there is no
     cleanup middleware, so leaving it open leaks a connection every request.

Following TDD: written before the fix.
"""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from codeframe.auth.api_keys import generate_api_key
from codeframe.auth.dependencies import get_api_key_auth


def _fake_request(app_db=None, req_db=None):
    """Minimal stand-in for a FastAPI Request with app/request state."""
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db=app_db)),
        state=SimpleNamespace(db=req_db),
    )


@pytest.mark.asyncio
async def test_transient_db_error_surfaced_at_warning_plus(caplog):
    """A DB failure during lookup is logged at ERROR (not DEBUG) and returns None."""
    full_key, _hash, _prefix = generate_api_key()

    db = MagicMock()
    db.api_keys.get_all_by_prefix.side_effect = RuntimeError("database is locked")
    request = _fake_request(app_db=db)

    with caplog.at_level(logging.DEBUG, logger="codeframe.auth.dependencies"):
        result = await get_api_key_auth(api_key=full_key, request=request)

    assert result is None
    # The failure must be visible in normal logs, not hidden at DEBUG.
    surfaced = [
        r for r in caplog.records if r.levelno >= logging.WARNING and "database is locked" in r.getMessage()
    ]
    assert surfaced, "transient DB error must be logged at WARNING or above"


@pytest.mark.asyncio
async def test_fallback_db_is_cached_not_rebuilt_per_request(monkeypatch, tmp_path):
    """The fallback is now process-wide, keyed on DATABASE_PATH (#963).

    This replaced ``test_fallback_db_is_closed``, which asserted the fallback
    Database was constructed and closed on every request. That per-request
    construct-initialise-close cycle was the defect: it also defaulted to
    ``os.getcwd()``, so a server started outside a workspace scattered SQLite
    files and then authenticated against the empty database it had just made.
    """
    from codeframe.auth.dependencies import reset_fallback_db

    fallback = MagicMock()
    fallback.api_keys.get_all_by_prefix.return_value = []  # key not found

    ctor = MagicMock(return_value=fallback)
    monkeypatch.setattr("codeframe.platform_store.database.Database", ctor)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    reset_fallback_db()

    full_key, _hash, _prefix = generate_api_key()
    request = _fake_request(app_db=None, req_db=None)

    assert await get_api_key_auth(api_key=full_key, request=request) is None
    assert await get_api_key_auth(api_key=full_key, request=request) is None

    # Built once across both requests, and not closed between them.
    ctor.assert_called_once()
    fallback.close.assert_not_called()

    reset_fallback_db()


@pytest.mark.asyncio
async def test_no_database_path_refuses_rather_than_using_cwd(monkeypatch, tmp_path):
    """Without DATABASE_PATH the key is refused — no cwd default (#963)."""
    from codeframe.auth.dependencies import reset_fallback_db

    ctor = MagicMock()
    monkeypatch.setattr("codeframe.platform_store.database.Database", ctor)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    reset_fallback_db()

    full_key, _hash, _prefix = generate_api_key()
    request = _fake_request(app_db=None, req_db=None)

    assert await get_api_key_auth(api_key=full_key, request=request) is None
    ctor.assert_not_called()

    reset_fallback_db()
