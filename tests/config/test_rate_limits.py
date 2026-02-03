"""Tests for rate limiting configuration module.

TDD tests written before implementation to define the expected behavior
of the RateLimitConfig class.
"""

import os
from unittest.mock import patch


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
        assert config.trusted_proxies == []

    def test_from_global_config_with_defaults(self):
        """from_global_config should use defaults when env vars not set."""
        from codeframe.config.rate_limits import RateLimitConfig, _reset_rate_limit_config
        from codeframe.core.config import reset_global_config

        # Reset caches to ensure clean state
        _reset_rate_limit_config()
        reset_global_config()

        # Clear any rate limit env vars
        env_vars = [
            "RATE_LIMIT_ENABLED",
            "RATE_LIMIT_AUTH",
            "RATE_LIMIT_STANDARD",
            "RATE_LIMIT_AI",
            "RATE_LIMIT_WEBSOCKET",
            "RATE_LIMIT_STORAGE",
            "RATE_LIMIT_TRUSTED_PROXIES",
            "REDIS_URL",
        ]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_vars}

        with patch.dict(os.environ, clean_env, clear=True):
            reset_global_config()  # Reset after clearing env
            config = RateLimitConfig.from_global_config()

            assert config.auth_limit == "10/minute"
            assert config.standard_limit == "100/minute"
            assert config.ai_limit == "20/minute"
            assert config.websocket_limit == "30/minute"
            assert config.enabled is True
            assert config.storage == "memory"

        # Cleanup
        _reset_rate_limit_config()
        reset_global_config()

    def test_from_global_config_custom_values(self):
        """from_global_config should read custom values from GlobalConfig."""
        from codeframe.config.rate_limits import RateLimitConfig, _reset_rate_limit_config
        from codeframe.core.config import reset_global_config

        # Reset caches
        _reset_rate_limit_config()
        reset_global_config()

        custom_env = {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_AUTH": "5/minute",
            "RATE_LIMIT_STANDARD": "200/minute",
            "RATE_LIMIT_AI": "10/minute",
            "RATE_LIMIT_WEBSOCKET": "50/minute",
            "RATE_LIMIT_STORAGE": "redis",
            "REDIS_URL": "redis://localhost:6379/0",
            "RATE_LIMIT_TRUSTED_PROXIES": "10.0.0.1,172.16.0.0/12",
        }

        with patch.dict(os.environ, custom_env, clear=True):
            reset_global_config()  # Reset after setting env
            config = RateLimitConfig.from_global_config()

            assert config.auth_limit == "5/minute"
            assert config.standard_limit == "200/minute"
            assert config.ai_limit == "10/minute"
            assert config.websocket_limit == "50/minute"
            assert config.enabled is True
            assert config.storage == "redis"
            assert config.redis_url == "redis://localhost:6379/0"
            assert config.trusted_proxies == ["10.0.0.1", "172.16.0.0/12"]

        # Cleanup
        _reset_rate_limit_config()
        reset_global_config()

    def test_from_global_config_disabled(self):
        """from_global_config should handle disabled rate limiting."""
        from codeframe.config.rate_limits import RateLimitConfig, _reset_rate_limit_config
        from codeframe.core.config import reset_global_config

        # Reset caches
        _reset_rate_limit_config()
        reset_global_config()

        with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "false"}, clear=True):
            reset_global_config()
            config = RateLimitConfig.from_global_config()

            assert config.enabled is False

        # Cleanup
        _reset_rate_limit_config()
        reset_global_config()

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
        from codeframe.core.config import reset_global_config

        # Reset to ensure clean state
        _reset_rate_limit_config()
        reset_global_config()

        config1 = get_rate_limit_config()
        config2 = get_rate_limit_config()

        assert config1 is config2

        # Clean up
        _reset_rate_limit_config()
        reset_global_config()


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


class TestTrustedProxyValidation:
    """Tests for trusted proxy IP validation."""

    def test_is_trusted_proxy_exact_ip_match(self):
        """is_trusted_proxy should match exact IP addresses."""
        from codeframe.config.rate_limits import RateLimitConfig

        config = RateLimitConfig(trusted_proxies=["10.0.0.1", "192.168.1.1"])

        assert config.is_trusted_proxy("10.0.0.1") is True
        assert config.is_trusted_proxy("192.168.1.1") is True
        assert config.is_trusted_proxy("10.0.0.2") is False

    def test_is_trusted_proxy_cidr_match(self):
        """is_trusted_proxy should match CIDR network ranges."""
        from codeframe.config.rate_limits import RateLimitConfig

        config = RateLimitConfig(trusted_proxies=["10.0.0.0/8", "172.16.0.0/12"])

        # IPs in 10.0.0.0/8 range
        assert config.is_trusted_proxy("10.0.0.1") is True
        assert config.is_trusted_proxy("10.255.255.255") is True

        # IPs in 172.16.0.0/12 range
        assert config.is_trusted_proxy("172.16.0.1") is True
        assert config.is_trusted_proxy("172.31.255.255") is True

        # IPs outside the ranges
        assert config.is_trusted_proxy("11.0.0.1") is False
        assert config.is_trusted_proxy("172.32.0.1") is False

    def test_is_trusted_proxy_empty_list(self):
        """is_trusted_proxy should return False with empty list."""
        from codeframe.config.rate_limits import RateLimitConfig

        config = RateLimitConfig(trusted_proxies=[])

        assert config.is_trusted_proxy("10.0.0.1") is False
        assert config.is_trusted_proxy("127.0.0.1") is False

    def test_is_trusted_proxy_invalid_ip(self):
        """is_trusted_proxy should handle invalid IPs gracefully."""
        from codeframe.config.rate_limits import RateLimitConfig

        config = RateLimitConfig(trusted_proxies=["10.0.0.1"])

        assert config.is_trusted_proxy("not-an-ip") is False
        assert config.is_trusted_proxy("") is False

    def test_is_trusted_proxy_invalid_config(self):
        """is_trusted_proxy should skip invalid proxy entries."""
        from codeframe.config.rate_limits import RateLimitConfig

        config = RateLimitConfig(trusted_proxies=["invalid", "10.0.0.1"])

        # Should still match valid entries
        assert config.is_trusted_proxy("10.0.0.1") is True
        assert config.is_trusted_proxy("10.0.0.2") is False
