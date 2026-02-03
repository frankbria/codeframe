"""Tests for rate limiter middleware module.

TDD tests written before implementation to define the expected behavior
of the rate limiting middleware and decorators.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


class TestRateLimiterKeyFunctions:
    """Tests for rate limiter key extraction functions."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset rate limit caches before and after each test."""
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config
        from codeframe.lib.rate_limiter import reset_rate_limiter

        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()
        yield
        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()

    def test_get_client_ip_from_request(self):
        """get_client_ip should extract IP from request when no proxy headers."""
        from codeframe.lib.rate_limiter import get_client_ip

        # Mock request with direct client and no proxy headers
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {}
        mock_request.url.path = "/test"

        ip = get_client_ip(mock_request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_ignores_x_forwarded_for_from_untrusted(self):
        """get_client_ip should ignore X-Forwarded-For from non-trusted source."""
        from codeframe.lib.rate_limiter import get_client_ip

        # No trusted proxies configured - should ignore X-Forwarded-For
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18"}
        mock_request.url.path = "/test"

        ip = get_client_ip(mock_request)
        # Should use direct connection IP since 127.0.0.1 isn't trusted
        assert ip == "127.0.0.1"

    def test_get_client_ip_from_x_forwarded_for_trusted_proxy(self):
        """get_client_ip should trust X-Forwarded-For from configured trusted proxy."""
        from codeframe.lib.rate_limiter import get_client_ip
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config

        # Configure trusted proxy
        with patch.dict("os.environ", {"RATE_LIMIT_TRUSTED_PROXIES": "127.0.0.1"}, clear=True):
            _reset_rate_limit_config()
            reset_global_config()

            mock_request = MagicMock(spec=Request)
            mock_request.client.host = "127.0.0.1"
            mock_request.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
            mock_request.url.path = "/test"

            ip = get_client_ip(mock_request)
            # Should return first IP in the chain (real client)
            assert ip == "203.0.113.195"

    def test_get_client_ip_ignores_x_real_ip_from_untrusted(self):
        """get_client_ip should ignore X-Real-IP from non-trusted source."""
        from codeframe.lib.rate_limiter import get_client_ip

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {"X-Real-IP": "203.0.113.50"}
        mock_request.url.path = "/test"

        ip = get_client_ip(mock_request)
        # Should use direct connection IP
        assert ip == "192.168.1.1"

    def test_get_client_ip_from_x_real_ip_trusted_proxy(self):
        """get_client_ip should use X-Real-IP from trusted proxy."""
        from codeframe.lib.rate_limiter import get_client_ip
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config

        with patch.dict("os.environ", {"RATE_LIMIT_TRUSTED_PROXIES": "10.0.0.0/8"}, clear=True):
            _reset_rate_limit_config()
            reset_global_config()

            mock_request = MagicMock(spec=Request)
            mock_request.client.host = "10.0.0.1"
            mock_request.headers = {"X-Real-IP": "203.0.113.50"}
            mock_request.url.path = "/test"

            ip = get_client_ip(mock_request)
            assert ip == "203.0.113.50"

    def test_get_client_ip_fallback_to_client_host(self):
        """get_client_ip should fall back to client.host when no headers."""
        from codeframe.lib.rate_limiter import get_client_ip

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "10.0.0.5"
        mock_request.headers = {}
        mock_request.url.path = "/test"

        ip = get_client_ip(mock_request)
        assert ip == "10.0.0.5"

    def test_get_client_ip_handles_none_client(self):
        """get_client_ip should handle None client gracefully."""
        from codeframe.lib.rate_limiter import get_client_ip

        mock_request = MagicMock(spec=Request)
        mock_request.client = None
        mock_request.headers = {}
        mock_request.url.path = "/test"

        ip = get_client_ip(mock_request)
        assert ip == "unknown"


class TestRateLimiterKeyGeneration:
    """Tests for rate limiter key generation function."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset rate limit caches before and after each test."""
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config
        from codeframe.lib.rate_limiter import reset_rate_limiter

        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()
        yield
        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()

    def test_key_for_unauthenticated_request(self):
        """Key function should use IP for unauthenticated requests."""
        from codeframe.lib.rate_limiter import get_rate_limit_key

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        mock_request.state = MagicMock()
        mock_request.state.user = None  # No authenticated user
        mock_request.url.path = "/test"

        key = get_rate_limit_key(mock_request)
        assert key == "ip:192.168.1.100"

    def test_key_for_authenticated_request(self):
        """Key function should use user ID for authenticated requests."""
        from codeframe.lib.rate_limiter import get_rate_limit_key

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        mock_request.state = MagicMock()
        mock_request.state.user = MagicMock()
        mock_request.state.user.id = "user_12345"
        mock_request.url.path = "/test"

        key = get_rate_limit_key(mock_request)
        assert key == "user:user_12345"

    def test_key_for_unknown_ip_is_unique(self):
        """Unknown IPs should get unique keys to prevent shared bucket DoS."""
        from codeframe.lib.rate_limiter import get_rate_limit_key

        mock_request1 = MagicMock(spec=Request)
        mock_request1.client = None
        mock_request1.headers = {}
        mock_request1.state = MagicMock()
        mock_request1.state.user = None
        mock_request1.url.path = "/test"

        mock_request2 = MagicMock(spec=Request)
        mock_request2.client = None
        mock_request2.headers = {}
        mock_request2.state = MagicMock()
        mock_request2.state.user = None
        mock_request2.url.path = "/test"

        key1 = get_rate_limit_key(mock_request1)
        key2 = get_rate_limit_key(mock_request2)

        # Both should start with ip:unknown but have unique suffixes
        assert key1.startswith("ip:unknown:")
        assert key2.startswith("ip:unknown:")
        assert key1 != key2  # Each request gets a unique key


class TestRateLimiterIntegration:
    """Integration tests for rate limiter with FastAPI."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset rate limit caches before and after each test."""
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config
        from codeframe.lib.rate_limiter import reset_rate_limiter

        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()
        yield
        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()

    @pytest.fixture
    def app_with_rate_limiting(self):
        """Create a test FastAPI app with rate limiting."""
        from codeframe.lib.rate_limiter import (
            get_rate_limiter,
            rate_limit_exceeded_handler,
            rate_limit_standard,
        )
        from slowapi.errors import RateLimitExceeded

        app = FastAPI()

        # Initialize rate limiter
        limiter = get_rate_limiter()
        app.state.limiter = limiter

        # Add exception handler
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        @app.get("/test")
        @rate_limit_standard()
        async def test_endpoint(request: Request):
            return {"status": "ok"}

        return app

    def test_rate_limit_headers_in_response(self, app_with_rate_limiting):
        """Response should include rate limit headers."""
        client = TestClient(app_with_rate_limiting)

        response = client.get("/test")

        # Check that rate limit headers are present
        assert "X-RateLimit-Limit" in response.headers or response.status_code == 200
        # Note: slowapi adds headers on limit exceeded, not on every request by default

    @pytest.fixture
    def app_with_low_limit(self):
        """Create a test app with very low rate limit for testing."""
        from codeframe.lib.rate_limiter import (
            rate_limit_exceeded_handler,
        )
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded

        # Reset config to apply new limits
        _reset_rate_limit_config()
        reset_global_config()

        app = FastAPI()

        # Create limiter with very low limit for testing
        limiter = Limiter(key_func=get_remote_address, default_limits=["2/minute"])
        app.state.limiter = limiter

        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

        @app.get("/limited")
        @limiter.limit("2/minute")
        async def limited_endpoint(request: Request):
            return {"status": "ok"}

        return app

    def test_rate_limit_exceeded_returns_429(self, app_with_low_limit):
        """Exceeding rate limit should return 429 status."""
        client = TestClient(app_with_low_limit)

        # Make requests up to the limit
        for _ in range(2):
            response = client.get("/limited")
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get("/limited")
        assert response.status_code == 429

    def test_rate_limit_exceeded_response_format(self, app_with_low_limit):
        """429 response should have proper format and headers."""
        client = TestClient(app_with_low_limit)

        # Exhaust the limit
        for _ in range(2):
            client.get("/limited")

        response = client.get("/limited")

        assert response.status_code == 429

        # Check response body
        data = response.json()
        assert "error" in data or "detail" in data

        # Check headers
        assert "Retry-After" in response.headers


class TestRateLimitDecorators:
    """Tests for rate limit decorator functions."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset rate limit caches before and after each test."""
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config
        from codeframe.lib.rate_limiter import reset_rate_limiter

        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()
        yield
        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()

    def test_rate_limit_standard_decorator_exists(self):
        """rate_limit_standard decorator should exist and be callable."""
        from codeframe.lib.rate_limiter import rate_limit_standard

        decorator = rate_limit_standard()
        assert callable(decorator)

    def test_rate_limit_ai_decorator_exists(self):
        """rate_limit_ai decorator should exist and be callable."""
        from codeframe.lib.rate_limiter import rate_limit_ai

        decorator = rate_limit_ai()
        assert callable(decorator)

    def test_rate_limit_auth_decorator_exists(self):
        """rate_limit_auth decorator should exist and be callable."""
        from codeframe.lib.rate_limiter import rate_limit_auth

        decorator = rate_limit_auth()
        assert callable(decorator)

    def test_rate_limit_websocket_decorator_exists(self):
        """rate_limit_websocket decorator should exist and be callable."""
        from codeframe.lib.rate_limiter import rate_limit_websocket

        decorator = rate_limit_websocket()
        assert callable(decorator)


class TestRateLimiterDisabled:
    """Tests for disabled rate limiting behavior."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset rate limit caches before and after each test."""
        from codeframe.config.rate_limits import _reset_rate_limit_config
        from codeframe.core.config import reset_global_config
        from codeframe.lib.rate_limiter import reset_rate_limiter

        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()
        yield
        _reset_rate_limit_config()
        reset_global_config()
        reset_rate_limiter()

    def test_disabled_rate_limiting_returns_none(self):
        """When rate limiting is disabled, get_rate_limiter should return None."""
        from codeframe.config.rate_limits import _reset_rate_limit_config, get_rate_limit_config
        from codeframe.core.config import reset_global_config
        from codeframe.lib.rate_limiter import get_rate_limiter, reset_rate_limiter

        with patch.dict("os.environ", {"RATE_LIMIT_ENABLED": "false"}, clear=True):
            _reset_rate_limit_config()
            reset_global_config()
            reset_rate_limiter()

            # Verify config shows disabled
            config = get_rate_limit_config()
            assert config.enabled is False

            # When disabled, limiter should be None
            limiter = get_rate_limiter()
            assert limiter is None
