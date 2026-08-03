"""The cost cap now binds on `--engine plan` too (#1004).

#911 made `max_cost_usd` real for the built-in ReAct engine. The plan engine had
**no token accounting at all** — it set `max_tokens` per call and recorded
nothing — so there was no accumulated spend for a cap to be compared against. A
user on `--engine plan` who set a $5 cap got zero cost limiting, and since the
sibling `max_turns` control genuinely worked, an inert cap was indistinguishable
from a working one. That is the same complaint #911 was filed about, one engine
over.

The accounting and the gate are now one `CostTracker`, extracted from
`ReactAgent` rather than reimplemented, so the two engines cannot drift.

Delegated adapters (`claude-code`, `codex`, `opencode`, `kilocode`) are
deliberately still uncovered: the external CLI spends inside a subprocess and
reports no usage back, so there is nothing to meter. `covers_engine()` states
that boundary in code instead of showing a limit that cannot fire.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from codeframe.core.config import EnvironmentConfig, save_environment_config
from codeframe.core.cost_tracker import (
    CostCapExceeded,
    CostTracker,
    covers_engine,
    resolve_cost_cap,
)
from codeframe.core.executor import ExecutionStatus, Executor
from codeframe.core.planner import ImplementationPlan, PlanStep, StepType
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

#: Priced in MODEL_PRICING, so spend is measurable.
PRICED_MODEL = "claude-sonnet-4-5"


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


@pytest.fixture
def context(workspace):
    """A real TaskContext — the generation prompts read `context.task`."""
    from codeframe.core import tasks
    from codeframe.core.context import TaskContext

    task = tasks.create(workspace, title="add a file", description="")
    return TaskContext(task=task)


def _set_cap(workspace, cap) -> None:
    save_environment_config(workspace.repo_path, EnvironmentConfig(max_cost_usd=cap))


@dataclass
class _Response:
    """The parts of LLMResponse the tracker reads."""

    content: str = "print('hi')\n"
    model: str = PRICED_MODEL
    input_tokens: int = 500_000
    output_tokens: int = 500_000


class _CountingLLM:
    """Returns a fixed response and counts how often it was asked."""

    def __init__(self, response: _Response = None):
        self.calls = 0
        self._response = response or _Response()

    def complete(self, **kwargs):
        self.calls += 1
        return self._response


_STEP_INDEX = iter(range(1, 10_000))


def _step(name: str = "a.py") -> PlanStep:
    return PlanStep(
        index=next(_STEP_INDEX),
        type=StepType.FILE_CREATE,
        description=f"create {name}",
        target=name,
    )


class TestTheCapIsResolvedTheSameWayForBothEngines:
    """The resolver is engine-agnostic and reads the file Settings writes."""

    def test_it_reads_the_settings_page_config(self, workspace, context):
        _set_cap(workspace, 5.0)

        assert resolve_cost_cap(workspace.repo_path) == 5.0

    def test_an_unset_cap_is_none(self, workspace, context):
        assert resolve_cost_cap(workspace.repo_path) is None

    def test_zero_means_no_cap_rather_than_bricking_every_run(self, workspace, context):
        _set_cap(workspace, 0)

        assert resolve_cost_cap(workspace.repo_path) is None

    def test_a_nonsense_value_is_ignored_not_fatal(self, workspace, context):
        save_environment_config(
            workspace.repo_path, EnvironmentConfig(max_cost_usd="not-a-number")
        )

        assert resolve_cost_cap(workspace.repo_path) is None


class TestThePlanEngineNowAccountsForSpend:
    """The missing half: without records there is nothing to cap."""

    def test_an_executor_records_the_llm_calls_it_makes(self, workspace, context):
        llm = _CountingLLM()
        ex = Executor(llm_provider=llm, repo_path=workspace.repo_path)

        ex.execute_step(_step(), context=context)

        assert ex.cost_tracker.records, "the plan engine still records nothing"
        assert ex.cost_tracker.records[0]["model"] == PRICED_MODEL

    def test_the_recorded_tokens_are_the_response_s_own(self, workspace, context):
        llm = _CountingLLM(_Response(input_tokens=11, output_tokens=22))
        ex = Executor(llm_provider=llm, repo_path=workspace.repo_path)

        ex.execute_step(_step(), context=context)

        assert ex.cost_tracker.total_tokens == (11, 22)

    def test_spend_is_estimated_from_them(self, workspace, context):
        llm = _CountingLLM()
        ex = Executor(llm_provider=llm, repo_path=workspace.repo_path)

        ex.execute_step(_step(), context=context)

        assert ex.cost_tracker.estimate_cost() > 0, (
            "a million tokens of a priced model estimated at $0"
        )

    def test_an_executor_with_no_cap_still_accounts(self, workspace, context):
        """Accounting is unconditional; only the LIMIT is opt-in. Otherwise the
        cost data users see would depend on whether they set a cap."""
        ex = Executor(llm_provider=_CountingLLM(), repo_path=workspace.repo_path)

        assert ex.cost_tracker.cap_usd is None
        ex.execute_step(_step(), context=context)
        assert ex.cost_tracker.records


class TestALowCapStopsThePlanEngine:
    """The AC, from the outside."""

    def _capped_executor(self, workspace, cap=0.01) -> Executor:
        return Executor(
            llm_provider=_CountingLLM(),
            repo_path=workspace.repo_path,
            cost_tracker=CostTracker(cap_usd=cap),
        )

    def test_the_first_step_runs_and_the_second_is_refused(self, workspace, context):
        """The cap can only bind after something has been spent — a check that
        fired before the first call would be a cap of zero."""
        ex = self._capped_executor(workspace)

        first = ex.execute_step(_step("a.py"), context=context)
        second = ex.execute_step(_step("b.py"), context=context)

        assert first.status != ExecutionStatus.FAILED, first.error
        assert second.status == ExecutionStatus.FAILED
        assert "cap" in (second.error or "").lower()

    def test_the_refusal_names_the_cap_and_the_setting(self, workspace, context):
        ex = self._capped_executor(workspace)
        ex.execute_step(_step("a.py"), context=context)

        error = ex.execute_step(_step("b.py"), context=context).error

        assert "$0.01" in error
        assert "Max cost per task (USD)" in error

    def test_no_further_llm_call_is_made(self, workspace, context):
        """"Reported failed" and "stopped spending" are different claims."""
        ex = self._capped_executor(workspace)
        ex.execute_step(_step("a.py"), context=context)
        calls_after_first = ex.llm.calls

        ex.execute_step(_step("b.py"), context=context)

        assert ex.llm.calls == calls_after_first, "it kept spending after the cap"

    def test_an_uncapped_run_of_the_same_steps_does_not_stop(self, workspace, context):
        """The control. Without it, a broken execute_step would pass the test
        above for the wrong reason."""
        ex = Executor(llm_provider=_CountingLLM(), repo_path=workspace.repo_path)

        first = ex.execute_step(_step("a.py"), context=context)
        second = ex.execute_step(_step("b.py"), context=context)

        assert first.status != ExecutionStatus.FAILED
        assert second.status != ExecutionStatus.FAILED, second.error

    def test_a_generous_cap_does_not_stop_it(self, workspace, context):
        ex = self._capped_executor(workspace, cap=1_000_000.0)

        ex.execute_step(_step("a.py"), context=context)
        second = ex.execute_step(_step("b.py"), context=context)

        assert second.status != ExecutionStatus.FAILED, second.error


class TestTheGateSitsWhereBothLoopsPassThrough:
    """`Agent._execute_plan` drives `execute_step` directly rather than calling
    `execute_plan`, so a check in the latter's loop would leave the real plan
    engine uncapped. Pinned because it is an easy thing to "tidy" back."""

    def test_execute_step_is_the_one_that_checks(self):
        import inspect

        from codeframe.core import executor as executor_mod

        source = inspect.getsource(executor_mod.Executor.execute_step)

        assert "cap_message()" in source

    def test_execute_plan_inherits_it_rather_than_repeating_it(self):
        import inspect

        from codeframe.core import executor as executor_mod

        source = inspect.getsource(executor_mod.Executor.execute_plan)
        code = "\n".join(line.split("#")[0] for line in source.splitlines())

        assert "cap_message()" not in code, "the check is duplicated"

    def test_execute_plan_still_stops_at_the_cap(self, workspace, context):
        """Because execute_step returns FAILED and the loop breaks on failure."""
        ex = Executor(
            llm_provider=_CountingLLM(),
            repo_path=workspace.repo_path,
            cost_tracker=CostTracker(cap_usd=0.01),
        )
        plan = ImplementationPlan(
            task_id="t1",
            summary="three files",
            steps=[_step("a.py"), _step("b.py"), _step("c.py")],
        )

        result = ex.execute_plan(plan, context=context)

        assert result.success is False
        assert ex.llm.calls == 1, f"spent on {ex.llm.calls} calls despite the cap"


class TestAnUnmeasurableCapRefusesRatherThanPretends:
    """A cap on an unpriced model keeps the running total at $0.00 forever, so
    the guard would never fire — the same silently-inert control, one layer
    down."""

    def test_an_unpriced_model_is_refused(self, workspace, context):
        ex = Executor(
            llm_provider=_CountingLLM(_Response(model="some-local-model-7b")),
            repo_path=workspace.repo_path,
            cost_tracker=CostTracker(cap_usd=100.0),
        )

        ex.execute_step(_step("a.py"), context=context)
        second = ex.execute_step(_step("b.py"), context=context)

        assert second.status == ExecutionStatus.FAILED
        assert "cannot be measured" in second.error

    def test_the_message_names_the_model(self, workspace, context):
        ex = Executor(
            llm_provider=_CountingLLM(_Response(model="some-local-model-7b")),
            repo_path=workspace.repo_path,
            cost_tracker=CostTracker(cap_usd=100.0),
        )
        ex.execute_step(_step("a.py"), context=context)

        assert "some-local-model-7b" in ex.execute_step(_step("b.py"), context=context).error

    def test_an_unpriced_model_with_no_cap_is_fine(self, workspace, context):
        """Only a cap needs measurable spend. An uncapped run must not be
        blocked for using a local model."""
        ex = Executor(
            llm_provider=_CountingLLM(_Response(model="some-local-model-7b")),
            repo_path=workspace.repo_path,
        )

        ex.execute_step(_step("a.py"), context=context)

        assert ex.execute_step(_step("b.py"), context=context).status != (
            ExecutionStatus.FAILED
        )


class TestPriorSpendCountsSoResumeCannotBypassTheCap:
    def test_prior_cost_is_added_to_this_run_s(self):
        tracker = CostTracker(cap_usd=1.0, prior_cost_usd=0.99)
        tracker.record(model=PRICED_MODEL, input_tokens=10_000, output_tokens=10_000)

        assert tracker.cap_message() is not None

    def test_the_same_spend_without_prior_cost_is_allowed(self):
        """Isolates prior_cost_usd as the cause rather than the tokens."""
        tracker = CostTracker(cap_usd=1.0, prior_cost_usd=0.0)
        tracker.record(model=PRICED_MODEL, input_tokens=10_000, output_tokens=10_000)

        assert tracker.cap_message() is None

    def test_the_agent_loads_it_on_run_and_on_resume(self):
        """Resume is the bypass this exists to close: a blocked task answered
        and resumed would otherwise start again at $0 spent."""
        import inspect

        from codeframe.core import agent as agent_mod

        for method in (agent_mod.Agent.run, agent_mod.Agent.resume):
            assert "load_prior_task_cost(" in inspect.getsource(method), (
                f"{method.__name__} does not carry prior spend forward"
            )


class TestTheAgentWiresItUp:
    def test_the_agent_resolves_the_cap_and_shares_one_tracker(self, workspace, context):
        import inspect

        from codeframe.core import agent as agent_mod

        init = inspect.getsource(agent_mod.Agent.__init__)
        exec_plan = inspect.getsource(agent_mod.Agent._execute_plan)

        assert "resolve_cost_cap(" in init
        assert "cost_tracker=self.cost_tracker" in exec_plan, (
            "the Executor gets its own tracker, so spend does not accumulate "
            "across the agent's plan and its self-correction retries"
        )


class TestTheDelegatedEngineBoundaryIsExplicit:
    """AC2's "decide explicitly". The cap cannot bind where the spending happens
    inside someone else's CLI, so say so rather than show a dead control."""

    @pytest.mark.parametrize("engine", ["react", "plan", "builtin"])
    def test_metered_engines_are_covered(self, engine: str):
        assert covers_engine(engine) is True

    @pytest.mark.parametrize(
        "engine", ["claude-code", "codex", "opencode", "kilocode", "cloud"]
    )
    def test_delegated_engines_are_not(self, engine: str):
        assert covers_engine(engine) is False

    def test_it_is_case_and_whitespace_insensitive(self):
        assert covers_engine("  React ") is True

    def test_an_empty_engine_is_not_claimed_as_covered(self):
        assert covers_engine("") is False
        assert covers_engine(None) is False


