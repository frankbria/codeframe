"""Authentication dependencies for route handlers.

Supports dual authentication:
- JWT Bearer tokens (existing FastAPI Users integration)
- API keys via X-API-Key header (new for programmatic access)

Both credential types use scope-based permissions (read, write, admin). API-key
scopes are stored on the key; JWT scopes are derived from the user record —
read+write always, admin only for ``is_superuser`` accounts (issue #898).
"""

import logging
import os
import re
import threading
import time
from typing import Callable, Dict, Optional, Any, Tuple

from fastapi import Depends, HTTPException, Request, Security, WebSocket, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

from codeframe.auth.models import User
from codeframe.auth.api_keys import (
    extract_prefix,
    verify_api_key,
    SCOPE_READ,
    SCOPE_WRITE,
    SCOPE_ADMIN,
)
from codeframe.auth.scopes import has_scope

logger = logging.getLogger(__name__)

# Security schemes
security = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Truthy/falsy values for CODEFRAME_AUTH_REQUIRED (case-insensitive).
_AUTH_FALSY = {"0", "false", "no", "off"}

# Routes allowed to authenticate via a ?ticket=<value> query parameter.
# Browser EventSource (SSE) cannot send an Authorization header, so these
# streaming routes accept a short-lived, single-use ticket in the URL instead
# — the same trade-off the WebSocket routes already make. Keep this list
# tight: query-string credentials can leak via proxy/access logs and browser
# history, so the fallback must NOT apply to the rest of the API (codex
# review P2, issue #336). Tickets (not long-lived JWTs) close that exposure
# window to TICKET_TTL_SECONDS and single use (issue #745).
_QUERY_TICKET_PATHS = (
    re.compile(r"^/api/v2/tasks/[^/]+/stream$"),  # task event stream (SSE)
    re.compile(r"^/api/v2/prd/stress-test$"),  # PRD stress-test stream (SSE)
    re.compile(r"^/api/v2/tasks/[^/]+/output$"),  # raw task output stream (SSE, #934)
)


def _query_ticket_allowed(path: str) -> bool:
    """Whether this request path may authenticate via ?ticket= (SSE only)."""
    return any(pattern.match(path) for pattern in _QUERY_TICKET_PATHS)


