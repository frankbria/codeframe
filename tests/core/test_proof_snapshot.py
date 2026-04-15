"""Tests for pr_proof_snapshots ledger functions.

Verifies save_pr_proof_snapshot and get_pr_proof_snapshot work correctly
with the SQLite-backed proof ledger.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_ws"
    workspace_path.mkdir(parents=True, exist_ok=True)

    workspace = create_or_load_workspace(workspace_path)

    yield workspace

    shutil.rmtree(temp_dir, ignore_errors=True)


class TestPrProofSnapshot:
    """Tests for save/get pr_proof_snapshot functions."""

    def test_save_and_get_snapshot(self, test_workspace):
        """Save a snapshot, retrieve it, verify all fields."""
        from codeframe.core.proof.ledger import (
            init_proof_tables,
            save_pr_proof_snapshot,
            get_pr_proof_snapshot,
        )

        init_proof_tables(test_workspace)

        gate_breakdown = [
            {"gate": "unit_test", "status": "satisfied"},
            {"gate": "lint", "status": "failed"},
        ]
        save_pr_proof_snapshot(
            test_workspace,
            pr_number=42,
            gates_passed=1,
            gates_total=2,
            gate_breakdown=gate_breakdown,
        )

        result = get_pr_proof_snapshot(test_workspace, 42)

        assert result is not None
        assert result["pr_number"] == 42
        assert result["gates_passed"] == 1
        assert result["gates_total"] == 2
        assert result["gate_breakdown"] == gate_breakdown
        assert "snapshotted_at" in result

    def test_get_nonexistent_snapshot_returns_none(self, test_workspace):
        """Getting a snapshot for a non-existent PR returns None."""
        from codeframe.core.proof.ledger import (
            init_proof_tables,
            get_pr_proof_snapshot,
        )

        init_proof_tables(test_workspace)

        result = get_pr_proof_snapshot(test_workspace, 9999)
        assert result is None

    def test_snapshot_overwrites_on_same_pr_number(self, test_workspace):
        """Saving a snapshot for the same PR overwrites the previous one."""
        from codeframe.core.proof.ledger import (
            init_proof_tables,
            save_pr_proof_snapshot,
            get_pr_proof_snapshot,
        )

        init_proof_tables(test_workspace)

        save_pr_proof_snapshot(
            test_workspace,
            pr_number=10,
            gates_passed=3,
            gates_total=5,
            gate_breakdown=[{"gate": "unit_test", "status": "satisfied"}],
        )

        save_pr_proof_snapshot(
            test_workspace,
            pr_number=10,
            gates_passed=5,
            gates_total=5,
            gate_breakdown=[
                {"gate": "unit_test", "status": "satisfied"},
                {"gate": "lint", "status": "satisfied"},
            ],
        )

        result = get_pr_proof_snapshot(test_workspace, 10)
        assert result is not None
        assert result["gates_passed"] == 5
        assert result["gates_total"] == 5
        assert len(result["gate_breakdown"]) == 2
