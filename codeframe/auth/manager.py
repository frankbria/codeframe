"""User manager and authentication backends."""
import os
from typing import Optional
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, IntegerIDMixin, FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from codeframe.auth.models import User
from codeframe.persistence.database import Database

# Get configuration from environment
SECRET = os.getenv("AUTH_SECRET", "CHANGE-ME-IN-PRODUCTION")
JWT_LIFETIME_SECONDS = int(os.getenv("JWT_LIFETIME_SECONDS", "604800"))  # 7 days

class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    """User manager for CodeFRAME."""
    
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        """Called after successful registration."""
        print(f"User {user.id} ({user.email}) registered.")

    async def on_after_login(
        self, user: User, request: Optional[Request] = None, response=None
    ):
        """Called after successful login."""
        print(f"User {user.id} ({user.email}) logged in.")

async def get_async_session(request: Request) -> AsyncSession:
    """Get async database session from app state."""
    db: Database = request.app.state.db
    async_conn = await db._get_async_conn()
    # Create async session from connection
    from sqlalchemy.ext.asyncio import AsyncSession
    session = AsyncSession(bind=async_conn)
    try:
        yield session
    finally:
        await session.close()

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
