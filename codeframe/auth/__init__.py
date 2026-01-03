"""Authentication module for CodeFRAME."""
from codeframe.auth.models import User
from codeframe.auth.schemas import UserRead, UserCreate, UserUpdate
from codeframe.auth.manager import fastapi_users, auth_backend, current_active_user
from codeframe.auth.dependencies import get_current_user

__all__ = [
    "User",
    "UserRead",
    "UserCreate",
    "UserUpdate",
    "fastapi_users",
    "auth_backend",
    "current_active_user",
    "get_current_user",
]
