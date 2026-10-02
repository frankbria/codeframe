"""Per-user daily spend ceiling (#1303).

An operator sets ``CODEFRAME_USER_DAILY_COST_LIMIT_USD``; a principal's spend
today is the sum of ``token_usage`` across the workspaces it runs in, and what
is left clamps the workspace ``max_cost_usd``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codeframe.core import spend_limit
from codeframe.core.adapters.agent_adapter import AgentResult
from codeframe.core.cost_tracker import resolve_cost_cap
from codeframe.core.models import TokenUsage
from codeframe.core.workspace import create_or_load_workspace
from codeframe.platform_store.repositories.token_repository import TokenRepository

pytestmark = pytest.mark.v2

LIMIT_ENV = "CODEFRAME_USER_DAILY_COST_LIMIT_USD"


def _record(repo: Path, cost: float, when: datetime | None = None) -> None:
    ws = create_or_load_workspace(repo)
    conn = sqlite3.connect(str(ws.db_path))
    try:
        TokenRepository(sync_conn=conn).save_token_usage(
            TokenUsage(
                task_id="t1",
                agent_id="react",
                project_id=0,
                model_name="claude-sonnet-4-5",
                input_tokens=1,
                output_tokens=1,
                estimated_cost_usd=cost,
                timestamp=when or datetime.now(timezone.utc),
            )
        )
    finally:
        conn.close()


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    create_or_load_workspace(a)
    create_or_load_workspace(b)
    return a, b


class TestDailyLimit:
    @pytest.mark.parametrize("value", [None, "", "0", "-3", "abc"])
    def test_unset_or_invalid_means_no_limit(self, monkeypatch, value):
        if value is None:
            monkeypatch.delenv(LIMIT_ENV, raising=False)
        else:
            monkeypatch.setenv(LIMIT_ENV, value)
        assert spend_limit.daily_limit_usd() is None

    def test_positive_value_is_the_limit(self, monkeypatch):
        monkeypatch.setenv(LIMIT_ENV, "2.5")
        assert spend_limit.daily_limit_usd() == 2.5


class TestSpendToday:
    def test_sums_today_across_workspaces(self, repos):
        a, b = repos
        _record(a, 1.25)
        _record(b, 0.5)
        assert spend_limit.spend_today_usd([a, b]) == pytest.approx(1.75)

    def test_ignores_yesterday(self, repos):
        a, _ = repos
        _record(a, 9.0, when=datetime.now(timezone.utc) - timedelta(days=1))
        _record(a, 0.25)
        assert spend_limit.spend_today_usd([a]) == pytest.approx(0.25)

    def test_same_workspace_listed_twice_counts_once(self, repos):
        a, _ = repos
        _record(a, 1.0)
        assert spend_limit.spend_today_usd([a, a]) == pytest.approx(1.0)

    def test_missing_workspace_is_skipped(self, repos, tmp_path):
        a, _ = repos
        _record(a, 1.0)
        assert spend_limit.spend_today_usd([a, tmp_path / "gone"]) == pytest.approx(1.0)


class TestRemainingToday:
    def test_no_limit_returns_none(self, monkeypatch, repos):
        monkeypatch.delenv(LIMIT_ENV, raising=False)
        _record(repos[0], 100.0)
        assert spend_limit.remaining_today_usd([repos[0]]) is None

    def test_returns_what_is_left(self, monkeypatch, repos):
        monkeypatch.setenv(LIMIT_ENV, "3")
        _record(repos[0], 1.0)
        _record(repos[1], 0.5)
        assert spend_limit.remaining_today_usd(list(repos)) == pytest.approx(1.5)

    def test_exhausted_raises(self, monkeypatch, repos):
        monkeypatch.setenv(LIMIT_ENV, "1")
        _record(repos[0], 1.0)
        with pytest.raises(spend_limit.SpendLimitExceeded) as exc:
            spend_limit.remaining_today_usd([repos[0]])
        assert "1.00" in str(exc.value)


class TestCeilingClampsWorkspaceCap:
    def _set_cap(self, repo: Path, cap):
        from codeframe.core.config import (
            EnvironmentConfig,
            load_environment_config,
            save_environment_config,
        )

        cfg = load_environment_config(repo) or EnvironmentConfig()
        cfg.max_cost_usd = cap
        save_environment_config(repo, cfg)

    def test_ceiling_below_workspace_cap_wins(self, repos):
        self._set_cap(repos[0], 5.0)
        assert resolve_cost_cap(repos[0], ceiling_usd=1.5) == 1.5

    def test_workspace_cap_below_ceiling_wins(self, repos):
        self._set_cap(repos[0], 0.75)
        assert resolve_cost_cap(repos[0], ceiling_usd=1.5) == 0.75

    def test_null_workspace_cap_cannot_escape_the_ceiling(self, repos):
        self._set_cap(repos[0], None)
        assert resolve_cost_cap(repos[0], ceiling_usd=2.0) == 2.0

    def test_no_ceiling_keeps_workspace_cap(self, repos):
        self._set_cap(repos[0], 4.0)
        assert resolve_cost_cap(repos[0]) == 4.0


class TestCeilingReachesBothEngines:
    """The clamp is useless unless each metered engine actually reads it."""

    def test_react_agent(self, repos):
        from codeframe.core.react_agent import ReactAgent

        TestCeilingClampsWorkspaceCap()._set_cap(repos[0], 5.0)
        ws = create_or_load_workspace(repos[0])
        agent = ReactAgent(workspace=ws, llm_provider=None, cost_ceiling_usd=0.5)
        assert agent._resolve_cost_cap() == 0.5

    def test_plan_agent(self, repos):
        from codeframe.core.agent import Agent

        ws = create_or_load_workspace(repos[0])
        agent = Agent(workspace=ws, llm_provider=None, cost_ceiling_usd=0.5)
        assert agent.cost_tracker.cap_usd == 0.5

    @pytest.mark.parametrize("engine", ["react", "plan"])
    def test_runtime_hands_the_env_ceiling_to_the_adapter(self, monkeypatch, repos, engine):
        """A batch's `cf work start` child gets the clamp only through the env."""
        from unittest.mock import MagicMock, patch

        from codeframe.core.runtime import Run, RunStatus, execute_agent

        ws = create_or_load_workspace(repos[0])
        run = Run(
            id="run-1", workspace_id=ws.id, task_id="task-1",
            status=RunStatus.RUNNING, started_at="2026-10-01T00:00:00Z",
            completed_at=None,
        )
        monkeypatch.setenv(spend_limit.RUN_CEILING_ENV, "0.75")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with (
            patch("codeframe.core.engine_registry.get_builtin_adapter") as factory,
            patch("codeframe.core.runtime.complete_run"),
            patch("codeframe.core.runtime.fail_run"),
            patch("codeframe.core.runtime.block_run"),
        ):
            factory.return_value = MagicMock(**{"run.return_value": AgentResult(status="completed")})
            execute_agent(ws, run, engine=engine)
        assert factory.call_args.kwargs["cost_ceiling_usd"] == 0.75

    def test_an_explicit_ceiling_beats_the_env(self, monkeypatch, repos):
        from unittest.mock import MagicMock, patch

        from codeframe.core.runtime import Run, RunStatus, execute_agent

        ws = create_or_load_workspace(repos[0])
        run = Run(
            id="run-1", workspace_id=ws.id, task_id="task-1",
            status=RunStatus.RUNNING, started_at="2026-10-01T00:00:00Z",
            completed_at=None,
        )
        monkeypatch.setenv(spend_limit.RUN_CEILING_ENV, "9")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with (
            patch("codeframe.core.engine_registry.get_builtin_adapter") as factory,
            patch("codeframe.core.runtime.complete_run"),
            patch("codeframe.core.runtime.fail_run"),
            patch("codeframe.core.runtime.block_run"),
        ):
            factory.return_value = MagicMock(**{"run.return_value": AgentResult(status="completed")})
            execute_agent(ws, run, engine="react", cost_ceiling_usd=0.25)
        assert factory.call_args.kwargs["cost_ceiling_usd"] == 0.25


