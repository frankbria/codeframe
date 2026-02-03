"""Rate limiting middleware for CodeFRAME API.

This module provides rate limiting functionality using slowapi, with support
for different rate limits per endpoint category and proper 429 responses.

Rate limit categories:
- auth: Authentication endpoints (login, register)
- standard: Standard API endpoints (CRUD operations)
- ai: AI/expensive operations (chat, generation)
- websocket: WebSocket connections

Key extraction:
- Authenticated requests: User ID from token
- Unauthenticated requests: Client IP address

Security:
- X-Forwarded-For is only trusted when request comes from a configured trusted proxy
- "unknown" IPs are logged and tracked for security monitoring
- Configure RATE_LIMIT_TRUSTED_PROXIES to define trusted proxy networks
"""

import logging
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from codeframe.config.rate_limits import get_rate_limit_config

logger = logging.getLogger(__name__)

# Global limiter instance
_limiter: Optional[Limiter] = None
# Track if we've logged the disabled message to avoid duplicate logs
_logged_disabled: bool = False


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request with trusted proxy validation.

    Only trusts X-Forwarded-For and X-Real-IP headers when the direct
    connection is from a configured trusted proxy. This prevents header
    spoofing attacks.

    Security Note:
    - If RATE_LIMIT_TRUSTED_PROXIES is not configured, proxy headers are ignored
    - Configure trusted proxies when running behind a reverse proxy (nginx, ALB, etc.)

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string, or "unknown" if not determinable
    """
    config = get_rate_limit_config()

    # Get the direct connection IP
    direct_ip = None
    if request.client and request.client.host:
        direct_ip = request.client.host

    # Only trust proxy headers if direct connection is from a trusted proxy
    if direct_ip and config.is_trusted_proxy(direct_ip):
        # Check X-Forwarded-For header (may contain multiple IPs)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Return first IP in the chain (real client)
            client_ip = forwarded_for.split(",")[0].strip()
            if client_ip:
                return client_ip

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    elif direct_ip:
        # Not from trusted proxy - check if headers were spoofed
        if request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP"):
            logger.warning(
                f"Proxy headers present from non-trusted IP {direct_ip}. "
                f"Headers ignored. Configure RATE_LIMIT_TRUSTED_PROXIES if "
                f"running behind a reverse proxy."
            )

    # Use direct connection IP
    if direct_ip:
        return direct_ip

    # Unable to determine IP - log for security monitoring
    logger.warning(
        "Unable to determine client IP address. "
        "This may indicate proxy misconfiguration. "
        f"Path: {request.url.path}"
    )
    return "unknown"


def get_rate_limit_key(request: Request) -> str:
    """Generate rate limit key for a request.

    Uses user ID for authenticated requests, IP address for unauthenticated.
    Applies stricter rate limiting for "unknown" IPs to mitigate DoS risk.

    Args:
        request: FastAPI request object

    Returns:
        Rate limit key string in format "user:{id}" or "ip:{address}"
    """
    # Check if user is authenticated (set by auth middleware)
    user = getattr(getattr(request, "state", None), "user", None)

    if user and hasattr(user, "id") and user.id:
        return f"user:{user.id}"

    # Fall back to IP address
    client_ip = get_client_ip(request)

    # Mark "unknown" IPs specially for potential stricter handling
    if client_ip == "unknown":
        # Use a unique key per request for unknown IPs
        # This effectively gives each "unknown" request its own bucket
        # preventing the shared bucket DoS attack
        request_id = id(request)
        return f"ip:unknown:{request_id}"

    return f"ip:{client_ip}"


def get_rate_limiter() -> Optional[Limiter]:
    """Get or create the rate limiter instance.

    Returns:
        Limiter instance if rate limiting is enabled, None otherwise
    """
    global _limiter
    global _logged_disabled

    config = get_rate_limit_config()

    if not config.enabled:
        if not _logged_disabled:
            logger.info("Rate limiting is disabled")
            _logged_disabled = True
        return None

    if _limiter is None:
        # Create limiter with appropriate storage
        if config.storage == "redis" and config.redis_url:
            try:
                _limiter = Limiter(
                    key_func=get_rate_limit_key,
                    storage_uri=config.redis_url,
                )
                logger.info("Rate limiter initialized with Redis storage")
            except ImportError as e:
                logger.error(f"Redis storage requested but redis module not available: {e}. Falling back to memory.")
                _limiter = Limiter(key_func=get_rate_limit_key)
        else:
            _limiter = Limiter(key_func=get_rate_limit_key)
            logger.info("Rate limiter initialized with in-memory storage")

    return _limiter


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom exception handler for rate limit exceeded errors.

    Returns a proper 429 response with standard rate limit headers.
    Also logs the event to the audit log for security monitoring.

    Args:
        request: FastAPI request object
        exc: RateLimitExceeded exception

    Returns:
        JSONResponse with 429 status and rate limit headers
    """
    # Extract request info
    client_ip = get_client_ip(request)
    user = getattr(getattr(request, "state", None), "user", None)
    user_id = user.id if user and hasattr(user, "id") and user.id else None
    endpoint = request.url.path

    # Log to standard logger
    logger.warning(
        f"Rate limit exceeded: path={endpoint}, "
        f"ip={client_ip}, user_id={user_id}"
    )

    # Log to audit log for security monitoring
    try:
        db = getattr(getattr(request, "app", None), "state", None)
        db = getattr(db, "db", None) if db else None
        if db:
            from codeframe.lib.audit_logger import AuditLogger, AuditEventType

            audit = AuditLogger(db)
            audit.log_rate_limit_event(
                event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
                user_id=user_id,
                ip_address=client_ip,
                endpoint=endpoint,
                limit_category=None,  # Not easily determinable from exception
                metadata={
                    "limit": str(exc.limit) if hasattr(exc, "limit") else None,
                    "retry_after": str(exc.detail) if hasattr(exc, "detail") else "60",
                },
            )
    except Exception as e:
        # Don't let audit logging failure affect the rate limit response
        logger.debug(f"Failed to log rate limit event to audit log: {e}")

    # Build response headers
    headers = {
        "Retry-After": str(exc.detail) if hasattr(exc, "detail") else "60",
    }

    # Add rate limit info headers if available
    if hasattr(exc, "limit"):
        headers["X-RateLimit-Limit"] = str(exc.limit)

    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": "Too many requests. Please try again later.",
            "retry_after": headers.get("Retry-After", "60"),
        },
        headers=headers,
    )

    return response


