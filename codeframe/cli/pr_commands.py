"""CLI PR commands for GitHub Pull Request management.

This module provides commands for PR operations:
- create: Create a new PR from current or specified branch
- list: List PRs with optional status filter
- get: Get PR details by number
- merge: Merge a PR with specified strategy
- close: Close a PR without merging
- status: Show PR status for current branch

Usage:
    codeframe pr create --title "My feature"
    codeframe pr list --status open
    codeframe pr get 42
    codeframe pr merge 42 --strategy squash
    codeframe pr close 42
    codeframe pr status
"""

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from codeframe.cli.helpers import console
from codeframe.git.github_integration import GitHubAPIError, GitHubIntegration

logger = logging.getLogger(__name__)


pr_app = typer.Typer(
    name="pr",
    help="Pull request management (create, list, merge, close)",
    no_args_is_help=True,
)


def get_current_branch(repo_path: Optional[Path] = None) -> str:
    """Get the current git branch name.

    Args:
        repo_path: Path to the git repository (defaults to cwd)

    Returns:
        Current branch name

    Raises:
        RuntimeError: If not in a git repository
    """
    cwd = repo_path or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get current branch: {e.stderr}")


def get_git_diff_stats(repo_path: Path, base: str, head: str) -> str:
    """Get diff statistics between two branches.

    Args:
        repo_path: Path to the git repository
        base: Base branch name
        head: Head branch name

    Returns:
        Diff statistics as string
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", f"{base}...{head}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def get_commit_messages(repo_path: Path, base: str, head: str) -> str:
    """Get commit messages between two branches.

    Args:
        repo_path: Path to the git repository
        base: Base branch name
        head: Head branch name

    Returns:
        Commit messages as string
    """
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", f"{base}..{head}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def _get_github_config() -> tuple[str, str]:
    """Get GitHub token and repo from environment.

    Returns:
        Tuple of (token, repo)

    Raises:
        typer.Exit: If configuration is missing
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")

    if not token:
        console.print("[red]Error:[/red] GITHUB_TOKEN environment variable not set.")
        console.print("Set it with: export GITHUB_TOKEN=ghp_yourtoken")
        raise typer.Exit(1)

    if not repo:
        console.print("[red]Error:[/red] GITHUB_REPO environment variable not set.")
        console.print("Set it with: export GITHUB_REPO=owner/repo")
        raise typer.Exit(1)

    return token, repo


def _run_async(coro):
    """Run an async coroutine in a sync context."""
    return asyncio.run(coro)


@pr_app.command("create")
def create_pr(
    branch: Optional[str] = typer.Option(
        None, "--branch", "-b", help="Branch name (defaults to current)"
    ),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="PR title"
    ),
    body: Optional[str] = typer.Option(
        None, "--body", help="PR description body"
    ),
    base: str = typer.Option(
        "main", "--base", help="Base branch to merge into"
    ),
    auto_description: bool = typer.Option(
        True,
        "--auto-description/--no-auto-description",
        help="Auto-generate PR description from commits",
    ),
):
    """Create a new pull request.

    Creates a PR from the current branch (or specified branch) to the base branch.
    Optionally auto-generates a description from commit messages.

    Examples:

        codeframe pr create --title "Add new feature"

        codeframe pr create --branch feature/auth --title "Auth system" --base develop

        codeframe pr create --title "Quick fix" --no-auto-description
    """
    try:
        token, repo = _get_github_config()

        # Get branch name
        if not branch:
            try:
                branch = get_current_branch()
            except RuntimeError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1)

        # Validate not on base branch
        if branch == base:
            console.print(f"[red]Error:[/red] Cannot create PR from '{branch}' to itself.")
            console.print("Please checkout a feature branch first.")
            raise typer.Exit(1)

        # Generate body if auto-description and no body provided
        if auto_description and not body:
            repo_path = Path.cwd()
            commits = get_commit_messages(repo_path, base, branch)
            diff_stats = get_git_diff_stats(repo_path, base, branch)

            body = f"## Changes\n\n{commits}\n\n## Files Changed\n\n```\n{diff_stats}\n```"

        if not body:
            body = ""

        # Title is required
        if not title:
            console.print("[red]Error:[/red] --title is required.")
            raise typer.Exit(1)

        async def _create():
            gh = GitHubIntegration(token=token, repo=repo)
            try:
                pr = await gh.create_pull_request(
                    branch=branch,
                    title=title,
                    body=body,
                    base=base,
                )
                return pr
            finally:
                await gh.close()

        pr = _run_async(_create())

        console.print(f"[green]✓ PR #{pr.number} created successfully[/green]")
        console.print(f"\n[bold]Title:[/bold] {pr.title}")
        console.print(f"[bold]Branch:[/bold] {pr.head_branch} → {pr.base_branch}")
        console.print(f"[bold]URL:[/bold] [link={pr.url}]{pr.url}[/link]")

    except GitHubAPIError as e:
        if e.status_code == 422:
            console.print("[red]Error:[/red] PR already exists for this branch or validation failed.")
            if e.details:
                console.print(f"Details: {e.details}")
        else:
            console.print(f"[red]GitHub API Error ({e.status_code}):[/red] {e.message}")
        raise typer.Exit(1)


