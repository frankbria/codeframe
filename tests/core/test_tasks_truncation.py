"""Regression tests for #743 — CLI task resolution/listing truncated at 100.

`list_tasks` defaulted to ``limit=100`` and the CLI resolved id-prefixes in
Python over that truncated, ``priority ASC`` ordered list, so any task beyond
the first 100 was unreachable by ``cf work start/stop/resume/diagnose``,
invisible in ``tasks list``, and skipped by bulk updates.

Fix: a SQL ``LIKE 'prefix%'`` lookup (`find_by_prefix`) that bypasses the cap
for resolution, and an opt-in unbounded ``limit=None`` for listing/bulk ops.
"""

import pytest

from codeframe.core import tasks
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def many_tasks(workspace):
    """150 tasks with ascending priority so the 101st+ sort *after* the cap.

    ``list_tasks`` orders by ``priority ASC``; giving each task a distinct,
    increasing priority guarantees the last-created tasks are exactly the ones
    a ``LIMIT 100`` would drop.
    """
    created = [
        tasks.create(workspace, title=f"task {i}", priority=i) for i in range(150)
    ]
    return workspace, created


class TestResolutionBypassesLimit:
    def test_find_by_prefix_resolves_task_beyond_first_100(self, many_tasks):
        """AC1: a task sorted past position 100 is still resolvable by prefix."""
        workspace, created = many_tasks
        target = created[149]  # highest priority → last in ORDER BY, dropped by cap

        matches = tasks.find_by_prefix(workspace, target.id[:8])

        assert [t.id for t in matches] == [target.id]

    def test_find_by_prefix_returns_all_ambiguous_matches(self, workspace):
        """Ambiguity detection still works — callers report >1 match."""
        a = tasks.create(workspace, title="a")
        b = tasks.create(workspace, title="b")
        # Empty prefix matches every id (LIKE '%'), so ambiguity is guaranteed
        # rather than left to a ~1/16 first-hex-char collision.
        matches = tasks.find_by_prefix(workspace, "")
        ids = {t.id for t in matches}
        assert a.id in ids and b.id in ids

    def test_find_by_prefix_no_match_returns_empty(self, workspace):
        tasks.create(workspace, title="x")
        assert tasks.find_by_prefix(workspace, "zzzzzzzz-nope") == []

    def test_find_by_prefix_escapes_like_wildcards(self, workspace):
        """A user-typed prefix containing LIKE metachars must not over-match.

        Task IDs are UUIDs (never contain ``_``/``%``), so a prefix with a raw
        wildcard should match nothing rather than every task.
        """
        tasks.create(workspace, title="one")
        tasks.create(workspace, title="two")
        assert tasks.find_by_prefix(workspace, "%") == []
        assert tasks.find_by_prefix(workspace, "_") == []


class TestListingRespectsLimit:
    def test_default_limit_still_caps_at_100(self, many_tasks):
        """Backward-compat: the default cap is unchanged (API pagination relies on it)."""
        workspace, _ = many_tasks
        assert len(tasks.list_tasks(workspace)) == 100

    def test_limit_none_returns_all_tasks(self, many_tasks):
        """AC2: unbounded listing sees every task so counts/bulk ops are complete."""
        workspace, created = many_tasks
        listed = tasks.list_tasks(workspace, limit=None)
        assert len(listed) == len(created) == 150

    def test_limit_none_with_status_filter(self, workspace):
        for i in range(120):
            tasks.create(workspace, title=f"t{i}", priority=i)
        from codeframe.core.state_machine import TaskStatus

        listed = tasks.list_tasks(workspace, status=TaskStatus.BACKLOG, limit=None)
        assert len(listed) == 120
