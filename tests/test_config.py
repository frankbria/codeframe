"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path
import pytest
from codeframe.core.config import Config, GlobalConfig, load_environment


class TestGlobalConfig:
    """Test GlobalConfig class."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = GlobalConfig()
        assert config.database_path == ".codeframe/state.db"
        assert config.api_host == "0.0.0.0"
        assert config.api_port == 8080
        assert config.log_level == "INFO"
        assert config.debug is False
        assert config.default_provider == "claude"

    def test_cors_origins_parsing(self):
        """Test CORS origins list parsing."""
        config = GlobalConfig(cors_origins="http://localhost:3000, http://localhost:5173")
        origins = config.get_cors_origins_list()
        assert len(origins) == 2
        assert "http://localhost:3000" in origins
        assert "http://localhost:5173" in origins

    def test_log_level_validation(self):
        """Test log level validation."""
        # Valid log level
        config = GlobalConfig(log_level="DEBUG")
        assert config.log_level == "DEBUG"

        # Case insensitive
        config = GlobalConfig(log_level="info")
        assert config.log_level == "INFO"

        # Invalid log level should raise ValueError
        with pytest.raises(ValueError, match="LOG_LEVEL must be one of"):
            GlobalConfig(log_level="INVALID")

    def test_port_validation(self):
        """Test port validation."""
        # Valid port
        config = GlobalConfig(api_port=3000)
        assert config.api_port == 3000

        # Invalid port (too low)
        with pytest.raises(ValueError, match="API_PORT must be between"):
            GlobalConfig(api_port=0)

        # Invalid port (too high)
        with pytest.raises(ValueError, match="API_PORT must be between"):
            GlobalConfig(api_port=99999)

    def test_sprint_1_validation_success(self):
        """Test Sprint 1 validation with API key."""
        config = GlobalConfig(anthropic_api_key="sk-ant-test-key")
        # Should not raise
        config.validate_required_for_sprint(sprint=1)

    def test_sprint_1_validation_failure(self):
        """Test Sprint 1 validation without API key."""
        config = GlobalConfig()
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is required"):
            config.validate_required_for_sprint(sprint=1)

    def test_ensure_directories(self, tmp_path):
        """Test that ensure_directories creates required paths."""
        db_path = tmp_path / "test_db" / "state.db"
        log_path = tmp_path / "logs" / "test.log"

        config = GlobalConfig(
            database_path=str(db_path),
            log_file=str(log_path)
        )
        config.ensure_directories()

        assert db_path.parent.exists()
        assert log_path.parent.exists()


class TestConfig:
    """Test Config manager class."""

    def test_load_environment(self, tmp_path):
        """Test environment file loading."""
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
            # Clean up environment
            os.environ.pop("TEST_VAR", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_config_initialization(self, tmp_path):
        """Test Config initialization."""
        config = Config(tmp_path)
        assert config.project_dir == tmp_path
        assert config.config_dir == tmp_path / ".codeframe"
        assert config.config_file == tmp_path / ".codeframe" / "config.json"

    def test_validate_for_sprint(self, tmp_path, monkeypatch):
        """Test sprint validation through Config."""
        # Set API key in environment
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

        config = Config(tmp_path)
        # Should not raise with API key set
        config.validate_for_sprint(sprint=1)

    def test_validate_for_sprint_missing_key(self, tmp_path, monkeypatch):
        """Test sprint validation fails without API key."""
        # Ensure no API key in environment
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        config = Config(tmp_path)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is required"):
            config.validate_for_sprint(sprint=1)


class TestEnvironmentLoading:
    """Test environment variable loading."""

    def test_load_from_env_file(self, tmp_path):
        """Test loading from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-from-env-file")

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            load_environment()

            config = GlobalConfig()
            assert config.anthropic_api_key == "sk-from-env-file"
        finally:
            os.chdir(original_cwd)
            os.environ.pop("ANTHROPIC_API_KEY", None)

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
