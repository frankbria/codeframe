"""Tests for CLI auth commands (login, logout, register, whoami).

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from codeframe.cli.auth_commands import auth_app


runner = CliRunner()


class TestLoginCommand:
    """Tests for the login command."""

    def test_login_success(self, tmp_path):
        """Successful login should store token."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        # Mock successful login response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "jwt-token-12345",
            "token_type": "bearer",
        }

        with patch("requests.post", return_value=mock_response):
            with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
                result = runner.invoke(
                    auth_app,
                    ["login", "--email", "test@example.com", "--password", "secret123"],
                )

        assert result.exit_code == 0
        assert "logged in" in result.output.lower() or "success" in result.output.lower()

        # Token should be stored
        assert creds_path.exists()
        with open(creds_path) as f:
            data = json.load(f)
        assert data["access_token"] == "jwt-token-12345"

    def test_login_invalid_credentials(self):
        """Login with invalid credentials should show error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "LOGIN_BAD_CREDENTIALS"}

        with patch("requests.post", return_value=mock_response):
            result = runner.invoke(
                auth_app,
                ["login", "--email", "test@example.com", "--password", "wrongpassword"],
            )

        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "incorrect" in result.output.lower()

    def test_login_prompts_for_email(self):
        """Login should prompt for email if not provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token"}

        with patch("requests.post", return_value=mock_response):
            result = runner.invoke(
                auth_app,
                ["login", "--password", "secret"],
                input="prompted@example.com\n",
            )

        # Should prompt and succeed
        assert "email" in result.output.lower()

    def test_login_prompts_for_password(self):
        """Login should prompt for password if not provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "token"}

        with patch("requests.post", return_value=mock_response):
            result = runner.invoke(
                auth_app,
                ["login", "--email", "test@example.com"],
                input="secretpassword\n",
            )

        # Should prompt and succeed
        assert "password" in result.output.lower()


class TestLogoutCommand:
    """Tests for the logout command."""

    def test_logout_clears_credentials(self, tmp_path):
        """Logout should remove credentials file."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"access_token": "old-token"}, f)

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            result = runner.invoke(auth_app, ["logout"])

        assert result.exit_code == 0
        assert "logged out" in result.output.lower()
        assert not creds_path.exists()

    def test_logout_noop_if_not_logged_in(self, tmp_path):
        """Logout should succeed even if not logged in."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            result = runner.invoke(auth_app, ["logout"])

        assert result.exit_code == 0


class TestRegisterCommand:
    """Tests for the register command."""

    def test_register_success(self, tmp_path):
        """Successful registration should store token and show success."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        # Mock successful registration
        mock_register_response = MagicMock()
        mock_register_response.status_code = 201
        mock_register_response.json.return_value = {
            "id": "user-id-123",
            "email": "new@example.com",
        }

        # Mock subsequent login
        mock_login_response = MagicMock()
        mock_login_response.status_code = 200
        mock_login_response.json.return_value = {"access_token": "new-user-token"}

        with patch("requests.post", side_effect=[mock_register_response, mock_login_response]):
            with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
                result = runner.invoke(
                    auth_app,
                    ["register", "--email", "new@example.com", "--password", "newpassword"],
                )

        assert result.exit_code == 0
        assert "registered" in result.output.lower() or "created" in result.output.lower()

    def test_register_email_exists(self):
        """Registration with existing email should show error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "REGISTER_USER_ALREADY_EXISTS"}

        with patch("requests.post", return_value=mock_response):
            result = runner.invoke(
                auth_app,
                ["register", "--email", "existing@example.com", "--password", "password"],
            )

        assert result.exit_code != 0
        assert "exists" in result.output.lower() or "already" in result.output.lower()


class TestWhoamiCommand:
    """Tests for the whoami command."""

    def test_whoami_authenticated(self, tmp_path):
        """Whoami should display user info when authenticated."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "user-123",
            "email": "user@example.com",
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(auth_app, ["whoami"])

        assert result.exit_code == 0
        assert "user@example.com" in result.output

    def test_whoami_not_authenticated(self, tmp_path):
        """Whoami should show login prompt when not authenticated."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            result = runner.invoke(auth_app, ["whoami"])

        assert result.exit_code != 0
        assert "not logged in" in result.output.lower() or "login" in result.output.lower()

    def test_whoami_expired_token(self, tmp_path):
        """Whoami with expired token should suggest re-login."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)

        with open(creds_path, "w") as f:
            json.dump({"access_token": "expired-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(auth_app, ["whoami"])

        assert result.exit_code != 0
        assert "login" in result.output.lower()
