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


def _refine(reply: LLMResponse, original: str = _PRD) -> str:
    from codeframe.core.prd_stress_test import Ambiguity, resolve_ambiguities_into_prd

    provider = MockProvider()
    provider.add_response(reply)
    amb = Ambiguity(
        id="amb-1", label="Sort order", questions=["Which order?"], source_node_title="Search",
        recommendation="", severity="blocking", resolved_answer="By relevance",
    )
    return resolve_ambiguities_into_prd(original, [amb], provider)


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


def test_a_wrapped_refine_is_rejected(caplog):
    """A reply wrapped in a fence (with or without a preamble) was stored
    verbatim as the new PRD. It is rejected, as the AC says: unwrapping it
    cannot be done safely, because a real PRD with code blocks at both ends
    has the same shape (#1293 reviews), and rejecting keeps the original."""
    body = _PRD.replace("date", "relevance") + "\n```python\nsearch(q)\n```\n"
    reply = f"Here is the updated PRD:\n\n```markdown\n{body}```\n"
    with caplog.at_level(logging.WARNING):
        result = _refine(LLMResponse(content=reply, stop_reason="end_turn"))
    assert result == _PRD
    assert "fence" in caplog.text


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


@pytest.mark.parametrize("reply", ["Not atomic", "non-atomic", "This is not atomic."])
def test_a_negated_atomic_is_composite(reply):
    """`\\b` matched 'atomic' inside 'not atomic' / 'non-atomic' (review)."""
    provider = MockProvider()
    provider.add_text_response(reply)
    assert classify_task(provider, "task", []) == "composite"


def test_a_prd_that_opens_and_ends_with_code_blocks_is_not_unwrapped():
    """A title plus an untagged opening block read as preamble + outer fence,
    so the title and the first/last fences were stripped and the
    unbalanced remainder stored (review)."""
    body = (
        "# Search\n\n```\nproj/\n  src/\n```\n\n"
        + "Results are sorted by relevance. " * 40
        + "\n\n## API\n\n```\nGET /search?q=x\n```"
    )
    # The PRD itself has this shape; its refined echo is stored as returned.
    result = _refine(LLMResponse(content=body, stop_reason="end_turn"), original=body.replace("relevance", "date").replace("markdown. ", "markdown! "))
    assert result == body.strip()


def test_a_blocked_task_with_an_active_run_is_left_alone(tmp_path, monkeypatch):
    """Walking it to DONE left its run BLOCKED and its blocker open against a
    finished task (review)."""
    from codeframe.core import runtime
    from codeframe.core.importers.ralph import import_ralph_project
    from codeframe.core.workspace import get_workspace

    root = tmp_path / "proj"
    (root / ".ralph").mkdir(parents=True)
    plan = root / ".ralph" / "fix_plan.md"
    plan.write_text("## Auth\n- [ ] Add login\n")
    import_ralph_project(root)
    ws = get_workspace(root)
    (task,) = tasks.list_tasks(ws)
    tasks.update_status(ws, task.id, TaskStatus.IN_PROGRESS)
    tasks.update_status(ws, task.id, TaskStatus.BLOCKED)
    monkeypatch.setattr(runtime, "get_active_run", lambda w, tid: object() if tid == task.id else None)

    plan.write_text("## Auth\n- [x] Add login\n")
    report = import_ralph_project(root)

    assert tasks.get(ws, task.id).status == TaskStatus.BLOCKED
    assert any("run is active" in s["reason"] for s in report.tasks_skipped)


def test_a_prd_opening_with_plain_text_and_a_code_block_is_not_unwrapped():
    """Same shape without a heading: the inner text holds one closer and one
    opener, so it is fence-balanced and only the untagged-fence rule stops it."""
    body = (
        "Search service\n\n```\nproj/\n  src/\n```\n\n"
        + "Results are sorted by relevance. " * 40
        + "\n\n```\nGET /search?q=x\n```"
    )
    # The PRD itself has this shape; its refined echo is stored as returned.
    result = _refine(LLMResponse(content=body, stop_reason="end_turn"), original=body.replace("relevance", "date").replace("markdown. ", "markdown! "))
    assert result == body.strip()


def test_an_untagged_wrapper_is_rejected_too():
    body = _PRD.replace("date", "relevance").strip()
    reply = f"Updated PRD:\n```\n{body}\n```"
    assert _refine(LLMResponse(content=reply, stop_reason="end_turn")) == _PRD


