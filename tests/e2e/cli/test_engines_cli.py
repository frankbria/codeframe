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

    def test_check_missing_requirements(self, monkeypatch, tmp_path):
        # The CLI loads ~/.env and ./.env (env_provenance.load_env_files), so
        # clearing os.environ is not enough: from the repo root, the repo's own
        # .env put ANTHROPIC_API_KEY straight back and this passed only when
        # run from a directory without one (#1200). Point both at an empty dir.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))
        with patch.dict("os.environ", {}, clear=True):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            result = runner.invoke(app, ["engines", "check", "react"])
            assert result.exit_code == 1
            assert "not set" in result.output


class TestEnginesNoArgs:
    def test_no_args_shows_help(self):
        result = runner.invoke(app, ["engines"])
        # no_args_is_help exits 2 on the Typer pinned in uv.lock (0.19.2). If a
        # bump changes it, update this — don't widen it back to `in (0, 2)`,
        # which is what tests/ci/test_assertion_quality_guard_973.py rejects.
        assert result.exit_code == 2
        assert "Usage" in result.output
        # Both subcommands must be listed, not just any one of them.
        assert "list" in result.output
        assert "check" in result.output