@pr_app.command("list")
def list_prs(
    status: str = typer.Option(
        "open", "--status", "-s", help="Filter by status: open, closed, all"
    ),
    format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table or json"
    ),
):
    """List pull requests.

    Shows PRs with optional filtering by status.

    Examples:

        codeframe pr list

        codeframe pr list --status closed

        codeframe pr list --format json
    """
    try:
        token, repo = _get_github_config()

        async def _list():
            gh = GitHubIntegration(token=token, repo=repo)
            try:
                prs = await gh.list_pull_requests(state=status)
                return prs
            finally:
                await gh.close()

        prs = _run_async(_list())

        if format == "json":
            # Convert PRDetails to dicts for JSON output
            pr_dicts = []
            for pr in prs:
                d = asdict(pr)
                # Convert datetime to ISO string
                d["created_at"] = pr.created_at.isoformat() if pr.created_at else None
                d["merged_at"] = pr.merged_at.isoformat() if pr.merged_at else None
                pr_dicts.append(d)
            console.print(json.dumps(pr_dicts, indent=2))
            return

        # Table format
        if not prs:
            console.print(f"[yellow]No {status} pull requests found.[/yellow]")
            return

        table = Table(title=f"Pull Requests ({status})")
        table.add_column("PR #", style="cyan", no_wrap=True)
        table.add_column("Title", max_width=40)
        table.add_column("Branch", style="blue")
        table.add_column("State", style="yellow")
        table.add_column("Created")

        for pr in prs:
            # Format state with color
            state_display = pr.state
            if pr.state == "open":
                state_display = f"[green]{pr.state}[/green]"
            elif pr.merged_at:
                state_display = "[magenta]merged[/magenta]"
            elif pr.state == "closed":
                state_display = f"[red]{pr.state}[/red]"

            table.add_row(
                str(pr.number),
                pr.title[:40] if pr.title else "",
                pr.head_branch,
                state_display,
                pr.created_at.strftime("%Y-%m-%d") if pr.created_at else "",
            )

        console.print(table)

    except GitHubAPIError as e:
        if "rate limit" in e.message.lower():
            console.print("[red]Error:[/red] GitHub API rate limit exceeded.")
            console.print("Please wait and try again later.")
        else:
            console.print(f"[red]GitHub API Error ({e.status_code}):[/red] {e.message}")
        raise typer.Exit(1)


@pr_app.command("get")
def get_pr(
    pr_number: int = typer.Argument(..., help="PR number"),
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text or json"
    ),
):
    """Get pull request details.

    Shows full information about a specific PR.

    Example:

        codeframe pr get 42
    """
    try:
        token, repo = _get_github_config()

        async def _get():
            gh = GitHubIntegration(token=token, repo=repo)
            try:
                pr = await gh.get_pull_request(pr_number)
                return pr
            finally:
                await gh.close()

        pr = _run_async(_get())

        if format == "json":
            d = asdict(pr)
            d["created_at"] = pr.created_at.isoformat() if pr.created_at else None
            d["merged_at"] = pr.merged_at.isoformat() if pr.merged_at else None
            console.print(json.dumps(d, indent=2))
            return

        # Text format
        console.print(f"\n[bold]PR #{pr.number}[/bold] - {pr.title}")
        console.print(f"\n[bold]State:[/bold] {pr.state}")
        console.print(f"[bold]Branch:[/bold] {pr.head_branch} → {pr.base_branch}")
        console.print(f"[bold]Created:[/bold] {pr.created_at.strftime('%Y-%m-%d %H:%M') if pr.created_at else 'N/A'}")

        if pr.merged_at:
            console.print(f"[bold]Merged:[/bold] {pr.merged_at.strftime('%Y-%m-%d %H:%M')}")

        console.print(f"[bold]URL:[/bold] {pr.url}")

        if pr.body:
            console.print(f"\n[bold]Description:[/bold]\n{pr.body}")

    except GitHubAPIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] PR #{pr_number} not found")
        else:
            console.print(f"[red]GitHub API Error ({e.status_code}):[/red] {e.message}")
        raise typer.Exit(1)