def auth_required() -> bool:
    """Whether authentication is enforced, read from the environment.

    Controlled by ``CODEFRAME_AUTH_REQUIRED`` (default ON / secure by default).
    Read at request time so tests can monkeypatch the value per call.

    Falsy values (case-insensitive): ``0``, ``false``, ``no``, ``off``.
    Anything else (including unset) is treated as enabled.
    """
    value = os.getenv("CODEFRAME_AUTH_REQUIRED")
    if value is None:
        return True
    return value.strip().lower() not in _AUTH_FALSY


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Get currently authenticated user.

    Requires a valid JWT, supplied as an ``Authorization: Bearer`` header. On
    the allowlisted SSE routes only (``_QUERY_TICKET_PATHS``), a
    ``?ticket=<value>`` query parameter is accepted when no header is present
    (browser EventSource cannot send headers; mirrors the WebSocket auth
    pattern). The ticket is a short-lived, single-use value minted by
    ``POST /auth/stream-ticket`` — not a JWT (issue #745) — so it is redeemed
    rather than decoded.

    Args:
        request: FastAPI request object
        credentials: Bearer token from Authorization header (optional)

    Returns:
        Authenticated user

    Raises:
        HTTPException: 401 if authentication not provided or invalid
    """
    if credentials and getattr(credentials, "credentials", None):
        return await _authenticate_bearer_token(credentials.credentials)

    if request is not None and _query_ticket_allowed(request.url.path):
        ticket = request.query_params.get("ticket")
        if ticket:
            return await _authenticate_stream_ticket(ticket)

    # Auth disabled (local opt-out): act as the local operator rather than
    # rejecting (#963). require_auth already degrades this way; this path did
    # not, so POST /api/auth/api-keys returned 401 with auth switched off.
    #
    # Deliberately NOT applied to the ticket-gated SSE routes. Those demand a
    # single-use ticket regardless of auth mode today, and relaxing that here
    # would widen the change from "the api-keys router works" to "SSE streams
    # open without a ticket" — a different decision than this issue asks for.
    on_ticket_path = request is not None and _query_ticket_allowed(request.url.path)
    if not auth_required() and not on_ticket_path:
        operator = await _local_operator_user(request)
        if operator is not None:
            return operator
        logger.error(
            "Auth is disabled but the database holds no user row to act as; "
            "rejecting the request."
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _authenticate_bearer_token(token: str) -> User:
    """Decode a JWT bearer token and load the active user it names."""
    # Validate JWT token
    try:
        import jwt as pyjwt
        from codeframe.auth.manager import SECRET, JWT_ALGORITHM, JWT_AUDIENCE

        # Decode JWT token directly using PyJWT
        # Note: We use direct PyJWT decoding instead of JWTStrategy.read_token()
        # because read_token() requires a user_manager instance, which would
        # create a circular dependency. The JWT constants are centralized in
        # auth.manager to ensure consistency with the JWTStrategy configuration.
        try:
            payload = pyjwt.decode(
                token,
                SECRET,
                algorithms=[JWT_ALGORITHM],
                audience=JWT_AUDIENCE,
            )
            user_id_str = payload.get("sub")
            if not user_id_str:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing subject",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user_id = int(user_id_str)
        except pyjwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (pyjwt.InvalidTokenError, ValueError) as e:
            logger.debug(f"JWT decode error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await _load_active_user(user_id)

    except HTTPException:
        raise
    except Exception as e:
        # Log full error server-side for debugging
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        # Return generic message to client (avoid leaking implementation details)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _app_db(request: Optional[Request]) -> Any:
    """The control-plane Database this request will read and write."""
    if request is None:
        return None
    db = getattr(getattr(request, "app", None), "state", None)
    db = getattr(db, "db", None) if db is not None else None
    if db is None:
        db = getattr(getattr(request, "state", None), "db", None)
    return db


async def _local_operator_user(request: Optional[Request] = None) -> Optional[User]:
    """The account the auth-disabled synthetic principal acts as (#963).

    With ``CODEFRAME_AUTH_REQUIRED=false`` the principal used to carry
    ``user_id=None``. ``api_keys.user_id`` is ``NOT NULL REFERENCES users(id)``,
    so every key operation broke in a different way: list returned nothing,
    revoke 404'd, and create 401'd because it required a JWT. The first thing a
    self-hosted evaluator tries, broken three ways.

    Resolved from **this request's** database when one is attached, not from
    the SQLAlchemy auth engine. The two are the same file in production but not
    necessarily in tests or a split-database setup, and handing back an id from
    a different database produces a foreign-key failure at write time.

    Prefers the lowest-id **login-capable** account, falling back to the
    lowest-id account overall only when none exists (a fresh local install,
    where the seeded ``admin@localhost`` placeholder is all there is). The
    preference matters because anything created under this identity — notably
    an API key — outlives the auth mode that created it; see
    ``_owner_is_login_capable`` for the other half of that guard.

    Deliberately **not** cached: caching a row keyed to a database is the exact
    staleness bug this same issue fixes in ``get_async_session_maker``.

    Returns ``None`` when no user row exists at all, which callers surface as
    401 rather than inventing an identity.
    """
    from codeframe.auth.manager import DISABLED_PASSWORD

    db = _app_db(request)
    if db is not None:
        # Offloaded like _resolve_api_key: db.conn.execute is blocking sqlite,
        # and this runs on every request while auth is disabled.
        return await run_in_threadpool(_local_operator_row, db, DISABLED_PASSWORD)

    # No request-scoped database: fall back to the auth engine. Best-effort —
    # an unreachable or unmigrated database means "no operator to act as", not
    # a failed request. Letting OperationalError escape here turned "auth is
    # disabled, let them through" into a 500 wherever DATABASE_PATH pointed at
    # nothing usable.
    try:
        from sqlalchemy import select

        from codeframe.auth.manager import get_async_session_maker

        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            base = select(User).where(User.is_active.is_(True))
            result = await session.execute(
                base.where(User.hashed_password != DISABLED_PASSWORD)
                .order_by(User.id)
                .limit(1)
            )
            user = result.scalar_one_or_none()
            if user is not None:
                return user
            result = await session.execute(base.order_by(User.id).limit(1))
            return result.scalar_one_or_none()
    except Exception as e:
        logger.debug("No local operator account resolvable: %s", e)
        return None


def _local_operator_row(db: Any, disabled_password: str) -> Optional[User]:
    """Blocking half of :func:`_local_operator_user`. Runs on a worker thread.

    Only ``is_active`` accounts are eligible. Every other identity path in this
    module enforces that — ``_load_active_user`` for JWTs, ``_owner_is_active``
    for API keys — and nothing downstream re-checks the resolved operator, so
    without it a deactivated account would still be handed read+write+admin.
    """
    try:
        row = db.conn.execute(
            "SELECT id, email, is_active, is_superuser FROM users "
            "WHERE is_active = 1 AND hashed_password != ? ORDER BY id LIMIT 1",
            (disabled_password,),
        ).fetchone()
        if row is None:
            row = db.conn.execute(
                "SELECT id, email, is_active, is_superuser FROM users "
                "WHERE is_active = 1 ORDER BY id LIMIT 1"
            ).fetchone()
    except Exception as e:
        logger.error("Could not resolve the local operator account: %s", e)
        return None
    if row is None:
        return None
    user = User()
    user.id = row[0]
    user.email = row[1]
    user.is_active = bool(row[2])
    user.is_superuser = bool(row[3])
    user.hashed_password = ""
    return user


async def _load_active_user(user_id: int) -> User:
    """Load a user by id, raising 401 if not found or inactive.

    Shared by the JWT bearer path and the stream-ticket path so both apply
    the same active-user check.
    """
    from codeframe.auth.manager import get_async_session_maker
    from sqlalchemy import select

    async_session_maker = get_async_session_maker()
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User is inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user


async def _authenticate_stream_ticket(ticket: str) -> User:
    """Redeem a stream ticket (issue #745) and load the active user it names.

    Raises 401 for an unknown/expired/already-used ticket, and for a ticket
    that redeems to ``user_id=None`` (only mintable while auth is disabled —
    there is no real user to load; ``require_auth``'s auth-disabled fallback
    is what admits that case).
    """
    from codeframe.auth.stream_tickets import TicketRedemptionError, redeem_ticket

    try:
        user_id = redeem_ticket(ticket)
    except TicketRedemptionError as e:
        logger.debug(f"Stream ticket redemption failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired ticket",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return await _load_active_user(user_id)
    except HTTPException:
        raise
    except Exception as e:
        # Unexpected DB/session failures must degrade to 401, not 500 —
        # matching the bearer path and authenticate_websocket.
        logger.error(f"Stream ticket user lookup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Get currently authenticated user, or None if not authenticated.

    Non-raising version for endpoints that optionally use authentication.

    Deliberately does **not** fall back to the local-operator identity when
    auth is disabled (#963). "Optional auth" means "tell me who authenticated,
    if anyone" — with auth off nobody did, and inventing an identity here would
    silently change what every optional-auth endpoint sees.
    """
    if credentials and getattr(credentials, "credentials", None):
        try:
            return await _authenticate_bearer_token(credentials.credentials)
        except HTTPException:
            return None

    if request is not None and _query_ticket_allowed(request.url.path):
        ticket = request.query_params.get("ticket")
        if ticket:
            try:
                return await _authenticate_stream_ticket(ticket)
            except HTTPException:
                return None

    return None


# =============================================================================
# API Key Authentication
# =============================================================================


def _owner_is_active(db: Any, user_id: Any) -> bool:
    """Whether the account behind a key is still active (#919).

    Fails closed: a missing row or an unreadable column denies rather than
    grants, so a deleted or unreadable owner cannot keep a key alive.
    """
    try:
        row = db.conn.execute(
            "SELECT is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    except Exception as e:
        logger.error(f"Could not verify API key owner's active status: {e}")
        return False

    return bool(row[0]) if row is not None else False


def _owner_is_login_capable(db: Any, user_id: Any) -> bool:
    """Whether the key's owner is an account someone can actually log in as.

    Guards a cross-mode escalation (#963 review): with auth disabled, key
    creation is attributed to the local operator, which on a fresh install is
    the seeded ``admin@localhost`` placeholder — ``is_active=1``,
    ``is_superuser=1``, and a password of ``!DISABLED!`` that no one can use.
    A key minted that way is a durable admin credential created without anyone
    authenticating; when auth is later switched on and the server exposed, it
    would keep working, because key auth otherwise checks only is_active and
    is_superuser.

    Enforced only while auth is required — with auth off the placeholder IS the
    operator, and refusing it would re-break the flow this issue fixes.

    Fails closed: a missing or unreadable row denies.
    """
    if not auth_required():
        return True
    try:
        from codeframe.auth.manager import DISABLED_PASSWORD

        row = db.conn.execute(
            "SELECT hashed_password FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    except Exception as e:
        logger.error(f"Could not verify API key owner's login capability: {e}")
        return False
    if row is None:
        return False
    return row[0] != DISABLED_PASSWORD


def _scopes_within_owner_grant(db: Any, key_record: Dict[str, Any]) -> list:
    """Clamp a key's stored scopes to what its owner currently holds (#898).

    ``admin`` is the only scope tied to the user record, so this drops it when
    the owning account is not ``is_superuser``. Enforcing it here rather than at
    creation alone makes the invariant *continuous*: it also covers admin keys
    persisted before the creation guard existed, and a key whose owner is later
    demoted — neither of which a one-time migration would keep true.

    Fails closed: a missing user row or an unreadable ``is_superuser`` drops
    admin rather than granting it.
    """
    scopes = list(key_record.get("scopes") or [])
    if SCOPE_ADMIN not in scopes:
        return scopes

    try:
        row = db.conn.execute(
            "SELECT is_superuser FROM users WHERE id = ?", (key_record["user_id"],)
        ).fetchone()
        is_superuser = bool(row[0]) if row is not None else False
    except Exception as e:
        logger.error(f"Could not verify API key owner's admin status: {e}")
        is_superuser = False

    if is_superuser:
        return scopes

    logger.warning(
        "API key %s carries admin scope but its owner (user_id=%s) is not a "
        "superuser; admin dropped for this request (#898).",
        key_record.get("id"),
        key_record.get("user_id"),
    )
    return [s for s in scopes if s != SCOPE_ADMIN]


# How long to suppress repeat ``last_used_at`` writes for the same key (#902).
# Every API-key request used to do a bcrypt verify, a SELECT *and* an
# UPDATE+COMMIT against a lock with busy_timeout=5000 — a write per request, on
# the event loop, purely to refresh a timestamp nothing reads at that
# resolution. Five minutes keeps the field useful for "is this key still in
# use?" while removing almost all of the writes.
_LAST_USED_COALESCE_SECONDS = 300.0

# In-process only: each worker refreshes at most once per window per key, which
# is the right trade for a usage hint. Entries older than the window are pruned
# on access, so this tracks keys in *current* use rather than every key ever
# authenticated — a revoked key's slot does not outlive the window.
_last_used_writes: Dict[str, float] = {}
_last_used_lock = threading.Lock()


def _should_record_last_used(key_id: str) -> bool:
    """Whether this key's ``last_used_at`` is due for a refresh."""
    now = time.monotonic()
    with _last_used_lock:
        # Prune first: an expired entry would be overwritten anyway, and this
        # keeps the dict proportional to keys in active use.
        for stale in [
            k
            for k, t in _last_used_writes.items()
            if (now - t) >= _LAST_USED_COALESCE_SECONDS
        ]:
            del _last_used_writes[stale]

        if key_id in _last_used_writes:
            return False
        _last_used_writes[key_id] = now
        return True


def _release_last_used_claim(key_id: str) -> None:
    """Undo a claim whose write failed, so the next request can retry.

    The slot is claimed *before* the UPDATE (it is what makes the check atomic),
    so a failed write must give it back rather than suppress refreshes for the
    rest of the window.
    """
    with _last_used_lock:
        _last_used_writes.pop(key_id, None)


async def get_api_key_auth(
    api_key: Optional[str] = Security(api_key_header),
    request: Request = None,
) -> Optional[Dict[str, Any]]:
    """Extract and validate API key from X-API-Key header.

    The work is entirely synchronous — a bcrypt verify plus SQLite reads — so
    it runs on a worker thread (#902). Inline, every API-key request blocked the
    event loop on a lock with a 5s busy timeout.

    Args:
        api_key: API key from header (auto-extracted by FastAPI Security)
        request: FastAPI request object (for accessing db via state)

    Returns:
        Auth dict if valid API key, None otherwise.
        Dict contains: type, user_id, scopes, key_id
    """
    if not api_key:
        return None
    return await run_in_threadpool(_resolve_api_key, api_key, request)


# Process-wide fallback database for API-key auth, keyed on the resolved
# DATABASE_PATH (#963). Two things were wrong before: it was constructed AND
# schema-initialised *per request*, and its default was
# ``os.path.join(os.getcwd(), ".codeframe", "state.db")`` — so a server started
# outside a workspace scattered SQLite files wherever it happened to run, then
# authenticated against the empty database it had just created. There is no
# cwd default any more; without DATABASE_PATH the key is simply refused.
_fallback_db_lock = threading.Lock()
_fallback_db: Any = None
_fallback_db_path: Optional[str] = None


def _shared_fallback_db() -> Any:
    """Return a cached Database for DATABASE_PATH, or ``None`` if unset.

    Keyed on the resolved path so a changed DATABASE_PATH rebuilds rather than
    serving a handle to the previous database — the same staleness trap #963
    fixes in ``get_async_session_maker``.
    """
    global _fallback_db, _fallback_db_path

    db_path = os.getenv("DATABASE_PATH")
    if not db_path:
        return None

    with _fallback_db_lock:
        if _fallback_db is not None and _fallback_db_path == db_path:
            return _fallback_db
        if _fallback_db is not None:
            try:
                _fallback_db.close()
            except Exception:
                pass
            _fallback_db = None
        from codeframe.platform_store.database import Database

        logger.warning(
            "No db on app.state; using the DATABASE_PATH fallback for API-key "
            "auth. The server should attach its control-plane store instead."
        )
        db = Database(db_path)
        db.initialize()
        _fallback_db = db
        _fallback_db_path = db_path
        return _fallback_db


def reset_fallback_db() -> None:
    """Drop the cached fallback database (tests, and DATABASE_PATH changes)."""
    global _fallback_db, _fallback_db_path
    with _fallback_db_lock:
        if _fallback_db is not None:
            try:
                _fallback_db.close()
            except Exception:
                pass
        _fallback_db = None
        _fallback_db_path = None


def _resolve_api_key(api_key: str, request: Optional[Request]) -> Optional[Dict[str, Any]]:
    """Blocking half of :func:`get_api_key_auth`. Runs on a worker thread."""
    try:
        # Get database from app state (singleton) or request state
        db = getattr(request.app.state, "db", None)
        if db is None:
            db = getattr(request.state, "db", None)
        if db is None:
            db = _shared_fallback_db()
        if db is None:
            logger.error(
                "API key auth attempted with no database on app.state and no "
                "DATABASE_PATH set; rejecting the key."
            )
            return None

        # Extract prefix and look up key
        try:
            prefix = extract_prefix(api_key)
        except ValueError:
            logger.warning("API key auth failed: invalid key format")
            return None

        # Every live key sharing this prefix, not one arbitrary row: the prefix
        # carries only 4 random hex characters and its index is not UNIQUE, so a
        # collision used to leave one of the two keys permanently dead (#919).
        candidates = db.api_keys.get_all_by_prefix(prefix)
        if not candidates:
            logger.warning(f"API key auth failed: key not found (prefix: {prefix[:4]}...)")
            return None

        key_record = next(
            (c for c in candidates if verify_api_key(api_key, c["key_hash"])), None
        )
        if key_record is None:
            logger.warning(f"API key auth failed: verification failed (prefix: {prefix[:4]}...)")
            return None

        # An API key is only as live as the account behind it. Without this,
        # `users.is_active = 0` revoked browser sessions but left every API key
        # of that user working — there was no revocation-by-account at all
        # (#919). Fails closed on a missing or unreadable row.
        if not _owner_is_active(db, key_record["user_id"]):
            logger.warning(
                "API key auth failed: owner (user_id=%s) is inactive",
                key_record["user_id"],
            )
            return None

        # A key owned by an account nobody can log in as is not a credential
        # anyone authenticated to create (#963 review). Refused while auth is
        # enforced, so a key minted in local auth-off mode cannot survive into
        # an exposed deployment.
        if not _owner_is_login_capable(db, key_record["user_id"]):
            logger.warning(
                "API key auth failed: owner (user_id=%s) cannot log in "
                "(placeholder account); refusing while auth is enforced.",
                key_record["user_id"],
            )
            return None

        # Refresh last_used_at at most once per key per window (#902) — this is
        # an UPDATE+COMMIT, and doing it on every request made each
        # authenticated call a database writer.
        if _should_record_last_used(key_record["id"]):
            try:
                db.api_keys.update_last_used(key_record["id"])
            except Exception as e:
                logger.warning(f"Failed to update last_used_at: {e}")
                _release_last_used_claim(key_record["id"])

        return {
            "type": "api_key",
            "user_id": key_record["user_id"],
            "scopes": _scopes_within_owner_grant(db, key_record),
            "key_id": key_record["id"],
        }

    except HTTPException:
        raise
    except Exception as e:
        # Unexpected failure (e.g. transient DB error). Surface it loudly — a
        # valid key must not silently degrade to 401 with the cause hidden at
        # debug level (#760). Matches the bearer path's logging; still degrades
        # to no-auth (returns None) per this module's degrade-to-401 policy.
        logger.error(f"API key authentication error: {e}", exc_info=True)
        return None


async def require_auth(
    request: Request = None,
    api_key_auth: Optional[Dict[str, Any]] = Depends(get_api_key_auth),
    jwt_user: Optional[User] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Require authentication via either API key or JWT token.

    API keys take precedence if both are present.

    The resolved principal is also published to ``request.state.user`` so the
    rate limiter's key function can key limits per user (issue #754). Without
    this, ``request.state.user`` is never set and every rate limit — including
    auth brute-force protection — collapses to per-IP, sharing one bucket
    behind a NAT/proxy.

    Args:
        request: FastAPI request object (injected; used to publish the principal)
        api_key_auth: Result from get_api_key_auth (if API key provided)
        jwt_user: Result from get_current_user_optional (if JWT provided)

    Returns:
        Auth dict with: type, user_id, scopes, and optional user/key_id

    Raises:
        HTTPException: 401 if no valid authentication provided
    """

    def _resolve(principal: Dict[str, Any]) -> Dict[str, Any]:
        # Publish the principal for the rate limiter's key func (issue #754).
        if request is not None:
            request.state.user = principal
        return principal

    # Prefer API key if provided
    if api_key_auth is not None:
        return _resolve(api_key_auth)

    # Fall back to JWT
    if jwt_user is not None:
        # Scopes come from the user record (#898). Handing every session
        # [read, write, admin] made require_scope(SCOPE_ADMIN) decorative:
        # anyone with a browser token could store credentials and merge PRs.
        # getattr, not attribute access: a principal that somehow lacks the
        # column must fail closed to non-admin rather than 500.
        scopes = [SCOPE_READ, SCOPE_WRITE]
        if getattr(jwt_user, "is_superuser", False):
            scopes.append(SCOPE_ADMIN)
        return _resolve({
            "type": "jwt",
            "user_id": jwt_user.id,
            "scopes": scopes,
            "user": jwt_user,
        })

    # Auth disabled (local opt-out): return a synthetic local-admin principal
    # instead of raising. Real credentials above always take precedence.
    if not auth_required():
        # A stable, real user_id (#963): api_keys.user_id is a NOT NULL foreign
        # key, so None made list/create/revoke fail in three different ways.
        operator = await _local_operator_user(request)
        return _resolve({
            "type": "disabled",
            "user_id": getattr(operator, "id", None),
            "scopes": [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
            "user": operator,
        })

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )


# HTTP methods that only read state — everything else mutates (#717).
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def require_method_scope(
    request: Request,
    auth: Dict[str, Any] = Depends(require_auth),
) -> Dict[str, Any]:
    """Router-level guard that enforces scope by HTTP method (issue #717).

    Safe methods (GET/HEAD/OPTIONS) require the ``read`` scope; mutating
    methods (POST/PUT/PATCH/DELETE) require ``write``. Admin-only routes layer
    their own ``Depends(require_scope("admin"))`` on top. JWT principals carry
    read+write (admin only when ``is_superuser``, #898) and the auth-disabled
    synthetic principal carries all scopes, so in practice this guard constrains
    scoped API keys — a read-only key can no longer mutate state.
    """
    required = SCOPE_READ if request.method.upper() in _SAFE_METHODS else SCOPE_WRITE
    if not has_scope(auth, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: '{required}' scope required",
        )
    return auth


async def authenticate_websocket(
    websocket: WebSocket,
    *,
    close_code: int,
) -> Tuple[bool, Optional[int]]:
    """Authenticate a WebSocket connection, honoring the no-auth opt-out.

    This is the single source of truth for WebSocket auth so the terminal and
    session-chat sockets cannot drift from the REST behavior of ``require_auth()``:

    - When auth is disabled (``CODEFRAME_AUTH_REQUIRED`` falsy), returns
      ``(True, None)`` without requiring a ticket.

      **This no longer matches REST.** Since #963 the REST no-auth principal
      resolves to a real account (``_local_operator_user``) so that API-key
      operations, which need a NOT NULL ``users.id``, work at all. WebSocket
      auth still admits an anonymous ``user_id=None``. The divergence is
      deliberate for now: nothing on these sockets writes a row keyed to the
      principal, so there is no foreign key to satisfy and no durable artifact
      to attribute — the reason REST needed a real id does not apply here.
      Align them if a WS path ever persists per-user state.
    - Otherwise redeems the ``?ticket=<value>`` query parameter — a short-lived,
      single-use value minted by ``POST /auth/stream-ticket`` (issue #745), not
      a JWT — then loads the active DB user it names. On success returns
      ``(True, user_id)``. On any failure the socket is closed with
      ``close_code`` and ``(False, None)`` is returned.

    Args:
        websocket: The incoming WebSocket connection (not yet accepted).
        close_code: Close code to use when rejecting (callers pass their existing
            code, e.g. ``4001`` for terminal, ``1008`` for session chat).

    Returns:
        ``(authenticated, user_id)``. ``user_id`` is ``None`` both in no-auth
        mode and on failure — callers gate on the boolean, not on ``user_id``.
    """
    # Single source of truth for the no-auth opt-out — shared with require_auth().
    if not auth_required():
        return True, None

    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=close_code, reason="Authentication required: missing ticket")
        return False, None

    from codeframe.auth.stream_tickets import TicketRedemptionError, redeem_ticket

    try:
        user_id = redeem_ticket(ticket)
    except TicketRedemptionError as exc:
        logger.debug("WebSocket ticket redemption failed: %s", exc)
        await websocket.close(code=close_code, reason="Invalid or expired ticket")
        return False, None

    if user_id is None:
        # Only mintable while auth was disabled at mint time; auth is required
        # here, so there is no real user to admit.
        await websocket.close(code=close_code, reason="Authentication required")
        return False, None

    try:
        await _load_active_user(user_id)
    except HTTPException:
        await websocket.close(code=close_code, reason="Authentication failed")
        return False, None
    except Exception as exc:
        logger.error("WebSocket user lookup error: %s", exc)
        await websocket.close(code=close_code, reason="Authentication failed")
        return False, None

    return True, user_id


def require_scope(required_scope: str) -> Callable:
    """Create a dependency that checks for a required scope.

    Scope Hierarchy:
        - admin: grants read, write, and admin permissions
        - write: grants read and write permissions
        - read: grants read permission only

    Usage:
        @router.post("/resource")
        async def create_resource(auth: dict = Depends(require_scope("write"))):
            ...

    Args:
        required_scope: The scope required for access (read, write, or admin)

    Returns:
        Dependency function that validates scope
    """
    # Depends on require_auth directly (not require_method_scope): on admin
    # routes both run, but FastAPI caches require_auth within a request, so
    # there is exactly one authentication call — the method guard checks
    # write and this checks admin against the same principal (#717).
    async def check_scope(auth: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
        """Verify principal has required scope."""
        if not has_scope(auth, required_scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: '{required_scope}' scope required",
            )
        return auth

    return check_scope
