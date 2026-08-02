"""The 'Max cost per task (USD)' setting actually caps spend (#911).

Settings → Agent rendered the control, the API persisted ``max_cost_usd``, and a
full-repo grep found the field only in ``config.py``, ``ui/models.py``,
``settings_v2.py`` and the frontend — no runtime, ``react_agent``, ``conductor``
or adapter read it. A user who set a $5 cap got **zero** cost limiting, and the
sibling ``max_turns`` control genuinely worked, so an inert cap was
indistinguishable from a working one.

For a paid product a spend cap that silently does nothing is worse than no cap.
"""

import pytest

from codeframe.core.config import (
    EnvironmentConfig,
    load_environment_config,
    save_environment_config,
)
from codeframe.core.react_agent import ReactAgent
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


def _agent(workspace) -> ReactAgent:
    """An agent with no LLM: every test here stops before a call is made."""
    return ReactAgent(workspace=workspace, llm_provider=None)


def _set_cap(workspace, cap) -> None:
    save_environment_config(workspace.repo_path, EnvironmentConfig(max_cost_usd=cap))


# ---------------------------------------------------------------------------
# The setting is read at all
# ---------------------------------------------------------------------------


def test_the_cap_is_read_from_the_config_the_settings_page_writes(workspace):
    """Settings → Agent PUTs to the same file this reads."""
    _set_cap(workspace, 5.0)

    assert _agent(workspace)._resolve_cost_cap() == 5.0


def test_no_cap_configured_means_no_limit(workspace):
    save_environment_config(workspace.repo_path, EnvironmentConfig())

    assert _agent(workspace)._resolve_cost_cap() is None


def test_a_zero_cap_is_treated_as_unset(workspace):
    """0 would stop before the first call and brick every run."""
    _set_cap(workspace, 0)

    assert _agent(workspace)._resolve_cost_cap() is None


def test_a_malformed_cap_does_not_break_the_run(workspace, monkeypatch):
    """A hand-edited config must not take the agent down."""
    import codeframe.core.config as config_module

    monkeypatch.setattr(
        config_module,
        "load_environment_config",
        lambda p: EnvironmentConfig(max_cost_usd="five dollars"),  # type: ignore[arg-type]
    )

    assert _agent(workspace)._resolve_cost_cap() is None


# ---------------------------------------------------------------------------
# The cap actually stops the run
# ---------------------------------------------------------------------------


def test_exceeding_the_cap_blocks_the_run(workspace, monkeypatch):
    """The headline behaviour: spend over the cap terminates the loop."""
    _set_cap(workspace, 1.0)
    agent = _agent(workspace)

    # Pretend a prior iteration already spent past the cap.
    monkeypatch.setattr(agent, "_estimate_total_cost", lambda: 1.25)
    created: list[tuple[str, str]] = []
    monkeypatch.setattr(
        agent, "_create_text_blocker", lambda text, reason: created.append((text, reason))
    )

    from codeframe.core.react_agent import AgentStatus

    agent._max_cost_usd = agent._resolve_cost_cap()
    status = agent._react_loop("do the thing")

    assert status == AgentStatus.BLOCKED
    assert created, "no blocker was created"
    text, reason = created[0]
    assert reason == "cost_cap_exceeded"
    assert "1.25" in text and "1.00" in text, text


def test_the_llm_is_never_called_once_the_cap_is_reached(workspace, monkeypatch):
    """Stopping *before* the next call is the point — an after-the-fact check
    would spend another call's worth every time."""
    _set_cap(workspace, 1.0)

    calls: list[str] = []

    class ExplodingProvider:
        def complete(self, *args, **kwargs):
            calls.append("called")
            raise AssertionError("the LLM was called after the cap was reached")

    agent = ReactAgent(workspace=workspace, llm_provider=ExplodingProvider())
    monkeypatch.setattr(agent, "_estimate_total_cost", lambda: 99.0)
    monkeypatch.setattr(agent, "_create_text_blocker", lambda text, reason: None)
    agent._max_cost_usd = agent._resolve_cost_cap()

    agent._react_loop("do the thing")

    assert calls == []


