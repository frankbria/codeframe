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
from typing import Any, Callable, Optional

from codeframe.core.workspace import Workspace
from codeframe.core import events


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


_RUFF_ERROR_PATTERN = re.compile(r'^(.+?):(\d+):(\d+): ([A-Z]+\d+) (.+)$')
_TSC_ERROR_PATTERN = re.compile(r'^(.+?)\((\d+),(\d+)\): error (TS\d+): (.+)$')


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


def _parse_tsc_errors(output: str) -> list[dict[str, Any]]:
    """Parse TypeScript compiler output into structured error dicts.

    Parses lines matching the pattern: src/file.ts(10,5): error TS2339: Property does not exist

    Args:
        output: Raw tsc stdout/stderr output.

    Returns:
        List of dicts with keys: file, line, col, code, message.
    """
    errors = []
    for line in output.splitlines():
        match = _TSC_ERROR_PATTERN.match(line.strip())
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


def _ensure_dependencies_installed(
    repo_path: Path,
    auto_install: bool = True,
) -> tuple[bool, str]:
    """Ensure project dependencies are installed before running test gates.

    Checks for missing dependencies and optionally installs them:
    - Python: If requirements.txt exists but no .venv/ or venv/ directory
    - Node.js: If package.json exists but no node_modules/ directory

    Args:
        repo_path: Path to the repository root
        auto_install: Whether to auto-install missing dependencies (default: True)

    Returns:
        Tuple of (success: bool, message: str)
        - success=True means deps installed or already present
        - success=False means installation failed
    """
    messages = []

    # Check Python dependencies
    requirements_txt = repo_path / "requirements.txt"
    venv_dirs = [repo_path / ".venv", repo_path / "venv"]
    has_venv = any(d.exists() and d.is_dir() for d in venv_dirs)

    if requirements_txt.exists() and not has_venv:
        if not auto_install:
            messages.append("Python dependencies not installed (auto-install disabled)")
        else:
            # Try to install using uv first, fallback to pip
            uv_bin = shutil.which("uv")
            pip_bin = shutil.which("pip")

            if uv_bin:
                try:
                    result = subprocess.run(
                        ["uv", "pip", "install", "-r", str(requirements_txt)],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minutes
                    )
                    if result.returncode == 0:
                        messages.append(f"Installed Python dependencies via uv: {requirements_txt.name}")
                    else:
                        return False, f"Failed to install Python dependencies: {result.stderr}"
                except Exception as e:
                    return False, f"Error installing Python dependencies: {e}"
            elif pip_bin:
                try:
                    result = subprocess.run(
                        ["pip", "install", "-r", str(requirements_txt)],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    if result.returncode == 0:
                        messages.append(f"Installed Python dependencies via pip: {requirements_txt.name}")
                    else:
                        return False, f"Failed to install Python dependencies: {result.stderr}"
                except Exception as e:
                    return False, f"Error installing Python dependencies: {e}"
            else:
                messages.append("Python dependencies needed but no package manager found (uv/pip)")
    elif requirements_txt.exists() and has_venv:
        messages.append("Python dependencies already installed (venv exists)")

    # Check Node.js dependencies
    package_json = repo_path / "package.json"
    node_modules = repo_path / "node_modules"

    if package_json.exists() and not node_modules.exists():
        if not auto_install:
            messages.append("Node dependencies not installed (auto-install disabled)")
        else:
            npm_bin = shutil.which("npm")

            if npm_bin:
                try:
                    result = subprocess.run(
                        ["npm", "install"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minutes
                    )
                    if result.returncode == 0:
                        messages.append("Installed Node dependencies via npm")
                    else:
                        return False, f"Failed to install Node dependencies: {result.stderr}"
                except Exception as e:
                    return False, f"Error installing Node dependencies: {e}"
            else:
                messages.append("Node dependencies needed but npm not found")
    elif package_json.exists() and node_modules.exists():
        messages.append("Node dependencies already installed (node_modules exists)")

    # Success if we get here
    if not messages:
        return True, "No dependency checks needed"
    return True, " | ".join(messages)


def run(
    workspace: Workspace,
    gates: Optional[list[str]] = None,
    verbose: bool = False,
    auto_install_deps: bool = True,
) -> GateResult:
    """Run verification gates.

    Args:
        workspace: Target workspace
        gates: Specific gates to run (None = all available)
        verbose: Whether to capture full output
        auto_install_deps: Whether to auto-install missing dependencies before test gates (default: True)

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

    # PRE-FLIGHT: Ensure dependencies are installed before running test gates
    dep_success, dep_message = _ensure_dependencies_installed(
        workspace.repo_path,
        auto_install=auto_install_deps,
    )
    if verbose:
        print(f"[gates] Dependency check: {dep_message}")

    # If dependency installation fails, create an ERROR check and return early
    if not dep_success:
        check = GateCheck(
            name="dependency-check",
            status=GateStatus.ERROR,
            output=f"Dependency installation failed: {dep_message}",
        )
        result = GateResult(
            passed=False,
            checks=[check],
            started_at=started_at,
            completed_at=_utc_now(),
        )
        events.emit_for_workspace(
            workspace,
            events.EventType.GATES_COMPLETED,
            {
                "passed": False,
                "summary": "Dependency installation failed",
                "checks": [{"name": check.name, "status": check.status.value}],
            },
            print_event=True,
        )
        return result

    checks: list[GateCheck] = []
    repo_path = workspace.repo_path

    # Determine which gates to run
    if gates is None:
        gates = _detect_available_gates(repo_path)

    # Known gate names
    known_gates = {"pytest", "ruff", "mypy", "npm-test", "npm-lint", "tsc"}

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
        elif gate_name == "tsc":
            check = _run_tsc(repo_path, verbose)
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

    # TypeScript: tsc type checking
    if (repo_path / "tsconfig.json").exists():
        gates.append("tsc")

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


def _run_tsc(repo_path: Path, verbose: bool = False) -> GateCheck:
    """Run TypeScript type checking (tsc --noEmit).

    Checks for type-check script in package.json first, otherwise uses npx tsc --noEmit.
    """
    import json
    import time

    start = time.time()

    # Check if tsconfig.json exists
    tsconfig_path = repo_path / "tsconfig.json"
    if not tsconfig_path.exists():
        return GateCheck(
            name="tsc",
            status=GateStatus.SKIPPED,
            output="tsconfig.json not found",
        )

    # Check if npx is available
    if not shutil.which("npx"):
        return GateCheck(
            name="tsc",
            status=GateStatus.SKIPPED,
            output="npx not found",
        )

    # Determine command: prefer "type-check" script in package.json
    package_json_path = repo_path / "package.json"
    cmd = ["npx", "tsc", "--noEmit"]  # Default fallback

    if package_json_path.exists():
        try:
            package_data = json.loads(package_json_path.read_text())
            scripts = package_data.get("scripts", {})
            if "type-check" in scripts:
                cmd = ["npm", "run", "type-check"]
        except Exception:
            pass  # Fallback to npx tsc --noEmit

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minutes, same as mypy
        )

        duration_ms = int((time.time() - start) * 1000)

        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        # Parse TypeScript errors into structured format
        detailed_errors = _parse_tsc_errors(output) if result.returncode != 0 else None

        return GateCheck(
            name="tsc",
            status=GateStatus.PASSED if result.returncode == 0 else GateStatus.FAILED,
            exit_code=result.returncode,
            output=output[:2000] if not verbose else output,
            duration_ms=duration_ms,
            detailed_errors=detailed_errors,
        )

    except subprocess.TimeoutExpired:
        return GateCheck(
            name="tsc",
            status=GateStatus.ERROR,
            output="Timeout after 120 seconds",
        )
    except Exception as e:
        return GateCheck(
            name="tsc",
            status=GateStatus.ERROR,
            output=str(e),
        )


# ---------------------------------------------------------------------------
# Per-file lint gate (language-aware)
# ---------------------------------------------------------------------------


@dataclass
class LinterConfig:
    """Configuration for a file-level linter.

    Attributes:
        name: Human-readable linter name (used in GateCheck.name).
        extensions: File extensions this linter handles (e.g., {".py", ".pyi"}).
        cmd: Command list to invoke.  The placeholder ``{file}`` is replaced
             with the absolute file path at runtime.
        check_available: Binary name checked via ``shutil.which`` to see if the
             linter is installed.  ``None`` means always available.
        use_uv: If True *and* ``uv`` is on PATH, prepend ``["uv", "run"]``.
        parse_errors: Optional callable to parse raw output into structured
             error dicts.  Receives the raw stdout string.
    """

    name: str
    extensions: set[str]
    cmd: list[str]
    check_available: str | None = None
    use_uv: bool = False
    parse_errors: Optional[Callable[[str], list[dict[str, Any]]]] = None
    autofix_cmd: list[str] | None = None


# ---- Registry ---------------------------------------------------------------
# Add new linters here.  Order does not matter – the first config whose
# ``extensions`` set contains the file suffix wins.

LINTER_REGISTRY: list[LinterConfig] = [
    LinterConfig(
        name="ruff",
        extensions={".py", ".pyi"},
        cmd=["ruff", "check", "--output-format=concise", "{file}"],
        check_available="ruff",
        use_uv=True,
        parse_errors=_parse_ruff_errors,
        autofix_cmd=["ruff", "check", "--fix", "{file}"],
    ),
    LinterConfig(
        name="eslint",
        extensions={".ts", ".tsx", ".js", ".jsx"},
        cmd=["npx", "eslint", "{file}"],
        check_available="npx",
        autofix_cmd=["npx", "eslint", "--fix", "{file}"],
    ),
    # Clippy lints the whole crate, not a single file.  Omitted from the
    # per-file registry to avoid slow full-project checks on every edit.
    # TODO: re-add when a per-file Rust lint solution is available
    # (e.g., rustfmt --check {file} for formatting).
    # LinterConfig(
    #     name="clippy",
    #     extensions={".rs"},
    #     cmd=["cargo", "clippy", "--", "-D", "warnings"],
    #     check_available="cargo",
    # ),
]


def _find_linter_for_file(file_path: Path) -> Optional[LinterConfig]:
    """Return the first matching ``LinterConfig`` for *file_path*, or ``None``."""
    suffix = file_path.suffix.lower()
    for cfg in LINTER_REGISTRY:
        if suffix in cfg.extensions:
            return cfg
    return None


def run_lint_on_file(
    file_path: Path,
    repo_path: Path,
    *,
    timeout: int = 30,
) -> GateCheck:
    """Run the appropriate linter on a single file.

    Returns a ``GateCheck`` with status PASSED / FAILED / SKIPPED / ERROR.
    SKIPPED is returned when no linter is registered for the file extension,
    the required binary is not installed, or the tool is not found in the
    project's dependencies (e.g. ``uv run ruff`` fails to spawn).
    """
    import time

    cfg = _find_linter_for_file(file_path)
    if cfg is None:
        return GateCheck(name="lint", status=GateStatus.SKIPPED,
                         output=f"No linter configured for {file_path.suffix}")

    # Check binary availability — when use_uv is set, uv can provide the tool
    if cfg.check_available and not shutil.which(cfg.check_available):
        if not (cfg.use_uv and shutil.which("uv")):
            return GateCheck(name=cfg.name, status=GateStatus.SKIPPED,
                             output=f"{cfg.check_available} not found")

    # Build command – replace {file} placeholder
    cmd = [part.replace("{file}", str(file_path)) for part in cfg.cmd]
    if cfg.use_uv and shutil.which("uv"):
        cmd = ["uv", "run"] + cmd

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        duration_ms = int((time.time() - start) * 1000)
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        output = output.strip()

        # Detect tool-not-found: uv/shell report "Failed to spawn",
        # "command not found", or "No such file or directory" when the
        # linter binary isn't installed in the target project.
        # Note: "no such file or directory" is only matched when the tool
        # name also appears in stderr, to avoid false positives from
        # missing *target* files.
        if result.returncode != 0 and result.stderr:
            stderr_lower = result.stderr.lower()
            tool_names = {cfg.cmd[0].lower(), cfg.name.lower()}
            if (
                "failed to spawn" in stderr_lower
                or "command not found" in stderr_lower
                or (
                    "no such file or directory" in stderr_lower
                    and any(name in stderr_lower for name in tool_names)
                )
            ):
                return GateCheck(
                    name=cfg.name,
                    status=GateStatus.SKIPPED,
                    output=f"{cfg.name} not found in project dependencies",
                    duration_ms=duration_ms,
                )

        passed = result.returncode == 0
        check = GateCheck(
            name=cfg.name,
            status=GateStatus.PASSED if passed else GateStatus.FAILED,
            exit_code=result.returncode,
            output=output,
            duration_ms=duration_ms,
        )

        if not passed and cfg.parse_errors:
            check.detailed_errors = cfg.parse_errors(output)

        return check

    except subprocess.TimeoutExpired:
        return GateCheck(name=cfg.name, status=GateStatus.ERROR,
                         output=f"Timeout after {timeout}s")
    except FileNotFoundError:
        return GateCheck(name=cfg.name, status=GateStatus.SKIPPED,
                         output=f"{cfg.check_available or cfg.cmd[0]} not found")
    except Exception as e:
        return GateCheck(name=cfg.name, status=GateStatus.ERROR,
                         output=str(e))


def run_autofix_on_file(
    file_path: Path,
    repo_path: Path,
    *,
    timeout: int = 30,
) -> GateCheck:
    """Run the appropriate linter autofix on a single file.

    Returns a ``GateCheck`` with status PASSED / SKIPPED / ERROR.
    SKIPPED is returned when no linter is registered for the file extension,
    the linter has no ``autofix_cmd``, or the required binary is not installed.
    """
    import time

    cfg = _find_linter_for_file(file_path)
    if cfg is None:
        return GateCheck(name="autofix", status=GateStatus.SKIPPED,
                         output=f"No linter configured for {file_path.suffix}")

    if cfg.autofix_cmd is None:
        return GateCheck(name="autofix", status=GateStatus.SKIPPED,
                         output=f"{cfg.name} has no autofix command")

    # Check binary availability — when use_uv is set, uv can provide the tool
    if cfg.check_available and not shutil.which(cfg.check_available):
        if not (cfg.use_uv and shutil.which("uv")):
            return GateCheck(name=f"autofix-{cfg.name}", status=GateStatus.SKIPPED,
                             output=f"{cfg.check_available} not found")

    # Build command – replace {file} placeholder
    cmd = [part.replace("{file}", str(file_path)) for part in cfg.autofix_cmd]
    if cfg.use_uv and shutil.which("uv"):
        cmd = ["uv", "run"] + cmd

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        duration_ms = int((time.time() - start) * 1000)
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        output = output.strip()

        # Detect tool-not-found (same pattern as run_lint_on_file)
        if result.returncode != 0 and result.stderr:
            stderr_lower = result.stderr.lower()
            tool_names = {cfg.autofix_cmd[0].lower(), cfg.name.lower()}
            if (
                "failed to spawn" in stderr_lower
                or "command not found" in stderr_lower
                or (
                    "no such file or directory" in stderr_lower
                    and any(name in stderr_lower for name in tool_names)
                )
            ):
                return GateCheck(
                    name=f"autofix-{cfg.name}",
                    status=GateStatus.SKIPPED,
                    output=f"{cfg.name} not found in project dependencies",
                    duration_ms=duration_ms,
                )

        return GateCheck(
            name=f"autofix-{cfg.name}",
            status=GateStatus.PASSED if result.returncode == 0 else GateStatus.ERROR,
            exit_code=result.returncode,
            output=output,
            duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        return GateCheck(name=f"autofix-{cfg.name}", status=GateStatus.ERROR,
                         output=f"Timeout after {timeout}s")
    except FileNotFoundError:
        return GateCheck(name=f"autofix-{cfg.name}", status=GateStatus.SKIPPED,
                         output=f"{cfg.check_available or cfg.autofix_cmd[0]} not found")
    except Exception as e:
        return GateCheck(name=f"autofix-{cfg.name}", status=GateStatus.ERROR,
                         output=str(e))


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