class TestCheckRaisesForCallersThatPreferAnException:
    def test_it_raises_with_the_message(self):
        tracker = CostTracker(cap_usd=0.000001)
        tracker.record(model=PRICED_MODEL, input_tokens=1000, output_tokens=1000)

        with pytest.raises(CostCapExceeded) as exc:
            tracker.check()

        assert "cap" in str(exc.value).lower()

    def test_it_is_silent_below_the_cap(self):
        CostTracker(cap_usd=1000.0).check()


class TestTheTwoEnginesShareOneImplementation:
    """Extracted rather than reimplemented, so a fix to one is a fix to both."""

    def test_the_react_agent_uses_the_shared_module(self):
        import inspect

        from codeframe.core import react_agent

        source = inspect.getsource(react_agent)

        assert "cost_tracker" in source, (
            "ReactAgent still carries its own copy of the cap logic"
        )

    def test_the_shared_module_is_headless(self):
        """Core rule: no FastAPI or UI imports.

        Asserted on the parsed IMPORTS, not the text — the module docstring says
        the words "no fastapi", and a substring scan would flag its own
        explanation.
        """
        import ast

        tree = ast.parse(
            Path("codeframe/core/cost_tracker.py").read_text(encoding="utf-8")
        )
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        assert not any(
            m.startswith(("fastapi", "starlette", "codeframe.ui")) for m in imported
        ), sorted(imported)


