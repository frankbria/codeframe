"""Tests for SQL-side token_usage aggregation + streaming export (issue #752 / P2.3).

Before the fix, `cf stats` pulled the whole `token_usage` table into Python and
aggregated with for-loops (`get_workspace_token_usage` → SELECT * → sum in
Python). These tests lock in that:

1. `get_costs_by_model()` pushes the per-model rollup into SQL (SUM/GROUP BY),
   honours the [start, end] window, and orders by cost DESC.
2. `get_token_usage_iter()` is a lazy generator (streams rows) and honours
   the same window.
3. `MetricsTracker.get_workspace_costs()` derives its totals from the SQL rollup.
4. `export_to_csv` / `export_to_json` consume an iterator (no full-table list),
   return the row count, and JSON round-trips.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import GeneratorType

import pytest

from codeframe.core.models import CallType, TokenUsage
from codeframe.core.workspace import create_or_load_workspace
from codeframe.lib.metrics_tracker import MetricsTracker
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


def _mk(db: Database, *, model: str, inp: int, out: int, cost: float, ts: datetime,
        task_id: str = "t1", agent_id: str = "a1") -> None:
    db.save_token_usage(
        TokenUsage(
            task_id=task_id,
            agent_id=agent_id,
            project_id=0,
            model_name=model,
            input_tokens=inp,
            output_tokens=out,
            estimated_cost_usd=cost,
            call_type=CallType.TASK_EXECUTION,
            timestamp=ts,
        )
    )


@pytest.fixture
def db(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    ws = create_or_load_workspace(repo)
    database = Database(str(ws.db_path))
    database.initialize()
    now = datetime.now(timezone.utc)
    # Two models, three records; one record 10 days old for window tests.
    _mk(database, model="claude-sonnet-4-5", inp=100, out=50, cost=0.01, ts=now)
    _mk(database, model="claude-sonnet-4-5", inp=200, out=100, cost=0.02, ts=now)
    _mk(database, model="gpt-4o", inp=1000, out=500, cost=0.50, ts=now - timedelta(days=10))
    yield database
    database.close()


class TestGetCostsByModel:
    def test_groups_and_sums_per_model(self, db: Database):
        rows = db.get_costs_by_model()
        by_model = {r["model_name"]: r for r in rows}

        assert by_model["claude-sonnet-4-5"]["input_tokens"] == 300
        assert by_model["claude-sonnet-4-5"]["output_tokens"] == 150
        assert by_model["claude-sonnet-4-5"]["call_count"] == 2
        assert by_model["claude-sonnet-4-5"]["total_cost_usd"] == pytest.approx(0.03)

        assert by_model["gpt-4o"]["input_tokens"] == 1000
        assert by_model["gpt-4o"]["call_count"] == 1

    def test_ordered_by_cost_desc(self, db: Database):
        rows = db.get_costs_by_model()
        costs = [r["total_cost_usd"] for r in rows]
        assert costs == sorted(costs, reverse=True)
        assert rows[0]["model_name"] == "gpt-4o"  # 0.50 > 0.03

    def test_window_excludes_old_records(self, db: Database):
        start = datetime.now(timezone.utc) - timedelta(days=1)
        rows = db.get_costs_by_model(start_date=start)
        models = {r["model_name"] for r in rows}
        assert models == {"claude-sonnet-4-5"}  # the 10-day-old gpt-4o row is out

    def test_empty_window_returns_empty(self, db: Database):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        assert db.get_costs_by_model(start_date=future) == []


class TestStreamingIterator:
    def test_is_a_generator(self, db: Database):
        it = db.get_token_usage_iter()
        assert isinstance(it, GeneratorType)

    def test_yields_all_rows(self, db: Database):
        rows = list(db.get_token_usage_iter())
        assert len(rows) == 3
        assert all("model_name" in r for r in rows)

    def test_window_filters(self, db: Database):
        start = datetime.now(timezone.utc) - timedelta(days=1)
        rows = list(db.get_token_usage_iter(start_date=start))
        assert len(rows) == 2  # old gpt-4o excluded


class TestWorkspaceCostsTotals:
    def test_totals_match_sql_rollup(self, db: Database):
        tracker = MetricsTracker(db=db)
        result = tracker.get_workspace_costs()
        # 0.01 + 0.02 + 0.50
        assert result["total_cost_usd"] == pytest.approx(0.53)
        # (100+50)+(200+100)+(1000+500)
        assert result["total_tokens"] == 1950
        assert result["total_calls"] == 3

    def test_totals_honour_window(self, db: Database):
        tracker = MetricsTracker(db=db)
        start = datetime.now(timezone.utc) - timedelta(days=1)
        result = tracker.get_workspace_costs(start_date=start)
        assert result["total_cost_usd"] == pytest.approx(0.03)
        assert result["total_calls"] == 2


class TestStreamingExport:
    def test_csv_streams_iterator_and_counts(self, db: Database, tmp_path: Path):
        out = tmp_path / "out.csv"
        n = MetricsTracker.export_to_csv(db.get_token_usage_iter(), str(out))
        assert n == 3
        lines = out.read_text().strip().splitlines()
        assert len(lines) == 4  # header + 3 rows

    def test_json_streams_and_roundtrips(self, db: Database, tmp_path: Path):
        out = tmp_path / "out.json"
        n = MetricsTracker.export_to_json(db.get_token_usage_iter(), str(out))
        assert n == 3
        data = json.loads(out.read_text())
        assert data["metadata"]["record_count"] == 3
        assert len(data["records"]) == 3

    def test_json_empty_records_is_valid_json(self, tmp_path: Path):
        out = tmp_path / "empty.json"
        n = MetricsTracker.export_to_json(iter([]), str(out))
        assert n == 0
        data = json.loads(out.read_text())  # must not raise
        assert data["records"] == []
        assert data["metadata"]["record_count"] == 0

    def test_mid_stream_failure_leaves_no_partial_file(self, tmp_path: Path):
        out = tmp_path / "partial.csv"

        def boom():
            yield {"id": 1, "input_tokens": 1, "output_tokens": 1}
            raise RuntimeError("source blew up mid-stream")

        with pytest.raises(RuntimeError):
            MetricsTracker.export_to_csv(boom(), str(out))
        # Atomic write: the destination must not exist, and no temp junk remains.
        assert not out.exists()
        assert list(tmp_path.iterdir()) == []
