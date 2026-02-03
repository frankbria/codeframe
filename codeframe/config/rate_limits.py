"""Rate limiting configuration for CodeFRAME API.

This module provides configuration for API rate limiting using slowapi.
It delegates to GlobalConfig in core/config.py as the single source of truth
for environment variable handling.

Environment Variables (via GlobalConfig):
    RATE_LIMIT_ENABLED: Enable/disable rate limiting (default: true)
    RATE_LIMIT_AUTH: Rate limit for authentication endpoints (default: 10/minute)
    RATE_LIMIT_STANDARD: Rate limit for standard API endpoints (default: 100/minute)
    RATE_LIMIT_AI: Rate limit for AI/expensive operations (default: 20/minute)
    RATE_LIMIT_WEBSOCKET: Rate limit for WebSocket connections (default: 30/minute)
    RATE_LIMIT_STORAGE: Storage backend - memory or redis (default: memory)
    RATE_LIMIT_TRUSTED_PROXIES: Comma-separated trusted proxy IPs/CIDRs
    REDIS_URL: Redis connection URL for distributed rate limiting (optional)
"""

import ipaddress
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for API rate limiting.

    Attributes:
        auth_limit: Rate limit for authentication endpoints
        standard_limit: Rate limit for standard API endpoints
        ai_limit: Rate limit for AI/expensive operations
        websocket_limit: Rate limit for WebSocket connections
        enabled: Whether rate limiting is enabled
        storage: Storage backend ('memory' or 'redis')
        redis_url: Redis connection URL for distributed rate limiting
        trusted_proxies: List of trusted proxy IP addresses/networks
    """

    auth_limit: str = "10/minute"
    standard_limit: str = "100/minute"
    ai_limit: str = "20/minute"
    websocket_limit: str = "30/minute"
    enabled: bool = True
    storage: str = "memory"
    redis_url: Optional[str] = None
    trusted_proxies: list = field(default_factory=list)

    def is_trusted_proxy(self, ip: str) -> bool:
        """Check if an IP address is from a trusted proxy.

        Args:
            ip: IP address to check

        Returns:
            True if IP is in trusted_proxies list or matches a trusted network
        """
        if not self.trusted_proxies:
            return False

        try:
            client_ip = ipaddress.ip_address(ip)
            for proxy in self.trusted_proxies:
                try:
                    # Check if it's a network (CIDR notation)
                    if "/" in proxy:
                        network = ipaddress.ip_network(proxy, strict=False)
                        if client_ip in network:
                            return True
                    else:
                        # Check exact IP match
                        if client_ip == ipaddress.ip_address(proxy):
                            return True
                except ValueError:
                    # Invalid proxy entry, skip it
                    continue
            return False
        except ValueError:
            # Invalid IP address
            return False

    @classmethod
    def from_global_config(cls) -> "RateLimitConfig":
        """Create RateLimitConfig from GlobalConfig.

        Uses core/config.py as the single source of truth for
        environment variable handling.

        Returns:
            RateLimitConfig instance with values from GlobalConfig
        """
        # Import here to avoid circular imports
        from codeframe.core.config import get_global_config

        global_config = get_global_config()

        enabled = global_config.rate_limit_enabled
        storage = global_config.rate_limit_storage
        redis_url = global_config.redis_url

        # Parse trusted proxies from comma-separated string
        trusted_proxies_str = global_config.rate_limit_trusted_proxies.strip()
        trusted_proxies = []
        if trusted_proxies_str:
            trusted_proxies = [
                p.strip() for p in trusted_proxies_str.split(",") if p.strip()
            ]

        # Validate storage type (already validated by Pydantic, but double-check)
        if storage not in ("memory", "redis"):
            logger.warning(
                f"Invalid RATE_LIMIT_STORAGE: {storage}. "
                f"Must be 'memory' or 'redis'. Defaulting to 'memory'."
            )
            storage = "memory"

        # Warn if redis storage is requested but no URL provided
        if storage == "redis" and not redis_url:
            logger.warning(
                "RATE_LIMIT_STORAGE is 'redis' but REDIS_URL is not set. "
                "Falling back to in-memory storage."
            )
            storage = "memory"

        return cls(
            auth_limit=global_config.rate_limit_auth,
            standard_limit=global_config.rate_limit_standard,
            ai_limit=global_config.rate_limit_ai,
            websocket_limit=global_config.rate_limit_websocket,
            enabled=enabled,
            storage=storage,
            redis_url=redis_url,
            trusted_proxies=trusted_proxies,
        )


@lru_cache(maxsize=1)
def get_rate_limit_config() -> RateLimitConfig:
    """Get the global rate limit configuration.

    Loads from GlobalConfig on first call, cached thereafter.
    Thread-safe via lru_cache.

    Returns:
        RateLimitConfig instance
    """
    config = RateLimitConfig.from_global_config()
    logger.info(
        f"Rate limit config initialized: "
        f"enabled={config.enabled}, "
        f"storage={config.storage}, "
        f"standard={config.standard_limit}, "
        f"trusted_proxies={len(config.trusted_proxies)} configured"
    )
    return config


def _reset_rate_limit_config() -> None:
    """Reset the global rate limit configuration.

    Useful for testing to ensure clean state between tests.
    """
    get_rate_limit_config.cache_clear()
