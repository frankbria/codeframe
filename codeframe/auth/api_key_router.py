"""API key management endpoints.

Provides endpoints for creating, listing, and revoking API keys.
API key creation requires JWT authentication (not API key auth) to prevent
privilege escalation attacks.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from codeframe.auth.dependencies import get_current_user, require_auth
from codeframe.auth.models import User
from codeframe.auth.api_keys import (
    generate_api_key,
    validate_scopes,
    SCOPE_READ,
    SCOPE_WRITE,
)
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


class ApiKeyInfo(BaseModel):
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
    """Get database instance from request state or create new one."""
    db = getattr(request.state, "db", None)
    if db is None:
        db_path = os.getenv(
            "DATABASE_PATH",
            os.path.join(os.getcwd(), ".codeframe", "state.db")
        )
        db = Database(db_path)
        db.initialize()
        request.state.db = db
    return db


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
    db = get_db(request)

    # Generate the API key
    full_key, key_hash, prefix = generate_api_key()

    # Parse expiration if provided
    expires_at = body.expires_at

    # Store in database
    key_id = db.api_keys.create(
        user_id=current_user.id,
        name=body.name,
        key_hash=key_hash,
        prefix=prefix,
        scopes=body.scopes,
        expires_at=expires_at,
    )

    logger.info(f"API key created for user {current_user.id}: {prefix}...")

    return CreateApiKeyResponse(
        key=full_key,  # Shown only once
        id=key_id,
        prefix=prefix,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("", response_model=List[ApiKeyInfo])
async def list_api_keys(
    request: Request,
    auth: dict = Depends(require_auth),  # Either JWT or API key
):
    """List all API keys for the authenticated user.

    Does not expose the key hash or full key. Shows prefix for identification.

    Returns:
        List of API key information
    """
    db = get_db(request)

    keys = db.api_keys.list_user_keys(user_id=auth["user_id"])

    return [
        ApiKeyInfo(
            id=k["id"],
            name=k["name"],
            prefix=k["prefix"],
            scopes=k["scopes"],
            created_at=k["created_at"],
            last_used_at=k.get("last_used_at"),
            expires_at=k.get("expires_at"),
            is_active=k["is_active"],
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
    db = get_db(request)

    success = db.api_keys.revoke(key_id, user_id=auth["user_id"])

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    logger.info(f"API key revoked by user {auth['user_id']}: {key_id}")

    return RevokeApiKeyResponse(id=key_id, revoked=True)
