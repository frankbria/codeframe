"""`cf prd generate` ends discovery on the user's word or at the cap (#1443)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import prd
from codeframe.core.workspace import create_or_load_workspace, get_workspace
from tests.core.test_prd_discovery_bounded_1443 import FakeProvider, _coverage_json

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    create_or_load_workspace(tmp_path)
    return tmp_path


def _run(workspace_dir: Path, answers: list[str], *extra: str):
    path = workspace_dir / "answers.json"
    path.write_text(json.dumps(answers))
    # Coverage keeps rising and the model never says ready: only the user or
    # the cap can end this session.
    provider = FakeProvider([_coverage_json(a) for a in range(10, 100, 6)])
    with patch("codeframe.core.llm_resolution.create_provider", return_value=provider):
        return runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir), "--answers-file", str(path), *extra],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )


def test_done_generates_the_prd(workspace_dir):
    result = _run(workspace_dir, ["A todo API for my team.", "/done"])

    assert result.exit_code == 0, result.output
    assert "PRD generated" in result.output
    record = prd.get_latest(get_workspace(workspace_dir))
    assert record.metadata["questions_asked"] == 1


def test_bare_done_is_an_ordinary_answer(workspace_dir):
    """"Done" is a plausible answer ("Is auth built?"), so only /done finishes."""
    result = _run(workspace_dir, ["A todo API for my team.", "Done", "/done"])

    assert result.exit_code == 0, result.output
    assert prd.get_latest(get_workspace(workspace_dir)).metadata["questions_asked"] == 2


def test_done_before_any_answer_is_refused(workspace_dir):
    result = _run(workspace_dir, ["/done", "A todo API for my team.", "/done"])

    assert result.exit_code == 0, result.output
    assert "Answer at least one question" in result.output
    assert prd.get_latest(get_workspace(workspace_dir)).metadata["questions_asked"] == 1


def test_max_questions_flag_bounds_discovery(workspace_dir):
    result = _run(workspace_dir, [f"answer {i}" for i in range(5)], "--max-questions", "2")

    assert result.exit_code == 0, result.output
    assert "Question 1 of at most 2" in result.output
    assert prd.get_latest(get_workspace(workspace_dir)).metadata["questions_asked"] == 2