def test_spend_under_the_cap_does_not_block(workspace, monkeypatch):
    """The guard must not stop runs that are within budget."""
    _set_cap(workspace, 10.0)
    agent = _agent(workspace)

    monkeypatch.setattr(agent, "_estimate_total_cost", lambda: 0.5)
    blocked: list[str] = []
    monkeypatch.setattr(
        agent, "_create_text_blocker", lambda text, reason: blocked.append(reason)
    )

    class OneShotProvider:
        def complete(self, *args, **kwargs):
            raise RuntimeError("stop here — we only needed to get past the cap check")

    agent.llm_provider = OneShotProvider()
    agent._max_cost_usd = agent._resolve_cost_cap()
    # `_react_loop` is normally entered from `run()`, which sets this up.
    agent._current_task_id = "task-1"

    with pytest.raises(RuntimeError, match="stop here"):
        agent._react_loop("do the thing")

    assert "cost_cap_exceeded" not in blocked


# ---------------------------------------------------------------------------
# No UI control persists a value nothing reads
# ---------------------------------------------------------------------------


def test_the_persisted_setting_round_trips_to_the_enforcer(workspace):
    """End to end from the API's write path to the agent's read path."""
    config = load_environment_config(workspace.repo_path) or EnvironmentConfig()
    config.max_cost_usd = 2.5  # what PUT /api/v2/settings does
    save_environment_config(workspace.repo_path, config)

    assert _agent(workspace)._resolve_cost_cap() == 2.5


# ---------------------------------------------------------------------------
# Review findings: every spending loop, per-task, and measurability
# ---------------------------------------------------------------------------


def test_the_verification_fix_loop_also_respects_the_cap(workspace, monkeypatch):
    """A run can sit just under the cap, fail verification, then spend
    max_verification_retries * max_fix_turns more calls. A cap the correction
    loop ignores is not a cap.

    Drives the real `_run_final_verification` — asserting only that
    `_cost_cap_message()` returns something would test the helper, not the
    loop's use of it, and would pass with the guard deleted.
    """
    from codeframe.core import gates as core_gates
    from codeframe.core.react_agent import _REASON_COST_CAP_EXCEEDED

    _set_cap(workspace, 1.0)

    calls: list[str] = []

    class ExplodingProvider:
        def complete(self, *args, **kwargs):
            calls.append("called")
            raise AssertionError("spent past the cap during verification fixes")

    agent = ReactAgent(workspace=workspace, llm_provider=ExplodingProvider())
    agent._max_cost_usd = agent._resolve_cost_cap()
    agent._current_task_id = "task-1"
    monkeypatch.setattr(agent, "_estimate_total_cost", lambda: 5.0)

    # Gates fail, so verification enters the LLM fix loop.
    monkeypatch.setattr(
        core_gates,
        "run",
        lambda *a, **k: core_gates.GateResult(
            passed=False,
            checks=[
                core_gates.GateCheck(
                    name="pytest",
                    status=core_gates.GateStatus.FAILED,
                    output="1 failed",
                )
            ],
        ),
    )
    monkeypatch.setattr(agent, "_try_quick_fix", lambda summary: False)

    blockers: list[str] = []
    monkeypatch.setattr(
        agent, "_create_text_blocker", lambda text, reason: blockers.append(reason)
    )

    ok, reason = agent._run_final_verification("do the thing")

    assert calls == [], "the LLM was called after the cap was reached"
    assert ok is False
    assert reason == _REASON_COST_CAP_EXCEEDED
    assert _REASON_COST_CAP_EXCEEDED in blockers


def test_prior_spend_on_the_task_counts_toward_the_cap(workspace, monkeypatch):
    """The setting is per *task*. Without this, answering the blocker and
    resuming hands the task a fresh full budget every time."""
    _set_cap(workspace, 5.0)
    agent = _agent(workspace)
    agent._max_cost_usd = agent._resolve_cost_cap()

    # This run has spent almost nothing; an earlier run spent most of the cap.
    monkeypatch.setattr(agent, "_estimate_total_cost", lambda: 0.10)
    agent._prior_task_cost_usd = 4.95

    message = agent._cost_cap_message()

    assert message is not None, "prior spend was ignored; the cap resets on resume"
    assert "5.05" in message


