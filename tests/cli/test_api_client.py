"""Tests for CLI API client module.

TDD approach: Write tests first, then implement.
"""

import json
import os
from unittest.mock import patch, MagicMock
from typing import Any

import pytest
import requests

from codeframe.cli.api_client import (
    APIClient,
    APIError,
    AuthenticationError,
    get_api_base_url,
)


class TestGetApiBaseUrl:
    """Tests for get_api_base_url function."""

    def test_default_url(self):
        """Default URL should be localhost:8080."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing CODEFRAME_API_URL
            os.environ.pop("CODEFRAME_API_URL", None)
            url = get_api_base_url()
        assert url == "http://localhost:8080"

    def test_env_override(self):
        """CODEFRAME_API_URL should override default."""
        with patch.dict(os.environ, {"CODEFRAME_API_URL": "https://api.example.com"}):
            url = get_api_base_url()
        assert url == "https://api.example.com"

    def test_strips_trailing_slash(self):
        """URL should not have trailing slash."""
        with patch.dict(os.environ, {"CODEFRAME_API_URL": "https://api.example.com/"}):
            url = get_api_base_url()
        assert url == "https://api.example.com"


class TestAPIClient:
    """Tests for APIClient class."""

    def test_init_default_base_url(self):
        """APIClient should use default base URL."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CODEFRAME_API_URL", None)
            client = APIClient()
        assert client.base_url == "http://localhost:8080"

    def test_init_custom_base_url(self):
        """APIClient should accept custom base URL."""
        client = APIClient(base_url="https://custom.api.com")
        assert client.base_url == "https://custom.api.com"

    def test_init_with_token(self):
        """APIClient should accept token parameter."""
        client = APIClient(token="test-token")
        assert client.token == "test-token"

    def test_init_loads_token_from_storage(self):
        """APIClient should load token from storage if not provided."""
        with patch("codeframe.cli.api_client.get_token", return_value="stored-token"):
            client = APIClient()
        assert client.token == "stored-token"


class TestAPIClientHeaders:
    """Tests for APIClient header generation."""

    def test_get_headers_with_token(self):
        """Headers should include Authorization with token."""
        client = APIClient(token="my-jwt-token")
        headers = client._get_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer my-jwt-token"
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_without_token(self):
        """Headers should not include Authorization without token."""
        with patch("codeframe.cli.api_client.get_token", return_value=None):
            client = APIClient()
        headers = client._get_headers()

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"


