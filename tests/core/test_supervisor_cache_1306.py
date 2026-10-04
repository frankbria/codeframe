"""The supervisor's decision cache answers only the blocker it was made for (#1306).

Keys came from substring tests ("pip" matched "pipeline"), the fallback hashed
only the first 50 characters, and the cache was process-global, so a decision
made for one workspace auto-answered an unrelated blocker in another.
"""

import pytest

from codeframe.core import blockers, conductor, tasks
from codeframe.core.conductor import SupervisorResolver
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture(autouse=True)
def _empty_cache(monkeypatch):
    monkeypatch.setattr(conductor, "_decision_cache", {})


def _resolver(ws, monkeypatch, *, classify="human"):
    r = SupervisorResolver(ws)
    monkeypatch.setattr(r, "_generate_tactical_resolution", lambda q: f"answer for {ws.repo_path.name}")
    monkeypatch.setattr(r, "_classify_with_supervision", lambda q: classify)
    return r


def _blocked(ws, question):
    task = tasks.create(ws, title="t")
    blockers.create(ws, question, task_id=task.id)
    return task.id


@pytest.mark.parametrize("question", [
    "Should the data pipeline run nightly?",       # not pip
    "Should the snapshot include the npmrc file?",  # not npm
])
def test_a_word_inside_another_word_is_not_a_cache_topic(question):
    assert SupervisorResolver._get_cache_key(None, question) != "package_manager"


def test_questions_sharing_an_opening_get_different_keys():
    opening = "Before I continue with the refactor of the billing module, "
    a = SupervisorResolver._get_cache_key(None, opening + "may I delete the legacy API?")
    b = SupervisorResolver._get_cache_key(None, opening + "which test runner do you prefer?")
    assert a != b


def test_a_decision_in_one_workspace_does_not_answer_another(tmp_path, monkeypatch):
    ws_a = create_or_load_workspace((tmp_path / "a").mkdir() or tmp_path / "a")
    ws_b = create_or_load_workspace((tmp_path / "b").mkdir() or tmp_path / "b")

    # Workspace A: tactical, answered and cached.
    assert _resolver(ws_a, monkeypatch).try_resolve_blocked_task(
        _blocked(ws_a, "Should I use pip or uv as the package manager?")
    )
    # Workspace B: same topic, but its own supervisor says a human must decide.
    # Same cache topic (package_manager), but not a tactical pattern.
    task_b = _blocked(ws_b, "Does the deploy image expect npm here?")
    assert not _resolver(ws_b, monkeypatch).try_resolve_blocked_task(task_b)
    assert blockers.list_all(ws_b, task_id=task_b, status=blockers.BlockerStatus.OPEN)
