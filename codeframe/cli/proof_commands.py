"""CLI commands for PROOF9 quality memory system.

Provides `cf proof` subcommands for capturing requirements,
running obligations, managing waivers, and viewing status.
"""

from datetime import date
from pathlib import Path
from typing import Optional

import click
import typer
from rich.console import Console
from rich.table import Table

console = Console()

proof_app = typer.Typer(
    name="proof",
    help="PROOF9 quality memory system — evidence-based verification",
    no_args_is_help=True,
)


@proof_app.command("capture")
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
) -> None:
    """Capture a glitch as a permanent proof requirement.

    Creates a REQ with proof obligations and generates test stubs.
    Interactive when run without arguments.

    Example:
        codeframe proof capture
        codeframe proof capture --title "Login rejects empty password" --severity high
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof.models import Severity, Source
    from codeframe.core.proof.capture import capture_requirement

    workspace_path = repo_path or Path.cwd()
    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Interactive prompts for missing fields
    if not title:
        title = typer.prompt("What happened? (short title)")
    if not description:
        description = typer.prompt("Describe the issue (expected vs actual)")
    if not where:
        where = typer.prompt("Where? (file path, URL, API route, or component)")
    if not severity:
        severity = typer.prompt(
            "Severity", default="medium",
            # click.Choice — typer has no Choice; typer.prompt delegates to
            # click.prompt, so this constrains the interactive input (#723).
            type=click.Choice(["critical", "high", "medium", "low"]),
        )
    if not source:
        source = typer.prompt(
            "Source", default="qa",
            type=click.Choice(["production", "qa", "dogfooding", "monitoring", "user_report"]),
        )

    try:
        sev = Severity(severity)
    except ValueError:
        console.print(f"[red]Error:[/red] Invalid severity: {severity}")
        raise typer.Exit(1)

    try:
        src = Source(source)
    except ValueError:
        console.print(f"[red]Error:[/red] Invalid source: {source}")
        raise typer.Exit(1)

    req, stubs = capture_requirement(
        workspace,
        title=title,
        description=description,
        where=where,
        severity=sev,
        source=src,
        source_issue=source_issue,
    )

    console.print(f"\n[green]✓[/green] Created [bold]{req.id}[/bold]: {req.title}")
    console.print(f"  Glitch type: [cyan]{req.glitch_type.value if req.glitch_type else 'unknown'}[/cyan]")
    console.print(f"  Obligations: {', '.join(o.gate.value for o in req.obligations)}")
    console.print(f"  Scope files: {', '.join(req.scope.files) or 'none'}")
    console.print(f"  Scope routes: {', '.join(req.scope.routes) or 'none'}")

    if stubs:
        console.print("\n[bold]Test stubs written:[/bold]")
        for gate, path in stubs.items():
            try:
                shown = path.relative_to(workspace.repo_path)
            except ValueError:
                shown = path
            console.print(f"  [cyan]{gate.value}[/cyan]: {shown}")


@proof_app.command("run")
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
) -> None:
    """Run proof obligations for current changes.

    Determines which requirements apply to changed files,
    runs their obligations, and collects evidence.

    Exit codes:
        0  obligations ran and none failed
        1  an obligation failed
        2  nothing was verified — no applicable obligations (see --allow-empty)

    Example:
        codeframe proof run
        codeframe proof run --full
        codeframe proof run --gate unit
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof.models import Gate, GateOutcome
    from codeframe.core.proof.runner import run_proof

    workspace_path = repo_path or Path.cwd()
    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    gate_filter = None
    if gate:
        try:
            gate_filter = Gate(gate.lower())
        except ValueError:
            console.print(f"[red]Error:[/red] Unknown gate: {gate}")
            console.print(f"Valid gates: {', '.join(g.value for g in Gate)}")
            raise typer.Exit(1)

    mode = "full" if full else "scope-filtered"
    console.print(f"[dim]Running proof obligations ({mode})...[/dim]")

    results = run_proof(workspace, full=full, gate_filter=gate_filter)

    if not results:
        # `run_proof` returning {} has three causes and they need different
        # answers. Two review rounds went by patching one branch at a time and
        # getting the reason wrong each time, so this asks the runner's own
        # selector instead of inferring it from the mode:
        #
        #   ledger empty        -> nothing to verify at all (the #1118 case)
        #   nothing runnable    -> requirements exist but all SATISFIED/WAIVED
        #                          for this mode; scope was never consulted,
        #                          because run_proof short-circuits first
        #   nothing in scope    -> runnable requirements existed and the scope
        #                          filter excluded every one
        from codeframe.core.proof import ledger as _ledger
        from codeframe.core.proof.models import ReqStatus
        from codeframe.core.proof.runner import _requirements_for_run

        try:
            all_reqs = _ledger.list_requirements(workspace)
            # Same selector the runner uses, so this cannot drift from it.
            runnable = _requirements_for_run(workspace, full=full)
        except Exception:
            # A ledger we cannot read is not evidence of an empty one; fall
            # through to the unverified case rather than inventing a reason.
            all_reqs, runnable = [], []

        if runnable and not full:
            # Scope is only consulted on a scoped run, so this is the one case
            # where "the changed files" is a true explanation.
            console.print(
                f"[yellow]Nothing was verified.[/yellow] "
                f"{len(runnable)} runnable requirement(s), but none apply to "
                f"the changed files."
            )
            console.print(
                "Run [bold]cf proof run --full[/bold] to check all of them "
                "regardless of scope."
            )
            return

        if runnable:
            # --full with runnable requirements and no results: not scope, and
            # not a status filter either. Say only what is known rather than
            # inventing a fourth reason.
            console.print(
                f"[yellow]Nothing was verified.[/yellow] "
                f"{len(runnable)} runnable requirement(s) produced no results."
            )
            console.print("See [bold]cf proof status[/bold] for the ledger.")
            return

        if all_reqs:
            satisfied = sum(1 for r in all_reqs if r.status == ReqStatus.SATISFIED)
            waived = sum(1 for r in all_reqs if r.status == ReqStatus.WAIVED)
            detail = ", ".join(
                part
                for part in (
                    f"{satisfied} satisfied" if satisfied else "",
                    f"{waived} waived" if waived else "",
                )
                if part
            )
            console.print(
                f"[yellow]Nothing was verified.[/yellow] "
                f"{len(all_reqs)} requirement(s) exist, but none are runnable"
                + (f" ({detail})." if detail else ".")
            )
            console.print(
                "A waiver is an accepted risk that no run re-checks; "
                "[bold]cf proof run --full[/bold] also re-verifies satisfied "
                "ones. See [bold]cf proof status[/bold] for the ledger."
            )
            return

        # An empty ledger is not a pass (#1118). Exiting 0 here is what let the
        # quickstart's PROVE step read as "PROOF9 gates passed" when nothing had
        # been checked — and every new workspace is in exactly this state.
        #
        # Exit 2 rather than 1: this is not a failure either, and a script needs
        # to tell "the gate failed" from "the gate had nothing to check". CI
        # treats any non-zero as a stop, which is the point.
        console.print("[yellow]Nothing was verified.[/yellow]")
        console.print(
            "There are no proof obligations in this workspace, so this run "
            "checked nothing — it is not a pass."
        )
        console.print(
            "\nCapture your first requirement with:\n"
            "  [bold]cf proof capture[/bold]"
        )
        if allow_empty:
            console.print("\n[dim]--allow-empty: exiting 0 anyway.[/dim]")
            return
        raise typer.Exit(2)

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
def list_reqs(
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
    status: Optional[str] = typer.Option(
        None, "--status", help="Filter by status (open/satisfied/waived)",
    ),
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
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    status_filter = None
    if status:
        try:
            status_filter = ReqStatus(status.lower())
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid status: {status}")
            raise typer.Exit(1)

    reqs = ledger.list_requirements(workspace, status=status_filter)

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
            req.title[:50],
            f"[{sev_color}]{req.severity.value}[/{sev_color}]",
            f"[{status_color}]{req.status.value}[/{status_color}]",
            ", ".join(o.gate.value for o in req.obligations),
        )

    console.print(table)


