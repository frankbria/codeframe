#!/usr/bin/env python3
"""
Quality Ratchet System

Tracks quality metrics (test pass rate, coverage) across AI conversation sessions
to detect degradation before it becomes a problem.

Usage:
    python scripts/quality-ratchet.py record --response-count 5
    python scripts/quality-ratchet.py check
    python scripts/quality-ratchet.py stats
    python scripts/quality-ratchet.py reset --yes

Key Features:
- Tracks test pass rate and coverage percentage
- Detects >10% degradation from peak quality
- Provides moving average (last 3 checkpoints)
- Recommends context reset when quality degrades

Based on issue #14 recommendations.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Quality Ratchet - Track code quality across sessions")
console = Console()

# Default history file location
DEFAULT_HISTORY_FILE = Path(".claude") / "quality_history.json"


def load_history(history_file: str = None) -> List[Dict]:
    """
    Load quality history from JSON file.

    Args:
        history_file: Path to history file (default: .claude/quality_history.json)

    Returns:
        List of quality checkpoints
    """
    if history_file is None:
        history_file = str(DEFAULT_HISTORY_FILE)

    path = Path(history_file)

    if not path.exists():
        return []

    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        console.print(f"[yellow]Warning: Could not read history file {history_file}[/yellow]")
        return []


def save_history(history: List[Dict], history_file: str = None) -> None:
    """
    Save quality history to JSON file.

    Args:
        history: List of quality checkpoints
        history_file: Path to history file (default: .claude/quality_history.json)
    """
    if history_file is None:
        history_file = str(DEFAULT_HISTORY_FILE)

    path = Path(history_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(history, f, indent=2)


def run_tests() -> Dict[str, float]:
    """
    Run pytest with JSON report to collect test metrics.

    Returns:
        Dict with test_count, passed_count, failed_count, pass_rate
    """
    report_file = Path(".report.json")

    # Run pytest with JSON report
    result = subprocess.run(
        ["pytest", "--json-report", f"--json-report-file={report_file}"],
        capture_output=True,
        text=True,
    )

    if not report_file.exists():
        console.print("[yellow]Warning: pytest JSON report not found, using defaults[/yellow]")
        return {
            "test_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "pass_rate": 0.0,
        }

    try:
        with open(report_file, "r") as f:
            report = json.load(f)

        summary = report.get("summary", {})
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)

        pass_rate = (passed / total * 100) if total > 0 else 0.0

        return {
            "test_count": total,
            "passed_count": passed,
            "failed_count": total - passed,
            "pass_rate": round(pass_rate, 1),
        }
    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[yellow]Warning: Could not parse test report: {e}[/yellow]")
        return {
            "test_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "pass_rate": 0.0,
        }
    finally:
        # Clean up report file
        if report_file.exists():
            report_file.unlink()


def get_coverage() -> float:
    """
    Get coverage percentage from coverage.json.

    Returns:
        Coverage percentage (0-100)
    """
    coverage_file = Path("coverage.json")

    if not coverage_file.exists():
        # Try to generate coverage
        subprocess.run(["pytest", "--cov", "--cov-report=json"], capture_output=True, text=True)

    if not coverage_file.exists():
        console.print("[yellow]Warning: coverage.json not found, using default[/yellow]")
        return 0.0

    try:
        with open(coverage_file, "r") as f:
            data = json.load(f)

        percent_covered = data.get("totals", {}).get("percent_covered", 0.0)
        return round(percent_covered, 1)

    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[yellow]Warning: Could not parse coverage.json: {e}[/yellow]")
        return 0.0


def calculate_moving_average(history: List[Dict], window: int = 3) -> Optional[Dict[str, float]]:
    """
    Calculate moving average of quality metrics.

    Args:
        history: List of quality checkpoints
        window: Number of recent entries to average (default: 3)

    Returns:
        Dict with averaged metrics or None if history is empty
    """
    if not history:
        return None

    recent = history[-window:]

    avg_pass_rate = sum(e["test_pass_rate"] for e in recent) / len(recent)
    avg_coverage = sum(e["coverage_percentage"] for e in recent) / len(recent)

    return {
        "test_pass_rate": round(avg_pass_rate, 1),
        "coverage_percentage": round(avg_coverage, 1),
    }


def find_peak_quality(history: List[Dict]) -> Optional[Dict]:
    """
    Find the peak quality checkpoint in history.

    Peak is defined as the checkpoint with highest combined score:
    score = (test_pass_rate + coverage_percentage) / 2

    Args:
        history: List of quality checkpoints

    Returns:
        Peak checkpoint or None if history is empty
    """
    if not history:
        return None

    def score(checkpoint: Dict) -> float:
        return (checkpoint["test_pass_rate"] + checkpoint["coverage_percentage"]) / 2

    return max(history, key=score)


def detect_degradation(history: List[Dict]) -> Optional[Dict]:
    """
    Detect quality degradation comparing recent metrics to peak.

    Degradation is detected when:
    - Recent < Peak - 10% for coverage
    - Recent < Peak - 10% for pass rate

    For histories with ≥3 entries: uses moving average (last 3)
    For histories with <3 entries: uses latest entry

    Args:
        history: List of quality checkpoints

    Returns:
        Dict with degradation info or None if no degradation
    """
    if len(history) < 2:
        return {"has_degradation": False, "message": "Not enough data"}

    peak = find_peak_quality(history)

    # For small histories, compare latest directly to peak
    # For larger histories, use moving average
    if len(history) < 3:
        recent = history[-1]
    else:
        recent = calculate_moving_average(history, window=3)

    if not peak or not recent:
        return {"has_degradation": False, "message": "Insufficient data"}

    coverage_drop = peak["coverage_percentage"] - recent["coverage_percentage"]
    pass_rate_drop = peak["test_pass_rate"] - recent["test_pass_rate"]

    has_coverage_degradation = coverage_drop > 10.0
    has_pass_rate_degradation = pass_rate_drop > 10.0

    if has_coverage_degradation or has_pass_rate_degradation:
        issues = []
        if has_coverage_degradation:
            issues.append(
                f"Coverage: {recent['coverage_percentage']:.1f}% (peak: {peak['coverage_percentage']:.1f}%, drop: {coverage_drop:.1f}%)"
            )
        if has_pass_rate_degradation:
            issues.append(
                f"Pass rate: {recent['test_pass_rate']:.1f}% (peak: {peak['test_pass_rate']:.1f}%, drop: {pass_rate_drop:.1f}%)"
            )

        return {
            "has_degradation": True,
            "coverage_drop": coverage_drop,
            "pass_rate_drop": pass_rate_drop,
            "issues": issues,
        }

    return {"has_degradation": False, "message": "Quality stable"}


@app.command()
def record(
    response_count: int = typer.Option(
        ..., "--response-count", help="Number of AI responses in current session"
    ),
    history_file: str = typer.Option(None, "--history-file", help="Path to history file"),
) -> None:
    """
    Record current quality metrics to history.

    Runs tests, collects coverage, and saves checkpoint.
    """
    console.print("[bold blue]Recording quality checkpoint...[/bold blue]")

    # Get test metrics
    console.print("Running tests...")
    test_metrics = run_tests()

    # Get coverage
    console.print("Getting coverage...")
    coverage = get_coverage()

    # Create checkpoint
    checkpoint = {
        "timestamp": datetime.now().isoformat(),
        "response_count": response_count,
        "test_pass_rate": test_metrics["pass_rate"],
        "coverage_percentage": coverage,
    }

    # Load history, append, save
    history = load_history(history_file)
    history.append(checkpoint)
    save_history(history, history_file)

    console.print("[green]✓[/green] Checkpoint recorded:")
    console.print(f"  Response count: {response_count}")
    console.print(f"  Pass rate: {test_metrics['pass_rate']}%")
    console.print(f"  Coverage: {coverage}%")
    console.print(f"  Total checkpoints: {len(history)}")


@app.command()
def check(
    history_file: str = typer.Option(None, "--history-file", help="Path to history file"),
) -> None:
    """
    Check for quality degradation.

    Compares recent average to peak and recommends context reset if degraded.
    """
    console.print("[bold blue]Checking for quality degradation...[/bold blue]")

    history = load_history(history_file)

    if not history:
        console.print("[yellow]No history found. Run 'record' first.[/yellow]")
        raise typer.Exit(1)

    degradation = detect_degradation(history)

    if degradation["has_degradation"]:
        console.print("\n[bold red]⚠️  QUALITY DEGRADATION DETECTED[/bold red]\n")

        for issue in degradation["issues"]:
            console.print(f"  • {issue}")

        console.print("\n[bold yellow]RECOMMENDATION: Consider context reset[/bold yellow]")
        console.print("  1. Save current state")
        console.print("  2. Create context handoff using template in .claude/rules.md")
        console.print("  3. Start fresh conversation with handoff context")

        raise typer.Exit(1)
    else:
        console.print(f"[green]✓ Quality stable[/green] - {degradation['message']}")


@app.command()
def stats(
    history_file: str = typer.Option(None, "--history-file", help="Path to history file"),
) -> None:
    """
    Display quality statistics with Rich table.
    """
    history = load_history(history_file)

    if not history:
        console.print("[yellow]No history found. Run 'record' first.[/yellow]")
        return

    current = history[-1]
    peak = find_peak_quality(history)
    avg = calculate_moving_average(history, window=3)

    table = Table(title="Quality Ratchet Statistics", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Current", style="green")
    table.add_column("Peak", style="yellow")
    table.add_column("Average (last 3)", style="blue")

    table.add_row(
        "Pass Rate",
        f"{current['test_pass_rate']:.1f}%",
        f"{peak['test_pass_rate']:.1f}%",
        f"{avg['test_pass_rate']:.1f}%",
    )

    table.add_row(
        "Coverage",
        f"{current['coverage_percentage']:.1f}%",
        f"{peak['coverage_percentage']:.1f}%",
        f"{avg['coverage_percentage']:.1f}%",
    )

    console.print(table)
    console.print(f"\nTotal checkpoints: {len(history)}")
    console.print(f"Latest: {current['timestamp']}")


@app.command()
def reset(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
    history_file: str = typer.Option(None, "--history-file", help="Path to history file"),
) -> None:
    """
    Reset quality history (clear all checkpoints).
    """
    if not yes:
        confirm = typer.confirm("Are you sure you want to clear all quality history?")
        if not confirm:
            console.print("Cancelled.")
            return

    save_history([], history_file)
    console.print("[green]✓ Quality history reset[/green]")


if __name__ == "__main__":
    app()
