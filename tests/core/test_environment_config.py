"""Tests for v2 environment configuration."""

import tempfile
from pathlib import Path

from codeframe.core.config import (
    EnvironmentConfig,
    ContextConfig,
    PackageManager,
    TestFramework,
    LintTool,
    load_environment_config,
    save_environment_config,
    get_default_environment_config,
)


class TestEnvironmentConfig:
    """Tests for EnvironmentConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = EnvironmentConfig()

        assert config.package_manager == "uv"
        assert config.python_version is None
        assert config.node_version is None
        assert config.test_framework == "pytest"
        assert config.test_command is None
        assert config.lint_tools == ["ruff"]
        assert config.lint_command is None
        assert isinstance(config.context, ContextConfig)
        assert config.custom_commands == {}

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = EnvironmentConfig(
            package_manager="pip",
            python_version="3.11",
            test_framework="jest",
            lint_tools=["eslint", "prettier"],
        )

        assert config.package_manager == "pip"
        assert config.python_version == "3.11"
        assert config.test_framework == "jest"
        assert config.lint_tools == ["eslint", "prettier"]

    def test_context_config_defaults(self):
        """Test ContextConfig default values."""
        config = ContextConfig()

        assert config.max_files == 20
        assert config.max_file_size == 5000
        assert config.max_total_tokens == 50000

    def test_context_config_custom(self):
        """Test ContextConfig with custom values."""
        config = ContextConfig(
            max_files=50,
            max_file_size=10000,
            max_total_tokens=100000,
        )

        assert config.max_files == 50
        assert config.max_file_size == 10000
        assert config.max_total_tokens == 100000


class TestEnvironmentConfigValidation:
    """Tests for configuration validation."""

    def test_valid_config(self):
        """Test validation passes for valid config."""
        config = EnvironmentConfig()
        errors = config.validate()
        assert errors == []

    def test_invalid_package_manager(self):
        """Test validation fails for invalid package manager."""
        config = EnvironmentConfig(package_manager="invalid")
        errors = config.validate()
        assert len(errors) == 1
        assert "package_manager" in errors[0]
        assert "invalid" in errors[0]

    def test_invalid_test_framework(self):
        """Test validation fails for invalid test framework."""
        config = EnvironmentConfig(test_framework="unknown")
        errors = config.validate()
        assert len(errors) == 1
        assert "test_framework" in errors[0]

    def test_invalid_lint_tool(self):
        """Test validation fails for invalid lint tool."""
        config = EnvironmentConfig(lint_tools=["ruff", "invalid_linter"])
        errors = config.validate()
        assert len(errors) == 1
        assert "invalid_linter" in errors[0]

    def test_multiple_validation_errors(self):
        """Test validation returns all errors."""
        config = EnvironmentConfig(
            package_manager="bad",
            test_framework="bad",
            lint_tools=["bad"],
        )
        errors = config.validate()
        assert len(errors) == 3


class TestEnvironmentConfigCommands:
    """Tests for command generation."""

    def test_get_install_command_uv(self):
        """Test install command for uv."""
        config = EnvironmentConfig(package_manager="uv")
        assert config.get_install_command("requests") == "uv pip install requests"

    def test_get_install_command_pip(self):
        """Test install command for pip."""
        config = EnvironmentConfig(package_manager="pip")
        assert config.get_install_command("requests") == "pip install requests"

    def test_get_install_command_poetry(self):
        """Test install command for poetry."""
        config = EnvironmentConfig(package_manager="poetry")
        assert config.get_install_command("requests") == "poetry add requests"

    def test_get_install_command_npm(self):
        """Test install command for npm."""
        config = EnvironmentConfig(package_manager="npm")
        assert config.get_install_command("express") == "npm install express"

    def test_get_test_command_pytest(self):
        """Test test command for pytest."""
        config = EnvironmentConfig(test_framework="pytest")
        assert config.get_test_command() == "pytest"

    def test_get_test_command_jest(self):
        """Test test command for jest."""
        config = EnvironmentConfig(test_framework="jest", package_manager="npm")
        assert config.get_test_command() == "npm test"

    def test_get_test_command_custom(self):
        """Test custom test command override."""
        config = EnvironmentConfig(
            test_framework="pytest",
            test_command="pytest -v --cov=src tests/",
        )
        assert config.get_test_command() == "pytest -v --cov=src tests/"

    def test_get_lint_command_ruff(self):
        """Test lint command for ruff."""
        config = EnvironmentConfig(lint_tools=["ruff"])
        assert config.get_lint_command() == "ruff check ."

    def test_get_lint_command_eslint(self):
        """Test lint command for eslint."""
        config = EnvironmentConfig(lint_tools=["eslint"])
        assert config.get_lint_command() == "eslint ."

    def test_get_lint_command_custom(self):
        """Test custom lint command override."""
        config = EnvironmentConfig(
            lint_tools=["ruff"],
            lint_command="ruff check --fix src/",
        )
        assert config.get_lint_command() == "ruff check --fix src/"


class TestEnvironmentConfigSerialization:
    """Tests for YAML serialization."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = EnvironmentConfig(
            package_manager="pip",
            python_version="3.11",
        )
        data = config.to_dict()

        assert data["package_manager"] == "pip"
        assert data["python_version"] == "3.11"
        assert "context" in data
        assert data["context"]["max_files"] == 20

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "package_manager": "poetry",
            "test_framework": "pytest",
            "lint_tools": ["ruff", "mypy"],
        }
        config = EnvironmentConfig.from_dict(data)

        assert config.package_manager == "poetry"
        assert config.test_framework == "pytest"
        assert config.lint_tools == ["ruff", "mypy"]

    def test_from_dict_with_context(self):
        """Test creation from dict with nested context."""
        data = {
            "package_manager": "uv",
            "context": {
                "max_files": 50,
                "max_file_size": 10000,
            },
        }
        config = EnvironmentConfig.from_dict(data)

        assert config.context.max_files == 50
        assert config.context.max_file_size == 10000

    def test_roundtrip(self):
        """Test dict -> config -> dict roundtrip."""
        original = EnvironmentConfig(
            package_manager="pip",
            python_version="3.12",
            test_framework="pytest",
            lint_tools=["ruff", "mypy"],
            custom_commands={"build": "make build"},
        )

        data = original.to_dict()
        restored = EnvironmentConfig.from_dict(data)

        assert restored.package_manager == original.package_manager
        assert restored.python_version == original.python_version
        assert restored.test_framework == original.test_framework
        assert restored.lint_tools == original.lint_tools
        assert restored.custom_commands == original.custom_commands


