"""Tests for configuration management."""

import os
from pathlib import Path
import pytest
from codeframe.core.config import GlobalConfig, load_environment


class TestGlobalConfig:
    """Test GlobalConfig class."""

    def test_default_values(self, monkeypatch):
        """Test that default values are set correctly."""
        # Clear environment variables that would override defaults
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("HOT_RELOAD", raising=False)
        monkeypatch.delenv("DATABASE_PATH", raising=False)
        monkeypatch.delenv("API_HOST", raising=False)
        monkeypatch.delenv("API_PORT", raising=False)
        monkeypatch.delenv("DEFAULT_PROVIDER", raising=False)

        config = GlobalConfig(_env_file=None)
        assert config.database_path == ".codeframe/state.db"
        # 127.0.0.1 since #935 — binding every interface by default put
        # workspace file access and agent execution on the LAN.
        assert config.api_host == "127.0.0.1"
        assert config.api_port == 8080
        assert config.log_level == "INFO"
        assert config.debug is False
        assert config.default_provider == "claude"

    def test_log_level_validation(self, monkeypatch):
        """Test log level validation."""
        # Valid log level (use env var as that's how BaseSettings works)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        config = GlobalConfig(_env_file=None)
        assert config.log_level == "DEBUG"

        # Case insensitive
        monkeypatch.setenv("LOG_LEVEL", "info")
        config = GlobalConfig(_env_file=None)
        assert config.log_level == "INFO"

        # Invalid log level should raise ValueError
        monkeypatch.setenv("LOG_LEVEL", "INVALID")
        with pytest.raises(ValueError, match="LOG_LEVEL must be one of"):
            GlobalConfig(_env_file=None)

    def test_port_validation(self, monkeypatch):
        """Test port validation."""
        # Valid port (use env var as that's how BaseSettings works)
        monkeypatch.setenv("API_PORT", "3000")
        config = GlobalConfig(_env_file=None)
        assert config.api_port == 3000

        # Invalid port (too low)
        monkeypatch.setenv("API_PORT", "0")
        with pytest.raises(ValueError, match="API_PORT must be between"):
            GlobalConfig(_env_file=None)

        # Invalid port (too high)
        monkeypatch.setenv("API_PORT", "99999")
        with pytest.raises(ValueError, match="API_PORT must be between"):
            GlobalConfig(_env_file=None)


class TestEnvironmentLoading:
    """Test environment variable loading."""

    def test_load_environment(self, tmp_path, monkeypatch):
        """Test environment file loading."""
        # Clear any existing values to ensure clean test
        monkeypatch.delenv("TEST_VAR", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=test_value\nANTHROPIC_API_KEY=sk-test")

        # Change to temp directory
        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            load_environment(str(env_file))
            assert os.getenv("TEST_VAR") == "test_value"
            assert os.getenv("ANTHROPIC_API_KEY") == "sk-test"
        finally:
            os.chdir(original_cwd)


    def test_load_from_env_file(self, tmp_path, monkeypatch):
        """Test loading from .env file."""
        # Clear any existing value to ensure clean test
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=****************")

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            load_environment()

            config = GlobalConfig()
            assert config.anthropic_api_key == "****************"
        finally:
            os.chdir(original_cwd)

    def test_env_override(self, tmp_path, monkeypatch):
        """Test that environment variables override .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-from-file")

        # Set in environment (should take precedence)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env-var")

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            load_environment()

            config = GlobalConfig()
            # Environment variable should win
            assert config.anthropic_api_key == "sk-from-env-var"
        finally:
            os.chdir(original_cwd)
