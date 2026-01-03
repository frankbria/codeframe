"""SQLAlchemy User model for fastapi-users."""
from typing import Optional
from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase

class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass

class User(SQLAlchemyBaseUserTable[int], Base):
    """User model compatible with existing users table.
    
    Uses integer primary key instead of UUID to match existing schema.
    Maps to existing 'users' table created by SchemaManager.
    """
    __tablename__ = "users"
    
    # Override id to use Integer instead of UUID
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Required fastapi-users fields (already in schema)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Additional fields from existing schema
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
