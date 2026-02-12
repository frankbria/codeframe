"""Unit tests for GoldenPathRunner._detect_success().

Validates that the success detection logic uses conservative defaults:
- Explicit success patterns → True
- Explicit failure patterns → False
- No patterns matched → False (not True!)
- Non-zero exit code → always False
"""

import pytest

from tests.e2e.cli.golden_path_runner import GoldenPathRunner

pytestmark = pytest.mark.v2


@pytest.fixture
def runner(tmp_path):
    """Create a GoldenPathRunner instance for testing."""
    return GoldenPathRunner(project_path=tmp_path, engine="react")


class TestDetectSuccess:
    """Tests for _detect_success() conservative detection logic."""

    def test_explicit_success_pattern_returns_true(self, runner):
        output = "Some output\nTask completed successfully!\nDone."
        assert runner._detect_success(exit_code=0, output=output) is True

    def test_explicit_failure_pattern_returns_false(self, runner):
        output = "Task execution failed\nSome error occurred"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_api_key_missing_returns_false(self, runner):
        output = "ANTHROPIC_API_KEY environment variable is required"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_api_key_missing_nonzero_exit_returns_false(self, runner):
        output = "ANTHROPIC_API_KEY environment variable is required"
        assert runner._detect_success(exit_code=1, output=output) is False

    def test_error_pattern_returns_false(self, runner):
        output = "Error: something went wrong"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_blocked_pattern_returns_false(self, runner):
        output = "Task blocked - needs human input"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_empty_output_exit_zero_returns_false(self, runner):
        """The core bug: empty output should NOT be treated as success."""
        assert runner._detect_success(exit_code=0, output="") is False

    def test_no_patterns_exit_zero_returns_false(self, runner):
        """Output with no matching patterns should be failure (conservative)."""
        output = "Some random output that matches nothing"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_nonzero_exit_code_always_returns_false(self, runner):
        output = "Task completed successfully!"
        assert runner._detect_success(exit_code=1, output=output) is False

    def test_nonzero_exit_code_with_no_output(self, runner):
        assert runner._detect_success(exit_code=1, output="") is False

    def test_mixed_success_and_failure_returns_false(self, runner):
        """When both success and failure patterns present, failure wins."""
        output = "Task completed successfully!\nBut then Error: crash"
        assert runner._detect_success(exit_code=0, output=output) is False


class TestBuildEnv:
    """Tests for _build_env() .env loading logic."""

    def test_returns_env_dict(self, runner):
        """_build_env() always returns a dict."""
        env = runner._build_env()
        assert isinstance(env, dict)

    def test_propagates_existing_api_key(self, runner, monkeypatch):
        """When ANTHROPIC_API_KEY is in os.environ, it appears in result."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-existing")
        env = runner._build_env()
        assert env["ANTHROPIC_API_KEY"] == "sk-test-existing"

    def test_loads_api_key_from_dotenv(self, runner, tmp_path, monkeypatch):
        """When key is NOT in os.environ, _build_env loads it from .env file."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Ensure CWD has no .env that could interfere
        monkeypatch.chdir(tmp_path)
        # Create a .env file in CODEFRAME_ROOT
        env_file = tmp_path / ".env"
        env_file.write_text('ANTHROPIC_API_KEY=sk-from-dotenv-123\n')
        monkeypatch.setenv("CODEFRAME_ROOT", str(tmp_path))
        env = runner._build_env()
        assert env.get("ANTHROPIC_API_KEY") == "sk-from-dotenv-123"

    def test_loads_api_key_with_quotes(self, runner, tmp_path, monkeypatch):
        """Handles quoted values in .env file."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / ".env"
        env_file.write_text('ANTHROPIC_API_KEY="sk-quoted-key"\n')
        monkeypatch.setenv("CODEFRAME_ROOT", str(tmp_path))
        env = runner._build_env()
        assert env.get("ANTHROPIC_API_KEY") == "sk-quoted-key"

    def test_no_dotenv_no_key_returns_env_without_key(self, runner, tmp_path, monkeypatch):
        """When no .env and no env var, result has no ANTHROPIC_API_KEY."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Use a clean tmp dir with no .env file for both CWD and CODEFRAME_ROOT
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.chdir(empty_dir)
        monkeypatch.setenv("CODEFRAME_ROOT", str(empty_dir))
        env = runner._build_env()
        assert "ANTHROPIC_API_KEY" not in env
