"""Tests for proof runner config integration (issue #556).

The runner must:
- Load `.codeframe/proof_config.json` if present
- Filter obligations by `enabled_gates`
- Respect `strictness` setting: in 'warn' mode, gate failures should not flip
  overall_passed; in 'strict' mode, behavior is unchanged
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core.proof.ledger import get_run, init_proof_tables, save_requirement
from codeframe.core.proof.models import (
    PROOF_CONFIG_FILENAME,
    Gate,
    Obligation,
    Requirement,
    RequirementScope,
    ReqStatus,
    Severity,
    Source,
)
from codeframe.core.proof.runner import run_proof
from codeframe.core.workspace import Workspace, create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    ws = create_or_load_workspace(tmp_path)
    init_proof_tables(ws)
    return ws


def _make_req(req_id: str, gates: list[Gate]) -> Requirement:
    return Requirement(
        id=req_id,
        title=f"Test {req_id}",
        description="test",
        severity=Severity.MEDIUM,
        source=Source.QA,
        scope=RequirementScope(files=["x.py"]),
        obligations=[Obligation(gate=g) for g in gates],
        evidence_rules=[],
        status=ReqStatus.OPEN,
        created_at=datetime.now(timezone.utc),
    )


class TestRunnerEnabledGatesFilter:
    """The runner must skip obligations whose gate is not in enabled_gates."""

    def test_filters_disabled_gates(self, workspace):
        """A gate disabled in proof_config.json must not run."""
        save_requirement(workspace, _make_req("REQ-0001", [Gate.UNIT, Gate.SEC]))

        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            json.dumps({"enabled_gates": ["unit"], "strictness": "strict"})
        )

        # Patch _run_gate so we can see which gates were invoked
        with patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(True, ""),
        ) as mock_gate:
            run_proof(workspace, full=True)

        invoked_gates = [call.args[1] for call in mock_gate.call_args_list]
        assert Gate.UNIT in invoked_gates
        assert Gate.SEC not in invoked_gates

    def test_all_gates_run_when_no_config(self, workspace):
        """With no proof_config.json, behavior is unchanged — all gates run."""
        save_requirement(workspace, _make_req("REQ-0002", [Gate.UNIT, Gate.SEC]))

        with patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(True, ""),
        ) as mock_gate:
            run_proof(workspace, full=True)

        invoked_gates = [call.args[1] for call in mock_gate.call_args_list]
        assert Gate.UNIT in invoked_gates
        assert Gate.SEC in invoked_gates


class TestEmptyEnabledGates:
    """Documents the empty-gates behavior: nothing runs, overall_passed=True,
    and a warning is logged."""

    def test_empty_enabled_gates_vacuous_pass(self, workspace, caplog):
        save_requirement(workspace, _make_req("REQ-EMPTY", [Gate.UNIT, Gate.SEC]))
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            json.dumps({"enabled_gates": [], "strictness": "strict"})
        )

        with caplog.at_level(logging.WARNING, logger="codeframe.core.proof.runner"), patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(True, ""),
        ) as mock_gate:
            run_proof(workspace, full=True, run_id="empty-gates")

        # Nothing executed
        mock_gate.assert_not_called()

        # Run records as passing (vacuously)
        run = get_run(workspace, "empty-gates")
        assert run is not None
        assert run.overall_passed is True

        # Warning was emitted
        assert any("vacuously" in r.message for r in caplog.records)


class TestRunnerStrictness:
    """In 'warn' mode the run's overall_passed must remain True on failure."""

    def test_strict_mode_propagates_failure(self, workspace):
        """In strict mode (default), a failing gate flips overall_passed to False."""
        save_requirement(workspace, _make_req("REQ-0003", [Gate.UNIT]))
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            json.dumps({"enabled_gates": ["unit"], "strictness": "strict"})
        )

        with patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(False, "boom"),
        ):
            run_proof(workspace, full=True, run_id="strict-run")

        # Inspect the persisted run record
        run = get_run(workspace, "strict-run")
        assert run is not None
        assert run.overall_passed is False

    def test_warn_mode_keeps_overall_passed(self, workspace):
        """In warn mode, a failing gate does NOT flip overall_passed."""
        save_requirement(workspace, _make_req("REQ-0004", [Gate.UNIT]))
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            json.dumps({"enabled_gates": ["unit"], "strictness": "warn"})
        )

        with patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(False, "boom"),
        ):
            run_proof(workspace, full=True, run_id="warn-run")

        run = get_run(workspace, "warn-run")
        assert run is not None
        assert run.overall_passed is True
