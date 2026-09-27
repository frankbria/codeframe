"""Pydantic schemas for user operations."""
from typing import Optional
from fastapi_users import schemas

class UserRead(schemas.BaseUser[int]):
    """Schema for reading user data."""
    name: Optional[str] = None

class UserCreate(schemas.BaseUserCreate):
    """Schema for creating users."""
    name: Optional[str] = None

class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating users."""
    name: Optional[str] = None
    #: Required to change password or email (#1285). Not a column, so the
    #: update only sets it as a plain attribute; UserRead never returns it.
    current_password: Optional[str] = None
