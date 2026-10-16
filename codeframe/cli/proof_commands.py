"""CLI commands for PROOF9 quality memory system.

Provides `cf proof` subcommands for capturing requirements,
running obligations, managing waivers, and viewing status.
"""

import functools
import json
import sys
from contextlib import redirect_stdout
from contextvars import ContextVar
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TextIO, TypeVar

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from codeframe.cli.helpers import cli_actor, print_error

if TYPE_CHECKING:
    from codeframe.core.proof.models import Gate, Requirement
    from codeframe.core.workspace import Workspace

_E = TypeVar("_E", bound=Enum)

console = Console()

proof_app = typer.Typer(
    name="proof",
    help="PROOF9 quality memory system — evidence-based verification",
    no_args_is_help=True,
)


JSON_HELP = (
    "Print one JSON document on stdout; everything else goes to stderr. "
    "Nothing is printed on stdout when the command fails before it has a result."
)

#: The real stdout while a `--json` command runs with stdout sent to stderr.
_json_stdout: ContextVar[Optional[TextIO]] = ContextVar("_json_stdout", default=None)


def _json_capable(fn):
    """With ``--json``, stdout carries only the document `_emit` writes (#1488).

    Every other line — progress, warnings, errors, interactive prompts — goes
    to stderr, because the Rich consoles and ``typer.prompt`` all write to
    whatever ``sys.stdout`` is at the time. That keeps the human-readable paths
    and their exit codes exactly as they are.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not kwargs.get("as_json"):
            return fn(*args, **kwargs)
        token = _json_stdout.set(sys.stdout)
        try:
            with redirect_stdout(sys.stderr):
                return fn(*args, **kwargs)
        finally:
            _json_stdout.reset(token)

    return wrapper


def _emit(doc: dict) -> None:
    out = _json_stdout.get()
    out.write(json.dumps(doc, indent=2) + "\n")
    out.flush()


def _prompt_choice(text: str, choices: list[str], default: str) -> str:
    """Prompt until the answer is one of ``choices`` (#723).

    A plain loop rather than ``type=click.Choice``: typer >= 0.27 vendors its
    own click, so an installed-click type handed to ``typer.prompt`` lost its
    choice list and turned a typo into a traceback (#1268).
    """
    while True:
        answer = typer.prompt(f"{text} ({'/'.join(choices)})", default=default)
        if answer in choices:
            return answer
        console.print(f"[red]Choose one of:[/red] {', '.join(choices)}")


def _load_or_create_workspace(root: Path) -> "Workspace":
    """Load the workspace at ``root``, creating it with a one-line notice (#1464)."""
    from codeframe.core.workspace import CODEFRAME_DIR, create_or_load_workspace

    existed = (root / CODEFRAME_DIR).is_dir()
    try:
        workspace = create_or_load_workspace(root)
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)
    if not existed:
        console.print("Created .codeframe/ in this repository.")
    return workspace


def _or_prompt(value: Optional[str], text: str) -> str:
    return value or typer.prompt(text)


def _choose(
    enum_cls: type[_E],
    label: str,
    value: Optional[str],
    default: str,
    reserved: tuple[_E, ...] = (),
) -> _E:
    """``value`` (prompted for when missing) as an ``enum_cls``; exit 1 if
    invalid or one of ``reserved`` (members only other commands may set)."""
    value = value or _prompt_choice(
        label, [e.value for e in enum_cls if e not in reserved], default
    )
    try:
        chosen = enum_cls(value)
    except ValueError:
        chosen = None
    if chosen is None or chosen in reserved:
        console.print(f"[red]Error:[/red] Invalid {label.lower()}: {escape(str(value))}")
        raise typer.Exit(1)
    return chosen


def _print_captured(req: "Requirement", stubs: "dict[Gate, Path]", repo_root: Path) -> None:
    console.print(f"\n[green]✓[/green] Created [bold]{req.id}[/bold]: {escape(req.title)}")
    console.print(f"  Glitch type: [cyan]{req.glitch_type.value if req.glitch_type else 'unknown'}[/cyan]")
    console.print(f"  Obligations: {', '.join(o.gate.value for o in req.obligations)}")
    console.print(f"  Scope files: {', '.join(req.scope.files) or 'none'}")
    console.print(f"  Scope routes: {', '.join(req.scope.routes) or 'none'}")

    _print_stubs(stubs, repo_root)


def _print_stubs(stubs: "dict[Gate, Path]", repo_root: Path) -> None:
    if not stubs:
        return
    console.print("\n[bold]Test stubs written:[/bold]")
    for gate, path in stubs.items():
        try:
            shown = path.relative_to(repo_root)
        except ValueError:
            shown = path
        console.print(f"  [cyan]{gate.value}[/cyan]: {shown}")


@proof_app.command("capture")
@_json_capable
def capture(
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Short description of the glitch",
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="What happened (expected vs actual)",
    ),
    where: Optional[str] = typer.Option(
        None, "--where", help="Where it happened (URL, file, API route)",
    ),
    severity: Optional[str] = typer.Option(
        None, "--severity", "-s", help="critical/high/medium/low",
    ),
    source: Optional[str] = typer.Option(
        None, "--source", help="production/qa/dogfooding/monitoring/user_report",
    ),
    source_issue: Optional[str] = typer.Option(
        None, "--from-issue", help="GitHub issue reference (e.g., GH-123)",
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Capture a glitch as a permanent proof requirement.

    Creates a REQ with proof obligations and generates test stubs.
    Interactive when run without arguments.

    Works in any git repository: the workspace is created on first use,
    so `cf init` is not required.

    Example:
        codeframe proof capture
        codeframe proof capture --title "Login rejects empty password" --severity high
    """
    from codeframe.core.workspace import CODEFRAME_DIR, capture_workspace_root
    from codeframe.core.proof.models import Severity, Source
    from codeframe.core.proof.capture import capture_requirement
    from codeframe.core.proof.serialize import capture_document

    try:
        workspace_path = capture_workspace_root(repo_path or Path.cwd())
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)

    # Interactive prompts for missing fields
    title = _or_prompt(title, "What happened? (short title)")
    description = _or_prompt(description, "Describe the issue (expected vs actual)")
    where = _or_prompt(where, "Where? (file path, URL, API route, or component)")
    sev = _choose(Severity, "Severity", severity, "medium")
    src = _choose(Source, "Source", source, "qa", reserved=(Source.RATCHET,))

    warnings: list[str] = []

    def _scope_warning(message: str) -> None:
        warnings.append(message)
        console.print(f"[yellow]⚠[/yellow] {escape(message)}")

    # Created only now, after the input is known good: a rejected capture
    # must not leave an empty workspace behind (#1464).
    existed = (workspace_path / CODEFRAME_DIR).is_dir()
    workspace = _load_or_create_workspace(workspace_path)

    req, stubs = capture_requirement(
        workspace,
        title=title,
        description=description,
        where=where,
        severity=sev,
        source=src,
        source_issue=source_issue,
        on_warning=_scope_warning,
    )

    if as_json:
        _emit(capture_document(
            req, stubs, workspace.repo_path, workspace_created=not existed, warnings=warnings,
        ))
        return
    _print_captured(req, stubs, workspace.repo_path)


@proof_app.command("ratchet")
@_json_capable
def ratchet(
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
    path_glob: Optional[str] = typer.Option(
        None, "--path", help="Only tests under paths matching this glob (e.g. 'tests/unit/*')",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would be locked in; write nothing",
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Lock every currently-passing test in as a proof obligation.

    Runs the project's pytest suite once. Each passing test becomes a
    requirement whose UNIT obligation is that test, scoped to the files it
    covers (needs pytest-cov in the project; otherwise the whole repository).
    Failing and skipped tests are not locked. Re-running adds only tests not
    already locked. Creates the workspace on first use, like capture.

    Exit codes:
        0  tests were locked in, or every passing test already was
        1  the test suite could not run
        2  nothing to lock: no tests found, or none passed

    Example:
        codeframe proof ratchet --dry-run
        codeframe proof ratchet --path 'tests/unit/*'
    """
    from codeframe.core.workspace import CODEFRAME_DIR, capture_workspace_root, get_workspace
    from codeframe.core.proof.ratchet import RatchetError, lock_in, run_suite
    from codeframe.core.proof.serialize import ratchet_document

    try:
        root = capture_workspace_root(repo_path or Path.cwd())
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)

    workspace = None
    if (root / CODEFRAME_DIR).is_dir():
        try:
            workspace = get_workspace(root)
        except Exception as e:
            print_error(e)
            raise typer.Exit(1)

    console.print("[dim]Running the test suite...[/dim]")
    try:
        suite = run_suite(
            root, path_glob=path_glob,
            sandbox_root=workspace.repo_path if workspace else None,
        )
    except RatchetError as e:
        console.print(f"[red]Error:[/red] {escape(str(e))}")
        raise typer.Exit(2 if e.no_tests else 1)

    not_locked = []
    if suite.failed:
        not_locked.append(f"{len(suite.failed)} failed")
    if suite.skipped:
        not_locked.append(f"{len(suite.skipped)} skipped")
    if not_locked:
        console.print(f"Not locked in: {', '.join(not_locked)}.")
    if suite.unenforceable:
        console.print(
            "[yellow]⚠[/yellow] Not locked in — a proof rule can only name tests "
            f"starting with test_: {escape(', '.join(suite.unenforceable))}"
        )

    if not suite.passing:
        console.print("[red]No passing tests eligible to lock in.[/red]")
        if as_json:
            _emit(ratchet_document(suite, None, dry_run=dry_run, workspace_created=False))
        raise typer.Exit(2)

    if not suite.per_file_scope:
        console.print(
            "[yellow]⚠[/yellow] Per-test coverage was not available (it needs "
            "pytest-cov with --cov-context), so each obligation is scoped to the "
            "whole repository. Install pytest-cov to scope each one to the files "
            "its test covers."
        )

    workspace_created = not dry_run and workspace is None
    if workspace_created:
        workspace = _load_or_create_workspace(root)
    try:
        result = lock_in(workspace, suite, dry_run=dry_run)
    except Exception as e:
        # Any locked before the failure stay; a re-run skips them.
        print_error(e)
        raise typer.Exit(1)

    if as_json:
        _emit(ratchet_document(
            suite, result, dry_run=dry_run, workspace_created=workspace_created,
        ))
        return
    n = len(result.locked)
    tests = "test" if n == 1 else "tests"
    if dry_run and n:
        console.print(f"Would lock in {n} passing {tests} as obligations (dry run — ledger not written):")
        for name, files in result.locked.items():
            console.print(f"  {escape(name)}  [dim]({len(files)} file(s) in scope)[/dim]")
    elif n:
        console.print(
            f"[green]✓[/green] Locked in {n} passing {tests} as obligations. "
            "Nothing that passes today can silently stop passing."
        )
        console.print(
            "Run `cf proof run --full` to record their evidence. After that, "
            "`cf proof run` re-checks each one whenever your changes touch its scope."
        )
    if result.already_locked:
        console.print(f"{len(result.already_locked)} passing test(s) already locked in.")


@proof_app.command("run")
@_json_capable
def run(
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
    full: bool = typer.Option(
        False, "--full", help="Run all obligations (not just changed scope)",
    ),
    gate: Optional[str] = typer.Option(
        None, "--gate", help="Run only this gate (e.g., unit, e2e)",
    ),
    allow_empty: bool = typer.Option(
        False,
        "--allow-empty",
        help=(
            "Exit 0 when there are no applicable obligations. Off by default: "
            "a run that verified nothing is not a pass (#1118)."
        ),
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Run proof obligations for current changes.

    Determines which requirements apply to changed files,
    runs their obligations, and collects evidence.

    Exit codes:
        0  obligations ran and none failed — or nothing applied because the
           caller narrowed the run (out of scope, --gate, waived)
        1  an obligation failed
        2  nothing was verified and verification was impossible: an empty
           ledger, every gate disabled in proof_config.json, or requirements
           with no obligations (see --allow-empty)

    Example:
        codeframe proof run
        codeframe proof run --full
        codeframe proof run --gate unit
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof.models import PROOF_CONFIG_FILENAME, Gate, GateOutcome
    from codeframe.core.proof import ledger
    from codeframe.core.proof.runner import (
        EmptyReason,
        _new_run_id,
        run_proof_with_diagnostics,
    )
    from codeframe.core.proof.serialize import run_document

    workspace_path = repo_path or Path.cwd()
    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)

    gate_filter = None
    if gate:
        try:
            gate_filter = Gate(gate.lower())
        except ValueError:
            console.print(f"[red]Error:[/red] Unknown gate: {escape(str(gate))}")
            console.print(f"Valid gates: {', '.join(g.value for g in Gate)}")
            raise typer.Exit(1)

    mode = "full" if full else "scope-filtered"
    console.print(f"[dim]Running proof obligations ({mode})...[/dim]")

    run_id = _new_run_id()
    before = {}
    if as_json:
        # The runner expires lapsed waivers before it runs; do it first so the
        # snapshot shows what the run actually started from.
        ledger.check_expired_waivers(workspace)
        before = {r.id: r for r in ledger.list_requirements(workspace)}
    results, diagnostics = run_proof_with_diagnostics(
        workspace, full=full, gate_filter=gate_filter, run_id=run_id
    )

    if as_json:
        saved = ledger.get_run(workspace, run_id)
        _emit(run_document(
            run_id=run_id,
            full=full,
            gate_filter=gate_filter,
            results=results,
            before=before,
            after={r.id: r for r in ledger.list_requirements(workspace)},
            vacuous=bool(saved and saved.vacuous_pass),
            empty_reason=None if results else diagnostics.reason.value,
            description=None if results else diagnostics.describe(),
        ))

    def _stop_nothing_verified() -> None:
        """End the run for an empty result: exit 2, or 0 under --allow-empty.

        Single-sourced deliberately. #1253 exists *because* this policy was
        applied to one empty reason and not the others, so having two copies of
        it — which must agree on both the exit code and the message — would
        rebuild the same hazard one level down. A new EmptyReason that needs to
        stop the run calls this and cannot get it wrong.

        Always terminal, so callers need no follow-up `return`.
        """
        if allow_empty:
            console.print("\n[dim]--allow-empty: exiting 0 anyway.[/dim]")
            raise typer.Exit(0)
        raise typer.Exit(2)

    if not results:
        # The runner now reports WHY (#1138). Before that, this block inferred
        # the cause from the mode and the ledger, and four consecutive review
        # rounds on #1137 caught it asserting a reason that was wrong — each
        # time about a different one of the six causes. It ended up listing
        # candidates instead, which was honest but useless. The runner is the
        # only thing that knows, so ask it.
        reason = diagnostics.reason

        if reason is EmptyReason.NO_REQUIREMENTS:
            # An empty ledger is not a pass (#1118). Exiting 0 here is what let
            # the quickstart's PROVE step read as "PROOF9 gates passed" when
            # nothing had been checked — and every new workspace is in exactly
            # this state.
            #
            # Exit 2 rather than 1: this is not a failure either, and a script
            # needs to tell "the gate failed" from "the gate had nothing to
            # check". CI treats any non-zero as a stop, which is the point.
            console.print("[yellow]Nothing was verified.[/yellow]")
            console.print(
                "There are no proof obligations in this workspace, so this run "
                "checked nothing — it is not a pass."
            )
            console.print(
                "\nCapture your first requirement with:\n"
                "  [bold]cf proof capture[/bold]"
            )
            _stop_nothing_verified()

        console.print(
            f"[yellow]Nothing was verified.[/yellow] {diagnostics.describe()}."
        )

        hints = {
            EmptyReason.EXCLUDED_BY_STATUS: (
                "A waiver is an accepted risk that no run re-checks. Satisfied ones "
                "are re-checked when your changes touch them; "
                "[bold]cf proof run --full[/bold] re-verifies them all."
            ),
            EmptyReason.EXCLUDED_BY_SCOPE: (
                "[bold]cf proof run --full[/bold] ignores scope entirely."
            ),
            EmptyReason.EXCLUDED_BY_GATE_FILTER: (
                "Drop [bold]--gate[/bold] to run every obligation."
            ),
            EmptyReason.EXCLUDED_BY_CONFIG: (
                "Check [bold]enabled_gates[/bold] in "
                f"[bold].codeframe/{PROOF_CONFIG_FILENAME}[/bold]."
            ),
            EmptyReason.EXCLUDED_BY_FILTER_COMBINATION: (
                "Drop [bold]--gate[/bold], or add that gate to "
                f"[bold]enabled_gates[/bold] in [bold].codeframe/{PROOF_CONFIG_FILENAME}"
                "[/bold] — each filter alone leaves work to do, but they do not "
                "overlap."
            ),
            EmptyReason.NO_OBLIGATIONS: (
                "Add obligations to those requirements, or they can never be "
                "satisfied."
            ),
        }
        if reason in hints:
            console.print(hints[reason])
        console.print("See [bold]cf proof status[/bold] for the ledger.")

        # Two of these reasons mean verification was *impossible*, not merely
        # narrowed, and exiting 0 on them reported success for a run that
        # checked nothing (#1253) — the same lie #1118 fixed for an empty
        # ledger, and the CLI-side twin of #1247's `vacuous_pass`:
        #
        #   config_filtered  the operator disabled the gates in
        #                    proof_config.json, so obligations that exist and
        #                    apply were never run
        #   no_obligations   the requirement defines nothing to run, so it can
        #                    never be satisfied
        #
        # The other reasons keep exiting 0 deliberately: a scope filter on a
        # doc-only change, an explicit --gate, and a waiver are all the caller
        # getting what they asked for. Failing CI on those would be a new bug
        # in the name of fixing this one (#1118).
        #
        # Keyed on the buckets, not on `reason`. `reason` collapses to MIXED as
        # soon as two causes apply, so a reason-based test would let "one out of
        # scope + one excluded by disabled gates" exit 0 — letting an operator
        # hide disabled gates behind a single out-of-scope requirement.
        if diagnostics.config_filtered or diagnostics.no_obligations:
            _stop_nothing_verified()
        return

    # Display results
    table = Table(title="Proof Results")
    table.add_column("REQ", style="cyan")
    table.add_column("Gate", style="blue")
    table.add_column("Result", style="bold")

    _CELL = {
        GateOutcome.PASSED: "[green]PASS[/green]",
        GateOutcome.FAILED: "[red]FAIL[/red]",
        GateOutcome.UNVERIFIABLE: "[yellow]UNVERIFIABLE[/yellow]",
    }
    any_failed = False
    unverifiable_gates: set[str] = set()
    for req_id, gate_results in results.items():
        for g, outcome in gate_results:
            if outcome == GateOutcome.FAILED:
                any_failed = True
            elif outcome == GateOutcome.UNVERIFIABLE:
                unverifiable_gates.add(g.value)
            table.add_row(req_id, g.value, _CELL[outcome])

    console.print(table)

    if unverifiable_gates:
        gates = ", ".join(sorted(unverifiable_gates))
        console.print(
            f"\n[yellow]Could not verify {len(unverifiable_gates)} gate(s):[/yellow] "
            f"{gates} — no automated runner. "
            "Waive with 'cf proof waive <REQ> --reason \"...\"'."
        )

    if any_failed:
        console.print("\n[red]Some obligations failed.[/red] Fix issues and re-run.")
        raise typer.Exit(1)
    elif unverifiable_gates:
        console.print(
            "\n[green]No obligations failed[/green] "
            "[dim](some gates could not be verified).[/dim]"
        )
    else:
        console.print("\n[green]All obligations satisfied.[/green]")


@proof_app.command("list")
@_json_capable
def list_reqs(
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
    status: Optional[str] = typer.Option(
        None, "--status", help="Filter by status (open/satisfied/waived)",
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """List all proof requirements.

    Example:
        codeframe proof list
        codeframe proof list --status open
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof import ledger
    from codeframe.core.proof.models import ReqStatus

    workspace_path = repo_path or Path.cwd()
    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)

    status_filter = None
    if status:
        try:
            status_filter = ReqStatus(status.lower())
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid status: {escape(str(status))}")
            raise typer.Exit(1)

    reqs = ledger.list_requirements(workspace, status=status_filter)

    if as_json:
        from codeframe.core.proof.serialize import requirement_to_dict

        _emit({"requirements": [requirement_to_dict(r) for r in reqs]})
        return
    if not reqs:
        console.print("No requirements found.")
        return

    table = Table(title=f"Proof Requirements ({len(reqs)})")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Severity")
    table.add_column("Status")
    table.add_column("Gates")

    for req in reqs:
        sev_color = {"critical": "red", "high": "yellow", "medium": "blue", "low": "dim"}.get(
            req.severity.value, "white"
        )
        status_color = {
            "open": "yellow", "satisfied": "green", "waived": "dim"
        }.get(req.status.value, "white")

        table.add_row(
            req.id,
            escape(req.title[:50]),
            f"[{sev_color}]{req.severity.value}[/{sev_color}]",
            f"[{status_color}]{req.status.value}[/{status_color}]",
            ", ".join(o.gate.value for o in req.obligations),
        )

    console.print(table)


@proof_app.command("show")
@_json_capable
def show(
    req_id: str = typer.Argument(help="Requirement ID (e.g., REQ-0001)"),
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Show detailed information about a requirement.

    Example:
        codeframe proof show REQ-0001
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof import ledger

    workspace_path = repo_path or Path.cwd()
    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)

    req = ledger.get_requirement(workspace, req_id)
    if not req:
        console.print(f"[red]Error:[/red] Requirement {escape(req_id)} not found.")
        raise typer.Exit(1)

    if as_json:
        from codeframe.core.proof.serialize import evidence_to_dict, requirement_to_dict

        _emit({
            "requirement": requirement_to_dict(req),
            "evidence": [evidence_to_dict(e) for e in ledger.list_evidence(workspace, req.id)],
        })
        return
    console.print(f"\n[bold]{req.id}[/bold]: {escape(req.title)}")
    console.print(f"  Status: {req.status.value}")
    console.print(f"  Severity: {req.severity.value}")
    console.print(f"  Source: {req.source.value}")
    if req.glitch_type:
        console.print(f"  Glitch type: {req.glitch_type.value}")
    console.print(f"  Created: {req.created_at}")
    if req.source_issue:
        console.print(f"  Issue: {req.source_issue}")

    console.print("\n[bold]Scope:[/bold]")
    for field_name in ("files", "routes", "apis", "components", "tags"):
        items = getattr(req.scope, field_name)
        if items:
            console.print(f"  {field_name}: {', '.join(items)}")

    console.print("\n[bold]Obligations:[/bold]")
    for obl in req.obligations:
        console.print(f"  {obl.gate.value}: {obl.status}")

    if req.waiver:
        console.print("\n[bold]Waiver:[/bold]")
        console.print(f"  Reason: {req.waiver.reason}")
        if req.waiver.expires:
            console.print(f"  Expires: {req.waiver.expires}")
        # The actor is the point of an attributable waiver (#1466): it was
        # recorded but only the API surfaced it.
        if req.waiver.approved_by:
            console.print(f"  Approved by: {escape(req.waiver.approved_by)}")
        if req.waiver.waived_at:
            console.print(f"  Waived at: {req.waiver.waived_at}")

    # Show evidence
    evidence_list = ledger.list_evidence(workspace, req.id)
    if evidence_list:
        console.print(f"\n[bold]Evidence ({len(evidence_list)}):[/bold]")
        for ev in evidence_list[:10]:
            if ev.status == "unverifiable":
                status = "[yellow]UNVERIFIABLE[/yellow]"
            elif ev.satisfied:
                status = "[green]PASS[/green]"
            else:
                # Legacy rows (status=None) fall back to the satisfied bool.
                status = "[red]FAIL[/red]"
            console.print(f"  {ev.gate.value} {status} — {ev.artifact_path}")


@proof_app.command("waive")
def waive(
    req_id: str = typer.Argument(help="Requirement ID to waive"),
    reason: str = typer.Option(..., "--reason", "-r", help="Why this is being waived"),
    expires: Optional[str] = typer.Option(
        None, "--expires", help="Expiry date (YYYY-MM-DD)",
    ),
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
) -> None:
    """Waive a requirement with reason and optional expiry.

    Example:
        codeframe proof waive REQ-0001 --reason "No automated test yet" --expires 2026-04-01
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof import ledger
    from codeframe.core.proof.models import Waiver

    workspace_path = repo_path or Path.cwd()
    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)

    expiry_date = None
    if expires:
        try:
            expiry_date = date.fromisoformat(expires)
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {escape(str(expires))} (use YYYY-MM-DD)")
            raise typer.Exit(1)

    waiver_obj = Waiver(reason=reason, expires=expiry_date, approved_by=cli_actor())
    updated = ledger.waive_requirement(workspace, req_id, waiver_obj)

    if updated:
        console.print(f"[green]✓[/green] {escape(req_id)} waived: {escape(reason)}")
        if expiry_date:
            console.print(f"  Expires: {expiry_date}")
    else:
        console.print(f"[red]Error:[/red] Requirement {escape(req_id)} not found.")
        raise typer.Exit(1)


@proof_app.command("status")
@_json_capable
def status_cmd(
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
    as_json: bool = typer.Option(False, "--json", help=JSON_HELP),
) -> None:
    """Show proof system status — satisfied/failing/waived counts.

    Example:
        codeframe proof status
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof import ledger

    workspace_path = repo_path or Path.cwd()
    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        print_error(e)
        raise typer.Exit(1)

    # Check for expired waivers first
    expired = ledger.check_expired_waivers(workspace)
    if expired:
        console.print(f"[yellow]Expired {len(expired)} waivers → reverted to open[/yellow]\n")

    reqs = ledger.list_requirements(workspace)
    if as_json:
        from codeframe.core.proof.serialize import status_document

        _emit(status_document(reqs, expired, ledger.list_runs(workspace, limit=20)))
        return
    if not reqs:
        # Same framing as `cf proof run` (#1118): an empty ledger means nothing
        # is being verified, which is a state to act on, not a clean bill.
        console.print(
            "[yellow]No proof requirements — nothing in this workspace is "
            "being verified.[/yellow]"
        )
        console.print("Capture your first one with: [bold]cf proof capture[/bold]")
        return

    counts = {"open": 0, "satisfied": 0, "waived": 0}
    for req in reqs:
        counts[req.status.value] = counts.get(req.status.value, 0) + 1

    total = len(reqs)
    console.print(f"[bold]PROOF9 Status[/bold] ({total} requirements)\n")
    console.print(f"  [yellow]Open:[/yellow]      {counts['open']}")
    console.print(f"  [green]Satisfied:[/green] {counts['satisfied']}")
    console.print(f"  [dim]Waived:[/dim]    {counts['waived']}")

    if counts["open"] > 0:
        console.print(f"\n[yellow]{counts['open']} open obligations need attention.[/yellow]")
        console.print("[dim]Run 'cf proof run' to execute obligations.[/dim]")
    else:
        console.print("\n[green]All obligations satisfied or waived.[/green]")
