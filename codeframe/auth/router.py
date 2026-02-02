"""Auth router configuration."""
from fastapi import APIRouter

from codeframe.auth.schemas import UserCreate, UserRead, UserUpdate
from codeframe.auth.manager import auth_backend, fastapi_users
from codeframe.auth.api_key_router import router as api_key_router

router = APIRouter()

# Authentication routes (login, logout) - JWT endpoints at /auth/jwt/*
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# Registration route at /auth/register
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
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