def test_prior_spend_is_read_from_the_persisted_task_total(workspace):
    """Writes a real usage row and reads it back.

    The first version of this test only asserted `== 0.0` for an unknown task,
    so it passed whether the read worked or raised — and it did raise:
    `Database()` needs an explicit db_path, and the broad `except` swallowed the
    TypeError, leaving prior spend permanently 0.0.
    """
    import sqlite3

    from codeframe.lib.metrics_tracker import MetricsTracker
    from codeframe.platform_store.repositories.token_repository import TokenRepository

    conn = sqlite3.connect(str(workspace.db_path))
    try:
        tracker = MetricsTracker(db=TokenRepository(sync_conn=conn))
        tracker.record_token_usage_sync(
            task_id="task-prior",
            agent_id="react",
            project_id=1,
            model_name="claude-sonnet-4-5",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        conn.commit()
    finally:
        conn.close()

    prior = _agent(workspace)._load_prior_task_cost("task-prior")

    assert prior > 0.0, "the persisted spend was not read back"
    assert prior == pytest.approx(3.0, rel=0.01)  # $3.00/MTok input


def test_an_unknown_task_has_no_prior_spend(workspace):
    assert _agent(workspace)._load_prior_task_cost("no-such-task") == 0.0


def test_a_cap_on_an_unpriced_model_refuses_rather_than_never_firing(
    workspace, monkeypatch
):
    """A cap we cannot measure is not a cap: refuse instead of never firing.

    The model here was `gpt-4o` until #932 added pricing for the advertised
    providers — so the example had to change to one that is genuinely unpriced.
    The behaviour under test is unchanged; only the stand-in moved.
    """
    _set_cap(workspace, 1.0)
    agent = _agent(workspace)
    agent._max_cost_usd = agent._resolve_cost_cap()

    agent._token_records.append(
        {"model": "some-unlisted-local-model", "input_tokens": 100000,
         "output_tokens": 50000, "call_type": "execution", "iteration": 1}
    )

    message = agent._cost_cap_message()

    assert message is not None, "an unmeasurable cap silently allowed unbounded spend"
    assert "some-unlisted-local-model" in message
    assert "pricing" in message


def test_an_advertised_openai_model_is_priced_and_does_not_refuse(workspace):
    """#932 AC4: pricing covers the advertised providers.

    gpt-4o used to hit the "no pricing data" refusal above, which meant a cap
    made the whole OpenAI path unusable rather than bounded.
    """
    _set_cap(workspace, 100.0)
    agent = _agent(workspace)
    agent._max_cost_usd = agent._resolve_cost_cap()

    agent._token_records.append(
        {"model": "gpt-4o", "input_tokens": 100000, "output_tokens": 50000,
         "call_type": "execution", "iteration": 1}
    )

    assert agent._cost_cap_message() is None
    assert agent._estimate_total_cost() == pytest.approx(0.75)  # 0.25 in + 0.50 out


def test_an_unpriced_model_is_refused_even_when_a_priced_one_also_ran(workspace):
    """A mixed run must not hide the unmeasurable part behind a measurable one."""
    _set_cap(workspace, 100.0)
    agent = _agent(workspace)
    agent._max_cost_usd = agent._resolve_cost_cap()

    agent._token_records.append(
        {"model": "claude-sonnet-4-5", "input_tokens": 1000, "output_tokens": 500,
         "call_type": "execution", "iteration": 1}
    )
    agent._token_records.append(
        {"model": "some-unlisted-local-model", "input_tokens": 1000,
         "output_tokens": 500, "call_type": "execution", "iteration": 2}
    )

    message = agent._cost_cap_message()

    assert message is not None, (
        "spend on an unpriced model was masked by a priced call in the same run"
    )


def test_a_priced_model_under_the_cap_still_runs(workspace):
    """The measurability guard must not block ordinary Anthropic runs."""
    _set_cap(workspace, 100.0)
    agent = _agent(workspace)
    agent._max_cost_usd = agent._resolve_cost_cap()

    agent._token_records.append(
        {"model": "claude-sonnet-4-5", "input_tokens": 1000, "output_tokens": 500,
         "call_type": "execution", "iteration": 1}
    )

    assert agent._cost_cap_message() is None


def test_the_cap_reason_maps_to_blocked_not_failed():
    """A cap hit during verification creates a blocker, so the run must be
    BLOCKED. Any reason not in this set falls through to FAILED, which would
    leave a blocker attached to a failed run."""
    from codeframe.core.react_agent import _BLOCKED_REASONS, _REASON_COST_CAP_EXCEEDED

    assert _REASON_COST_CAP_EXCEEDED in _BLOCKED_REASONS
