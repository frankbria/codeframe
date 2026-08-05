"""Dead surface and messages that no longer describe reality (#955).

Each of these was code or text that told a reader something untrue:

* ``AgentResultStatus`` had no production caller and listed a ``TIMEOUT`` value
  that ``AgentResult.status`` does not even accept.
* ``engine_stats._update_aggregate_stats`` had no caller and a docstring
  advertising external ones.
* ``IsolationLevel.CLOUD`` said "reserved for the future E2B adapter phase"
  after E2B shipped as ``--engine cloud``.
* Builtin ``requirements()`` hardcoded ``ANTHROPIC_API_KEY``, so ``cf engines
  check react`` called the engine unready on an OpenAI or Ollama workspace.
* ``engine_registry`` dropped ``**kwargs`` for opencode alone, silently ignoring
  the caller's ``timeout_s``.
* ``_truncate_history`` could return an empty list, which the caller sends
  straight to the provider as an invalid request.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.v2


class TestDeadSymbolsAreGone:
    def test_agent_result_status_is_removed(self):
        import codeframe.core.adapters as adapters
        import codeframe.core.adapters.agent_adapter as agent_adapter

        assert not hasattr(agent_adapter, "AgentResultStatus")
        assert not hasattr(adapters, "AgentResultStatus")
        assert "AgentResultStatus" not in adapters.__all__

    def test_the_surviving_status_type_is_the_literal(self):
        """The enum's TIMEOUT value was never assignable — this is why."""
        from codeframe.core.adapters.agent_adapter import AgentResult

        annotation = inspect.get_annotations(AgentResult)["status"]
        assert "timeout" not in str(annotation)

    def test_update_aggregate_stats_wrapper_is_removed(self):
        from codeframe.core import engine_stats

        assert not hasattr(engine_stats, "_update_aggregate_stats")
        # The connection-scoped one is the real implementation and stays.
        assert hasattr(engine_stats, "_update_aggregate_stats_conn")


class TestCloudIsolationMessage:
    def test_it_points_at_the_engine_that_exists(self):
        from codeframe.core.sandbox.context import IsolationLevel, validate_isolation

        with pytest.raises(NotImplementedError) as exc:
            validate_isolation(IsolationLevel.CLOUD)

        message = str(exc.value)
        assert "--engine cloud" in message
        # The stale promise is gone: E2B is not a future phase, it shipped.
        assert "future" not in message.lower()


class TestBuiltinRequirementsFollowTheProvider:
    """`cf engines check react` must ask for the key the workspace will use."""

    @pytest.mark.parametrize(
        "provider,expected",
        [
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
        ],
    )
    def test_key_bearing_providers(self, monkeypatch, provider, expected):
        from codeframe.core.engine_registry import check_requirements

        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", provider)
        assert list(check_requirements("react")) == [expected]
        assert list(check_requirements("plan")) == [expected]

    @pytest.mark.parametrize("provider", ["ollama", "vllm", "compatible"])
    def test_local_providers_need_no_key(self, monkeypatch, provider):
        """A local model has nothing to authenticate, so nothing is unmet."""
        from codeframe.core.engine_registry import check_requirements

        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", provider)
        assert check_requirements("react") == {}

    def test_the_key_is_reported_satisfied_only_when_set(self, monkeypatch):
        from codeframe.core.engine_registry import check_requirements

        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert check_requirements("react") == {"OPENAI_API_KEY": False}

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        assert check_requirements("react") == {"OPENAI_API_KEY": True}

    def test_the_workspace_config_tier_is_honoured(self, monkeypatch, tmp_path):
        """repo_path is the whole point: config.yaml must beat the default."""
        from codeframe.core.engine_registry import check_requirements

        monkeypatch.delenv("CODEFRAME_LLM_PROVIDER", raising=False)
        (tmp_path / ".codeframe").mkdir()
        (tmp_path / ".codeframe" / "config.yaml").write_text(
            "llm:\n  provider: openai\n  model: gpt-4o\n"
        )

        assert list(check_requirements("react", tmp_path)) == ["OPENAI_API_KEY"]
        # …and without the path, the config tier is simply not consulted.
        assert list(check_requirements("react")) == ["ANTHROPIC_API_KEY"]

    def test_external_engines_still_get_their_fixed_requirements(self, monkeypatch):
        """Only builtin engines are provider-dependent; don't break the rest."""
        from codeframe.core.engine_registry import check_requirements

        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        reqs = check_requirements("kilocode", Path.cwd())

        assert "OPENAI_API_KEY" not in reqs
        assert "KILOCODE_PATH" in reqs

    def test_a_broken_config_does_not_crash_the_check(self, monkeypatch, tmp_path):
        """Reporting requirements must not be the thing that fails on bad config."""
        from codeframe.core.engine_registry import check_requirements

        monkeypatch.delenv("CODEFRAME_LLM_PROVIDER", raising=False)
        (tmp_path / ".codeframe").mkdir()
        (tmp_path / ".codeframe" / "config.yaml").write_text("llm: [not, a, mapping\n")

        assert list(check_requirements("react", tmp_path)) == ["ANTHROPIC_API_KEY"]


