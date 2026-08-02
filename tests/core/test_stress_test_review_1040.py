"""Regression tests for the three gaps found in cross-family review of #927.

Each one is a place where the PR's stated acceptance criteria and the actual
behaviour of a surface disagreed:

1. ``extract_goals`` raises, but the CLI never caught it — AC2 says both
   surfaces report the failure, and a Typer traceback is not a report.
2. ``stress_test_prd`` let every goal default to its own ``_Budget()``, so the
   sync path was bounded per-goal, not per-run as AC3 requires.
3. The SSE route only sampled ``is_disconnected()`` between yielded events, so
   the cancellation latch could not fire inside a goal's walk — AC4.
"""

import asyncio
import time

import pytest

from codeframe.core.prd_stress_test import (
    MAX_LLM_CALLS,
    StressTestError,
    stress_test_prd,
)

pytestmark = pytest.mark.v2


class _Response:
    def __init__(self, content):
        self.content = content


class _CountingProvider:
    """Returns goals once, then an endlessly-composite tree, counting calls."""

    def __init__(self, goals, children_per_node=3):
        self._goals = goals
        self._children = children_per_node
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            import json

            return _Response(json.dumps(self._goals))
        children = [
            {"title": f"child-{self.calls}-{i}", "description": "d"}
            for i in range(self._children)
        ]
        import json

        return _Response(
            json.dumps({
                "classification": "composite",
                "children": children,
                "complexity_hint": "Low",
            })
        )


class TestSyncBudgetIsPerRun:
    def test_the_budget_spans_all_goals_not_each_goal(self):
        """Four goals must share one MAX_LLM_CALLS ceiling, not get one each.

        Before the fix this ran to ``goals × MAX_LLM_CALLS`` calls.
        """
        provider = _CountingProvider(["g1", "g2", "g3", "g4"])

        result = stress_test_prd("# PRD\nbody", provider, max_depth=10)

        # 1 goal-extraction call + at most MAX_LLM_CALLS classification calls.
        assert provider.calls <= MAX_LLM_CALLS + 1
        assert result.partial is True

    def test_a_walk_that_fits_the_budget_is_not_partial(self):
        """The flag must mean something — a small run stays non-partial."""

        class _AtomicProvider:
            def __init__(self):
                self.calls = 0

            def complete(self, **kwargs):
                self.calls += 1
                import json

                if self.calls == 1:
                    return _Response(json.dumps(["only goal"]))
                return _Response(
                    json.dumps({"classification": "atomic", "complexity_hint": "Low"})
                )

        result = stress_test_prd("# PRD\nbody", _AtomicProvider(), max_depth=3)
        assert result.partial is False


class TestCliReportsTheFailure:
    def test_stress_test_command_exits_cleanly_on_unparseable_goals(self, tmp_path, monkeypatch):
        """A StressTestError must become a red line + exit 1, not a traceback."""
        from typer.testing import CliRunner

        from codeframe.cli.app import app
        from codeframe.core import prd as prd_module
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        workspace = create_or_load_workspace(repo, tech_stack="python")
        prd_module.store(workspace, "# Demo PRD\nSome goals.", title="Demo PRD")

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        def _boom(*args, **kwargs):
            raise StressTestError("Could not read the model's goal list: no JSON found")

        monkeypatch.setattr("codeframe.core.prd_stress_test.stress_test_prd", _boom)
        monkeypatch.setattr(
            "codeframe.core.llm_resolution.create_provider", lambda *a, **k: object()
        )

        result = CliRunner().invoke(
            app, ["prd", "stress-test", "--workspace", str(repo)]
        )

        assert result.exit_code == 1
        assert "Could not read the model's goal list" in result.output
        assert not isinstance(result.exception, StressTestError)


class TestDisconnectLatchFiresDuringAGoal:
    """Drives the real ``_stress_test_event_stream`` with a stand-in core
    generator that decomposes one long 'goal' in a worker thread, polling
    ``is_cancelled`` as the real recursion does. The route must flip the latch
    while that thread is still running — not only between yielded events.
    """

    @pytest.mark.asyncio
    async def test_the_latch_flips_mid_goal(self, monkeypatch, tmp_path):
        from codeframe.core import prd as prd_module
        from codeframe.core.workspace import create_or_load_workspace
        from codeframe.ui.routers import prd_v2

        repo = tmp_path / "repo"
        repo.mkdir()
        workspace = create_or_load_workspace(repo, tech_stack="python")
        prd_module.store(workspace, "# Demo PRD\nSome goals.", title="Demo PRD")

        monkeypatch.setattr(prd_v2, "_resolve_llm_provider", lambda ws: object())

        observed = {"cancelled_at_node": None}

        async def _fake_stream(content, provider, max_depth=3, is_cancelled=None):
            yield {"type": "goals_extracted", "goals": ["one long goal"]}

            def _walk():
                # Stands in for recursive_decompose: many nodes, one thread,
                # no yields back to the loop until the whole goal is done.
                for node in range(200):
                    if is_cancelled is not None and is_cancelled():
                        return node
                    time.sleep(0.01)
                return None

            observed["cancelled_at_node"] = await asyncio.to_thread(_walk)
            yield {"type": "goal_analyzed", "goal": "one long goal"}

        monkeypatch.setattr(
            "codeframe.core.prd_stress_test.stress_test_prd_stream", _fake_stream
        )

        class _Request:
            """Stays connected past the startup poll and the first yielded
            event, then drops — so the only thing that can notice is the
            concurrent poller running while the goal decomposes.
            """

            def __init__(self):
                self.polls = 0

            async def is_disconnected(self):
                self.polls += 1
                return self.polls >= 3

        frames = []
        async for frame in prd_v2._stress_test_event_stream(
            workspace, max_depth=3, request=_Request()
        ):
            frames.append(frame)

        node = observed["cancelled_at_node"]
        assert node is not None, (
            "the walk ran to completion — the latch never fired inside the goal"
        )
        assert node < 200
        # The goal never finished, so its goal_analyzed frame was never sent.
        assert not any("goal_analyzed" in f for f in frames)
