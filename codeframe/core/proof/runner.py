"""PROOF9 runner — executes obligations and collects evidence.

Determines which requirements apply to the current changes,
runs their obligations via the existing gates infrastructure,
and attaches evidence artifacts.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Sequence

from codeframe.core.proof import ledger
from codeframe.core.proof.evidence import attach_evidence
from codeframe.core.proof.models import (
    PROOF_CONFIG_FILENAME,
    EvidenceRule,
    Gate,
    GateOutcome,
    ProofRun,
    ReqStatus,
)
from codeframe.core.proof.scope import get_changed_scope, intersects
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


class EmptyReason(str, Enum):
    """Why a proof run produced no results (#1138).

    ``run_proof`` used to return only ``dict[req_id, [(gate, outcome)]]``, and
    an empty dict has six different causes. The reasons were computed inside the
    runner and then thrown away, so ``cf proof run`` had to guess — four
    consecutive review rounds on #1137 caught a guess that was confidently
    wrong, each time about a different one of these.
    """

    #: Results were produced; there is nothing to explain.
    NOT_EMPTY = "not_empty"
    #: The ledger holds no requirements at all.
    NO_REQUIREMENTS = "no_requirements"
    #: Requirements exist but none were eligible: WAIVED always, and SATISFIED
    #: unless the run is --full.
    EXCLUDED_BY_STATUS = "excluded_by_status"
    #: Every eligible requirement was out of scope for the current changes.
    EXCLUDED_BY_SCOPE = "excluded_by_scope"
    #: --gate excluded every obligation of every in-scope requirement.
    EXCLUDED_BY_GATE_FILTER = "excluded_by_gate_filter"
    #: proof_config.json's enabled_gates did the same.
    EXCLUDED_BY_CONFIG = "excluded_by_config"
    #: Neither filter excluded everything on its own, but their intersection is
    #: empty — e.g. obligations {unit, sec} with --gate unit and
    #: enabled_gates ["sec"]. Blaming either alone would send the user to fix
    #: something that is not, by itself, the problem.
    EXCLUDED_BY_FILTER_COMBINATION = "excluded_by_filter_combination"
    #: In-scope requirements exist but define no obligations to run.
    NO_OBLIGATIONS = "no_obligations"
    #: More than one of the above applies, so naming one would be a lie.
    MIXED = "mixed"


@dataclass
class ProofRunDiagnostics:
    """What the runner decided, alongside what it produced.

    Counts rather than a single verdict: with three requirements dropped for
    three different reasons, any single reason is wrong. ``reason`` collapses
    them only when the collapse is honest.
    """

    total_requirements: int = 0
    considered: int = 0
    evaluated: int = 0
    scope_skipped: list[str] = field(default_factory=list)
    gate_filtered: list[str] = field(default_factory=list)
    config_filtered: list[str] = field(default_factory=list)
    filter_combination: list[str] = field(default_factory=list)
    no_obligations: list[str] = field(default_factory=list)

    @property
    def reason(self) -> EmptyReason:
        if self.evaluated:
            return EmptyReason.NOT_EMPTY
        if not self.total_requirements:
            return EmptyReason.NO_REQUIREMENTS
        if not self.considered:
            return EmptyReason.EXCLUDED_BY_STATUS

        buckets = {
            EmptyReason.EXCLUDED_BY_SCOPE: self.scope_skipped,
            EmptyReason.NO_OBLIGATIONS: self.no_obligations,
            EmptyReason.EXCLUDED_BY_GATE_FILTER: self.gate_filtered,
            EmptyReason.EXCLUDED_BY_CONFIG: self.config_filtered,
            EmptyReason.EXCLUDED_BY_FILTER_COMBINATION: self.filter_combination,
        }
        non_empty = [name for name, ids in buckets.items() if ids]
        if len(non_empty) == 1:
            return non_empty[0]
        if non_empty:
            return EmptyReason.MIXED
        # Considered requirements, none evaluated, and no bucket claims them —
        # a path this code does not know about. Say so rather than picking one.
        return EmptyReason.MIXED

    def describe(self) -> str:
        """One sentence a CLI or API can show verbatim."""
        return _REASON_TEXT[self.reason](self)


def _describe_mixed(d: "ProofRunDiagnostics") -> str:
    parts = []
    if d.scope_skipped:
        parts.append(f"{len(d.scope_skipped)} out of scope for the current changes")
    if d.no_obligations:
        parts.append(f"{len(d.no_obligations)} with no obligations defined")
    if d.gate_filtered:
        parts.append(f"{len(d.gate_filtered)} excluded by the --gate filter")
    if d.config_filtered:
        parts.append(f"{len(d.config_filtered)} excluded by enabled_gates in proof_config.json")
    if d.filter_combination:
        parts.append(
            f"{len(d.filter_combination)} excluded by --gate and enabled_gates together"
        )
    if not parts:
        return (
            f"{d.considered} requirement(s) were considered and none produced a "
            "result, for a reason this runner does not classify"
        )
    return "nothing ran: " + ", ".join(parts)


_REASON_TEXT = {
    EmptyReason.NOT_EMPTY: lambda d: f"{d.evaluated} requirement(s) verified",
    EmptyReason.NO_REQUIREMENTS: lambda d: "the requirement ledger is empty",
    EmptyReason.EXCLUDED_BY_STATUS: lambda d: (
        f"all {d.total_requirements} requirement(s) are waived, or satisfied on a "
        "scoped run — re-run with --full to include satisfied ones"
    ),
    EmptyReason.EXCLUDED_BY_SCOPE: lambda d: (
        f"all {len(d.scope_skipped)} open requirement(s) are out of scope for the "
        "current changes — re-run with --full to include them"
    ),
    EmptyReason.EXCLUDED_BY_GATE_FILTER: lambda d: (
        f"the --gate filter excluded every obligation of all "
        f"{len(d.gate_filtered)} in-scope requirement(s)"
    ),
    EmptyReason.EXCLUDED_BY_CONFIG: lambda d: (
        f"enabled_gates in proof_config.json excluded every obligation of all "
        f"{len(d.config_filtered)} in-scope requirement(s)"
    ),
    EmptyReason.EXCLUDED_BY_FILTER_COMBINATION: lambda d: (
        f"--gate and enabled_gates in proof_config.json do not overlap, so no "
        f"obligation of the {len(d.filter_combination)} in-scope requirement(s) "
        "could run — each filter alone would have left something to do"
    ),
    EmptyReason.NO_OBLIGATIONS: lambda d: (
        f"all {len(d.no_obligations)} in-scope requirement(s) define no obligations"
    ),
    EmptyReason.MIXED: _describe_mixed,
}


def _new_run_id() -> str:
    """A fresh proof-run identifier.

    A full UUID, never a truncated one. ``str(uuid4())[:8]`` gives 32 bits, so
    two runs in a workspace collide around 600 runs by the birthday bound — and
    a collision merges evidence across runs, letting a passing run absorb a
    failing run's artifacts (#952). Callers that need the id before the run
    starts (the v2 router, so its response matches the evidence rows) use this
    too, so there is one definition.
    """
    return str(uuid.uuid4())


def _load_proof_config(workspace: Workspace) -> tuple[Optional[set[Gate]], str]:
    """Load (enabled_gates, strictness) from .codeframe/proof_config.json.

    Returns:
        (enabled_gates, strictness). enabled_gates is None when no config file
        exists (meaning "all gates allowed"); a set of Gate enums otherwise.
        strictness defaults to 'strict' when missing or invalid.
    """
    path = workspace.state_dir / PROOF_CONFIG_FILENAME
    if not path.exists():
        return None, "strict"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    # ValueError, not just json.JSONDecodeError (#1029). The two are SIBLINGS
    # under ValueError, not parent and child — so catching JSONDecodeError does
    # nothing for a UnicodeDecodeError, and a proof_config.json with one
    # non-UTF-8 byte crashed `cf proof run` instead of falling back to defaults.
    except (OSError, ValueError) as exc:
        logger.warning("Invalid %s — using defaults: %s", PROOF_CONFIG_FILENAME, exc)
        return None, "strict"

    enabled: Optional[set[Gate]] = None
    gates_raw = data.get("enabled_gates")
    if isinstance(gates_raw, list):
        enabled = set()
        valid_values = {g.value for g in Gate}
        for name in gates_raw:
            if name in valid_values:
                enabled.add(Gate(name))
            else:
                logger.warning(
                    "Unknown gate name '%s' in %s — skipped (valid: %s)",
                    name,
                    PROOF_CONFIG_FILENAME,
                    valid_values,
                )

    strictness = data.get("strictness", "strict")
    if strictness not in ("strict", "warn"):
        strictness = "strict"
    return enabled, strictness


# Map PROOF9 gates to existing core/gates.py gate names
_GATE_TO_CORE: dict[Gate, str] = {
    Gate.UNIT: "pytest",
    Gate.CONTRACT: "pytest",
    # bandit, not ruff: a clean *lint* used to record checksummed "security"
    # evidence in the ledger (#925).
    Gate.SEC: "bandit",
}

# Map a gate outcome to the persisted obligation status string.
_OUTCOME_TO_OBLIGATION_STATUS: dict[GateOutcome, str] = {
    GateOutcome.PASSED: "satisfied",
    GateOutcome.FAILED: "failed",
    GateOutcome.UNVERIFIABLE: "unverifiable",
}


def _run_gate(
    workspace: Workspace,
    gate: Gate,
    rules: Sequence[EvidenceRule] = (),
) -> tuple[GateOutcome, str]:
    """Execute a single gate and return (outcome, output).

    Uses core/gates.py for gates that have direct tool support. Gates without
    an automated runner return UNVERIFIABLE — the obligation could not be
    checked, which is distinct from running and failing.

    For pytest-backed gates, each ``must_pass`` evidence rule is enforced
    individually: pytest runs scoped to the rule's ``test_id`` (via ``-k``),
    and a named test that doesn't exist is a FAILED obligation — a green
    whole-suite run proves nothing about a test that was never written.
    Rules with ``must_pass=False`` are informational only.

    Each enforced rule deliberately gets its own pytest subprocess — do not
    collapse them into one ``-k "a or b"`` run; per-rule exit codes are what
    distinguish "named test missing" from "collected but failing".
    """
    core_gate_name = _GATE_TO_CORE.get(gate)

    # Only pytest-style test_ids can be enforced by a scoped pytest run; e.g.
    # SEC's test_sec_* rules are pytest tests even though the SEC gate's own
    # runner is ruff.
    enforced = [r for r in rules if r.must_pass and r.test_id.startswith("test_")]
    unenforceable = [r for r in rules if r.must_pass and not r.test_id.startswith("test_")]

    # A gate with no dedicated runner is still verifiable through its evidence
    # rules — the scoped-pytest machinery below works for any test_-prefixed
    # id, and TEST_ID_PREFIXES gives every gate except MANUAL exactly such a
    # prefix. This lookup used to return early, so A11Y/PERF/VISUAL/E2E/DEMO
    # obligations reported UNVERIFIABLE forever, even after the developer
    # implemented the generated stub. Five of the seven glitch types include at
    # least one of those gates, so most captured glitches could never be
    # satisfied — only waived (#924).
    if not core_gate_name and not enforced:
        return (
            GateOutcome.UNVERIFIABLE,
            f"Gate {gate.value} has no automated runner and no pytest-style "
            f"evidence rules — cannot verify",
        )

    try:
        from codeframe.core import gates as core_gates

        lines: list[str] = []
        all_passed = True
        unverifiable = False

        for rule in enforced:
            result = core_gates.run(
                workspace,
                gates=["pytest"],
                verbose=False,
                test_selector=rule.test_id,
            )
            check = result.checks[0] if result.checks else None
            if check is None:
                lines.append(f"{rule.test_id}: FAILED — no gate check returned")
                all_passed = False
            elif check.exit_code == 5:
                lines.append(f"{rule.test_id}: FAILED — named test missing (not collected)")
                all_passed = False
            elif check.status == core_gates.GateStatus.PASSED:
                lines.append(f"{rule.test_id}: passed")
            else:
                # SKIPPED (pytest unavailable) and ERROR (timeout) are not
                # proof — enforcement needs a positive pass, unlike the
                # whole-suite path where SKIPPED counts as passing.
                lines.append(f"{rule.test_id}: FAILED ({check.status.value})")
                all_passed = False

        # A must_pass rule we cannot enforce must not silently count as
        # satisfied — that is the exact bug this module exists to prevent.
        for rule in unenforceable:
            lines.append(f"{rule.test_id}: FAILED — must_pass rule has no pytest-style test_id")
            all_passed = False

        # Run the gate's own runner unless it is pytest and the enforced rules
        # already covered it (scoped runs replace the whole-suite run). A gate
        # with no runner at all has nothing to fall back to — its evidence
        # rules above are the whole verification (#924).
        if core_gate_name and (core_gate_name != "pytest" or not enforced):
            result = core_gates.run(workspace, gates=[core_gate_name], verbose=False)
            lines.extend(
                f"{check.name}: {check.status.value}" for check in result.checks
            )
            lines.extend(result.notes)

            # A SKIPPED gate is not proof (#909). `result.passed` counts SKIPPED
            # as passing — reasonable for "did anything break?", fatal for
            # evidence: on a machine without ruff the SEC gate reported PASSED,
            # attach_evidence recorded satisfied=True, the requirement flipped to
            # SATISFIED, and the #731 merge gate unblocked on evidence that was
            # never produced. The scoped path above already refuses this; the
            # whole-suite path used to contradict it.
            all_passed = all_passed and result.passed

            skipped = [
                c for c in result.checks if c.status == core_gates.GateStatus.SKIPPED
            ]
            # Only downgrade a *pass*: a real failure is the stronger signal and
            # must never be softened into "could not verify". `result.passed` is
            # true when every check is PASSED or SKIPPED, so this is exactly the
            # case where the skips are what produced the pass.
            if result.passed and skipped:
                unverifiable = True
                lines.append(
                    "UNVERIFIABLE — "
                    + ", ".join(f"{c.name} did not run ({c.output.strip()[:80]})" for c in skipped)
                )

        for rule in rules:
            if not rule.must_pass:
                lines.append(f"{rule.test_id}: informational (must_pass=False, not enforced)")

        if not all_passed:
            outcome = GateOutcome.FAILED
        elif unverifiable:
            outcome = GateOutcome.UNVERIFIABLE
        else:
            outcome = GateOutcome.PASSED
        return outcome, "\n".join(lines)
    except Exception as exc:
        logger.warning("Gate %s failed to run: %s", gate.value, exc)
        return GateOutcome.FAILED, str(exc)


def _report_scope_skipped(run_id: str, skipped: list[str]) -> None:
    """Surface requirements a scoped run did not evaluate (#922).

    Dropping them with a bare ``continue`` is how ``overall_passed=True`` came
    to coexist with a merge gate that still blocked on the very same
    requirements — the user had no way to see the two were talking about
    different sets.
    """
    if not skipped:
        return
    logger.warning(
        "Proof run %s: %d requirement(s) not evaluated — out of scope for the "
        "current changes: %s. Re-run with --full to include them.",
        run_id, len(skipped), ", ".join(sorted(skipped)),
    )

def _requirements_for_run(workspace: Workspace, *, full: bool) -> list:
    """Which requirements a run evaluates (#923).

    A scoped run keeps the cheap behaviour — open requirements only. A ``--full``
    run also re-verifies SATISFIED ones, because otherwise there was no path
    back: the runner loaded only OPEN, so once satisfied a requirement could
    never re-fail on a later regression, and the #731 merge gate — which
    inspects only *open* requirements — then blocked nothing.

    WAIVED requirements stay out of both. A waiver is an accepted risk recorded
    by a human, not something a gate result should quietly overturn.
    """
    reqs = ledger.list_requirements(workspace, status=ReqStatus.OPEN)
    if full:
        reqs = reqs + ledger.list_requirements(workspace, status=ReqStatus.SATISFIED)
    return reqs


def run_proof(
    workspace: Workspace,
    *,
    full: bool = False,
    gate_filter: Optional[Gate] = None,
    run_id: Optional[str] = None,
) -> dict[str, list[tuple[Gate, GateOutcome]]]:
    """Execute proof obligations and collect evidence.

    The results only. Callers that need to explain an EMPTY result — every
    caller that shows a human anything — want :func:`run_proof_with_diagnostics`
    instead (#1138). Kept because ~60 call sites do not care.
    """
    return run_proof_with_diagnostics(
        workspace, full=full, gate_filter=gate_filter, run_id=run_id
    )[0]


def run_proof_with_diagnostics(
    workspace: Workspace,
    *,
    full: bool = False,
    gate_filter: Optional[Gate] = None,
    run_id: Optional[str] = None,
) -> tuple[dict[str, list[tuple[Gate, GateOutcome]]], ProofRunDiagnostics]:
    """Execute proof obligations and collect evidence, with the reasoning.

    Args:
        workspace: Target workspace
        full: If True, run ALL obligations regardless of scope
        gate_filter: If set, only run this specific gate
        run_id: Unique run identifier (auto-generated if not provided)

    Returns:
        ``(results, diagnostics)`` — results maps req_id → [(Gate, GateOutcome)],
        and diagnostics explains anything the results do not (#1138).
    """
    if not run_id:
        run_id = _new_run_id()

    started_at = datetime.now(timezone.utc)

    # Load PROOF9 config (enabled gates + strictness)
    enabled_gates, strictness = _load_proof_config(workspace)

    # Expire any stale waivers
    expired = ledger.check_expired_waivers(workspace)
    if expired:
        logger.info("Expired %d waivers", len(expired))

    # Get all open requirements
    reqs = _requirements_for_run(workspace, full=full)
    # The ledger total is what separates "no requirements exist" from "none were
    # eligible" — _requirements_for_run returns [] for both.
    diagnostics = ProofRunDiagnostics(
        total_requirements=len(ledger.list_requirements(workspace)),
        considered=len(reqs),
    )
    if not reqs:
        completed_at = datetime.now(timezone.utc)
        ledger.save_run(
            workspace,
            ProofRun(
                run_id=run_id,
                workspace_id=workspace.id,
                started_at=started_at,
                completed_at=completed_at,
                triggered_by="human",
                overall_passed=True,
                duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            ),
        )
        return {}, diagnostics

    # Warn loudly when config disables every gate — a "vacuous pass" is
    # easy to overlook: nothing runs, overall_passed=True, no evidence.
    if enabled_gates is not None and not enabled_gates:
        logger.warning(
            "Proof run %s: all 9 gates are disabled by proof_config.json — "
            "no obligations will run and the run will pass vacuously",
            run_id,
        )

    # Get changed scope (skip if running full)
    changed_scope = None
    if not full:
        changed_scope = get_changed_scope(workspace)

    results: dict[str, list[tuple[Gate, GateOutcome]]] = {}
    artifact_dir = workspace.state_dir / "proof_artifacts"
    artifact_dir.mkdir(exist_ok=True)

    scope_skipped: list[str] = []

    for req in reqs:
        # Check scope intersection (unless full mode or scope detection failed)
        # None changed_scope means "failed to detect" → run everything (fail closed)
        if not full and changed_scope is not None:
            if not intersects(req.scope, changed_scope):
                scope_skipped.append(req.id)
                continue

        if not req.obligations:
            diagnostics.no_obligations.append(req.id)

        req_results: list[tuple[Gate, GateOutcome]] = []

        unresolved = [r.test_id for r in req.evidence_rules if r.gate is None]
        if unresolved:
            logger.warning(
                "REQ %s: %d evidence rule(s) with no resolvable gate are not enforced: %s",
                req.id, len(unresolved), unresolved,
            )

        for obl in req.obligations:
            # Apply gate filter
            if gate_filter and obl.gate != gate_filter:
                continue

            # Apply config-driven gate filter (None means "all allowed")
            if enabled_gates is not None and obl.gate not in enabled_gates:
                continue

            # Run the gate, enforcing this requirement's evidence rules for it
            gate_rules = [r for r in req.evidence_rules if r.gate == obl.gate]
            outcome, output = _run_gate(workspace, obl.gate, gate_rules)

            # Write artifact
            artifact_path = artifact_dir / f"{req.id}_{obl.gate.value}_{run_id}.txt"
            artifact_path.write_text(output)

            # Attach evidence
            attach_evidence(
                workspace, req.id, obl.gate,
                str(artifact_path), outcome, run_id,
            )

            # Update obligation status
            obl.status = _OUTCOME_TO_OBLIGATION_STATUS[outcome]
            req_results.append((obl.gate, outcome))

        if not req_results and req.obligations:
            # Every obligation was filtered out. Attribute it to the filter that
            # did it ALONE, so the hint points somewhere that helps.
            survives_gate = [
                o for o in req.obligations
                if gate_filter is None or o.gate == gate_filter
            ]
            survives_config = [
                o for o in req.obligations
                if enabled_gates is None or o.gate in enabled_gates
            ]
            if not survives_gate:
                # --gate is the user's explicit flag, so it is named first when
                # it is sufficient on its own.
                diagnostics.gate_filtered.append(req.id)
            elif not survives_config:
                diagnostics.config_filtered.append(req.id)
            else:
                # Each filter leaves something; their intersection does not.
                # Neither is "the" cause, and blaming one sends the user to fix
                # something that is not by itself the problem (review finding).
                diagnostics.filter_combination.append(req.id)

        if req_results:
            results[req.id] = req_results

            # Always persist obligation status updates. A requirement is only
            # SATISFIED when every obligation PASSED and all obligations ran —
            # an unverifiable obligation leaves it OPEN (and waivable).
            all_passed = all(o == GateOutcome.PASSED for _, o in req_results)
            if all_passed and len(req_results) == len(req.obligations):
                # mark_satisfied stamps satisfied_at, which the ledger column
                # and the API field never carried before (#923).
                ledger.mark_satisfied(workspace, req)
            elif req.status == ReqStatus.SATISFIED:
                # A previously satisfied requirement that no longer passes is a
                # regression: return it to OPEN so it re-fails and the merge
                # gate sees it again (#923).
                ledger.reopen_requirement(
                    workspace, req.id,
                    reason="obligations no longer all pass",
                )
            else:
                ledger.save_requirement(workspace, req)

    completed_at = datetime.now(timezone.utc)
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    # Only gates that actually ran (passed or failed) count toward the tally;
    # unverifiable gates neither pass nor fail, so a run with only unverifiable
    # outcomes passes.
    executed = [
        outcome == GateOutcome.PASSED
        for gate_results in results.values()
        for _, outcome in gate_results
        if outcome != GateOutcome.UNVERIFIABLE
    ]
    all_passed = all(executed) if executed else True
    if not all_passed and strictness == "warn":
        logger.warning(
            "Proof run %s had gate failures but strictness='warn' — overall_passed=True",
            run_id,
        )
        overall_passed = True
    else:
        overall_passed = all_passed
    ledger.save_run(
        workspace,
        ProofRun(
            run_id=run_id,
            workspace_id=workspace.id,
            started_at=started_at,
            completed_at=completed_at,
            triggered_by="human",
            overall_passed=overall_passed,
            duration_ms=duration_ms,
        ),
    )

    _report_scope_skipped(run_id, scope_skipped)

    diagnostics.scope_skipped = scope_skipped
    diagnostics.evaluated = len(results)

    if not results:
        logger.info("Proof run %s produced no results: %s", run_id, diagnostics.describe())

    return results, diagnostics
