"""Auth router configuration."""
import asyncio
import hmac
import ipaddress
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select

from codeframe.auth.schemas import UserCreate, UserRead, UserUpdate
from codeframe.auth.manager import (
    DISABLED_PASSWORD,
    auth_backend,
    fastapi_users,
    get_async_session_maker,
)
from codeframe.auth.models import User
from codeframe.auth.api_key_router import router as api_key_router
from codeframe.auth.dependencies import require_auth
from codeframe.lib.audit_logger import (
    AuditEventType,
    audit_from_request,
    capture_audit_request,
)
from codeframe.auth.stream_tickets import TICKET_TTL_SECONDS, mint_ticket
from codeframe.lib.rate_limiter import enforce_auth_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()


class StreamTicketResponse(BaseModel):
    """Response body for POST /auth/stream-ticket."""

    ticket: str
    expires_in: int


# ``DISABLED_PASSWORD`` (imported from auth.manager) is the placeholder password
# for the seeded bootstrap admin (id=1). It cannot match any bcrypt hash, so that
# account can never log in. It is therefore NOT a real account and does not close
# the registration window. See SchemaManager._ensure_default_admin_user.

# Serializes the bootstrap registration check-then-create window. The count
# check (here) and the user INSERT (fastapi-users route handler) run in
# separate transactions, so without the lock two concurrent first-time
# registrations could both pass the zero-users check (TOCTOU). The yield
# dependency holds the lock until the response completes, covering creation.
# In-process only — multi-worker deployments retain a narrow race.
_register_lock = asyncio.Lock()

# Header carrying the out-of-band bootstrap secret (#897). A header rather than
# a body field so the fastapi-users ``UserCreate`` schema stays untouched and
# the secret never lands in the JSON echoed back by validation errors.
BOOTSTRAP_TOKEN_HEADER = "X-Bootstrap-Token"

_BOOTSTRAP_DENIED_DETAIL = (
    "Bootstrap registration is not permitted from this client. Set "
    "CODEFRAME_BOOTSTRAP_TOKEN on the server and send it as the "
    f"{BOOTSTRAP_TOKEN_HEADER} header, or register from the server host itself "
    "(e.g. `codeframe auth register` over loopback)."
)


def _bootstrap_token() -> str:
    """The configured out-of-band bootstrap secret, or ``""`` when unset.

    Read at request time (not import time) so tests and operators can change it
    without reimporting the module. Whitespace-only values are treated as unset
    — an empty string must never become a matchable secret.
    """
    return os.getenv("CODEFRAME_BOOTSTRAP_TOKEN", "").strip()


# Headers that name a *client* address. Any of them means something upstream is
# speaking for someone else, so every address they carry must also be loopback
# before the request counts as host-local. Deliberately excludes
# X-Forwarded-Host/Proto: those describe the request, not who made it, and the
# local Next.js `/auth/*` rewrite sets them in ordinary development.
_CLIENT_ADDRESS_HEADERS = ("x-forwarded-for", "x-real-ip")


def _is_loopback_ip(value: str) -> bool:
    """Whether ``value`` parses as a loopback IP. Unparseable → ``False``.

    Unwraps IPv4-mapped IPv6 first: ``ipaddress`` reports
    ``::ffff:127.0.0.1`` as **not** loopback (``IPv6Address.is_loopback`` only
    recognises ``::1``), yet that is exactly how a dual-stack listener reports a
    loopback IPv4 peer.
    """
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return (mapped or address).is_loopback


def _is_local_request(request: Request) -> bool:
    """Whether the request genuinely originated on this host (issue #897).

    Deliberately does NOT reuse ``lib.rate_limiter.get_client_ip``: that helper
    only honors ``X-Forwarded-For`` when ``RATE_LIMIT_TRUSTED_PROXIES`` is
    configured, and that setting is optional. Behind the documented Caddy deploy
    (``deploy/Caddyfile.example`` proxies ``/auth/*`` from the public Internet to
    ``127.0.0.1``) with that setting unset, it reports every Internet client as
    ``127.0.0.1`` — which would leave this gate wide open. A security gate must
    not depend on an optional performance/telemetry setting being present.

    So the rule here is strict and self-contained: the peer must be loopback,
    every hop in the forwarded chain must be loopback, and no RFC 7239
    ``Forwarded`` header may be present. Caddy *appends* the real client IP to
    ``X-Forwarded-For``, so a spoofed ``X-Forwarded-For: 127.0.0.1`` from the
    Internet still leaves a non-loopback hop behind it. A local dev proxy (the
    Next.js ``/auth/*`` rewrite) forwards loopback→loopback and still passes.
    """
    client = request.client
    if client is None or not _is_loopback_ip(client.host):
        return False

    # Any RFC 7239 header means a proxy is in the path. Its `for=` grammar
    # (quoted strings, ports, obfuscated identifiers) is fiddly enough that
    # parsing it is more risk than it is worth here — reject and let the
    # operator use a token instead.
    if request.headers.get("forwarded"):
        return False

    # getlist, not get: a request can carry the header more than once, and
    # `.get()` would return only the first — letting an attacker-supplied
    # `X-Forwarded-For: 127.0.0.1` mask the real address a proxy appended in a
    # second header. Reading every instance removes the dependence on which
    # style of proxy is in front.
    for header in _CLIENT_ADDRESS_HEADERS:
        for value in request.headers.getlist(header):
            hops = [hop for hop in value.split(",") if hop.strip()]
            if not all(_is_loopback_ip(hop) for hop in hops):
                return False

    return True


