"""Tests for --llm-provider and --llm-model CLI flags."""
import re
import pytest
from typer.testing import CliRunner
from codeframe.cli.app import app

pytestmark = pytest.mark.v2

# Wide terminal prevents Rich from wrapping/truncating flag names
runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def _plain(text: str) -> str:
    """Strip ANSI escape codes so assertions work regardless of terminal styling."""
    return re.sub(r"\x1b\[[0-9;]*[mGKHF]", "", text)


class TestWorkStartLLMFlags:
    """--llm-provider and --llm-model on `cf work start`."""

    def test_work_start_has_llm_provider_flag(self):
        """work start --help shows --llm-provider option."""
        result = runner.invoke(app, ["work", "start", "--help"])
        assert result.exit_code == 0
        assert "--llm-provider" in _plain(result.output)

    def test_work_start_has_llm_model_flag(self):
        """work start --help shows --llm-model option."""
        result = runner.invoke(app, ["work", "start", "--help"])
        assert result.exit_code == 0
        assert "--llm-model" in _plain(result.output)

    def test_batch_run_has_llm_provider_flag(self):
        """batch run --help shows --llm-provider option."""
        result = runner.invoke(app, ["work", "batch", "run", "--help"])
        assert result.exit_code == 0
        assert "--llm-provider" in _plain(result.output)

    def test_batch_run_has_llm_model_flag(self):
        """batch run --help shows --llm-model option."""
        result = runner.invoke(app, ["work", "batch", "run", "--help"])
        assert result.exit_code == 0
        assert "--llm-model" in _plain(result.output)
