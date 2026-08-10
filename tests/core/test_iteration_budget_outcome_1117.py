"""#1117 — exhausting the iteration budget read as a bare "Task execution failed".

The cold-start run produced a substantially complete implementation (15
create_file, 8 edit_file, 12 run_command, 6 run_tests) and then hit
`Iteration 45/45` while adding a Dockerfile and example clients. The user saw:

    Task execution failed

and a FAILED task — with no indication that most of the deliverable was sitting
in their working tree, what the cap was, or how to continue.

Budget exhaustion is not an error. It is the same shape as the cost cap, which
already blocks rather than fails: the work is not wrong, it needs a human
decision. So it now produces a blocker and BLOCKED, which is resumable and
reads differently from a genuine failure in `cf tasks list`.
"""

from unittest.mock import MagicMock

import pytest

from codeframe.adapters.llm.base import LLMResponse, ToolCall
from codeframe.core import blockers
from codeframe.core.react_agent import (
    _BLOCKED_REASONS,
    _REASON_ITERATION_BUDGET_EXHAUSTED,
    ReactAgent,
)
from codeframe.core.agent import AgentStatus
from codeframe.core.state_machine import TaskStatus
from codeframe.core import tasks, workspace as workspace_mod

pytestmark = pytest.mark.v2


@pytest.fixture
def ws(tmp_path):
    return workspace_mod.create_or_load_workspace(tmp_path)


def _always_uses_a_tool_provider():
    """A provider that never finishes, so the loop can only end by exhaustion.

    Real LLMResponse/ToolCall rather than mocks — the loop JSON-serialises tool
    calls into the transcript, which a MagicMock cannot survive.
    """
    provider = MagicMock()
    calls = {"n": 0}

    def complete(**kwargs):
        # Each call is distinct, or the repetition detector ends the loop first
        # and we would be testing that instead of the budget.
        calls["n"] += 1
        n = calls["n"]
        return LLMResponse(
            content="still working",
            tool_calls=[
                ToolCall(id=f"t{n}", name="run_command", input={"command": f"echo step-{n}"})
            ],
            stop_reason="tool_use",
            input_tokens=10,
            output_tokens=10,
        )

    provider.complete.side_effect = complete
    return provider


def _ok_tool_result(tc):
    """Every tool call succeeds, so only the budget can end the loop."""
    from codeframe.core.tools import ToolResult

    return ToolResult(tool_call_id=tc.id, content="ok")


def _agent(ws, task_id, max_iterations=3):
    agent = ReactAgent(
        workspace=ws,
        llm_provider=_always_uses_a_tool_provider(),
        max_iterations=max_iterations,
    )
    agent._current_task_id = task_id
    return agent


class TestBudgetExhaustionIsItsOwnOutcome:
    """AC: a distinct, named outcome — not a bare `Task execution failed`."""

    def test_the_reason_is_a_blocked_reason_not_a_failure(self):
        assert _REASON_ITERATION_BUDGET_EXHAUSTED in _BLOCKED_REASONS

    def test_the_loop_returns_blocked_rather_than_failed(self, ws, monkeypatch):
        task = tasks.create(ws, title="Build the thing", status=TaskStatus.READY)
        agent = _agent(ws, task.id)
        monkeypatch.setattr(agent, "_execute_tool_with_lint", _ok_tool_result)

        status = agent._react_loop("system prompt")

        assert status == AgentStatus.BLOCKED, (
            "budget exhaustion must not read the same as an error"
        )

    def test_a_blocker_is_created_so_the_run_is_resumable(self, ws, monkeypatch):
        """AC: a blocker is created so the run is resumable rather than terminal."""
        task = tasks.create(ws, title="Build the thing", status=TaskStatus.READY)
        agent = _agent(ws, task.id)
        monkeypatch.setattr(agent, "_execute_tool_with_lint", _ok_tool_result)

        agent._react_loop("system prompt")

        open_blockers = blockers.list_open(ws)
        assert len(open_blockers) == 1
        assert agent.blocker_id == open_blockers[0].id


