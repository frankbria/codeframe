"""Issue #968 — the dead v1 backend layers stay deleted.

The bulk of #968 is deletion, so most of what is worth testing is structural: a
symbol that came back, or a router that got re-mounted, is the regression. The
one behavioural change is the platform-store migration that drops the three
never-queried auth tables — ``accounts``, ``sessions`` and ``verification`` —
which needs a real ``MIGRATIONS`` entry because ``create_schema`` is idempotent
CREATE-IF-NOT-EXISTS against a long-lived ``state.db`` and would otherwise leave
them orphaned forever.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from codeframe.platform_store.database import Database
from codeframe.platform_store.schema_manager import SchemaManager

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEAD_AUTH_TABLES = ("accounts", "sessions", "verification")
#: Note these belong to `sessions`/`accounts`, NOT to the live
#: `interactive_sessions` table, whose own indexes must survive.
DEAD_AUTH_INDEXES = (
    "idx_sessions_user_id",
    "idx_sessions_expires_at",
    "idx_accounts_user_id",
)


def _tables(conn: sqlite3.Connection) -> set:
    return {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _indexes(conn: sqlite3.Connection) -> set:
    return {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }


# --- the migration ----------------------------------------------------------


def test_fresh_database_has_no_dead_auth_tables(tmp_path):
    """A fresh install builds none of the three, and none of their indexes.

    The index half is the sharp edge: ``_create_indexes`` used to build
    ``idx_sessions_user_id`` / ``idx_sessions_expires_at`` *outside* the DDL
    block, so removing only the CREATE TABLE statements would make every fresh
    ``Database.initialize()`` raise ``no such table: sessions``.
    """
    db = Database(tmp_path / "fresh.db")
    db.initialize()
    try:
        assert _tables(db.conn).isdisjoint(DEAD_AUTH_TABLES)
        assert _indexes(db.conn).isdisjoint(DEAD_AUTH_INDEXES)
        # users/api_keys are the live auth surface and must survive.
        assert {"users", "api_keys"} <= _tables(db.conn)
    finally:
        db.close()


def test_legacy_database_gets_the_dead_auth_tables_dropped(tmp_path):
    """A pre-#968 database carrying the three tables is migrated, not left alone."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE "
        "NOT NULL, name TEXT, hashed_password TEXT NOT NULL, is_active INTEGER DEFAULT 1, "
        "is_superuser INTEGER DEFAULT 0, is_verified INTEGER DEFAULT 0, "
        "email_verified INTEGER DEFAULT 0, image TEXT, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE accounts (id TEXT PRIMARY KEY, user_id INTEGER NOT NULL "
        "REFERENCES users(id) ON DELETE CASCADE, account_id TEXT NOT NULL, "
        "provider_id TEXT NOT NULL, password TEXT)"
    )
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, "
        "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "expires_at TIMESTAMP NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE verification (id TEXT PRIMARY KEY, identifier TEXT NOT NULL, "
        "value TEXT NOT NULL, expires_at TIMESTAMP NOT NULL)"
    )
    conn.execute("CREATE INDEX idx_sessions_user_id ON sessions(user_id)")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    db = Database(db_path)
    db.initialize()
    try:
        assert _tables(db.conn).isdisjoint(DEAD_AUTH_TABLES)
        # SQLite drops a table's indexes with the table.
        assert _indexes(db.conn).isdisjoint(DEAD_AUTH_INDEXES)
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == (
            SchemaManager.SCHEMA_VERSION
        )
        assert SchemaManager.SCHEMA_VERSION >= 2
    finally:
        db.close()

    # Idempotent: re-initializing an already-migrated DB is a no-op, not an error.
    again = Database(db_path)
    again.initialize()
    try:
        assert _tables(again.conn).isdisjoint(DEAD_AUTH_TABLES)
    finally:
        again.close()


# --- structural: the deletions stay deleted ---------------------------------


def test_ui_models_keeps_only_the_live_settings_surface():
    from codeframe.ui import models

    for gone in (
        "SourceType",
        "ProjectCreateRequest",
        "ReviewRequest",
        "ProjectResponse",
        "TaskResponse",
        "TaskListResponse",
        "BlockerResponse",
        "BlockerListResponse",
        "CheckpointResponse",
        "ErrorResponse",
    ):
        assert not hasattr(models, gone), f"dead v1 model {gone} is back in ui/models.py"

    # What settings_v2 imports must survive.
    for live in (
        "AGENT_TYPES",
        "KEY_PROVIDERS",
        "AgentSettingsResponse",
        "AgentTypeModelConfig",
        "KeyProvider",
        "KeyStatusResponse",
        "StoreKeyRequest",
        "UpdateAgentSettingsRequest",
        "VerifyKeyRequest",
        "VerifyKeyResponse",
    ):
        assert hasattr(models, live), f"live settings model {live} was deleted"


