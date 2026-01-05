"""CLI API client module - HTTP client with authentication.

This module provides:
- APIClient class for making authenticated HTTP requests
- Automatic token injection in Authorization header
- Retry logic for transient failures
- User-friendly error messages

Usage:
    from codeframe.cli.api_client import APIClient

    client = APIClient()  # Auto-loads token from storage
    projects = client.get("/api/projects")
"""

import json
import logging
import os
import time
from typing import Any

import requests

from codeframe.cli.auth import get_token

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: int | None = None, detail: str | None = None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class AuthenticationError(APIError):
    """Exception for authentication failures (401, 403)."""

    pass


def get_api_base_url() -> str:
    """Get the API base URL.

    Returns:
        API base URL from CODEFRAME_API_URL env var, or default localhost:8080
    """
    url = os.environ.get("CODEFRAME_API_URL", "http://localhost:8080")
    return url.rstrip("/")


class APIClient:
    """HTTP client for CodeFRAME API with authentication.

    Args:
        base_url: API base URL. Defaults to CODEFRAME_API_URL env var or localhost:8080
        token: JWT token. If not provided, loads from storage
        max_retries: Maximum number of retries for transient failures (default: 3)
        timeout: Request timeout in seconds (default: 30)
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        max_retries: int = 3,
        timeout: int = 30,
    ):
        self.base_url = base_url or get_api_base_url()
        self.token = token if token is not None else get_token()
        self.max_retries = max_retries
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers including auth token.

        Returns:
            Headers dict with Content-Type and optional Authorization
        """
        headers = {"Content-Type": "application/json"}

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        return headers

    def _make_url(self, endpoint: str) -> str:
        """Build full URL from endpoint.

        Args:
            endpoint: API endpoint (e.g., "/api/projects")

        Returns:
            Full URL
        """
        if endpoint.startswith("http"):
            return endpoint
        return f"{self.base_url}{endpoint}"

    def _handle_response(self, response: requests.Response) -> Any:
        """Handle HTTP response, raising appropriate exceptions.

        Args:
            response: requests Response object

        Returns:
            Parsed JSON response, or None for 204

        Raises:
            AuthenticationError: For 401/403 responses
            APIError: For other error responses
        """
        status = response.status_code

        # Success - return JSON or None
        if 200 <= status < 300:
            if status == 204 or not response.text:
                return None
            try:
                return response.json()
            except json.JSONDecodeError:
                return response.text

        # Authentication errors
        if status == 401:
            raise AuthenticationError(
                "Authentication failed. Please log in with: codeframe auth login",
                status_code=status,
            )

        if status == 403:
            raise AuthenticationError(
                "Access denied. You don't have permission for this resource.",
                status_code=status,
            )

        # Parse error detail from response
        detail = None
        try:
            error_data = response.json()
            detail = error_data.get("detail", str(error_data))
        except (json.JSONDecodeError, TypeError):
            detail = response.text or f"HTTP {status}"

        # Client errors (4xx)
        if 400 <= status < 500:
            raise APIError(
                f"Request failed: {detail}",
                status_code=status,
                detail=detail,
            )

        # Server errors (5xx)
        raise APIError(
            f"Server error ({status}): {detail}",
            status_code=status,
            detail=detail,
        )

    def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        **kwargs,
    ) -> Any:
        """Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments for requests

        Returns:
            Parsed response data

        Raises:
            APIError: After all retries exhausted
        """
        url = self._make_url(endpoint)
        headers = self._get_headers()

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
                return self._handle_response(response)

            except requests.ConnectionError as e:
                logger.warning(f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}")

                if attempt < self.max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s, ...
                    sleep_time = 2 ** attempt
                    time.sleep(sleep_time)
                continue

            except requests.Timeout as e:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries}): {e}")

                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                continue

        # All retries exhausted
        raise APIError(
            f"Connection error: Unable to connect to {self.base_url}. "
            "Please check the server is running and try again.",
            status_code=None,
        )

    def get(self, endpoint: str, params: dict | None = None) -> Any:
        """Make GET request.

        Args:
            endpoint: API endpoint (e.g., "/api/projects")
            params: Query parameters

        Returns:
            Parsed JSON response
        """
        return self._request_with_retry("GET", endpoint, params=params)

    def post(self, endpoint: str, data: dict | None = None) -> Any:
        """Make POST request.

        Args:
            endpoint: API endpoint
            data: Request body (will be sent as JSON)

        Returns:
            Parsed JSON response
        """
        return self._request_with_retry("POST", endpoint, json=data)

    def put(self, endpoint: str, data: dict | None = None) -> Any:
        """Make PUT request.

        Args:
            endpoint: API endpoint
            data: Request body (will be sent as JSON)

        Returns:
            Parsed JSON response
        """
        return self._request_with_retry("PUT", endpoint, json=data)

    def patch(self, endpoint: str, data: dict | None = None) -> Any:
        """Make PATCH request.

        Args:
            endpoint: API endpoint
            data: Request body (will be sent as JSON)

        Returns:
            Parsed JSON response
        """
        return self._request_with_retry("PATCH", endpoint, json=data)

    def delete(self, endpoint: str) -> Any:
        """Make DELETE request.

        Args:
            endpoint: API endpoint

        Returns:
            Parsed JSON response, or None for 204
        """
        return self._request_with_retry("DELETE", endpoint)