class TestBatchRechecksBeforeEachTask:
    """execute_batch re-reads the spend before spawning each task's child."""

    def _run_batch(self, repo: Path, monkeypatch, batch_opts=None, **kwargs):
        from codeframe.core import conductor, tasks
        from codeframe.core.state_machine import TaskStatus

        ws = create_or_load_workspace(repo)
        task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)
        batch = conductor.create_batch(ws, [task.id], **(batch_opts or {}))
        spawned: list = []

        class _Proc:
            returncode = 1
            pid = 0

            def wait(self, timeout=None):
                return 1

            def poll(self):
                return 1

        def _popen(cmd, **popen_kwargs):
            if "work" in cmd:  # the task child, not a git call
                spawned.append(popen_kwargs.get("env"))
            return _Proc()

        monkeypatch.setattr(conductor.subprocess, "Popen", _popen)
        conductor.execute_batch(ws, batch, **kwargs)
        assert batch.id not in conductor._batch_spend_paths  # cleaned up
        return spawned

    def test_child_receives_the_remaining_budget(self, monkeypatch, repos):
        monkeypatch.setenv(LIMIT_ENV, "2")
        _record(repos[1], 0.5)
        spawned = self._run_batch(repos[0], monkeypatch, user_id=7, spend_paths=list(repos))
        assert len(spawned) == 1
        assert float(spawned[0][spend_limit.RUN_CEILING_ENV]) == pytest.approx(1.5)

    def test_parallel_batch_child_gets_its_slots_share(self, monkeypatch, repos, clean_holds):
        """Siblings start together, so each holds remaining / max_parallel."""
        monkeypatch.setenv(LIMIT_ENV, "2")
        spawned = self._run_batch(
            repos[0], monkeypatch,
            batch_opts={"strategy": "parallel", "max_parallel": 2},
            user_id=7, spend_paths=[repos[0]],
        )
        assert len(spawned) == 1
        assert float(spawned[0][spend_limit.RUN_CEILING_ENV]) == pytest.approx(1.0)

    def test_exhausted_limit_spawns_nothing(self, monkeypatch, repos):
        monkeypatch.setenv(LIMIT_ENV, "1")
        _record(repos[1], 1.0)
        spawned = self._run_batch(repos[0], monkeypatch, user_id=7, spend_paths=list(repos))
        assert spawned == []

    def test_without_spend_paths_no_limit_applies(self, monkeypatch, repos):
        monkeypatch.setenv(LIMIT_ENV, "1")
        _record(repos[0], 5.0)
        spawned = self._run_batch(repos[0], monkeypatch)
        assert len(spawned) == 1
        assert spawned[0] is None or spend_limit.RUN_CEILING_ENV not in spawned[0]


