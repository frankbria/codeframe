"""Batch status counts come from SQL, not from materializing 1000 batches (#902).

``GET /api/v2/batches`` called ``list_batches(limit=1000)`` purely to tally
statuses — building up to a thousand ``BatchRun`` objects and JSON-decoding each
one's ``task_ids`` and ``results`` — on every poll, from every open tab.
"""

import pytest

from codeframe.core import conductor

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_path = tmp_path / "ws"
    ws_path.mkdir()
    return create_or_load_workspace(ws_path)


def _batch(workspace, task_id: str, status: conductor.BatchStatus):
    from codeframe.core import tasks as tasks_mod

    original = tasks_mod.get
    tasks_mod.get = lambda ws, tid: object()
    try:
        batch = conductor.create_batch(workspace, task_ids=[task_id])
    finally:
        tasks_mod.get = original
    batch.status = status
    conductor._save_batch(workspace, batch)
    return batch


class TestCountBatchesByStatus:
    def test_counts_match_the_rows(self, workspace):
        _batch(workspace, "t1", conductor.BatchStatus.COMPLETED)
        _batch(workspace, "t2", conductor.BatchStatus.COMPLETED)
        _batch(workspace, "t3", conductor.BatchStatus.FAILED)

        counts = conductor.count_batches_by_status(workspace)

        assert counts == {"COMPLETED": 2, "FAILED": 1}

    def test_empty_workspace_returns_empty(self, workspace):
        assert conductor.count_batches_by_status(workspace) == {}

    def test_counts_every_batch_not_just_a_page(self, workspace):
        """The old tally was capped at limit=1000; this is a plain aggregate."""
        for i in range(25):
            _batch(workspace, f"t{i}", conductor.BatchStatus.COMPLETED)

        counts = conductor.count_batches_by_status(workspace)

        assert counts == {"COMPLETED": 25}

    def test_does_not_materialize_batch_objects(self, workspace, monkeypatch):
        """The regression this guards: tallying via list_batches."""
        for i in range(5):
            _batch(workspace, f"t{i}", conductor.BatchStatus.COMPLETED)

        def _boom(*a, **kw):
            raise AssertionError("count must not go through list_batches")

        monkeypatch.setattr(conductor, "list_batches", _boom)

        assert conductor.count_batches_by_status(workspace) == {"COMPLETED": 5}