def test_response_models_keeps_only_the_envelope_routers_actually_use():
    from codeframe.ui import response_models

    for gone in (
        "ApiResponse",
        "ApiError",
        "PaginatedResponse",
        "api_response",
        "created_message",
        "updated_message",
        "deleted_message",
        "retrieved_message",
    ):
        assert not hasattr(response_models, gone), f"unused envelope {gone} is back"

    for live in ("api_error", "ErrorCodes", "internal_error"):
        assert hasattr(response_models, live)


def test_broadcast_connection_managers_are_gone():
    from codeframe.ui import shared

    assert not hasattr(shared, "ConnectionManager")
    assert not hasattr(shared, "WebSocketSubscriptionManager")
    assert not hasattr(shared, "manager")
    # The live chat manager stays — session_chat_ws depends on it.
    assert hasattr(shared, "SessionChatManager")
    assert hasattr(shared, "session_chat_manager")


def test_test_broadcast_route_and_its_gate_are_gone():
    server_src = (REPO_ROOT / "codeframe" / "ui" / "server.py").read_text()
    assert "/test/broadcast" not in server_src
    assert "CODEFRAME_ENABLE_TEST_ENDPOINTS" not in server_src

    provenance_src = (REPO_ROOT / "codeframe" / "core" / "env_provenance.py").read_text()
    assert "CODEFRAME_ENABLE_TEST_ENDPOINTS" not in provenance_src


def test_streaming_module_is_a_utility_not_a_mounted_router():
    """The SSE helpers are live; the never-decorated router object is not."""
    from codeframe.ui import streaming_utils

    for live in (
        "get_event_publisher",
        "set_event_publisher",
        "format_sse_event",
        "format_sse_comment",
        "event_stream_generator",
    ):
        assert hasattr(streaming_utils, live)

    assert not hasattr(streaming_utils, "router")
    assert not (REPO_ROOT / "codeframe" / "ui" / "routers" / "streaming_v2.py").exists()

    server_src = (REPO_ROOT / "codeframe" / "ui" / "server.py").read_text()
    assert "streaming_v2" not in server_src


def test_v1_json_config_is_gone():
    from codeframe.core import config

    for gone in (
        "Config",
        "ProjectConfig",
        "ProviderConfig",
        "AgentPolicyConfig",
        "InterruptionConfig",
        "NotificationChannelConfig",
        "CheckpointConfig",
    ):
        assert not hasattr(config, gone), f"v1 config symbol {gone} is back"

    # The live half must survive: rate limiting and the server lifespan use it.
    for live in (
        "GlobalConfig",
        "load_environment",
        "get_global_config",
        "reset_global_config",
    ):
        assert hasattr(config, live)

    import codeframe.core as core_pkg

    assert not hasattr(core_pkg, "Config")
    assert "Config" not in getattr(core_pkg, "__all__", [])


def test_unused_rate_limit_decorators_are_gone():
    from codeframe.lib import rate_limiter

    assert not hasattr(rate_limiter, "rate_limit_auth")
    assert not hasattr(rate_limiter, "rate_limit_websocket")
    # The decorators that are actually applied to routes stay.
    assert hasattr(rate_limiter, "rate_limit_standard")
    assert hasattr(rate_limiter, "rate_limit_ai")
    # Auth throttling lives in the dependency, not the decorator.
    assert hasattr(rate_limiter, "enforce_auth_rate_limit")


def test_default_workspace_path_is_no_longer_read():
    """The unreachable `app.state.default_workspace_path` branch is gone.

    Asserts on the attribute *access*, not the name — the surrounding comment
    still mentions it to explain why the branch was removed.
    """
    deps_src = (REPO_ROOT / "codeframe" / "ui" / "dependencies.py").read_text()
    assert "app.state.default_workspace_path" not in deps_src
    assert '"default_workspace_path"' not in deps_src


def test_dead_dependencies_are_removed_from_pyproject():
    """Parses the declared requirements rather than grepping the file.

    A raw substring check would trip over the comment that explains *why*
    passlib went away.
    """
    import tomllib

    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        deps = tomllib.load(fh)["project"]["dependencies"]

    names = {re.split(r"[\[<>=!~ ]", d, maxsplit=1)[0].lower() for d in deps}
    assert "python-jose" not in names
    assert "passlib" not in names
    # api_keys.py imports bcrypt directly, so it must be declared, not transitive.
    assert "bcrypt" in names
