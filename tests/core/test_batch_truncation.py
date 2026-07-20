"""Regression tests for #825 — CLI batch resolution truncated at 100.

The four ``cf work batch status/stop/resume/follow`` commands resolved a
partial batch id in Python over ``conductor.list_batches(workspace, limit=100)``,
so any batch beyond the first 100 was unreachable — the same class of bug as
#743 for tasks.

Fix: a SQL ``LIKE 'prefix%'`` lookup (``find_batch_by_prefix``) that bypasses
the cap, mirroring ``tasks.find_by_prefix``.
"""

import uuid
from datetime import datetime, timezone

import pytest

from codeframe.core import conductor
from codeframe.core.conductor import (
    BatchRun,
    BatchStatus,
    OnFailure,
    _save_batch,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_batch(workspace, *, status: BatchStatus = BatchStatus.PENDING) -> BatchRun:
    """Insert a minimal BatchRun directly without spawning real workers."""
    batch = BatchRun(
        id=str(uuid.uuid4()),
        workspace_id=workspace.id,
        task_ids=[],
        status=status,
        strategy="serial",
        max_parallel=1,
        on_failure=OnFailure.CONTINUE,
        started_at=_utc_now(),
        completed_at=None,
    )
    _save_batch(workspace, batch)
    return batch


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def many_batches(workspace):
    """150 batches — more than the old hard limit of 100."""
    created = [_make_batch(workspace) for _ in range(150)]
    return workspace, created


class TestFindBatchByPrefixResolvesBeyon100:
    def test_resolves_batch_beyond_first_100(self, many_batches):
        """AC1: a batch sorted past position 100 is resolvable by prefix."""
        workspace, created = many_batches
        # list_batches is newest-first; oldest batches (earliest indices) are
        # the ones a LIMIT 100 would drop from the top-100 window.
        target = created[0]

        matches = conductor.find_batch_by_prefix(workspace, target.id[:8])

        assert [b.id for b in matches] == [target.id]

    def test_exact_full_id_resolves(self, workspace):
        """A full UUID prefix still resolves correctly."""
        batch = _make_batch(workspace)
        matches = conductor.find_batch_by_prefix(workspace, batch.id)
        assert len(matches) == 1
        assert matches[0].id == batch.id

    def test_no_match_returns_empty(self, workspace):
        _make_batch(workspace)
        assert conductor.find_batch_by_prefix(workspace, "zzzzzzzz-nope") == []

    def test_ambiguous_prefix_returns_multiple(self, workspace):
        """Empty prefix (or shared prefix) returns all matching batches."""
        a = _make_batch(workspace)
        b = _make_batch(workspace)
        # Empty prefix → LIKE '%' → matches everything
        matches = conductor.find_batch_by_prefix(workspace, "")
        ids = {m.id for m in matches}
        assert a.id in ids and b.id in ids

    def test_like_metachar_prefix_does_not_over_match(self, workspace):
        """A user-typed prefix with LIKE wildcards must not over-match.

        Batch IDs are UUIDs (never contain ``_``/``%``), so a prefix that is
        only a wildcard should match nothing rather than every batch.
        """
        _make_batch(workspace)
        _make_batch(workspace)
        assert conductor.find_batch_by_prefix(workspace, "%") == []
        assert conductor.find_batch_by_prefix(workspace, "_") == []

    def test_backslash_in_prefix_does_not_crash(self, workspace):
        """A backslash in the prefix is escaped and returns empty (no UUID match)."""
        _make_batch(workspace)
        assert conductor.find_batch_by_prefix(workspace, "\\") == []