class TestAPIClientGet:
    """Tests for APIClient.get method."""

    def test_get_success(self):
        """GET request should return parsed JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}

        with patch("requests.request", return_value=mock_response) as mock_request:
            client = APIClient(token="test-token")
            result = client.get("/api/projects")

        mock_request.assert_called_once()
        assert result == {"data": "test"}

    def test_get_with_params(self):
        """GET request should pass query parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}

        with patch("requests.request", return_value=mock_response) as mock_request:
            client = APIClient(base_url="http://test.api", token="test-token")
            client.get("/api/projects", params={"status": "active", "limit": 10})

        call_args = mock_request.call_args
        assert call_args.kwargs["params"] == {"status": "active", "limit": 10}

    def test_get_401_raises_auth_error(self):
        """GET request with 401 should raise AuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="expired-token")

            with pytest.raises(AuthenticationError) as exc_info:
                client.get("/api/projects")

            assert "Authentication failed" in str(exc_info.value)

    def test_get_403_raises_auth_error(self):
        """GET request with 403 should raise AuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="test-token")

            with pytest.raises(AuthenticationError) as exc_info:
                client.get("/api/projects/1")

            assert "Access denied" in str(exc_info.value)

    def test_get_404_raises_api_error(self):
        """GET request with 404 should raise APIError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_response.json.return_value = {"detail": "Project not found"}

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="test-token")

            with pytest.raises(APIError) as exc_info:
                client.get("/api/projects/999")

            assert exc_info.value.status_code == 404
            assert "not found" in str(exc_info.value).lower()


class TestAPIClientPost:
    """Tests for APIClient.post method."""

    def test_post_success(self):
        """POST request should return parsed JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 1, "name": "Test Project"}

        with patch("requests.request", return_value=mock_response) as mock_request:
            client = APIClient(token="test-token")
            result = client.post("/api/projects", data={"name": "Test Project"})

        mock_request.assert_called_once()
        assert result == {"id": 1, "name": "Test Project"}

    def test_post_sends_json_body(self):
        """POST request should send data as JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {}

        with patch("requests.request", return_value=mock_response) as mock_request:
            client = APIClient(base_url="http://test.api", token="test-token")
            client.post("/api/projects", data={"name": "Test", "description": "Desc"})

        call_args = mock_request.call_args
        assert call_args.kwargs["json"] == {"name": "Test", "description": "Desc"}

    def test_post_409_conflict(self):
        """POST request with 409 should raise APIError with conflict info."""
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "Conflict"
        mock_response.json.return_value = {"detail": "Project already exists"}

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="test-token")

            with pytest.raises(APIError) as exc_info:
                client.post("/api/projects", data={"name": "Duplicate"})

            assert exc_info.value.status_code == 409


class TestAPIClientDelete:
    """Tests for APIClient.delete method."""

    def test_delete_success_204(self):
        """DELETE request with 204 should return None."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        with patch("requests.request", return_value=mock_response) as mock_request:
            client = APIClient(token="test-token")
            result = client.delete("/api/projects/1/checkpoints/5")

        mock_request.assert_called_once()
        assert result is None

    def test_delete_success_200(self):
        """DELETE request with 200 should return JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="test-token")
            result = client.delete("/api/some/resource")

        assert result == {"deleted": True}


class TestAPIClientPatch:
    """Tests for APIClient.patch method."""

    def test_patch_success(self):
        """PATCH request should return parsed JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "name": "Updated"}

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="test-token")
            result = client.patch("/api/projects/1", data={"name": "Updated"})

        assert result == {"id": 1, "name": "Updated"}


class TestAPIClientPut:
    """Tests for APIClient.put method."""

    def test_put_success(self):
        """PUT request should return parsed JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "status": "active"}

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="test-token")
            result = client.put("/api/projects/1/agents/2/role", data={"role": "worker"})

        assert result == {"id": 1, "status": "active"}


class TestAPIClientRetry:
    """Tests for APIClient retry logic."""

    def test_retry_on_connection_error(self):
        """Should retry on connection error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}

        # First call fails, second succeeds
        with patch("requests.request", side_effect=[
            requests.ConnectionError("Connection refused"),
            mock_response,
        ]) as mock_request:
            client = APIClient(token="test-token", max_retries=2)
            result = client.get("/api/projects")

        assert mock_request.call_count == 2
        assert result == {"success": True}

    def test_max_retries_exceeded(self):
        """Should raise after max retries exceeded."""
        with patch("requests.request", side_effect=requests.ConnectionError("Connection refused")):
            client = APIClient(token="test-token", max_retries=2)

            with pytest.raises(APIError) as exc_info:
                client.get("/api/projects")

            assert "Connection error" in str(exc_info.value)


class TestAPIClientErrorMessages:
    """Tests for user-friendly error messages."""

    def test_401_error_message(self):
        """401 should suggest logging in."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="bad-token")

            with pytest.raises(AuthenticationError) as exc_info:
                client.get("/api/projects")

            error = exc_info.value
            assert "codeframe auth login" in str(error) or "log in" in str(error).lower()

    def test_500_error_message(self):
        """500 should indicate server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json.side_effect = json.JSONDecodeError("", "", 0)

        with patch("requests.request", return_value=mock_response):
            client = APIClient(token="test-token")

            with pytest.raises(APIError) as exc_info:
                client.get("/api/projects")

            assert exc_info.value.status_code == 500
