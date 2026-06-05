"""Auth router configuration."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from codeframe.auth.schemas import UserCreate, UserRead, UserUpdate
from codeframe.auth.manager import auth_backend, fastapi_users, get_async_session_maker
from codeframe.auth.models import User
from codeframe.auth.api_key_router import router as api_key_router

router = APIRouter()


# Placeholder password for the seeded bootstrap admin (id=1). It cannot match
# any bcrypt hash, so that account can never log in. It is therefore NOT a real
# account and does not close the registration window. See SchemaManager
# ._ensure_default_admin_user.
_DISABLED_PASSWORD = "!DISABLED!"


async def allow_registration() -> None:
    """Gate registration to bootstrap-first-user only (issue #336).

    Registration is permitted only while no *real* (login-capable) account
    exists. The database always seeds a default admin (id=1) with a disabled
    password placeholder; that account cannot log in and does not count.
    Once the first real user registers, this raises 403.
    """
    async_session_maker = get_async_session_maker()
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count())
            .select_from(User)
            .where(User.hashed_password != _DISABLED_PASSWORD)
        )
        real_user_count = result.scalar_one()

    if real_user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed: an account already exists.",
        )


# Authentication routes (login, logout) - JWT endpoints at /auth/jwt/*
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# Registration route at /auth/register (bootstrap-first-user only)
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(allow_registration)],
)

# User management routes (get me, update me) at /users/*
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)

# Optional: Reset password, verify email
# router.include_router(
#     fastapi_users.get_reset_password_router(),
#     prefix="/auth",
#     tags=["auth"],
# )
# router.include_router(
#     fastapi_users.get_verify_router(UserRead),
#     prefix="/auth",
#     tags=["auth"],
# )

# API key management routes at /api/auth/api-keys
router.include_router(api_key_router)
