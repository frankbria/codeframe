"""THINK-stage output integrity (#1293).

Each case reproduces the issue with a scripted MockProvider: recursive
generation emitting placeholder tasks, a refine storing a truncated or wrapped
PRD, dependency resolution crashing on a self-edge or saving a cycle, fenced
task JSON misreported as truncated, and a ralph re-import leaving an item that
was checked off upstream as READY.
"""

import json
import logging

import pytest

from codeframe.adapters.llm.base import LLMResponse
from codeframe.adapters.llm.mock import MockProvider
from codeframe.core import prd, tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.task_tree import classify_task, decompose_task
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


# --- 1. Recursive generation -------------------------------------------------


@pytest.mark.parametrize("reply, expected", [
    ("Atomic.", "atomic"),
    ("**composite**", "composite"),
    ("  COMPOSITE\n", "composite"),
    ("atomic — a single change", "atomic"),
])
def test_classification_normalises_a_decorated_answer(reply, expected):
    provider = MockProvider()
    provider.add_text_response(reply)
    assert classify_task(provider, "task", []) == expected


@pytest.mark.parametrize("reply", ["", "maybe", "atomic or composite, hard to say"])
def test_classification_refuses_to_guess(reply):
    provider = MockProvider()
    provider.add_text_response(reply)
    with pytest.raises(tasks.TaskGenerationError):
        classify_task(provider, "task", [])


@pytest.mark.parametrize("reply", ["[]", '{"title": "not a list"}', '[{"no_title": 1}]'])
def test_a_decomposition_with_no_subtasks_is_an_error(reply):
    provider = MockProvider()
    provider.add_text_response(reply)
    with pytest.raises(tasks.TaskGenerationError):
        decompose_task(provider, "Implement the whole PRD", [])


# --- 2. Refine ---------------------------------------------------------------

_PRD = "# Search\n\n" + "Results are sorted by date. " * 40 + "\n"


def _refine(reply: LLMResponse) -> str:
    from codeframe.core.prd_stress_test import Ambiguity, resolve_ambiguities_into_prd

    provider = MockProvider()
    provider.add_response(reply)
    amb = Ambiguity(
        id="amb-1", label="Sort order", questions=["Which order?"], source_node_title="Search",
        recommendation="", severity="blocking", resolved_answer="By relevance",
    )
    return resolve_ambiguities_into_prd(_PRD, [amb], provider)


@pytest.mark.parametrize("stop_reason", ["max_tokens", "length"])
def test_a_truncated_refine_is_rejected(stop_reason, caplog):
    """A rewrite cut off by the token limit was stored as a new version when it
    was longer than half the original (#1293). Anthropic says max_tokens;
    OpenAI-compatible providers say length."""
    almost_all = _PRD.replace("date", "relevance")[:-40]
    with caplog.at_level(logging.WARNING):
        result = _refine(LLMResponse(content=almost_all, stop_reason=stop_reason))
    assert result == _PRD
    assert "truncated" in caplog.text


def test_a_fenced_refine_is_unwrapped_and_keeps_its_own_code_blocks():
    """The preamble and outer fence were stored verbatim; a PRD's own code
    example must survive the unwrapping."""
    body = _PRD.replace("date", "relevance") + "\n```python\nsearch(q)\n```\n"
    reply = f"Here is the updated PRD:\n\n```markdown\n{body}```\n"
    result = _refine(LLMResponse(content=reply, stop_reason="end_turn"))
    assert result == body.strip()


def test_an_unfenced_refine_is_stored_as_is():
    body = _PRD.replace("date", "relevance")
    assert _refine(LLMResponse(content=body, stop_reason="end_turn")) == body.strip()


# --- 3. Dependency resolution ------------------------------------------------


def _generate(workspace, task_list):
    provider = MockProvider()
    provider.add_text_response(json.dumps(task_list))
    record = prd.store(workspace, "# P\n\nBuild it.\n")
    return tasks.generate_from_prd(workspace, record, provider=provider)


def _deps(workspace):
    by_id = {t.id: t.title for t in tasks.list_tasks(workspace)}
    return {by_id[t.id]: sorted(by_id[d] for d in t.depends_on) for t in tasks.list_tasks(workspace)}


def test_a_self_dependency_is_dropped_not_a_crash(workspace, caplog):
    """A self-edge raised ValueError after the tasks were created: a partial
    result, and a 500 in the web UI (#1293)."""
    with caplog.at_level(logging.WARNING):
        created = _generate(workspace, [
            {"title": "A", "description": "a", "depends_on_titles": ["A"]},
            {"title": "B", "description": "b", "depends_on_titles": ["A"]},
        ])
    assert len(created) == 2
    assert _deps(workspace) == {"A": [], "B": ["A"]}
    assert "A" in caplog.text


