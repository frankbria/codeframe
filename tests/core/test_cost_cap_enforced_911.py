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
