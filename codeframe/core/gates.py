"""Verification gates for CodeFRAME v2.

Gates are automated checks that run before code is considered complete.
MVP gates: pytest, ruff/lint.

This module is headless - no FastAPI or HTTP dependencies.
"""

import re
import subprocess
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from codeframe.core.workspace import Workspace
from codeframe.core import events


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


_RUFF_ERROR_PATTERN = re.compile(r'^(.+?):(\d+):(\d+): ([A-Z]+\d+) (.+)$')


def _parse_ruff_errors(output: str) -> list[dict[str, Any]]:
    """Parse ruff output into structured error dicts.

    Parses lines matching the pattern: path/file.py:10:5: E501 Line too long

    Args:
        output: Raw ruff stdout/stderr output.

    Returns:
        List of dicts with keys: file, line, col, code, message.
    """
    errors = []
    for line in output.splitlines():
        match = _RUFF_ERROR_PATTERN.match(line.strip())
        if match:
            errors.append({
                "file": match.group(1),
                "line": int(match.group(2)),
                "col": int(match.group(3)),
                "code": match.group(4),
                "message": match.group(5),
            })
    return errors


class GateStatus(str, Enum):
    """Status of a gate check."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class GateCheck:
    """Result of a single gate check.

    Attributes:
        name: Gate name (e.g., 'pytest', 'ruff')
        status: Pass/fail/skip status
        exit_code: Process exit code (if run)
        output: Captured stdout/stderr
        duration_ms: How long the check took
        detailed_errors: Structured error list parsed from tool output
    """

    name: str
    status: GateStatus
    exit_code: Optional[int] = None
    output: str = ""
    duration_ms: int = 0
    detailed_errors: Optional[list[dict[str, Any]]] = None


@dataclass
class GateResult:
    """Result of running all gates.

    Attributes:
        passed: Whether all gates passed
        checks: List of individual gate checks
        started_at: When gates started
        completed_at: When gates completed
    """

    passed: bool
    checks: list[GateCheck] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def summary(self) -> str:
        """Human-readable summary."""
        passed_count = sum(1 for c in self.checks if c.status == GateStatus.PASSED)
        failed_count = sum(1 for c in self.checks if c.status == GateStatus.FAILED)
        skipped_count = sum(1 for c in self.checks if c.status == GateStatus.SKIPPED)
        error_count = sum(1 for c in self.checks if c.status == GateStatus.ERROR)

        parts = []
        if passed_count:
            parts.append(f"{passed_count} passed")
        if failed_count:
            parts.append(f"{failed_count} failed")
        if error_count:
            parts.append(f"{error_count} errors")
        if skipped_count:
            parts.append(f"{skipped_count} skipped")

        return ", ".join(parts) if parts else "no checks run"

    def get_error_summary(self) -> str:
        """Format all errors into a readable multi-line string.

        Returns:
            Newline-separated string of all structured errors from failed checks,
            or empty string if no errors.
        """
        lines = []
        for check in self.checks:
            if check.detailed_errors:
                for err in check.detailed_errors:
                    lines.append(
                        f"{err['file']}:{err['line']}:{err['col']}: "
                        f"{err['code']} {err['message']}"
                    )
        return "\n".join(lines)

    def get_errors_by_file(self) -> dict[str, list[str]]:
        """Group error messages by file path.

        Returns:
            Dict mapping file paths to lists of formatted error strings.
        """
        by_file: dict[str, list[str]] = {}
        for check in self.checks:
            if check.detailed_errors:
                for err in check.detailed_errors:
                    file_path = err["file"]
                    msg = f"{err['code']} {err['message']} (line {err['line']})"
                    by_file.setdefault(file_path, []).append(msg)
        return by_file


def run(
    workspace: Workspace,
    gates: Optional[list[str]] = None,
    verbose: bool = False,
) -> GateResult:
    """Run verification gates.

    Args:
        workspace: Target workspace
        gates: Specific gates to run (None = all available)
        verbose: Whether to capture full output

    Returns:
        GateResult with all check results
    """
    started_at = _utc_now()

    # Track whether gates were explicitly provided (vs auto-detected)
    gates_explicitly_provided = gates is not None

    # Emit gates started event - report actual provided list or ["auto"]
    events.emit_for_workspace(
        workspace,
        events.EventType.GATES_STARTED,
        {"gates": gates if gates is not None else ["auto"]},
        print_event=True,
    )

    checks: list[GateCheck] = []
    repo_path = workspace.repo_path

    # Determine which gates to run
    if gates is None:
        gates = _detect_available_gates(repo_path)

    # Known gate names
    known_gates = {"pytest", "ruff", "mypy", "npm-test", "npm-lint"}

    # Run each gate
    for gate_name in gates:
        if gate_name == "pytest":
            check = _run_pytest(repo_path, verbose)
        elif gate_name == "ruff":
            check = _run_ruff(repo_path, verbose)
        elif gate_name == "mypy":
            check = _run_mypy(repo_path, verbose)
        elif gate_name == "npm-test":
            check = _run_npm_test(repo_path, verbose)
        elif gate_name == "npm-lint":
            check = _run_npm_lint(repo_path, verbose)
        else:
            # Unknown gate: FAILED if explicitly requested, SKIPPED if auto-detected
            if gates_explicitly_provided:
                check = GateCheck(
                    name=gate_name,
                    status=GateStatus.FAILED,
                    output=f"Unknown gate: {gate_name}. Valid gates: {', '.join(sorted(known_gates))}",
                )
            else:
                check = GateCheck(
                    name=gate_name,
                    status=GateStatus.SKIPPED,
                    output=f"Unknown gate: {gate_name}",
                )

        checks.append(check)

    completed_at = _utc_now()

    # Determine overall pass/fail
    passed = all(
        c.status in (GateStatus.PASSED, GateStatus.SKIPPED) for c in checks
    )

    result = GateResult(
        passed=passed,
        checks=checks,
        started_at=started_at,
        completed_at=completed_at,
    )

    # Emit gates completed event
    events.emit_for_workspace(
        workspace,
        events.EventType.GATES_COMPLETED,
        {
            "passed": passed,
            "summary": result.summary,
            "checks": [{"name": c.name, "status": c.status.value} for c in checks],
        },
        print_event=True,
    )

    return result


def _detect_available_gates(repo_path: Path) -> list[str]:
    """Detect which gates are available in the repo."""
    gates = []

    # Python: pytest
    if (repo_path / "pytest.ini").exists() or \
       (repo_path / "pyproject.toml").exists() or \
       (repo_path / "setup.py").exists() or \
       (repo_path / "tests").is_dir():
        gates.append("pytest")

    # Python: ruff (available via direct command or via uv)
    if (shutil.which("ruff") or shutil.which("uv")) and (
        (repo_path / "pyproject.toml").exists() or
        (repo_path / "ruff.toml").exists() or
        any(repo_path.glob("*.py"))
    ):
        gates.append("ruff")

    # Node.js: npm test
    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            import json
            pkg = json.loads(package_json.read_text())
            scripts = pkg.get("scripts", {})
            if "test" in scripts:
                gates.append("npm-test")
            if "lint" in scripts:
                gates.append("npm-lint")
        except Exception:
            pass

    return gates


def _run_pytest(repo_path: Path, verbose: bool = False) -> GateCheck:
    """Run pytest."""
    import time

    start = time.time()

    # Check if pytest is available
    if not shutil.which("pytest") and not shutil.which("uv"):
        return GateCheck(
            name="pytest",
            status=GateStatus.SKIPPED,
            output="pytest not found",
        )

    try:
        # Try uv run pytest first, fall back to pytest
        if shutil.which("uv"):
            cmd = ["uv", "run", "pytest", "-v", "--tb=short"]
        else:
            cmd = ["pytest", "-v", "--tb=short"]

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        duration_ms = int((time.time() - start) * 1000)

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        # Truncate output if too long
        if len(output) > 10000:
            output = output[:5000] + "\n...[truncated]...\n" + output[-5000:]

        return GateCheck(
            name="pytest",
            status=GateStatus.PASSED if result.returncode == 0 else GateStatus.FAILED,
            exit_code=result.returncode,
            output=output if verbose else _summarize_pytest_output(output),
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        return GateCheck(
            name="pytest",
            status=GateStatus.ERROR,
            output="Timeout after 5 minutes",
        )
    except Exception as e:
        return GateCheck(
            name="pytest",
            status=GateStatus.ERROR,
            output=str(e),
        )


def _run_ruff(repo_path: Path, verbose: bool = False) -> GateCheck:
    """Run ruff linter."""
    import time

    start = time.time()

    # Check if ruff is available (either directly or via uv)
    if not shutil.which("ruff") and not shutil.which("uv"):
        return GateCheck(
            name="ruff",
            status=GateStatus.SKIPPED,
            output="ruff not found",
        )

    try:
        # Use uv run ruff if uv is available (runs in target project's environment)
        # This ensures ruff runs with the target project's dependencies
        if shutil.which("uv"):
            cmd = ["uv", "run", "ruff", "check", "."]
        else:
            cmd = ["ruff", "check", "."]

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        duration_ms = int((time.time() - start) * 1000)

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        check = GateCheck(
            name="ruff",
            status=GateStatus.PASSED if result.returncode == 0 else GateStatus.FAILED,
            exit_code=result.returncode,
            output=output if verbose else _summarize_ruff_output(output),
            duration_ms=duration_ms,
        )

        # Parse detailed errors for failed checks
        if check.status == GateStatus.FAILED:
            check.detailed_errors = _parse_ruff_errors(output)

        return check

    except subprocess.TimeoutExpired:
        return GateCheck(
            name="ruff",
            status=GateStatus.ERROR,
            output="Timeout after 60 seconds",
        )
    except Exception as e:
        return GateCheck(
            name="ruff",
            status=GateStatus.ERROR,
            output=str(e),
        )


def _run_mypy(repo_path: Path, verbose: bool = False) -> GateCheck:
    """Run mypy type checker."""
    import time

    start = time.time()

    if not shutil.which("mypy"):
        return GateCheck(
            name="mypy",
            status=GateStatus.SKIPPED,
            output="mypy not found",
        )

    try:
        result = subprocess.run(
            ["mypy", "."],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        duration_ms = int((time.time() - start) * 1000)

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return GateCheck(
            name="mypy",
            status=GateStatus.PASSED if result.returncode == 0 else GateStatus.FAILED,
            exit_code=result.returncode,
            output=output[:2000] if not verbose else output,
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        return GateCheck(
            name="mypy",
            status=GateStatus.ERROR,
            output="Timeout after 120 seconds",
        )
    except Exception as e:
        return GateCheck(
            name="mypy",
            status=GateStatus.ERROR,
            output=str(e),
        )


def _run_npm_test(repo_path: Path, verbose: bool = False) -> GateCheck:
    """Run npm test."""
    import time

    start = time.time()

    if not shutil.which("npm"):
        return GateCheck(
            name="npm-test",
            status=GateStatus.SKIPPED,
            output="npm not found",
        )

    try:
        result = subprocess.run(
            ["npm", "test"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=300,
        )

        duration_ms = int((time.time() - start) * 1000)

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return GateCheck(
            name="npm-test",
            status=GateStatus.PASSED if result.returncode == 0 else GateStatus.FAILED,
            exit_code=result.returncode,
            output=output[:5000] if not verbose else output,
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        return GateCheck(
            name="npm-test",
            status=GateStatus.ERROR,
            output="Timeout after 5 minutes",
        )
    except Exception as e:
        return GateCheck(
            name="npm-test",
            status=GateStatus.ERROR,
            output=str(e),
        )


def _run_npm_lint(repo_path: Path, verbose: bool = False) -> GateCheck:
    """Run npm run lint."""
    import time

    start = time.time()

    if not shutil.which("npm"):
        return GateCheck(
            name="npm-lint",
            status=GateStatus.SKIPPED,
            output="npm not found",
        )

    try:
        result = subprocess.run(
            ["npm", "run", "lint"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        duration_ms = int((time.time() - start) * 1000)

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return GateCheck(
            name="npm-lint",
            status=GateStatus.PASSED if result.returncode == 0 else GateStatus.FAILED,
            exit_code=result.returncode,
            output=output[:2000] if not verbose else output,
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        return GateCheck(
            name="npm-lint",
            status=GateStatus.ERROR,
            output="Timeout after 120 seconds",
        )
    except Exception as e:
        return GateCheck(
            name="npm-lint",
            status=GateStatus.ERROR,
            output=str(e),
        )


def _summarize_pytest_output(output: str) -> str:
    """Extract key summary from pytest output."""
    lines = output.split("\n")

    # Look for the summary line (e.g., "5 passed in 1.23s")
    for line in reversed(lines):
        if "passed" in line or "failed" in line or "error" in line:
            if "=" in line or "passed" in line.lower():
                return line.strip()

    # Fall back to last non-empty lines
    non_empty = [line.strip() for line in lines if line.strip()]
    if non_empty:
        return "\n".join(non_empty[-3:])

    return output[:500]


def _summarize_ruff_output(output: str) -> str:
    """Extract key summary from ruff output."""
    if not output.strip():
        return "No issues found"

    lines = output.strip().split("\n")

    # Count issues
    issue_count = len([line for line in lines if line.strip() and not line.startswith("Found")])

    # Look for "Found X errors" line
    for line in lines:
        if "Found" in line and ("error" in line or "warning" in line):
            return line.strip()

    if issue_count > 0:
        return f"{issue_count} issues found"

    return output[:500]
