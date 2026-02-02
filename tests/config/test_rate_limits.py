"""Tests for rate limiting configuration module.

TDD tests written before implementation to define the expected behavior
of the RateLimitConfig class.
"""

import os
from unittest.mock import patch
import pytest


class TestRateLimitConfig:
    """Tests for RateLimitConfig dataclass."""

    def test_default_values(self):
        """RateLimitConfig should have sensible defaults."""
        from codeframe.config.rate_limits import RateLimitConfig

        config = RateLimitConfig()

        assert config.auth_limit == "10/minute"
        assert config.standard_limit == "100/minute"
        assert config.ai_limit == "20/minute"
        assert config.websocket_limit == "30/minute"
        assert config.enabled is True
        assert config.storage == "memory"
        assert config.redis_url is None

    def test_from_environment_with_defaults(self):
        """from_environment should use defaults when env vars not set."""
        from codeframe.config.rate_limits import RateLimitConfig

        # Clear any rate limit env vars
        env_vars = [
            "RATE_LIMIT_ENABLED",
            "RATE_LIMIT_AUTH",
            "RATE_LIMIT_STANDARD",
            "RATE_LIMIT_AI",
            "RATE_LIMIT_WEBSOCKET",
            "RATE_LIMIT_STORAGE",
            "REDIS_URL",
        ]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_vars}

        with patch.dict(os.environ, clean_env, clear=True):
            config = RateLimitConfig.from_environment()

            assert config.auth_limit == "10/minute"
            assert config.standard_limit == "100/minute"
            assert config.ai_limit == "20/minute"
            assert config.websocket_limit == "30/minute"
            assert config.enabled is True
            assert config.storage == "memory"

    def test_from_environment_custom_values(self):
        """from_environment should read custom values from env vars."""
        from codeframe.config.rate_limits import RateLimitConfig

        custom_env = {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_AUTH": "5/minute",
            "RATE_LIMIT_STANDARD": "200/minute",
            "RATE_LIMIT_AI": "10/minute",
            "RATE_LIMIT_WEBSOCKET": "50/minute",
            "RATE_LIMIT_STORAGE": "redis",
            "REDIS_URL": "redis://localhost:6379/0",
        }

        with patch.dict(os.environ, custom_env, clear=True):
            config = RateLimitConfig.from_environment()

            assert config.auth_limit == "5/minute"
            assert config.standard_limit == "200/minute"
            assert config.ai_limit == "10/minute"
            assert config.websocket_limit == "50/minute"
            assert config.enabled is True
            assert config.storage == "redis"
            assert config.redis_url == "redis://localhost:6379/0"

    def test_from_environment_disabled(self):
        """from_environment should handle disabled rate limiting."""
        from codeframe.config.rate_limits import RateLimitConfig

        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "false"}, clear=True):
            config = RateLimitConfig.from_environment()

            assert config.enabled is False

    def test_from_environment_case_insensitive_boolean(self):
        """from_environment should handle various boolean formats."""
        from codeframe.config.rate_limits import RateLimitConfig

        for true_value in ["true", "True", "TRUE", "1", "yes"]:
            with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": true_value}, clear=True):
                config = RateLimitConfig.from_environment()
                assert config.enabled is True, f"Failed for value: {true_value}"

        for false_value in ["false", "False", "FALSE", "0", "no"]:
            with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": false_value}, clear=True):
                config = RateLimitConfig.from_environment()
                assert config.enabled is False, f"Failed for value: {false_value}"

    def test_storage_validation(self):
        """storage should only accept 'memory' or 'redis'."""
        from codeframe.config.rate_limits import RateLimitConfig

        # Valid values
        config = RateLimitConfig(storage="memory")
        assert config.storage == "memory"

        config = RateLimitConfig(storage="redis")
        assert config.storage == "redis"

    def test_get_rate_limit_config_singleton(self):
        """get_rate_limit_config should return cached instance."""
        from codeframe.config.rate_limits import (
            get_rate_limit_config,
            _reset_rate_limit_config,
        )

        # Reset to ensure clean state
        _reset_rate_limit_config()

        config1 = get_rate_limit_config()
        config2 = get_rate_limit_config()

        assert config1 is config2

        # Clean up
        _reset_rate_limit_config()


class TestRateLimitConfigParsing:
    """Tests for rate limit string parsing."""

    def test_parse_various_rate_formats(self):
        """Configuration should accept various rate limit formats."""
        from codeframe.config.rate_limits import RateLimitConfig

        # These are formats supported by slowapi
        valid_formats = [
            "10/minute",
            "100/hour",
            "1000/day",
            "5/second",
            "10 per minute",
            "100 per hour",
        ]

        for fmt in valid_formats:
            config = RateLimitConfig(standard_limit=fmt)
            assert config.standard_limit == fmt