@proof_app.command("show")
def show(
    req_id: str = typer.Argument(help="Requirement ID (e.g., REQ-0001)"),
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
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
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    req = ledger.get_requirement(workspace, req_id)
    if not req:
        console.print(f"[red]Error:[/red] Requirement {req_id} not found.")
        raise typer.Exit(1)

    console.print(f"\n[bold]{req.id}[/bold]: {req.title}")
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
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    expiry_date = None
    if expires:
        try:
            expiry_date = date.fromisoformat(expires)
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {expires} (use YYYY-MM-DD)")
            raise typer.Exit(1)

    waiver_obj = Waiver(reason=reason, expires=expiry_date, approved_by="cli-user")
    updated = ledger.waive_requirement(workspace, req_id, waiver_obj)

    if updated:
        console.print(f"[green]✓[/green] {req_id} waived: {reason}")
        if expiry_date:
            console.print(f"  Expires: {expiry_date}")
    else:
        console.print(f"[red]Error:[/red] Requirement {req_id} not found.")
        raise typer.Exit(1)


@proof_app.command("status")
def status_cmd(
    repo_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w", help="Workspace path",
    ),
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
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Check for expired waivers first
    expired = ledger.check_expired_waivers(workspace)
    if expired:
        console.print(f"[yellow]Expired {len(expired)} waivers → reverted to open[/yellow]\n")

    reqs = ledger.list_requirements(workspace)
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