def test_a_titled_prd_with_markdown_example_blocks_is_not_unwrapped():
    """Tagged blocks balance inside, so only the no-heading-in-preamble rule
    keeps the title from being read as preamble and dropped."""
    body = (
        "# Docs site\n\n```markdown\n# Example page\n```\n\n"
        + "Pages render from markdown. " * 40
        + "\n\n```markdown\n## Another example\n```"
    )
    # The PRD itself has this shape; its refined echo is stored as returned.
    result = _refine(LLMResponse(content=body, stop_reason="end_turn"), original=body.replace("relevance", "date").replace("markdown. ", "markdown! "))
    assert result == body.strip()


@pytest.mark.parametrize("reply", ["Not composite", "non-composite", "This is not composite."])
def test_a_negated_composite_is_atomic(reply):
    """The mirror case: matching the word alone read these as composite (codex)."""
    provider = MockProvider()
    provider.add_text_response(reply)
    assert classify_task(provider, "task", []) == "atomic"


def test_a_prd_echoed_with_a_tagged_example_block_first_is_not_unwrapped():
    """The tagged twin of the plain-text-first case (GLM review): its inner
    fences balance, so only "the reply opens like the PRD itself" tells an
    echoed PRD from a wrapper."""
    body = (
        "My Project\n\n```markdown\n# Example page\n```\n\n"
        + "Results are sorted by date. " * 40
        + "\n\n```\nGET /search?q=x\n```"
    )
    from codeframe.core.prd_stress_test import Ambiguity, resolve_ambiguities_into_prd

    provider = MockProvider()
    edited = body.replace("date", "relevance")
    provider.add_response(LLMResponse(content=edited, stop_reason="end_turn"))
    amb = Ambiguity(id="a", label="Sort", source_node_title="S", questions=["?"],
                    recommendation="", severity="blocking", resolved_answer="relevance")
    assert resolve_ambiguities_into_prd(body, [amb], provider) == edited.strip()


def _task_generation_error(workspace, reply: LLMResponse) -> str:
    provider = MockProvider()
    provider.add_response(reply)
    record = prd.store(workspace, "# P\n\nBuild it.\n")
    with pytest.raises(tasks.TaskGenerationError) as exc:
        tasks.generate_from_prd(workspace, record, provider=provider)
    return str(exc.value)


def test_a_truncated_task_reply_is_called_truncated_even_if_an_inner_array_decodes(workspace):
    """Cut at max_tokens after one task, the first complete array is that
    task's files_to_modify list, so truncation read as "no usable tasks" (GLM)."""
    cut = '[{"title": "A", "description": "a", "files_to_modify": ["src/a.py", "src/b.py"]}, {"title": "B", "files_to_mod'
    message = _task_generation_error(workspace, LLMResponse(content=cut, stop_reason="max_tokens"))
    assert "truncated" in message


def test_valid_json_that_is_not_an_array_says_so(workspace):
    """{"status": ...} has no '[', and was misreported as truncated (claude-review)."""
    message = _task_generation_error(
        workspace, LLMResponse(content='{"status": "no tasks needed"}', stop_reason="end_turn")
    )
    assert "did not return a JSON array" in message and "truncated" not in message


def test_a_wrapper_preamble_glued_to_an_echoed_prd_is_not_unwrapped():
    """One preamble line with no blank before the echoed PRD (GLM review):
    the first-line echo guard misses it; the payload must start like the PRD."""
    body = (
        "My Project\n\n```markdown\n# Example page\n```\n\n"
        + "Results are sorted by date. " * 40
        + "\n\n```\nGET /search?q=x\n```"
    )
    from codeframe.core.prd_stress_test import Ambiguity, resolve_ambiguities_into_prd

    provider = MockProvider()
    edited = body.replace("date", "relevance")
    provider.add_response(LLMResponse(content="Here is the updated PRD:\n" + edited, stop_reason="end_turn"))
    amb = Ambiguity(id="a", label="Sort", source_node_title="S", questions=["?"],
                    recommendation="", severity="blocking", resolved_answer="relevance")
    stored = resolve_ambiguities_into_prd(body, [amb], provider)
    assert "My Project" in stored and "```markdown\n# Example page\n```" in stored


def test_fenced_task_json_with_a_code_example_in_a_description_parses(workspace):
    """strip_code_fence stopped at the backticks inside a JSON string (codex)."""
    task_list = [{"title": "Add search", "description": "Call it like:\n```python\nsearch(q)\n```"}]
    provider = MockProvider()
    provider.add_text_response(f"```json\n{json.dumps(task_list)}\n```")
    record = prd.store(workspace, "# P\n\nBuild it.\n")
    created = tasks.generate_from_prd(workspace, record, provider=provider)
    assert [t.title for t in created] == ["Add search"]
    assert "search(q)" in created[0].description