@pr_app.command("merge")
def merge_pr(
    pr_number: int = typer.Argument(..., help="PR number to merge"),
    strategy: str = typer.Option(
        "squash",
        "--strategy",
        "-s",
        help="Merge strategy: squash, merge, rebase",
    ),
):
    """Merge a pull request.

    Merges the specified PR using the chosen merge strategy.

    Examples:

        codeframe pr merge 42

        codeframe pr merge 42 --strategy rebase
    """
    try:
        token, repo = _get_github_config()

        async def _merge():
            gh = GitHubIntegration(token=token, repo=repo)
            try:
                # First check PR state
                pr = await gh.get_pull_request(pr_number)

                if pr.merged_at:
                    console.print(f"[yellow]PR #{pr_number} is already merged.[/yellow]")
                    return None

                if pr.state != "open":
                    console.print(f"[yellow]PR #{pr_number} is {pr.state} and cannot be merged.[/yellow]")
                    return None

                # Merge the PR
                result = await gh.merge_pull_request(pr_number, method=strategy)
                return result
            finally:
                await gh.close()

        result = _run_async(_merge())

        if result is None:
            raise typer.Exit(0)

        if result.merged:
            console.print(f"[green]✓ PR #{pr_number} merged successfully[/green]")
            if result.sha:
                console.print(f"[bold]Merge commit:[/bold] {result.sha[:7]}")
            console.print(f"[bold]Strategy:[/bold] {strategy}")
        else:
            console.print(f"[red]Error:[/red] Merge failed: {result.message}")
            raise typer.Exit(1)

    except GitHubAPIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] PR #{pr_number} not found")
        elif e.status_code == 405:
            console.print("[red]Error:[/red] PR cannot be merged (check for conflicts)")
        else:
            console.print(f"[red]GitHub API Error ({e.status_code}):[/red] {e.message}")
        raise typer.Exit(1)


@pr_app.command("close")
def close_pr(
    pr_number: int = typer.Argument(..., help="PR number to close"),
):
    """Close a pull request without merging.

    Example:

        codeframe pr close 42
    """
    try:
        token, repo = _get_github_config()

        async def _close():
            gh = GitHubIntegration(token=token, repo=repo)
            try:
                # First check PR exists
                pr = await gh.get_pull_request(pr_number)

                if pr.state == "closed":
                    console.print(f"[yellow]PR #{pr_number} is already closed.[/yellow]")
                    return None

                # Close the PR
                result = await gh.close_pull_request(pr_number)
                return result
            finally:
                await gh.close()

        result = _run_async(_close())

        if result is None:
            # Already closed - message already printed
            raise typer.Exit(0)

        if result:
            console.print(f"[green]✓ PR #{pr_number} closed[/green]")
        else:
            console.print(f"[red]Error:[/red] Failed to close PR #{pr_number}")
            raise typer.Exit(1)

    except GitHubAPIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] PR #{pr_number} not found")
        else:
            console.print(f"[red]GitHub API Error ({e.status_code}):[/red] {e.message}")
        raise typer.Exit(1)


@pr_app.command("status")
def pr_status():
    """Show PR status for current branch.

    Checks if there's an open PR for the current branch and displays its status.

    Example:

        codeframe pr status
    """
    try:
        token, repo = _get_github_config()

        try:
            current_branch = get_current_branch()
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        async def _status():
            gh = GitHubIntegration(token=token, repo=repo)
            try:
                prs = await gh.list_pull_requests(state="open")
                # Find PR for current branch
                for pr in prs:
                    if pr.head_branch == current_branch:
                        return pr
                return None
            finally:
                await gh.close()

        pr = _run_async(_status())

        if pr:
            console.print(f"\n[bold]PR #{pr.number}[/bold] - {pr.title}")
            console.print(f"[bold]State:[/bold] [green]{pr.state}[/green]")
            console.print(f"[bold]Branch:[/bold] {pr.head_branch} → {pr.base_branch}")
            console.print(f"[bold]URL:[/bold] {pr.url}")
        else:
            console.print(f"[yellow]No open PR found for branch '{current_branch}'[/yellow]")
            console.print("\nCreate one with: codeframe pr create --title \"Your PR title\"")

    except GitHubAPIError as e:
        console.print(f"[red]GitHub API Error ({e.status_code}):[/red] {e.message}")
        raise typer.Exit(1)
