"""Auth router configuration."""
import asyncio
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from codeframe.auth.schemas import UserCreate, UserRead, UserUpdate
from codeframe.auth.manager import auth_backend, fastapi_users, get_async_session_maker
from codeframe.auth.models import User
from codeframe.auth.api_key_router import router as api_key_router
from codeframe.auth.dependencies import require_auth
from codeframe.auth.stream_tickets import TICKET_TTL_SECONDS, mint_ticket
from codeframe.lib.rate_limiter import enforce_auth_rate_limit

router = APIRouter()


class StreamTicketResponse(BaseModel):
    """Response body for POST /auth/stream-ticket."""

    ticket: str
    expires_in: int


# Placeholder password for the seeded bootstrap admin (id=1). It cannot match
# any bcrypt hash, so that account can never log in. It is therefore NOT a real
# account and does not close the registration window. See SchemaManager
# ._ensure_default_admin_user.
_DISABLED_PASSWORD = "!DISABLED!"

# Serializes the bootstrap registration check-then-create window. The count
# check (here) and the user INSERT (fastapi-users route handler) run in
# separate transactions, so without the lock two concurrent first-time
# registrations could both pass the zero-users check (TOCTOU). The yield
# dependency holds the lock until the response completes, covering creation.
# In-process only — multi-worker deployments retain a narrow race.
_register_lock = asyncio.Lock()


async def allow_registration():
    """Gate registration to bootstrap-first-user only (issue #336).

    Registration is permitted only while no *real* (login-capable) account
    exists. The database always seeds a default admin (id=1) with a disabled
    password placeholder; that account cannot log in and does not count.
    Once the first real user registers, this raises 403.
    """
    async with _register_lock:
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

        # Hold the lock until the registration request finishes.
        yield


# Authentication routes (login, logout) - JWT endpoints at /auth/jwt/*
# enforce_auth_rate_limit throttles credential brute-force (#644).
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
    dependencies=[Depends(enforce_auth_rate_limit)],
)

# Registration route at /auth/register (bootstrap-first-user only).
# Rate-limit dependency runs first so throttling precedes the bootstrap 403 (#644).
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(enforce_auth_rate_limit), Depends(allow_registration)],
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


@router.post(
    "/auth/stream-ticket",
    response_model=StreamTicketResponse,
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def create_stream_ticket(
    auth: Dict[str, Any] = Depends(require_auth),
) -> StreamTicketResponse:
    """Mint a short-lived, single-use ticket for SSE/WS stream authentication (#745).

    Browser ``EventSource`` (SSE) and WebSocket clients cannot send a custom
    ``Authorization`` header, so streaming routes accept a ``?ticket=<value>``
    query parameter instead of a long-lived JWT. Call this endpoint first
    (authenticated the normal way, via JWT Bearer or ``X-API-Key``), then open
    the stream with the returned ticket. The ticket is single-use and expires
    after ``expires_in`` seconds.

    Minting requires **write** scope: a redeemed ticket acts as a full user
    session on the WebSocket routes (terminal input / chat both mutate state),
    so a read-only API key must not be able to escalate through it (codex
    review P1). Read-only keys don't need tickets — header-capable clients
    authenticate the SSE routes with ``X-API-Key`` directly.
    """
    from codeframe.auth.api_keys import SCOPE_WRITE
    from codeframe.auth.scopes import has_scope

    if not has_scope(auth, SCOPE_WRITE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Stream tickets require write scope",
        )
    ticket = mint_ticket(auth.get("user_id"))
    return StreamTicketResponse(ticket=ticket, expires_in=TICKET_TTL_SECONDS)
