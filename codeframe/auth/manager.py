"""User manager and authentication backends."""
import logging
import os
from typing import AsyncGenerator, Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, IntegerIDMixin, FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from pwdlib.exceptions import UnknownHashError

from codeframe.auth.models import User
from codeframe.lib.audit_logger import (
    AuditEventType,
    audit_from_request,
    current_audit_request,
)

# Re-exported, never redefined. The placeholder password for the seeded
# bootstrap admin (id=1) is owned by the layer that writes it
# (SchemaManager._ensure_default_admin_user). Two independent copies would have
# to stay byte-identical forever: the registration gate, the bootstrap
# promotion and the admin backfill all compare against it, so any drift makes
# fresh deploys unclaimable and silently strips an upgraded deploy's admin.
from codeframe.platform_store.schema_manager import DISABLED_PASSWORD

logger = logging.getLogger(__name__)

# Get configuration from environment
DEFAULT_SECRET = "CHANGE-ME-IN-PRODUCTION"


def _read_auth_secret() -> str:
    """Read ``AUTH_SECRET`` from the env, treating blank/whitespace as unset.

    ``AUTH_SECRET=`` (empty) or a whitespace-only value would otherwise be a
    distinct-from-default string and slip past the startup guard as a "custom"
    secret — yet a blank HMAC key is just as forgeable as the known default. So
    empty/whitespace values fall back to ``DEFAULT_SECRET`` and into the same
    hard-fail path (issue #643). A real secret is returned verbatim (not
    stripped) so the operator's exact value is used for signing.
    """
    value = os.getenv("AUTH_SECRET")
    if value is None or not value.strip():
        return DEFAULT_SECRET
    # A whitespace-padded copy of the known default (e.g. an accidental
    # "CHANGE-ME-IN-PRODUCTION " paste) is just as guessable, so normalize it
    # back to the sentinel and let the startup guard catch it. Genuinely custom
    # secrets are returned verbatim (their exact bytes are used for signing).
    if value.strip() == DEFAULT_SECRET:
        return DEFAULT_SECRET
    return value


SECRET = _read_auth_secret()


def refresh_secret() -> str:
    """Re-read ``AUTH_SECRET`` from the environment and update the module global.

    ``SECRET`` is captured at import time, which happens before the server
    lifespan loads ``.env`` (the auth router is imported while the app module is
    imported via ``uvicorn codeframe.ui.server:app``). Call this after the
    environment is loaded so JWT signing (``get_jwt_strategy`` reads the live
    global), JWT verification, and the WS token decoders all use the configured
    secret instead of the default. Also keeps the fastapi-users password-reset /
    email-verify token secrets in sync in case those routers are re-enabled.
    Returns the refreshed secret.
    """
    global SECRET
    SECRET = _read_auth_secret()
    UserManager.reset_password_token_secret = SECRET
    UserManager.verification_token_secret = SECRET
    return SECRET

# JWT configuration constants
# These must match the JWTStrategy defaults from FastAPI Users
JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = ["fastapi-users:auth"]
JWT_LIFETIME_SECONDS = int(os.getenv("JWT_LIFETIME_SECONDS", "86400"))  # 24h (#657)

# NOTE: The default-secret warning is intentionally NOT emitted at import time.
# Importing this module must stay silent so it never leaks onto the CLI (the
# Golden Path never uses auth). The check that matters runs when the server
# actually starts — see codeframe/ui/server.py:_validate_security_config(),
# which warns in self-hosted mode and fails hard in hosted mode.

# Create async SQLAlchemy engine for auth
# Uses aiosqlite driver for async SQLite access
_engine = None
_async_session_maker = None
_current_database_path = None


def _get_database_path() -> str:
    """Get the current database path from environment."""
    return os.getenv(
        "DATABASE_PATH",
        os.path.join(os.getcwd(), ".codeframe", "state.db")
    )


def reset_auth_engine():
    """Reset the async SQLAlchemy engine.

    Call this when DATABASE_PATH environment variable changes
    (e.g., in tests that use temporary databases).

    Also disposes of the engine to close all connections.
    """
    global _engine, _async_session_maker, _current_database_path

    # Dispose of engine to close all connections
    if _engine is not None:
        import asyncio
        try:
            # Try to dispose synchronously if possible
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in running loop, schedule for later
                asyncio.ensure_future(_engine.dispose())
            else:
                loop.run_until_complete(_engine.dispose())
        except RuntimeError:
            # No event loop available, create one temporarily
            asyncio.run(_engine.dispose())
        except Exception:
            # Ignore disposal errors during cleanup
            pass

    _engine = None
    _async_session_maker = None
    _current_database_path = None


def get_engine():
    """Get or create the async SQLAlchemy engine."""
    global _engine, _current_database_path

    # Get current database path
    database_path = _get_database_path()

    # If path changed, reset engine
    if _current_database_path is not None and _current_database_path != database_path:
        reset_auth_engine()

    if _engine is None:
        # Use aiosqlite for async SQLite support
        database_url = f"sqlite+aiosqlite:///{database_path}"
        _engine = create_async_engine(database_url, echo=False)
        _current_database_path = database_path
    return _engine