def _create_rate_limit_decorator(limit_key: str) -> Callable:
    """Create a rate limit decorator for a specific limit category.

    Args:
        limit_key: Configuration key for the limit (e.g., 'standard_limit')

    Returns:
        Decorator function that applies the rate limit
    """

    def decorator():
        """Rate limit decorator that reads limit from config."""

        def wrapper(func: Callable) -> Callable:
            # Get the limiter and config
            limiter = get_rate_limiter()
            config = get_rate_limit_config()

            if limiter is None or not config.enabled:
                # Rate limiting disabled, return function as-is
                return func

            # Get the limit value from config
            limit_value = getattr(config, limit_key, "100/minute")

            # Apply the slowapi limit decorator
            return limiter.limit(limit_value)(func)

        return wrapper

    return decorator


# Rate limit decorators for each category
def rate_limit_auth() -> Callable:
    """Decorator for authentication endpoint rate limits.

    Default: 10 requests/minute (configurable via RATE_LIMIT_AUTH)
    """
    return _create_rate_limit_decorator("auth_limit")()


def rate_limit_standard() -> Callable:
    """Decorator for standard API endpoint rate limits.

    Default: 100 requests/minute (configurable via RATE_LIMIT_STANDARD)
    """
    return _create_rate_limit_decorator("standard_limit")()


def rate_limit_ai() -> Callable:
    """Decorator for AI/expensive operation rate limits.

    Default: 20 requests/minute (configurable via RATE_LIMIT_AI)
    """
    return _create_rate_limit_decorator("ai_limit")()


def rate_limit_websocket() -> Callable:
    """Decorator for WebSocket connection rate limits.

    Default: 30 connections/minute (configurable via RATE_LIMIT_WEBSOCKET)
    """
    return _create_rate_limit_decorator("websocket_limit")()


def reset_rate_limiter() -> None:
    """Reset the global rate limiter instance.

    Useful for testing to ensure clean state between tests.
    """
    global _limiter
    global _logged_disabled
    _limiter = None
    _logged_disabled = False
