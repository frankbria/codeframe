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
    #: Required to change password or email (#1285); never written to the row.
    current_password: Optional[str] = None

    def create_update_dict(self):
        return _without_current_password(super().create_update_dict())

    def create_update_dict_superuser(self):
        return _without_current_password(super().create_update_dict_superuser())


def _without_current_password(update: dict) -> dict:
    update.pop("current_password", None)
    return update
