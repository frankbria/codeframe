"""Single-use, short-lived tickets for SSE/WS stream authentication (issue #745).

Browser ``EventSource`` (SSE) and raw WebSocket clients cannot send a custom
``Authorization`` header, so streaming routes historically accepted a
long-lived JWT in the ``?token=`` query string instead. Query strings leak via
proxy/access logs and browser history, so a long-lived credential there is a
standing exposure. This module replaces that with an opaque, single-use
ticket: mint one via ``POST /auth/stream-ticket`` (itself authenticated
normally), then open the stream with ``?ticket=<value>``. A ticket is valid
for :data:`TICKET_TTL_SECONDS` and is consumed on first redemption.

Follows the module-global singleton + reset pattern used by
``codeframe.lib.rate_limiter`` (``_limiter`` / ``get_rate_limiter`` /
``reset_rate_limiter``).

Limitation: the ticket store is in-process only, like the rate limiter's
default in-memory storage. In a multi-worker deployment, a ticket minted by
one worker cannot be redeemed against another worker's store. Accepted
trade-off for the single-operator self-hosted default (see
``RATE_LIMIT_STORAGE`` for the same limitation elsewhere).
"""

import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

TICKET_TTL_SECONDS = 60

# Module-global ticket store + lock, mirroring rate_limiter.py's _limiter.
_tickets: Dict[str, "_TicketEntry"] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class _TicketEntry:
    user_id: Optional[int]
    expires_at: float


class TicketRedemptionError(Exception):
    """Raised when a ticket cannot be redeemed: missing, expired, or already used."""


def _now() -> float:
    """Monotonic clock, indirected so tests can substitute a fake one."""
    return time.monotonic()


def _sweep_expired_locked(now: float) -> None:
    """Drop expired entries. Caller must hold ``_lock``."""
    expired = [ticket for ticket, entry in _tickets.items() if entry.expires_at <= now]
    for ticket in expired:
        del _tickets[ticket]


def mint_ticket(user_id: Optional[int]) -> str:
    """Mint a new single-use ticket good for ``TICKET_TTL_SECONDS``.

    Args:
        user_id: The authenticated user's id, or ``None`` when minted while
            ``CODEFRAME_AUTH_REQUIRED`` is disabled (synthetic principal).

    Returns:
        An opaque, URL-safe ticket string.
    """
    ticket = secrets.token_urlsafe(32)
    now = _now()
    with _lock:
        _sweep_expired_locked(now)
        _tickets[ticket] = _TicketEntry(user_id=user_id, expires_at=now + TICKET_TTL_SECONDS)
    return ticket


def redeem_ticket(ticket: str) -> Optional[int]:
    """Redeem a ticket exactly once.

    Args:
        ticket: The ticket string to redeem.

    Returns:
        The ``user_id`` the ticket was minted for (may be ``None``).

    Raises:
        TicketRedemptionError: if the ticket is unknown, expired, or has
            already been redeemed.
    """
    now = _now()
    with _lock:
        _sweep_expired_locked(now)
        entry = _tickets.pop(ticket, None)

    if entry is None:
        raise TicketRedemptionError("Invalid or expired ticket")

    return entry.user_id


def reset_stream_tickets() -> None:
    """Clear the global ticket store. Useful for test isolation."""
    with _lock:
        _tickets.clear()
