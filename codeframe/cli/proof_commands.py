"""CLI commands for PROOF9 quality memory system.

Provides `cf proof` subcommands for capturing requirements,
running obligations, managing waivers, and viewing status.
"""

from datetime import date
from pathlib import Path
from typing import Optional

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
            type=typer.Choice(["critical", "high", "medium", "low"]),
        )
    if not source:
        source = typer.prompt(
            "Source", default="qa",
            type=typer.Choice(["production", "qa", "dogfooding", "monitoring", "user_report"]),
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
        console.print("\n[bold]Generated test stubs:[/bold]")
        for gate, content in stubs.items():
            lines = len(content.splitlines())
            console.print(f"  [cyan]{gate.value}[/cyan]: {lines} lines")


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
) -> None:
    """Run proof obligations for current changes.

    Determines which requirements apply to changed files,
    runs their obligations, and collects evidence.

    Example:
        codeframe proof run
        codeframe proof run --full
        codeframe proof run --gate unit
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core.proof.models import Gate
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
        console.print("[green]No applicable obligations found.[/green]")
        return

    # Display results
    table = Table(title="Proof Results")
    table.add_column("REQ", style="cyan")
    table.add_column("Gate", style="blue")
    table.add_column("Result", style="bold")

    all_pass = True
    for req_id, gate_results in results.items():
        for g, passed in gate_results:
            status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
            if not passed:
                all_pass = False
            table.add_row(req_id, g.value, status)

    console.print(table)

    if all_pass:
        console.print("\n[green]All obligations satisfied.[/green]")
    else:
        console.print("\n[red]Some obligations failed.[/red] Fix issues and re-run.")
        raise typer.Exit(1)


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
            status = "[green]PASS[/green]" if ev.satisfied else "[red]FAIL[/red]"
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
        console.print("No proof requirements. Use 'cf proof capture' to add one.")
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
