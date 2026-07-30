"""A SKIPPED gate is not proof (#909).

``gates.run()`` computes ``passed = all(status in (PASSED, SKIPPED))``, which is
right for "did anything break?" and fatal for evidence. The ruff and pytest
runners return SKIPPED when the binary is absent, so on a machine without ruff
the SEC gate reported PASSED, ``attach_evidence`` recorded ``satisfied=True``,
the requirement flipped to SATISFIED, and the #731 PROOF9 merge gate unblocked
on evidence that was never produced.

The scoped-rule path in ``_run_gate`` already refused to treat SKIPPED as proof.
The whole-suite path in the same function contradicted it.
"""


import pytest

from codeframe.core import gates as core_gates
from codeframe.core.proof.models import Gate, GateOutcome
from codeframe.core.proof.runner import _run_gate
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "clean.py").write_text("x = 1\n")
    return create_or_load_workspace(repo)


def _skipped_result(name: str) -> core_gates.GateResult:
    """What a runner returns when its binary is absent."""
    return core_gates.GateResult(
        passed=True,  # the bug: SKIPPED counts as passing here
        checks=[
            core_gates.GateCheck(
                name=name,
                status=core_gates.GateStatus.SKIPPED,
                output=f"{name} not found",
            )
        ],
    )


# ---------------------------------------------------------------------------
# The gate outcome
# ---------------------------------------------------------------------------


def test_a_skipped_gate_is_unverifiable_not_passed(workspace, monkeypatch):
    """The exact reported scenario: ruff absent, SEC gate asked for evidence."""
    monkeypatch.setattr(core_gates, "run", lambda *a, **k: _skipped_result("ruff"))

    outcome, detail = _run_gate(workspace, Gate.SEC, [])

    assert outcome == GateOutcome.UNVERIFIABLE, detail
    assert "UNVERIFIABLE" in detail
    assert "ruff" in detail


def test_a_passing_gate_is_still_passed(workspace, monkeypatch):
    """The fix must not make everything unverifiable."""
    monkeypatch.setattr(
        core_gates,
        "run",
        lambda *a, **k: core_gates.GateResult(
            passed=True,
            checks=[core_gates.GateCheck(name="ruff", status=core_gates.GateStatus.PASSED)],
        ),
    )

    outcome, _ = _run_gate(workspace, Gate.SEC, [])

    assert outcome == GateOutcome.PASSED


def test_a_failure_outranks_a_skip(workspace, monkeypatch):
    """A real failure must not be softened into 'could not verify'."""
    monkeypatch.setattr(
        core_gates,
        "run",
        lambda *a, **k: core_gates.GateResult(
            passed=False,
            checks=[
                core_gates.GateCheck(name="ruff", status=core_gates.GateStatus.FAILED),
                core_gates.GateCheck(name="mypy", status=core_gates.GateStatus.SKIPPED),
            ],
        ),
    )

    outcome, _ = _run_gate(workspace, Gate.SEC, [])

    assert outcome == GateOutcome.FAILED


# ---------------------------------------------------------------------------
# The consequence: no satisfied evidence, requirement stays open
# ---------------------------------------------------------------------------


def test_a_skipped_gate_leaves_the_requirement_open(workspace, monkeypatch):
    """End to end — the property the #731 merge gate depends on."""
    from codeframe.core.proof import ledger
    from codeframe.core.proof.models import (
        Obligation,
        ReqStatus,
        Requirement,
        RequirementScope,
        Severity,
        Source,
    )
    from codeframe.core.proof.runner import run_proof

    ledger.init_proof_tables(workspace)
    ledger.save_requirement(
        workspace,
        Requirement(
            id="REQ-909",
            title="a requirement whose only gate cannot run",
            description="",
            severity=Severity.HIGH,
            source=Source.QA,
            scope=RequirementScope(),
            obligations=[Obligation(gate=Gate.SEC)],
            evidence_rules=[],
            status=ReqStatus.OPEN,
        ),
    )

    monkeypatch.setattr(core_gates, "run", lambda *a, **k: _skipped_result("ruff"))

    run_proof(workspace)

    stored = ledger.get_requirement(workspace, "REQ-909")
    assert stored.status == ReqStatus.OPEN, (
        f"requirement flipped to {stored.status} on evidence never produced"
    )

    evidence = ledger.list_evidence(workspace, "REQ-909")
    assert evidence, "no evidence recorded at all; the test proves nothing"
    assert not any(e.satisfied for e in evidence), (
        "a SKIPPED gate recorded satisfied=True evidence"
    )