class TestResumeIsNotDoubleCounted:
    """The ceiling limits NEW spend; the cap is compared to lifetime spend.

    $6 already spent on a task and $4 left today must allow $4 more, not
    refuse at once because 6 > 4 (codex review of #1303).
    """

    def test_ceiling_is_offset_by_prior_spend(self, repos):
        assert resolve_cost_cap(repos[0], ceiling_usd=4.0, prior_usd=6.0) == 10.0

    def test_workspace_cap_still_bounds_lifetime_spend(self, repos):
        TestCeilingClampsWorkspaceCap()._set_cap(repos[0], 7.0)
        assert resolve_cost_cap(repos[0], ceiling_usd=4.0, prior_usd=6.0) == 7.0

    def test_react_agent_offsets_by_the_tasks_prior_spend(self, repos, monkeypatch):
        from codeframe.core import react_agent as ra

        ws = create_or_load_workspace(repos[0])
        agent = ra.ReactAgent(workspace=ws, llm_provider=None, cost_ceiling_usd=4.0)
        monkeypatch.setattr(agent, "_load_prior_task_cost", lambda task_id: 6.0)
        seen = {}

        def _stop(*a, **kw):
            seen["cap"] = agent._max_cost_usd
            raise RuntimeError("stop after cap resolution")

        monkeypatch.setattr(agent, "_calculate_adaptive_budget", _stop)
        monkeypatch.setattr(
            ra.TaskContextPackager, "load_context", lambda self, task_id: object()
        )
        try:
            agent.run("t1")
        except Exception:
            pass
        assert seen["cap"] == 10.0

    def test_plan_agent_offsets_by_the_tasks_prior_spend(self, repos, monkeypatch):
        from codeframe.core import agent as plan

        ws = create_or_load_workspace(repos[0])
        a = plan.Agent(workspace=ws, llm_provider=None, cost_ceiling_usd=4.0)
        monkeypatch.setattr(plan, "load_prior_task_cost", lambda ws, task_id: 6.0)
        a._load_prior_cost("t1")
        assert a.cost_tracker.cap_usd == 10.0
        assert a.cost_tracker.prior_cost_usd == 6.0


