"""fastapi-users configuration."""
import os
import uuid
from typing import Optional

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from codeframe.auth.models import User
from codeframe.db import get_async_session  # You may need to create this

SECRET = os.getenv("AUTH_SECRET", "CHANGE-ME-IN-PRODUCTION-USE-SECRETS")
JWT_LIFETIME_SECONDS = 60 * 60 * 24 * 7  # 7 days


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Custom user manager for CodeFRAME."""
    
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Called after successful registration."""
        print(f"User {user.id} registered.")

    async def on_after_login(
        self, user: User, request: Optional[Request] = None, response=None
    ):
        """Called after successful login."""
        print(f"User {user.id} logged in.")


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    """Dependency for user database adapter."""
    yield SQLAlchemyUserDatabase(session, User)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    """Dependency for user manager."""
    yield UserManager(user_db)


# JWT Bearer token transport
bearer_transport = BearerTransport(tokenUrl="auth/login")


def get_jwt_strategy() -> JWTStrategy:
    """JWT strategy for authentication."""
    return JWTStrategy(secret=SECRET, lifetime_seconds=JWT_LIFETIME_SECONDS)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPIUsers instance
fastapi_users = FastAPIUsers[User, uuid.UUID](
    get_user_manager,
    [auth_backend],
)

# Dependency for protected routes
current_active_user = fastapi_users.current_user(active=True)
current_superuser = fastapi_users.current_user(active=True, superuser=True)
