"""Tests for --llm-provider and --llm-model CLI flags."""
import pytest
from typer.testing import CliRunner
from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


class TestWorkStartLLMFlags:
    """--llm-provider and --llm-model on `cf work start`."""

    def test_work_start_has_llm_provider_flag(self):
        """work start --help shows --llm-provider option."""
        result = runner.invoke(app, ["work", "start", "--help"])
        assert result.exit_code == 0
        assert "--llm-provider" in result.output

    def test_work_start_has_llm_model_flag(self):
        """work start --help shows --llm-model option."""
        result = runner.invoke(app, ["work", "start", "--help"])
        assert result.exit_code == 0
        assert "--llm-model" in result.output

    def test_batch_run_has_llm_provider_flag(self):
        """batch run --help shows --llm-provider option."""
        result = runner.invoke(app, ["work", "batch", "run", "--help"])
        assert result.exit_code == 0
        assert "--llm-provider" in result.output

    def test_batch_run_has_llm_model_flag(self):
        """batch run --help shows --llm-model option."""
        result = runner.invoke(app, ["work", "batch", "run", "--help"])
        assert result.exit_code == 0
        assert "--llm-model" in result.output