def test_a_cycle_closing_dependency_is_dropped(workspace, caplog):
    """A cycle was saved silently and broke `cf schedule` later (#1293)."""
    with caplog.at_level(logging.WARNING):
        _generate(workspace, [
            {"title": "A", "description": "a", "depends_on_titles": ["C"]},
            {"title": "B", "description": "b", "depends_on_titles": ["A"]},
            {"title": "C", "description": "c", "depends_on_titles": ["B"]},
        ])
    # Edges resolve in generation order, so the one that closes the cycle is
    # the last: C -> B (A -> C and B -> A are already in place).
    assert _deps(workspace) == {"A": ["C"], "B": ["A"], "C": []}
    assert "cycle" in caplog.text.lower()


# --- 4. Secondary ------------------------------------------------------------


def test_fenced_task_json_with_brackets_in_prose_parses(workspace):
    """The greedy bracket search spanned prose brackets around a fenced array
    and misreported valid JSON as truncated (#1293)."""
    task_list = [{"title": "Add search", "description": "d"}]
    provider = MockProvider()
    provider.add_text_response(
        f"Here are the tasks [2 of them]:\n```json\n{json.dumps(task_list)}\n```\nSee [docs]."
    )
    record = prd.store(workspace, "# P\n\nBuild it.\n")
    created = tasks.generate_from_prd(workspace, record, provider=provider)
    assert [t.title for t in created] == ["Add search"]


def test_a_ralph_item_checked_off_upstream_is_marked_done_on_reimport(tmp_path):
    from codeframe.core.importers.ralph import import_ralph_project

    root = tmp_path / "proj"
    (root / ".ralph").mkdir(parents=True)
    plan = root / ".ralph" / "fix_plan.md"
    plan.write_text("## Auth\n- [ ] Add login\n- [ ] Add logout\n")
    import_ralph_project(root)

    plan.write_text("## Auth\n- [x] Add login\n- [ ] Add logout\n")
    import_ralph_project(root)

    from codeframe.core.workspace import get_workspace

    status = {t.title: t.status for t in tasks.list_tasks(get_workspace(root))}
    assert status == {"Add login": TaskStatus.DONE, "Add logout": TaskStatus.READY}


@pytest.mark.parametrize("reply", [
    '[{"title": "Add search", "description": "d"}]\nThese are the tasks.',
    'Tasks [1 of them]:\n[{"title": "Add search", "description": "d"}]\nDone [ok].',
])
def test_task_json_with_prose_around_it_still_parses(workspace, reply):
    """Unfencing must not lose the old tolerance for an array with prose
    around it (codex review)."""
    provider = MockProvider()
    provider.add_text_response(reply)
    record = prd.store(workspace, "# P\n\nBuild it.\n")
    created = tasks.generate_from_prd(workspace, record, provider=provider)
    assert [t.title for t in created] == ["Add search"]


def test_a_decomposition_with_trailing_prose_parses():
    provider = MockProvider()
    provider.add_text_response('[{"title": "A"}, {"title": "B"}]\nThat should cover it.')
    assert [s["title"] for s in decompose_task(provider, "task", [])] == ["A", "B"]


def test_a_reimport_keeps_existing_duplicate_keys_and_completes_nothing_ambiguous(tmp_path):
    """A checked item followed by an unchecked duplicate: the key an earlier
    import gave the unchecked one must not change, or a re-import creates a
    second task and the completion pass marks the original DONE (codex review).
    The task is seeded with the key the pre-#1293 importer stored: checked
    items did not consume an ordinal, so the unchecked one got the bare key."""
    from codeframe.core.importers.ralph import _external_url, import_ralph_project
    from codeframe.core.workspace import get_workspace

    root = tmp_path / "proj"
    (root / ".ralph").mkdir(parents=True)
    (root / ".ralph" / "fix_plan.md").write_text("## Auth\n- [x] Add login\n- [ ] Add login\n")
    workspace = create_or_load_workspace(root)
    tasks.create(
        workspace, title="Add login", status=TaskStatus.READY,
        external_url=_external_url("Auth", "Add login", set()),
    )

    import_ralph_project(root)

    found = [(t.title, t.status) for t in tasks.list_tasks(get_workspace(root))]
    assert found == [("Add login", TaskStatus.READY)]