class TestTheMessageTellsTheUserWhatHappened:
    """AC: states the cap, the flag/env var that raises it, and that partial work exists."""

    def _question(self, ws, monkeypatch, max_iterations=3) -> str:
        task = tasks.create(ws, title="Build the thing", status=TaskStatus.READY)
        agent = _agent(ws, task.id, max_iterations=max_iterations)
        monkeypatch.setattr(agent, "_execute_tool_with_lint", _ok_tool_result)
        agent._react_loop("system prompt")
        return blockers.list_open(ws)[0].question

    def test_it_states_the_cap_that_was_hit(self, ws, monkeypatch):
        assert "3" in self._question(ws, monkeypatch, max_iterations=3)

    def test_it_names_how_to_raise_the_cap(self, ws, monkeypatch):
        question = self._question(ws, monkeypatch)
        assert "CODEFRAME_MAX_ITERATIONS" in question
        assert "config.yaml" in question

    def test_it_says_partial_work_is_in_the_tree(self, ws, monkeypatch):
        question = self._question(ws, monkeypatch).lower()
        assert "partial" in question or "working tree" in question

    def test_it_points_at_the_diagnostic_commands(self, ws, monkeypatch):
        """AC: points at `cf work diagnose` / `cf events tail`."""
        question = self._question(ws, monkeypatch)
        assert "cf work diagnose" in question

    def test_it_does_not_read_as_a_generic_failure(self, ws, monkeypatch):
        assert "Task execution failed" not in self._question(ws, monkeypatch)


class TestItIsDistinctFromARealFailure:
    """AC: a test asserts the message is distinct from the generic failure message."""

    def test_a_genuine_error_still_fails(self, ws, monkeypatch):
        """An exploding provider is a real failure and must stay FAILED."""
        task = tasks.create(ws, title="Build the thing", status=TaskStatus.READY)
        agent = _agent(ws, task.id)

        def boom(**kwargs):
            raise RuntimeError("provider exploded")

        agent.llm_provider.complete.side_effect = boom

        with pytest.raises(RuntimeError):
            agent._react_loop("system prompt")

        assert blockers.list_open(ws) == [], (
            "a genuine error must not be dressed up as a resumable blocker"
        )


class TestTheEscapeHatchTheMessageNamesActuallyWorks:
    """The message is only useful if CODEFRAME_MAX_ITERATIONS really raises the cap.

    There was no such env var and no `--max-iterations` flag when this issue was
    written, so the obvious message would have pointed the user at nothing.
    """

    def _budget(self, ws, complexity=None):
        from codeframe.core.context import TaskContext

        task = tasks.create(
            ws, title="t", status=TaskStatus.READY, complexity_score=complexity
        )
        agent = _agent(ws, task.id)
        context = MagicMock(spec=TaskContext)
        context.task = task
        return agent._calculate_adaptive_budget(context)

    def test_the_env_var_sets_the_budget(self, ws, monkeypatch):
        monkeypatch.setenv("CODEFRAME_MAX_ITERATIONS", "77")
        assert self._budget(ws) == 77

    def test_it_wins_over_the_complexity_multiplier(self, ws, monkeypatch):
        """An explicit budget is exact, not a base the multiplier scales away from."""
        monkeypatch.setenv("CODEFRAME_MAX_ITERATIONS", "40")
        assert self._budget(ws, complexity=5) == 40

    @pytest.mark.parametrize("bad", ["not-a-number", "0", "-3"])
    def test_a_nonsense_value_is_ignored_rather_than_crashing(self, ws, monkeypatch, bad):
        monkeypatch.setenv("CODEFRAME_MAX_ITERATIONS", bad)
        assert self._budget(ws) == 45  # the adaptive default

    def test_unset_leaves_the_adaptive_budget_alone(self, ws, monkeypatch):
        monkeypatch.delenv("CODEFRAME_MAX_ITERATIONS", raising=False)
        assert self._budget(ws) == 45
