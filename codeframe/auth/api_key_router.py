"""API key management endpoints.

Provides endpoints for creating, listing, and revoking API keys.
API key creation requires JWT authentication (not API key auth) to prevent
privilege escalation attacks.

Uses core/api_key_service.py for business logic (shared with CLI).
"""

import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from codeframe.auth.dependencies import get_current_user, require_auth
from codeframe.auth.models import User
from codeframe.auth.api_keys import (
    validate_scopes,
    SCOPE_READ,
    SCOPE_WRITE,
)
from codeframe.core.api_key_service import ApiKeyService
from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/api-keys", tags=["auth", "api-keys"])


# =============================================================================
# Pydantic Models
# =============================================================================


class CreateApiKeyRequest(BaseModel):
    """Request body for creating an API key."""

    name: str
    scopes: List[str] = [SCOPE_READ, SCOPE_WRITE]
    expires_at: Optional[datetime] = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes_field(cls, v: List[str]) -> List[str]:
        if not validate_scopes(v):
            raise ValueError(f"Invalid scopes: {v}. Valid scopes are: read, write, admin")
        return v


class CreateApiKeyResponse(BaseModel):
    """Response body for API key creation."""

    key: str  # Full key - shown only once
    id: str
    prefix: str
    created_at: str


class ApiKeyInfoResponse(BaseModel):
    """API key information (without sensitive data)."""

    id: str
    name: str
    prefix: str
    scopes: List[str]
    created_at: str
    last_used_at: Optional[str]
    expires_at: Optional[str]
    is_active: bool


class RevokeApiKeyResponse(BaseModel):
    """Response body for API key revocation."""

    id: str
    revoked: bool


# =============================================================================
# Database Helper
# =============================================================================


def get_db(request: Request) -> Database:
    """Get database instance from app state (singleton managed by lifespan handler).

    Uses the app-scoped database to avoid per-request connection leaks.
    Falls back to DATABASE_PATH env var if app.state.db not available.
    """
    # Prefer app-scoped singleton (set by lifespan handler in server.py)
    db = getattr(request.app.state, "db", None)
    if db is not None:
        return db

    # Fallback for tests or standalone usage
    db = getattr(request.state, "db", None)
    if db is None:
        logger.warning("No db in app.state, creating fallback connection")
        db_path = os.getenv(
            "DATABASE_PATH",
            os.path.join(os.getcwd(), ".codeframe", "state.db")
        )
        db = Database(db_path)
        db.initialize()
        request.state.db = db
    return db


def get_api_key_service(request: Request) -> ApiKeyService:
    """Get API key service instance."""
    db = get_db(request)
    return ApiKeyService(db)


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreateApiKeyResponse)
async def create_api_key(
    request: Request,
    body: CreateApiKeyRequest,
    current_user: User = Depends(get_current_user),  # JWT required, not API key
):
    """Create a new API key.

    **Important**: This endpoint requires JWT authentication. API keys cannot
    be used to create new API keys (prevents privilege escalation).

    The full API key is returned only once. Store it securely - it cannot
    be retrieved again.

    Args:
        body: API key configuration (name, scopes, optional expiration)

    Returns:
        Created API key details including the full key (shown once)
    """
    service = get_api_key_service(request)

    result = service.create_api_key(
        user_id=current_user.id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )

    return CreateApiKeyResponse(
        key=result.key,
        id=result.id,
        prefix=result.prefix,
        created_at=result.created_at,
    )


@router.get("", response_model=List[ApiKeyInfoResponse])
async def list_api_keys(
    request: Request,
    auth: dict = Depends(require_auth),  # Either JWT or API key
):
    """List all API keys for the authenticated user.

    Does not expose the key hash or full key. Shows prefix for identification.

    Returns:
        List of API key information
    """
    service = get_api_key_service(request)

    keys = service.list_api_keys(user_id=auth["user_id"])

    return [
        ApiKeyInfoResponse(
            id=k.id,
            name=k.name,
            prefix=k.prefix,
            scopes=k.scopes,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            expires_at=k.expires_at,
            is_active=k.is_active,
        )
        for k in keys
    ]


@router.delete("/{key_id}", response_model=RevokeApiKeyResponse)
async def revoke_api_key(
    request: Request,
    key_id: str,
    auth: dict = Depends(require_auth),  # Either JWT or API key
):
    """Revoke an API key.

    The key will be marked as inactive and can no longer be used for
    authentication.

    Args:
        key_id: The API key ID to revoke

    Returns:
        Confirmation of revocation

    Raises:
        404: If key not found or not owned by user
    """
    service = get_api_key_service(request)

    success = service.revoke_api_key(key_id, user_id=auth["user_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    return RevokeApiKeyResponse(id=key_id, revoked=True)