# ---------------------------------------------------------------------------
# The #908 dependency note must not be mistaken for a skipped gate
# ---------------------------------------------------------------------------


def test_a_dependency_note_does_not_make_a_passing_gate_unverifiable(
    workspace, monkeypatch
):
    """#908 records a failed dependency install; that is a diagnostic.

    It travels in `notes`, not `checks`, precisely so it cannot be read as
    "a gate did not run" — the gate here genuinely passed.
    """
    monkeypatch.setattr(
        core_gates,
        "run",
        lambda *a, **k: core_gates.GateResult(
            passed=True,
            checks=[core_gates.GateCheck(name="ruff", status=core_gates.GateStatus.PASSED)],
            notes=["Dependency installation failed, ran gates anyway: boom"],
        ),
    )

    outcome, detail = _run_gate(workspace, Gate.SEC, [])

    assert outcome == GateOutcome.PASSED
    assert "Dependency installation failed" in detail, "the note should still surface"


def test_the_dependency_note_is_not_a_check(tmp_path, monkeypatch):
    """Guards the split at the producing end."""
    from codeframe.core import gates as gates_module

    repo = tmp_path / "dep-repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("packaging\n")
    (repo / "clean.py").write_text("x = 1\n")
    ws = create_or_load_workspace(repo)

    monkeypatch.setattr(
        gates_module,
        "_ensure_dependencies_installed",
        lambda *a, **k: (False, "simulated install failure"),
    )

    result = gates_module.run(ws, gates=["ruff"], verbose=False)

    assert [c.name for c in result.checks] == ["ruff"]
    assert any("simulated install failure" in n for n in result.notes)


# ---------------------------------------------------------------------------
# The note must reach every surface, not just the proof runner
# ---------------------------------------------------------------------------


def _result_with_note() -> core_gates.GateResult:
    return core_gates.GateResult(
        passed=True,
        checks=[core_gates.GateCheck(name="ruff", status=core_gates.GateStatus.PASSED)],
        notes=["Dependency installation failed, ran gates anyway: boom"],
    )


def test_the_note_reaches_the_gates_completed_event(tmp_path, monkeypatch):
    """Otherwise an event consumer sees 'All gates passed' and nothing else."""
    from codeframe.core import events, gates as gates_module

    repo = tmp_path / "evt-repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("packaging\n")
    (repo / "clean.py").write_text("x = 1\n")
    ws = create_or_load_workspace(repo)

    monkeypatch.setattr(
        gates_module,
        "_ensure_dependencies_installed",
        lambda *a, **k: (False, "simulated install failure"),
    )

    captured: list[dict] = []
    monkeypatch.setattr(
        events,
        "emit_for_workspace",
        lambda ws_, type_, payload, **kw: captured.append(payload),
    )

    gates_module.run(ws, gates=["ruff"], verbose=False)

    assert captured, "no event emitted"
    assert any(
        "simulated install failure" in n for n in captured[-1].get("notes", [])
    ), f"event payload dropped the diagnostic: {captured[-1]}"


def test_the_note_reaches_the_v2_api_response():
    """The API response schema carried only `checks`."""
    from codeframe.ui.routers.gates_v2 import _result_to_response

    response = _result_to_response(_result_with_note())

    assert any("Dependency installation failed" in n for n in response.notes)


def test_the_note_reaches_the_cli(tmp_path, monkeypatch):
    """`cf review` printed only checks, so the diagnostic was invisible."""
    from typer.testing import CliRunner

    from codeframe.cli import app as cli_app

    repo = tmp_path / "cli-repo"
    repo.mkdir()
    create_or_load_workspace(repo)

    # `review` imports gates inside the function, so patch the source module.
    monkeypatch.setattr(core_gates, "run", lambda *a, **k: _result_with_note())

    result = CliRunner().invoke(cli_app.app, ["review", "--workspace", str(repo)])

    assert "Dependency installation failed" in result.output, result.output
