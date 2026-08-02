"""Tier-2 compaction must work on the message list `_react_loop` actually builds (#929).

`_remove_intermediate_steps` walked `range(0, cutoff - 1, 2)` and treated even
indices as assistant turns. `_react_loop` seeds a **user** message at index 0, so
in production assistants sit at odd indices, the role check rejected every pair,
and tier 2 removed nothing — every long run fell straight through to lossy tier 3.

The existing tier-2 tests in `test_react_agent_compaction.py` built
`[assistant, user, ...]`, which is why the dead branch looked covered. These tests
build the list the way the loop does.
"""

from datetime import datetime, timezone

import pytest

from codeframe.adapters.llm.mock import MockProvider
from codeframe.core.workspace import Workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    state_dir = tmp_path / ".codeframe"
    state_dir.mkdir()
    return Workspace(
        id="ws-test",
        repo_path=tmp_path,
        state_dir=state_dir,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tech_stack="Python with uv",
    )


@pytest.fixture
def agent(workspace):
    from codeframe.core.react_agent import ReactAgent

    return ReactAgent(workspace=workspace, llm_provider=MockProvider())


def _seed() -> list[dict]:
    """The leading user message `_react_loop` always starts with."""
    return [{"role": "user", "content": "Implement the task described in the system prompt."}]


def _pair(tool_name="read_file", tool_input=None, result="ok", is_error=False, tc_id="tc1"):
    if tool_input is None:
        tool_input = {"path": "test.py"}
    assistant = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": tc_id, "name": tool_name, "input": tool_input}],
    }
    user = {
        "role": "user",
        "content": "",
        "tool_results": [
            {"tool_call_id": tc_id, "content": result, "is_error": is_error}
        ],
    }
    return [assistant, user]


def _filler(count: int) -> list[dict]:
    out: list[dict] = []
    for i in range(count):
        out += _pair(tool_input={"path": f"filler_{i}.py"}, result=f"c{i}", tc_id=f"f{i}")
    return out


class TestTier2OnReactLoopShape:
    def test_redundant_read_is_removed(self, agent):
        """Two reads of the same file with no edit between → the older pair goes."""
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        messages = (
            _seed()
            + _pair(tool_input={"path": "main.py"}, result="old", tc_id="r1")
            + _pair(tool_input={"path": "main.py"}, result="new", tc_id="r2")
            + _filler(PRESERVE_RECENT_PAIRS)
        )

        result, saved = agent._remove_intermediate_steps(list(messages))

        assert saved > 0, "tier 2 removed nothing on a _react_loop-shaped list"
        assert len(result) == len(messages) - 2
        kept = [
            tr["content"]
            for m in result
            for tr in m.get("tool_results", [])
        ]
        assert "new" in kept and "old" not in kept

    def test_passed_test_output_is_removed(self, agent):
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        messages = (
            _seed()
            + _pair(
                tool_name="run_tests",
                tool_input={"test_path": "tests/"},
                result="5 passed in 0.3s",
                tc_id="t1",
            )
            + _filler(PRESERVE_RECENT_PAIRS)
        )

        result, saved = agent._remove_intermediate_steps(list(messages))

        assert saved > 0
        assert len(result) == len(messages) - 2
        assert all("passed in 0.3s" not in str(m) for m in result)

    def test_intervening_edit_keeps_both_reads(self, agent):
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        messages = (
            _seed()
            + _pair(tool_input={"path": "main.py"}, result="before", tc_id="r1")
            + _pair(
                tool_name="edit_file",
                tool_input={"path": "main.py", "edits": []},
                result="edited",
                tc_id="e1",
            )
            + _pair(tool_input={"path": "main.py"}, result="after", tc_id="r2")
            + _filler(PRESERVE_RECENT_PAIRS)
        )

        result, saved = agent._remove_intermediate_steps(list(messages))

        assert saved == 0
        assert len(result) == len(messages)

    def test_failing_test_output_is_kept(self, agent):
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        messages = (
            _seed()
            + _pair(
                tool_name="run_tests",
                tool_input={"test_path": "tests/"},
                result="5 passed, 3 failed in 2.1s",
                tc_id="t1",
            )
            + _filler(PRESERVE_RECENT_PAIRS)
        )

        result, saved = agent._remove_intermediate_steps(list(messages))

        assert saved == 0
        assert len(result) == len(messages)

    def test_unique_reads_are_all_kept(self, agent):
        """Reads of different files are not redundant."""
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        messages = _seed()
        for i in range(PRESERVE_RECENT_PAIRS + 2):
            messages += _pair(
                tool_input={"path": f"unique_{i}.py"}, result=f"u{i}", tc_id=f"u{i}"
            )

        result, saved = agent._remove_intermediate_steps(list(messages))

        assert saved == 0
        assert len(result) == len(messages)

    def test_recent_pairs_are_preserved(self, agent):
        """A redundant read inside the preserve zone must survive."""
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        messages = _seed()
        for i in range(PRESERVE_RECENT_PAIRS):
            messages += _pair(tool_input={"path": "same.py"}, result=f"c{i}", tc_id=f"s{i}")

        result, saved = agent._remove_intermediate_steps(list(messages))

        assert saved == 0
        assert len(result) == len(messages)

    def test_unrelated_roles_do_not_desync_pairing(self, agent):
        """A stray system message must not hide the pairs that follow it."""
        from codeframe.core.react_agent import PRESERVE_RECENT_PAIRS

        messages = (
            [{"role": "system", "content": "system prompt"}]
            + _seed()
            + _pair(tool_input={"path": "main.py"}, result="old", tc_id="r1")
            + _pair(tool_input={"path": "main.py"}, result="new", tc_id="r2")
            + _filler(PRESERVE_RECENT_PAIRS)
        )

        result, saved = agent._remove_intermediate_steps(list(messages))

        assert saved > 0, "pairing desynced after an odd number of leading messages"
        assert len(result) == len(messages) - 2