def get_async_session_maker():
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """User manager for CodeFRAME."""

    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def authenticate(self, credentials):
        """Authenticate, recording failures (#937).

        fastapi-users exposes `on_after_login` but has no failed-login hook, and
        a failed login is the event an audit trail exists for — repeated ones are
        the signature of credential stuffing. This is the documented extension
        point that sees both the submitted identity and the outcome.
        """
        try:
            user = await super().authenticate(credentials)
        except UnknownHashError:
            # Every database seeds admin@localhost with the sentinel
            # '!DISABLED!' as its stored hash. fastapi-users 15.x calls
            # password_helper.verify_and_update with no try/except, and pwdlib
            # raises UnknownHashError on anything it cannot identify — so
            # POST /auth/jwt/login?username=admin@localhost was a trivially
            # triggerable unauthenticated 500 with a logged traceback, on a
            # publicly reachable endpoint, that also confirmed the account
            # exists (#938).
            #
            # Returning None makes it an ordinary failed login: a 400 that looks
            # exactly like any other bad credential, and one that is audited.
            user = None

        # `user is not None` is not the same as "logged in": fastapi-users'
        # generated route rejects an inactive account with the same 400
        # BAD_CREDENTIALS *after* authenticate() returns. Auditing only the None
        # case made repeated correct-password attempts against a disabled or
        # compromised account invisible — which is precisely the
        # credential-stuffing signal this exists to capture (PR review on #937).
        if user is None or not user.is_active:
            audit_from_request(
                current_audit_request(),
                AuditEventType.AUTH_LOGIN_FAILED,
                user_id=getattr(user, "id", None),
                email=getattr(credentials, "username", None),
                metadata=(
                    {"reason": "inactive_account"}
                    if user is not None
                    else {"reason": "bad_credentials"}
                ),
            )
        return user

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Called after successful registration."""
        logger.info(
            "User registered",
            extra={"user_id": user.id, "email": user.email}
        )
        audit_from_request(
            request, AuditEventType.USER_CREATED, user_id=user.id, email=user.email
        )
        await self._promote_if_bootstrap_user(user)

    async def _promote_if_bootstrap_user(self, user: User) -> None:
        """Grant ``is_superuser`` to the instance's first real account (#898).

        Admin scope derives from ``is_superuser``, and
        ``fastapi_users.get_register_router`` forces the field to ``False`` on
        every registration — so without this no principal would ever hold admin
        and credential storage, GitHub PAT storage and PR merge would be
        permanently 403.

        ``/auth/register`` already admits exactly one login-capable account
        (issues #336, #897), so that account is the operator. Two guards, both
        evaluated *inside* a *single atomic UPDATE* rather than read-then-write:

        - this must be the only login-capable account, and
        - no login-capable superuser may exist yet.

        Atomicity matters because ``_register_lock`` is an ``asyncio.Lock`` —
        in-process only, so it does not serialize across uvicorn/gunicorn
        workers. With count-then-write, two racing first-time registrations can
        each observe two users and neither promote, leaving the instance with
        zero admins and no in-product way back. Letting the database arbitrate
        removes that window.
        """
        from sqlalchemy import text

        session = getattr(self.user_db, "session", None)
        if session is None:  # pragma: no cover - non-SQLAlchemy user_db
            return

        result = await session.execute(
            text(
                "UPDATE users SET is_superuser = 1 "
                "WHERE id = :uid"
                "  AND (SELECT COUNT(*) FROM users"
                "       WHERE hashed_password != :disabled) = 1"
                "  AND NOT EXISTS ("
                "      SELECT 1 FROM users"
                "      WHERE is_superuser = 1 AND hashed_password != :disabled"
                "  )"
            ),
            {"uid": user.id, "disabled": DISABLED_PASSWORD},
        )
        await session.commit()

        if result.rowcount:
            # Keep the in-memory row consistent with what was just written, so
            # the registration response does not report is_superuser=false.
            await session.refresh(user)
            logger.info(
                "Promoted bootstrap user to superuser", extra={"user_id": user.id}
            )

    async def on_after_login(
        self, user: User, request: Optional[Request] = None, response=None
    ):
        """Called after successful login."""
        # Only log user_id on login (avoid excessive email logging)
        logger.info("User logged in", extra={"user_id": user.id})
        audit_from_request(
            request, AuditEventType.AUTH_LOGIN_SUCCESS, user_id=user.id
        )


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session for auth."""
    async_session_maker = get_async_session_maker()
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    """Get user database adapter."""
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    """Get user manager."""
    yield UserManager(user_db)


# JWT Bearer token transport
bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    """JWT strategy for authentication."""
    return JWTStrategy(secret=SECRET, lifetime_seconds=JWT_LIFETIME_SECONDS)


# Authentication backend
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPIUsers instance
fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

# Dependencies for protected routes
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