@pytest.fixture
def clean_holds():
    spend_limit._held.clear()
    yield
    spend_limit._held.clear()


class TestReservation:
    """Concurrent starts must not each be handed the whole remainder."""

    def test_second_concurrent_run_gets_only_what_is_left(self, monkeypatch, repos, clean_holds):
        monkeypatch.setenv(LIMIT_ENV, "10")
        assert spend_limit.reserve_today_usd(1, [repos[0]], share=4) == pytest.approx(2.5)
        assert spend_limit.reserve_today_usd(1, [repos[0]]) == pytest.approx(7.5)
        with pytest.raises(spend_limit.SpendLimitExceeded, match="held by runs in progress"):
            spend_limit.reserve_today_usd(1, [repos[0]])

    def test_release_returns_the_budget(self, monkeypatch, repos, clean_holds):
        monkeypatch.setenv(LIMIT_ENV, "10")
        held = spend_limit.reserve_today_usd(1, [repos[0]])
        spend_limit.release(1, held)
        assert spend_limit.remaining_today_usd([repos[0]], 1) == pytest.approx(10)

    def test_holds_are_per_principal(self, monkeypatch, repos, clean_holds):
        monkeypatch.setenv(LIMIT_ENV, "10")
        spend_limit.reserve_today_usd(1, [repos[0]])
        assert spend_limit.reserve_today_usd(2, [repos[1]]) == pytest.approx(10)

    def test_batch_task_holds_during_the_child_and_releases_after(
        self, monkeypatch, repos, clean_holds
    ):
        from codeframe.core import conductor

        monkeypatch.setenv(LIMIT_ENV, "10")
        seen = {}

        def _child(*a, **kw):
            seen["ceiling"] = kw["cost_ceiling_usd"]
            seen["held"] = dict(spend_limit._held)
            return "COMPLETED"

        monkeypatch.setattr(conductor, "_spawn_task_child", _child)
        conductor._batch_principal["b1"] = 1
        conductor._batch_spend_paths["b1"] = ([repos[0]], 4)
        try:
            ws = create_or_load_workspace(repos[0])
            assert conductor._execute_task_subprocess(ws, "t1", batch_id="b1") == "COMPLETED"
        finally:
            conductor._batch_principal.pop("b1", None)
            conductor._batch_spend_paths.pop("b1", None)
        assert seen["ceiling"] == pytest.approx(2.5)  # a quarter: 4 parallel slots
        assert seen["held"] == {1: pytest.approx(2.5)}
        assert spend_limit._held == {}  # released once the child exited
