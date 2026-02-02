"""Rate limiting configuration for CodeFRAME API.

This module provides configuration for API rate limiting using slowapi.
Rate limits can be configured via environment variables for flexibility
across deployment environments.

Environment Variables:
    RATE_LIMIT_ENABLED: Enable/disable rate limiting (default: true)
    RATE_LIMIT_AUTH: Rate limit for authentication endpoints (default: 10/minute)
    RATE_LIMIT_STANDARD: Rate limit for standard API endpoints (default: 100/minute)
    RATE_LIMIT_AI: Rate limit for AI/expensive operations (default: 20/minute)
    RATE_LIMIT_WEBSOCKET: Rate limit for WebSocket connections (default: 30/minute)
    RATE_LIMIT_STORAGE: Storage backend - memory or redis (default: memory)
    REDIS_URL: Redis connection URL for distributed rate limiting (optional)
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_bool(value: str) -> bool:
    """Parse boolean from string, supporting various formats.

    Args:
        value: String value to parse

    Returns:
        Boolean interpretation of the value
    """
    return value.lower() in ("true", "1", "yes", "on")


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
    """

    auth_limit: str = "10/minute"
    standard_limit: str = "100/minute"
    ai_limit: str = "20/minute"
    websocket_limit: str = "30/minute"
    enabled: bool = True
    storage: str = "memory"
    redis_url: Optional[str] = None

    @classmethod
    def from_environment(cls) -> "RateLimitConfig":
        """Create RateLimitConfig from environment variables.

        Returns:
            RateLimitConfig instance with values from environment
        """
        enabled_str = os.getenv("RATE_LIMIT_ENABLED", "true")
        enabled = _parse_bool(enabled_str)

        auth_limit = os.getenv("RATE_LIMIT_AUTH", "10/minute")
        standard_limit = os.getenv("RATE_LIMIT_STANDARD", "100/minute")
        ai_limit = os.getenv("RATE_LIMIT_AI", "20/minute")
        websocket_limit = os.getenv("RATE_LIMIT_WEBSOCKET", "30/minute")
        storage = os.getenv("RATE_LIMIT_STORAGE", "memory")
        redis_url = os.getenv("REDIS_URL")

        # Validate storage type
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
            auth_limit=auth_limit,
            standard_limit=standard_limit,
            ai_limit=ai_limit,
            websocket_limit=websocket_limit,
            enabled=enabled,
            storage=storage,
            redis_url=redis_url,
        )


@lru_cache(maxsize=1)
def get_rate_limit_config() -> RateLimitConfig:
    """Get the global rate limit configuration.

    Loads from environment on first call, cached thereafter.
    Thread-safe via lru_cache.

    Returns:
        RateLimitConfig instance
    """
    config = RateLimitConfig.from_environment()
    logger.info(
        f"Rate limit config initialized: "
        f"enabled={config.enabled}, "
        f"storage={config.storage}, "
        f"standard={config.standard_limit}"
    )
    return config


def _reset_rate_limit_config() -> None:
    """Reset the global rate limit configuration.

    Useful for testing to ensure clean state between tests.
    """
    get_rate_limit_config.cache_clear()
