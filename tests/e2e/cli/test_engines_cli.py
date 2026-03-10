"""CLI tests for cf engines list/check commands."""

import pytest
from unittest.mock import patch

from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


class TestEnginesList:
    def test_engines_list_runs(self):
        result = runner.invoke(app, ["engines", "list"])
        assert result.exit_code == 0
        assert "react" in result.output
        assert "plan" in result.output

    def test_engines_list_shows_external(self):
        result = runner.invoke(app, ["engines", "list"])
        assert result.exit_code == 0
        assert "claude-code" in result.output

    def test_engines_list_shows_builtin(self):
        result = runner.invoke(app, ["engines", "list"])
        assert "builtin" in result.output or "alias" in result.output


class TestEnginesCheck:
    def test_check_valid_engine(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            result = runner.invoke(app, ["engines", "check", "react"])
            assert result.exit_code == 0

    def test_check_invalid_engine(self):
        result = runner.invoke(app, ["engines", "check", "nonexistent"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_check_missing_requirements(self):
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            result = runner.invoke(app, ["engines", "check", "react"])
            assert result.exit_code == 1
            assert "not set" in result.output


class TestEnginesNoArgs:
    def test_no_args_shows_help(self):
        result = runner.invoke(app, ["engines"])
        # Typer no_args_is_help exits with code 0 or 2 depending on version
        assert result.exit_code in (0, 2)
        assert "list" in result.output or "check" in result.output or "Usage" in result.output
