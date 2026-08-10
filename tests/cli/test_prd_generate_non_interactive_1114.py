"""#1114 — `cf prd generate` could only be driven by a human at a TTY.

The primary THINK entry point, the command the README leads with, had no way to
run without someone typing. So it could not be covered end to end, could not be
demoed reproducibly, and #614's harness had to build an LLM-backed stand-in user
to get through it.

A fixed answer list is not a sufficient answer on its own: the questions are
AI-generated and the validator rejects partial ones, so a single rejection
desynchronises the list permanently — measured at 21 turns, 0 accepted answers,
coverage stuck at 0%. That is why the retry cap here is part of the same change:
without it, `--answers-file` reproduces exactly that hang with no TTY to
interrupt it.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import (
    MAX_ANSWER_ATTEMPTS,
    AnswersExhausted,
    _AnswerSource,
    _load_answers_file,
    _load_brief_file,
    app,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    create_or_load_workspace(tmp_path)
    return tmp_path


def _answers_file(tmp_path: Path, answers) -> Path:
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers))
    return path


class TestTheAnswerSource:
    """The seam that keeps `if non_interactive` out of every loop branch."""

    def test_a_file_source_is_not_interactive(self):
        assert not _AnswerSource(["a"]).interactive

    def test_no_answers_means_interactive(self):
        assert _AnswerSource(None).interactive

    def test_answers_are_consumed_in_order(self):
        source = _AnswerSource(["first", "second"])
        assert source.ask() == "first"
        assert source.ask() == "second"
        assert source.consumed == 2

    def test_running_out_raises_a_specific_error(self):
        """AC: fail loudly and specifically, not EOF inside Prompt.ask."""
        source = _AnswerSource(["only one"])
        source.ask()
        with pytest.raises(AnswersExhausted) as exc:
            source.ask()
        assert "1 of 1" in str(exc.value)


class TestTheAnswersFileFormat:
    def test_a_json_array_of_strings_loads(self, tmp_path):
        path = _answers_file(tmp_path, ["a", "b"])
        assert _load_answers_file(path) == ["a", "b"]

    @pytest.mark.parametrize(
        "content", ["not json at all", '{"a": 1}', "[1, 2, 3]", "[]"]
    )
    def test_a_malformed_file_is_rejected_with_a_usable_message(self, tmp_path, content):
        path = tmp_path / "answers.json"
        path.write_text(content)
        import typer

        with pytest.raises(typer.BadParameter):
            _load_answers_file(path)

    def test_a_missing_file_is_rejected(self, tmp_path):
        import typer

        with pytest.raises(typer.BadParameter):
            _load_answers_file(tmp_path / "nope.json")


class TestTheRetryCapExists:
    """AC: a retry cap per question, so a stuck run says something."""

    def test_the_cap_is_small_enough_to_notice(self):
        assert 1 < MAX_ANSWER_ATTEMPTS <= 10


class TestEndToEndWithoutATTY:
    """AC: a test drives `cf prd generate` end to end without a TTY."""

    @pytest.fixture
    def provider(self):
        """A provider that accepts every answer and completes after three."""
        mock = MagicMock()
        answered = [0]

        def complete(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()
            lowered = content.lower()

            if "opening question" in lowered:
                response.content = "What problem are you trying to solve?"
            elif "assess the current coverage" in lowered:
                ready = answered[0] >= 3
                response.content = json.dumps({
                    "scores": {
                        "problem": 90, "users": 90, "features": 90,
                        "constraints": 90, "tech_stack": 90,
                    },
                    "average": 90 if ready else 10,
                    "ready_for_prd": ready,
                    "weakest_category": "tech_stack",
                    "reasoning": "ok",
                })
            elif "validate" in lowered or "adequate" in lowered:
                answered[0] += 1
                response.content = json.dumps(
                    {"accepted": True, "feedback": "Good", "follow_up": None}
                )
            elif "next question" in lowered:
                response.content = "And who are the users?"
            else:
                response.content = "# Todo API\n\n## Problem\n\nThings."
            return response

        mock.complete.side_effect = complete
        return mock

    @patch("codeframe.core.llm_resolution.create_provider")
    def test_it_runs_with_no_input_stream(
        self, create_provider, provider, workspace_dir, tmp_path
    ):
        create_provider.return_value = provider
        path = _answers_file(tmp_path, [
            "Developers lose track of todos across scattered notes, and I wanted "
            "a self-hosted API after paying for three SaaS trackers.",
            "Self-hosting developers comfortable with REST and the command line.",
            "FastAPI and SQLite, deployed on a small VPS.",
            "Sub-50ms creates, and filtering by completion status.",
        ])

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir), "--answers-file", str(path)],
            # No `input=`: nothing is available to read from stdin.
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, result.output
        assert "Non-interactive" in result.output

    @patch("codeframe.core.llm_resolution.create_provider")
    def test_running_out_of_answers_says_which_question(
        self, create_provider, provider, workspace_dir, tmp_path
    ):
        """AC: fails loudly and specifically, not an EOF traceback."""
        create_provider.return_value = provider
        path = _answers_file(tmp_path, ["Only one answer, and discovery needs more."])

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir), "--answers-file", str(path)],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert result.exit_code == 1
        assert "ran out of answers" in result.output
        assert "coverage" in result.output.lower()
        # The old failure was an EOF traceback out of Prompt.ask.
        assert "EOF" not in result.output
        assert "Traceback" not in result.output


class TestARejectingValidatorDoesNotHang:
    """The #1114 scenario: 21 turns, 0 accepted, coverage pinned at 0%."""

    @pytest.fixture
    def always_rejects(self):
        mock = MagicMock()

        def complete(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()
            lowered = content.lower()
            if "opening question" in lowered:
                response.content = "What problem are you solving, and what inspired it?"
            elif "assess the current coverage" in lowered:
                response.content = json.dumps({
                    "scores": {
                        "problem": 0, "users": 0, "features": 0,
                        "constraints": 0, "tech_stack": 0,
                    },
                    "average": 0,
                    "ready_for_prd": False,
                    "weakest_category": "problem",
                    "reasoning": "nothing yet",
                })
            elif "validate" in lowered or "adequate" in lowered:
                response.content = json.dumps({
                    "accepted": False,
                    "feedback": "Omits the second part of the question.",
                    "follow_up": None,
                })
            else:
                response.content = "text"
            return response

        mock.complete.side_effect = complete
        return mock

    @patch("codeframe.core.llm_resolution.create_provider")
    def test_it_stops_instead_of_looping_forever(
        self, create_provider, always_rejects, workspace_dir, tmp_path
    ):
        create_provider.return_value = always_rejects
        # Far more answers than the cap: without the cap this consumes all of
        # them and then hangs or EOFs, which is the reported behaviour.
        path = _answers_file(tmp_path, [f"answer {i}" for i in range(30)])

        result = runner.invoke(
            app,
            ["prd", "generate", "-w", str(workspace_dir), "--answers-file", str(path)],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )

        assert result.exit_code == 1
        assert str(MAX_ANSWER_ATTEMPTS) in result.output
        assert "non-interactive" in result.output.lower()


class TestTheBriefBackedMode:
    """--brief-file answers the question actually asked, so it survives rejection.

    This is the mode that works against a real model. A fixed list cannot: the
    questions are AI-generated, so one rejection desynchronises it permanently.
    Verified end to end against a live model — a complete PRD in 67s with no TTY.
    """

    def test_a_brief_source_is_not_interactive(self):
        assert not _AnswerSource(None, "a brief", MagicMock()).interactive

    def test_only_a_fixed_list_can_desynchronise(self):
        assert _AnswerSource(["a"]).can_desynchronise
        assert not _AnswerSource(None, "brief", MagicMock()).can_desynchronise
        assert not _AnswerSource(None).can_desynchronise

    def test_the_question_is_passed_to_the_model(self):
        provider = MagicMock()
        provider.complete.return_value = MagicMock(content="An answer.")
        source = _AnswerSource(None, "The brief text", provider)

        assert source.ask("What problem are you solving?") == "An answer."

        prompt = provider.complete.call_args.kwargs["messages"][0]["content"]
        assert "What problem are you solving?" in prompt
        assert "The brief text" in prompt

    def test_the_prompt_demands_every_part_of_a_question(self):
        """Multi-part questions are what desynchronised the canned list."""
        provider = MagicMock()
        provider.complete.return_value = MagicMock(content="x")
        _AnswerSource(None, "brief", provider).ask("Two-part question?")

        prompt = provider.complete.call_args.kwargs["messages"][0]["content"].lower()
        assert "two parts" in prompt or "both" in prompt

    def test_it_never_runs_out(self):
        """Unlike a canned list, there is no fixed supply to exhaust."""
        provider = MagicMock()
        provider.complete.return_value = MagicMock(content="An answer.")
        source = _AnswerSource(None, "brief", provider)
        for _ in range(50):
            assert source.ask("q") == "An answer."

    def test_a_missing_brief_is_rejected(self, tmp_path):
        import typer

        with pytest.raises(typer.BadParameter):
            _load_brief_file(tmp_path / "nope.md")

    def test_an_empty_brief_is_rejected(self, tmp_path):
        import typer

        path = tmp_path / "brief.md"
        path.write_text("   \n")
        with pytest.raises(typer.BadParameter):
            _load_brief_file(path)

    def test_the_two_modes_are_mutually_exclusive(self, workspace_dir, tmp_path):
        answers = _answers_file(tmp_path, ["a"])
        brief = tmp_path / "brief.md"
        brief.write_text("A brief.")

        result = runner.invoke(
            app,
            [
                "prd", "generate", "-w", str(workspace_dir),
                "--answers-file", str(answers),
                "--brief-file", str(brief),
            ],
            env={"ANTHROPIC_API_KEY": "test-key"},
        )
        assert result.exit_code != 0
        assert "alternatives" in result.output or "one" in result.output.lower()
