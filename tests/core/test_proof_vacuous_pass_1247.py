"""`vacuous_pass` — a clean pass that verified nothing (#1247 AC2).

`overall_passed` conflated two very different outcomes: every gate ran and
passed, and *no gate ran at all*. The second is what `proof_config.json` with
`enabled_gates: []` produces, and it rendered in the run history as an ordinary
green pass.

The flag is deliberately computed as "passed, but nothing executed" rather than
by inspecting the config, so it also catches the runs that reach the same
dishonest state by another route — see `TestVacuousPassDefinition`.

Note this does *not* change the merge gate. A vacuous run leaves its
requirements OPEN (`runner.py`'s `if req_results:` guard never fires), so
`list_blocking_requirements` already blocks them on requirement status. The
defect being fixed here is a reporting one.
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
    GateOutcome,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
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


def _write_config(workspace: Workspace, **config) -> None:
    (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(json.dumps(config))


class TestVacuousPassDefinition:
    def test_all_gates_disabled_is_vacuous(self, workspace):
        """AC2: the case the issue names."""
        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT, Gate.SEC]))
        _write_config(workspace, enabled_gates=[], strictness="strict")

        with patch(
            "codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "")
        ) as mock_gate:
            run_proof(workspace, full=True, run_id="all-disabled")

        mock_gate.assert_not_called()
        run = get_run(workspace, "all-disabled")
        assert run.overall_passed is True
        assert run.vacuous_pass is True

    def test_real_pass_is_not_vacuous(self, workspace):
        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT]))

        with patch(
            "codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "")
        ):
            run_proof(workspace, full=True, run_id="real-pass")

        run = get_run(workspace, "real-pass")
        assert run.overall_passed is True
        assert run.vacuous_pass is False

    def test_real_failure_is_not_vacuous(self, workspace):
        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT]))

        with patch(
            "codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.FAILED, "boom")
        ):
            run_proof(workspace, full=True, run_id="real-fail")

        run = get_run(workspace, "real-fail")
        assert run.overall_passed is False
        assert run.vacuous_pass is False

    def test_warn_mode_masking_a_failure_is_not_vacuous(self, workspace):
        """warn-mode forces overall_passed=True, but gates did run.

        Dishonest in its own way, but not *this* way — conflating the two would
        make the flag mean "we don't trust this result" instead of "nothing was
        verified", and the run history needs to tell them apart.
        """
        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT]))
        _write_config(workspace, enabled_gates=[g.value for g in Gate], strictness="warn")

        with patch(
            "codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.FAILED, "boom")
        ):
            run_proof(workspace, full=True, run_id="warn-masked")

        run = get_run(workspace, "warn-masked")
        assert run.overall_passed is True
        assert run.vacuous_pass is False

    def test_only_unverifiable_outcomes_is_vacuous(self, workspace):
        """A run that could verify nothing passes — and says so.

        Broader than the issue's wording, which names only the disabled-gates
        config. The condition that matters is "passed having executed nothing",
        and an all-UNVERIFIABLE run is exactly that: `executed` filters
        UNVERIFIABLE out, so overall_passed lands True on an empty tally.
        """
        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT]))

        with patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(GateOutcome.UNVERIFIABLE, "no runner"),
        ):
            run_proof(workspace, full=True, run_id="unverifiable")

        run = get_run(workspace, "unverifiable")
        assert run.overall_passed is True
        assert run.vacuous_pass is True

    def test_no_requirements_is_not_vacuous(self, workspace):
        """An empty ledger makes no claim, so it cannot make a false one.

        Flagging every fresh workspace as vacuous would be noise, and would
        train people to ignore the badge that matters.
        """
        run_proof(workspace, full=True, run_id="empty-ledger")

        run = get_run(workspace, "empty-ledger")
        assert run.overall_passed is True
        assert run.vacuous_pass is False


class TestVacuousPassPersistence:
    def test_round_trips_through_the_ledger(self, workspace):
        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT]))
        _write_config(workspace, enabled_gates=[], strictness="strict")

        with patch(
            "codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "")
        ):
            run_proof(workspace, full=True, run_id="persisted")

        # Re-read from a fresh connection, not the in-process object.
        assert get_run(workspace, "persisted").vacuous_pass is True

    def test_migration_adds_the_column_to_a_pre_1247_ledger(self, workspace):
        """A ledger created before #1247 must migrate and still load.

        Rebuilds `proof_runs` with the *old* schema, seeds a row the way the
        previous build would have, then lets the lazy migration run. This is
        the path every existing workspace takes on upgrade, and it is the one
        thing `CREATE TABLE IF NOT EXISTS` cannot cover on its own.
        """
        from codeframe.core.proof import ledger as ledger_mod
        from codeframe.core.workspace import get_db_connection

        conn = get_db_connection(workspace)
        conn.execute("DROP TABLE IF EXISTS proof_runs")
        conn.execute(
            """CREATE TABLE proof_runs (
                   run_id TEXT NOT NULL,
                   workspace_id TEXT NOT NULL,
                   started_at TEXT NOT NULL,
                   completed_at TEXT,
                   triggered_by TEXT NOT NULL DEFAULT 'human',
                   overall_passed INTEGER NOT NULL DEFAULT 0,
                   duration_ms INTEGER,
                   PRIMARY KEY (run_id, workspace_id)
               )"""
        )
        conn.execute(
            "INSERT INTO proof_runs "
            "(run_id, workspace_id, started_at, completed_at, triggered_by, "
            " overall_passed, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-run",
                workspace.id,
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                "human",
                1,
                5,
            ),
        )
        conn.commit()
        conn.close()

        # This workspace already migrated in the fixture; forget that so the
        # lazy migration actually runs against the table we just rebuilt.
        ledger_mod._vacuous_migrated_workspaces.discard(workspace.id)

        run = get_run(workspace, "legacy-run")
        assert run.overall_passed is True
        # Backfilled to the column default, not left NULL for readers to guess.
        assert run.vacuous_pass is False

    def test_migration_is_idempotent(self, workspace):
        """_ensure_tables runs on every ledger call; re-running must be a no-op."""
        from codeframe.core.proof import ledger as ledger_mod

        for _ in range(3):
            ledger_mod._vacuous_migrated_workspaces.discard(workspace.id)
            ledger_mod._ensure_tables(workspace)

        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT]))
        with patch(
            "codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "")
        ):
            run_proof(workspace, full=True, run_id="after-remigrate")

        assert get_run(workspace, "after-remigrate").vacuous_pass is False


class TestVacuousPassStillWarns:
    def test_existing_warning_is_preserved(self, workspace, caplog):
        """The #556 log line is the only signal older tooling has."""
        save_requirement(workspace, _make_req("REQ-1", [Gate.UNIT]))
        _write_config(workspace, enabled_gates=[], strictness="strict")

        with caplog.at_level(logging.WARNING, logger="codeframe.core.proof.runner"):
            with patch(
                "codeframe.core.proof.runner._run_gate",
                return_value=(GateOutcome.PASSED, ""),
            ):
                run_proof(workspace, full=True, run_id="warns")

        assert any("vacuously" in r.message for r in caplog.records)
