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

from codeframe.auth.models import User

logger = logging.getLogger(__name__)

# Get configuration from environment
DEFAULT_SECRET = "CHANGE-ME-IN-PRODUCTION"
SECRET = os.getenv("AUTH_SECRET", DEFAULT_SECRET)

# JWT configuration constants
# These must match the JWTStrategy defaults from FastAPI Users
JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = ["fastapi-users:auth"]
JWT_LIFETIME_SECONDS = int(os.getenv("JWT_LIFETIME_SECONDS", "604800"))  # 7 days

# Warn if using default secret (but allow for development)
if SECRET == DEFAULT_SECRET:
    logger.warning(
        "⚠️  AUTH_SECRET not set - using default value. "
        "DO NOT USE IN PRODUCTION! Set AUTH_SECRET environment variable."
    )

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

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Called after successful registration."""
        logger.info(
            "User registered",
            extra={"user_id": user.id, "email": user.email}
        )

    async def on_after_login(
        self, user: User, request: Optional[Request] = None, response=None
    ):
        """Called after successful login."""
        # Only log user_id on login (avoid excessive email logging)
        logger.info("User logged in", extra={"user_id": user.id})


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