def _check_bootstrap_credential(request: Request) -> None:
    """Require the out-of-band secret, or a host-local request (issue #897).

    Without this, ``/auth/register`` is an unauthenticated route that hands out
    ``[read, write, admin]`` to whoever reaches it first on a fresh deploy — and
    the deploy path publishes it before any account exists.

    When ``CODEFRAME_BOOTSTRAP_TOKEN`` is set it is mandatory, loopback
    included: configuring it is an explicit opt-in to the stronger control, and
    behind a reverse proxy "loopback" means nothing anyway.

    Raises:
        HTTPException: 403 when neither the token nor host-locality holds.
    """
    expected = _bootstrap_token()

    if expected:
        presented = request.headers.get(BOOTSTRAP_TOKEN_HEADER, "")
        # Compare bytes, not str: compare_digest rejects non-ASCII str operands
        # with TypeError, and Starlette decodes headers as latin-1 — so a
        # non-ASCII header value would 500 instead of cleanly 403-ing.
        if hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
            return
        logger.warning(
            "Rejected bootstrap registration: %s missing or incorrect.",
            BOOTSTRAP_TOKEN_HEADER,
        )
    elif _is_local_request(request):
        return
    else:
        logger.warning(
            "Rejected bootstrap registration from a non-local client and no "
            "CODEFRAME_BOOTSTRAP_TOKEN is configured."
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=_BOOTSTRAP_DENIED_DETAIL,
    )


async def allow_registration(request: Request):
    """Gate registration to bootstrap-first-user only (issues #336, #897).

    Two gates, both of which must pass:

    1. The caller presents ``CODEFRAME_BOOTSTRAP_TOKEN`` out of band, or the
       request originates on the host itself (#897).
    2. No *real* (login-capable) account exists yet (#336). The database always
       seeds a default admin (id=1) with a disabled password placeholder; that
       account cannot log in and does not count.

    The credential gate runs first and outside the lock: an unauthorized caller
    then learns nothing about whether the instance has been claimed, and
    rejected requests never contend for the lock.
    """
    _check_bootstrap_credential(request)

    async with _register_lock:
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.hashed_password != DISABLED_PASSWORD)
            )
            real_user_count = result.scalar_one()

        if real_user_count > 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration is closed: an account already exists.",
            )

        # Hold the lock until the registration request finishes.
        yield



async def audit_logout(request: Request) -> None:
    """Record a logout (#937).

    fastapi-users has no ``on_after_logout`` hook, and this dependency runs on
    the whole /auth/jwt include, so it filters by path. It fires *before* the
    handler: with the JWT strategy, logout for an authenticated caller does not
    fail, so "attempted" and "succeeded" are the same event. The alternative —
    wrapping the generated route's endpoint — means rebuilding FastAPI's
    dependant graph, which is far more fragile than one path check.
    """
    if not request.url.path.endswith("/logout"):
        return
    audit_from_request(request, AuditEventType.AUTH_LOGOUT)


# Authentication routes (login, logout) - JWT endpoints at /auth/jwt/*
# enforce_auth_rate_limit throttles credential brute-force (#644).
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
    # capture_audit_request exposes the Request to UserManager.authenticate,
    # which fastapi-users calls with only the credentials — so a failed login
    # can still be audited with its client IP (#937).
    dependencies=[
        Depends(enforce_auth_rate_limit),
        Depends(capture_audit_request),
        Depends(audit_logout),
    ],
)

# Registration route at /auth/register (bootstrap-first-user only).
# Rate-limit dependency runs first so throttling precedes the bootstrap 403 (#644).
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
    dependencies=[
        Depends(enforce_auth_rate_limit),
        Depends(allow_registration),
        Depends(capture_audit_request),
    ],
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