class TestEnvironmentConfigFileIO:
    """Tests for file I/O operations."""

    def test_save_and_load(self):
        """Test saving and loading config from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)

            original = EnvironmentConfig(
                package_manager="poetry",
                python_version="3.11",
                test_framework="pytest",
                lint_tools=["ruff"],
            )

            # Save
            save_environment_config(workspace_path, original)

            # Verify file exists
            config_file = workspace_path / ".codeframe" / "config.yaml"
            assert config_file.exists()

            # Load
            loaded = load_environment_config(workspace_path)

            assert loaded is not None
            assert loaded.package_manager == original.package_manager
            assert loaded.python_version == original.python_version
            assert loaded.test_framework == original.test_framework
            assert loaded.lint_tools == original.lint_tools

    def test_load_nonexistent(self):
        """Test loading from nonexistent file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            config = load_environment_config(workspace_path)
            assert config is None

    def test_load_empty_file(self):
        """Test loading empty YAML file returns defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)
            config_dir = workspace_path / ".codeframe"
            config_dir.mkdir(parents=True)

            # Create empty file
            config_file = config_dir / "config.yaml"
            config_file.touch()

            config = load_environment_config(workspace_path)

            assert config is not None
            assert config.package_manager == "uv"  # default

    def test_yaml_format(self):
        """Test YAML file is human-readable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = Path(tmpdir)

            config = EnvironmentConfig(
                package_manager="uv",
                python_version="3.11",
                lint_tools=["ruff", "mypy"],
            )

            save_environment_config(workspace_path, config)

            config_file = workspace_path / ".codeframe" / "config.yaml"
            content = config_file.read_text()

            # Should be readable YAML, not inline
            assert "package_manager: uv" in content
            assert "python_version: '3.11'" in content or "python_version: \"3.11\"" in content
            # Lists should be multi-line
            assert "- ruff" in content
            assert "- mypy" in content


class TestGetDefaultEnvironmentConfig:
    """Tests for get_default_environment_config."""

    def test_returns_default_config(self):
        """Test returns a valid default config."""
        config = get_default_environment_config()

        assert isinstance(config, EnvironmentConfig)
        assert config.package_manager == "uv"
        assert config.test_framework == "pytest"
        assert config.lint_tools == ["ruff"]


class TestPackageManagerEnum:
    """Tests for PackageManager enum."""

    def test_all_values(self):
        """Test all package managers are defined."""
        values = [pm.value for pm in PackageManager]
        assert "uv" in values
        assert "pip" in values
        assert "poetry" in values
        assert "npm" in values
        assert "pnpm" in values
        assert "yarn" in values


class TestTestFrameworkEnum:
    """Tests for TestFramework enum."""

    def test_all_values(self):
        """Test all test frameworks are defined."""
        values = [tf.value for tf in TestFramework]
        assert "pytest" in values
        assert "jest" in values
        assert "vitest" in values
        assert "unittest" in values
        assert "mocha" in values


class TestLintToolEnum:
    """Tests for LintTool enum."""

    def test_all_values(self):
        """Test all lint tools are defined."""
        values = [lt.value for lt in LintTool]
        assert "ruff" in values
        assert "pylint" in values
        assert "flake8" in values
        assert "mypy" in values
        assert "eslint" in values
        assert "prettier" in values
        assert "biome" in values