class TestTheCapStopsTheRunNotJustTheStep:
    """Raised in review, and the worst possible shape for a spend cap: it was
    *causing* spend.

    `Executor` refuses a capped step by returning FAILED — but FAILED is exactly
    what triggers `Agent._execute_plan`'s self-correction path, which makes up to
    `MAX_SELF_CORRECTION_ATTEMPTS` further LLM calls on the stepped-UP CORRECTION
    model, plus a blocker-question call, none of which the cap could see. The
    loop then advanced to the next step and did it again.
    """

    def test_the_agent_loop_checks_before_the_step(self):
        import inspect

        from codeframe.core import agent as agent_mod

        source = inspect.getsource(agent_mod.Agent._execute_plan)
        # The check must precede the execute_step call, not follow it.
        assert source.index("cap_message()") < source.index("executor.execute_step")

    def test_hitting_the_cap_blocks_rather_than_failing_the_step(self):
        """BLOCKED, matching ReactAgent: the work is not wrong, it needs a human
        decision. FAILED would route straight back into self-correction."""
        import inspect

        from codeframe.core import agent as agent_mod

        source = inspect.getsource(agent_mod.Agent._execute_plan)
        after = source[source.index("cap_message()") :]
        head = after[: after.index("executor.execute_step")]

        assert "AgentStatus.BLOCKED" in head
        assert "return" in head

    def test_it_creates_a_real_blocker_row(self):
        """Otherwise a run that stopped for a cap looks like a silent hang to
        `cf blocker list` and the web UI."""
        import inspect

        from codeframe.core import agent as agent_mod

        source = inspect.getsource(agent_mod.Agent._execute_plan)
        head = source[: source.index("executor.execute_step")]

        assert "blockers.create(" in head

    def test_self_correction_refuses_once_the_cap_is_reached(self):
        """The expensive loop: it steps UP to the CORRECTION model and runs up
        to MAX_SELF_CORRECTION_ATTEMPTS times per failed step."""
        import inspect

        from codeframe.core import agent as agent_mod

        source = inspect.getsource(agent_mod.Agent._attempt_self_correction)
        head = source[: source.index("self.llm.complete")]

        assert "cap_message()" in head, (
            "the correction loop can still spend past the cap"
        )

    @pytest.mark.parametrize(
        "method,call_type",
        [
            ("_attempt_self_correction", "self_correction"),
            ("_generate_blocker_question", "blocker_question"),
        ],
    )
    def test_the_agents_own_calls_are_recorded(self, method: str, call_type: str):
        """They were invisible to the tracker, so spend accrued unmeasured even
        before the cap fired — the running total was simply wrong."""
        import inspect

        from codeframe.core import agent as agent_mod

        source = inspect.getsource(getattr(agent_mod.Agent, method))

        assert f'record_response(response, call_type="{call_type}")' in source

    def test_every_llm_call_in_the_agent_is_recorded(self):
        """Enumerated rather than listed, so a new call site fails here instead
        of quietly escaping the cap."""
        import inspect
        import re

        from codeframe.core import agent as agent_mod

        source = inspect.getsource(agent_mod)
        calls = len(re.findall(r"response = self\.llm\.complete\(", source))
        records = len(re.findall(r"self\.cost_tracker\.record_response\(", source))

        assert calls > 0
        assert records == calls, (
            f"{calls} LLM calls but only {records} recorded — "
            "one of them is invisible to the cost cap"
        )
