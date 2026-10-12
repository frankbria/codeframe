"""`cf prd generate` finishes instead of failing once an answer is in (#1450).

After MAX_ANSWER_ATTEMPTS rejections the CLI used to exit 1 in --brief-file mode
and offer only a pause interactively. Since #1443 discovery can finish early and
the PRD lists what is still uncovered, so with at least one accepted answer
finishing is the better exit. --answers-file still fails loudly (#1114), and with
nothing accepted every mode still stops.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import MAX_ANSWER_ATTEMPTS, app
from codeframe.core import prd
from codeframe.core.workspace import create_or_load_workspace, get_workspace
from tests.core.test_prd_discovery_bounded_1443 import FakeProvider, _coverage_json

pytestmark = pytest.mark.v2

runner = CliRunner()


class AcceptsFirstThenRejects(FakeProvider):
    """Accepts the first answer, then rejects every answer with no follow-up."""

    def __init__(self):
        super().__init__([_coverage_json(a) for a in range(10, 100, 6)])
        self.validations = 0

    def complete(self, messages, **kwargs):
        if messages[0]["content"].startswith("Evaluate whether this answer"):
            self.validations += 1
            response = super().complete(messages, **kwargs)
            if self.validations > 1:
                response.content = json.dumps(
                    {"adequate": False, "reason": "Covers only half the question.", "follow_up": None}
                )
            return response
        return super().complete(messages, **kwargs)


class RejectsAll(AcceptsFirstThenRejects):
    """Rejects every answer, the first included."""

    def __init__(self):
        super().__init__()
        self.validations = 1  # as if the accepted first answer had already happened


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    create_or_load_workspace(tmp_path)
    return tmp_path


def _questions_asked(workspace_dir: Path) -> int:
    return prd.get_latest(get_workspace(workspace_dir)).metadata["questions_asked"]


def test_brief_mode_finishes_after_rejections_once_an_answer_is_in(workspace_dir):
    brief = workspace_dir / "brief.md"
    brief.write_text("A self-hosted todo API for developers.")
    provider = AcceptsFirstThenRejects()

    with patch("codeframe.core.llm_resolution.create_provider", return_value=provider):
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir), "--brief-file", str(brief)],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

    assert result.exit_code == 0, result.output
    assert "PRD generated" in result.output
    assert _questions_asked(workspace_dir) == 1
    assert provider.validations == 1 + MAX_ANSWER_ATTEMPTS


def test_interactive_offers_finish_instead_of_only_pause(workspace_dir):
    provider = AcceptsFirstThenRejects()
    answers = ["first answer"] + [f"partial {i}" for i in range(MAX_ANSWER_ATTEMPTS)]
    # "n": stop trying this question; "y": finish discovery and generate the PRD.
    stdin = "\n".join(answers + ["n", "y"]) + "\n"

    with patch("codeframe.core.llm_resolution.create_provider", return_value=provider):
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input=stdin,
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

    assert result.exit_code == 0, result.output
    assert "Finish discovery now" in result.output
    assert "PRD generated" in result.output
    assert _questions_asked(workspace_dir) == 1


def test_interactive_with_nothing_accepted_still_pauses(workspace_dir):
    """No answer in: finishing would generate a PRD from nothing, so pause as before."""

    provider = RejectsAll()
    stdin = "\n".join([f"partial {i}" for i in range(MAX_ANSWER_ATTEMPTS)] + ["n"]) + "\n"

    with patch("codeframe.core.llm_resolution.create_provider", return_value=provider):
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input=stdin,
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

    assert "Session paused" in result.output, result.output
    assert "Finish discovery now" not in result.output
    assert prd.get_latest(get_workspace(workspace_dir)) is None


def test_answers_file_still_fails_loudly_even_with_an_answer_in(workspace_dir):
    """Unchanged (#1114): a desynchronised canned list must not finish silently."""
    answers = workspace_dir / "answers.json"
    answers.write_text(json.dumps(["first answer"] + [f"partial {i}" for i in range(10)]))

    with patch("codeframe.core.llm_resolution.create_provider", return_value=AcceptsFirstThenRejects()):
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir), "--answers-file", str(answers)],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

    assert result.exit_code == 1, result.output
    assert "--brief-file" in result.output
    assert prd.get_latest(get_workspace(workspace_dir)) is None


def test_brief_mode_with_nothing_accepted_still_exits_1(workspace_dir):
    brief = workspace_dir / "brief.md"
    brief.write_text("A self-hosted todo API for developers.")

    with patch("codeframe.core.llm_resolution.create_provider", return_value=RejectsAll()):
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir), "--brief-file", str(brief)],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

    assert result.exit_code == 1, result.output
    assert "brief" in result.output.lower()
    assert prd.get_latest(get_workspace(workspace_dir)) is None


def test_interactive_declining_both_prompts_pauses(workspace_dir):
    answers = ["first answer"] + [f"partial {i}" for i in range(MAX_ANSWER_ATTEMPTS)]
    stdin = "\n".join(answers + ["n", "n"]) + "\n"

    with patch("codeframe.core.llm_resolution.create_provider", return_value=AcceptsFirstThenRejects()):
        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir)],
            input=stdin,
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

    assert "Finish discovery now" in result.output
    assert "Session paused" in result.output, result.output
    assert prd.get_latest(get_workspace(workspace_dir)) is None