def test_a_prd_whose_first_block_repeats_its_title_is_stored_as_is():
    """GLM review: a doc-by-example PRD whose first fenced block starts with the
    PRD's own title. A PRD that already has a wrapper's shape is stored as the
    model returned it, never unwrapped and never rejected."""
    body = (
        "# Contributing Guide\n\n```markdown\n# Contributing Guide\n\nBody.\n```\n\n"
        + "## Requirements\n" + "Run the tests before pushing. " * 40
        + "\n\n```bash\nmake test\n```"
    )
    from codeframe.core.prd_stress_test import Ambiguity, resolve_ambiguities_into_prd

    provider = MockProvider()
    edited = body.replace("pushing", "opening a PR")
    provider.add_response(LLMResponse(content=edited, stop_reason="end_turn"))
    amb = Ambiguity(id="a", label="When", source_node_title="S", questions=["?"],
                    recommendation="", severity="blocking", resolved_answer="before a PR")
    assert resolve_ambiguities_into_prd(body, [amb], provider) == edited.strip()


def test_an_incomplete_outer_array_is_not_rescued_by_a_nested_one():
    """codex: '[{"title":"Parent","children":[{"title":"Child"}]},' returned only
    Child. A '[' after ':' / ',' / '[' is a nested value, never a candidate."""
    from codeframe.core.llm_json import LLMJsonError, extract_json_array

    with pytest.raises(LLMJsonError):
        extract_json_array('[{"title":"Parent","children":[{"title":"Child"}]},')


def test_a_prose_array_of_scalars_does_not_shadow_the_real_one():
    """GLM: 'Tasks [1]:' decoded as [1] and was returned before the fenced array."""
    from codeframe.core.llm_json import extract_json_array

    reply = 'Tasks [1]:\n```json\n[{"title": "A", "description": "d"}]\n```'
    assert extract_json_array(reply) == [{"title": "A", "description": "d"}]


def test_a_truncated_array_starting_with_a_scalar_is_not_rescued_either():
    """codex: '[null, {...,"children":[{"title":"Child"}]},' returned Child. The
    decoder failing at the end of the text means the outer array is cut off,
    whatever its first element, so everything after it is inside it."""
    from codeframe.core.llm_json import LLMJsonError, extract_json_array

    with pytest.raises(LLMJsonError):
        extract_json_array('[null, {"title":"Parent","children":[{"title":"Child"}]},')


def test_an_empty_prose_array_does_not_shadow_the_real_one():
    """GLM: 'No setup needed: []' returned [] before the real array."""
    from codeframe.core.llm_json import extract_json_array

    reply = 'No setup needed: []\n\n[{"title": "A", "description": "d"}]'
    assert extract_json_array(reply) == [{"title": "A", "description": "d"}]


def test_an_empty_array_alone_is_still_returned():
    from codeframe.core.llm_json import extract_json_array

    assert extract_json_array("No tasks: []") == []


def test_a_malformed_object_array_placeholder_is_rejected_not_guessed_past():
    """A '[ {...} ]' placeholder before the real array is rejected: an array of
    objects that fails mid-text cannot be told from a malformed result, and a
    loud, retryable error beats silently picking a later array. Known
    limitation, kept deliberately (GLM review)."""
    from codeframe.core.llm_json import LLMJsonError, extract_json_array

    with pytest.raises(LLMJsonError):
        extract_json_array('Shape: [ {"title": "...", "deps": [...]} ]\n\n[{"title": "A"}]')


def test_a_decoded_arrays_nested_arrays_are_never_candidates():
    """[1, [{"title": "x"}]] is skipped as a scalar-led list; scanning resumes
    after it, so its nested object array is not returned as the result."""
    from codeframe.core.llm_json import LLMJsonError, extract_json_array

    with pytest.raises(LLMJsonError):
        extract_json_array('[1, [{"title": "x"}]]')


def test_a_failed_container_past_its_first_element_is_not_rescued():
    """codex: '[null, undefined, {..."children":[{"title":"Child"}]}]' failed
    mid-text after an element, so it is a JSON container, not prose; resuming
    inside it returned the nested child."""
    from codeframe.core.llm_json import LLMJsonError, extract_json_array

    with pytest.raises(LLMJsonError):
        extract_json_array('[null, undefined, {"title":"Parent","children":[{"title":"Child"}]}]')


@pytest.mark.parametrize("prose", ["[2 of them]", "[see a, b]", "[ok]"])
def test_prose_brackets_before_the_array_are_still_skipped(prose):
    from codeframe.core.llm_json import extract_json_array

    assert extract_json_array(f'Tasks {prose}:\n[{{"title": "A"}}]') == [{"title": "A"}]