class TestOpenCodeKwargsAreForwarded:
    def test_timeout_reaches_the_adapter(self):
        from codeframe.core.engine_registry import get_external_adapter

        with patch("shutil.which", return_value="/usr/bin/opencode"):
            adapter = get_external_adapter("opencode", timeout_s=7)

        assert adapter._timeout_s == 7

    def test_other_engines_were_already_forwarding(self):
        """The bug was opencode-only; this pins the behaviour it should match."""
        from codeframe.core.engine_registry import get_external_adapter

        with patch("shutil.which", return_value="/usr/bin/kilo"):
            adapter = get_external_adapter("kilocode", timeout_s=7)

        assert adapter._timeout_s == 7


class TestTruncateHistoryNeverEmpties:
    """The budget is lowered rather than the messages enlarged.

    Building a genuinely 180k-token message costs megabytes and seconds of
    tiktoken encoding per assertion; shrinking the budget exercises the same
    branch in microseconds and does not depend on how a given encoder happens to
    tokenize filler.
    """

    @staticmethod
    def _adapter():
        from codeframe.core.adapters.streaming_chat import StreamingChatAdapter

        return StreamingChatAdapter.__new__(StreamingChatAdapter)

    @pytest.fixture(autouse=True)
    def _tiny_budget(self, monkeypatch):
        from codeframe.core.adapters import streaming_chat

        monkeypatch.setattr(streaming_chat, "_MAX_HISTORY_TOKENS", 5)

    #: Over a 5-token budget under either counter — tiktoken or the 4-chars-per
    #: -token fallback the module uses when tiktoken is unavailable.
    _OVERSIZED = "word " * 200

    def test_one_oversized_user_turn_survives(self):
        """The whole budget in a single message used to trim to nothing.

        The caller passes the result straight to the provider, and an empty
        `messages` is an API error — so the request failed outright instead of
        the history being shortened.
        """
        result = self._adapter()._truncate_history(
            [{"role": "user", "content": self._OVERSIZED}]
        )

        assert result != []
        assert result[0]["role"] == "user"

    def test_an_oversized_final_exchange_keeps_the_user_turn(self):
        messages = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "older reply"},
            {"role": "assistant", "content": self._OVERSIZED},
            {"role": "user", "content": self._OVERSIZED},
        ]

        result = self._adapter()._truncate_history(messages)

        assert result != []
        assert result[0]["role"] == "user"

    def test_older_turns_are_still_dropped_when_that_helps(self):
        """The floor must not turn into "never truncate"."""
        messages = [
            {"role": "user", "content": self._OVERSIZED},
            {"role": "assistant", "content": self._OVERSIZED},
            {"role": "user", "content": "hi"},
        ]

        result = self._adapter()._truncate_history(messages)

        assert result == [{"role": "user", "content": "hi"}]

    def test_a_history_with_no_user_turn_is_still_empty(self):
        """Unusable input stays unusable — this guard must not invent a turn."""
        result = self._adapter()._truncate_history(
            [{"role": "assistant", "content": "hi"}]
        )
        assert result == []

    def test_an_empty_history_is_unchanged(self):
        assert self._adapter()._truncate_history([]) == []
