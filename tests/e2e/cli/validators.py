"""Reusable validation checks for e2e CLI testing.

Each validator returns a (passed: bool, detail: str) tuple so results
can be aggregated into a report.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Optional

from .golden_path_runner import ValidationRun


def validate_ruff_lint(project_path: Path) -> tuple[bool, str]:
    """Check that ruff reports 0 lint errors in the project."""
    try:
        proc = subprocess.run(
            ["ruff", "check", "."],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=60,
        )
        if proc.returncode == 0:
            return True, "0 lint errors"
        error_count = proc.stdout.count("\n")
        return False, f"{error_count} lint errors:\n{proc.stdout[:500]}"
    except FileNotFoundError:
        return False, "ruff not found on PATH"


def validate_pyproject_preserved(
    project_path: Path,
    original_hash: str,
) -> tuple[bool, str]:
    """Verify pyproject.toml was not overwritten during execution."""
    toml_path = project_path / "pyproject.toml"
    if not toml_path.exists():
        return False, "pyproject.toml was deleted"

    current = hashlib.sha256(toml_path.read_text().encode()).hexdigest()
    if current == original_hash:
        return True, "pyproject.toml unchanged"
    return False, "pyproject.toml was modified during execution"


def validate_tests_pass(project_path: Path) -> tuple[bool, str]:
    """Run the project's test suite and check all tests pass."""
    try:
        proc = subprocess.run(
            ["uv", "run", "pytest", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=120,
        )
        if proc.returncode == 0:
            return True, f"All tests passed\n{proc.stdout[-300:]}"
        return False, f"Tests failed (exit {proc.returncode}):\n{proc.stdout[-500:]}"
    except FileNotFoundError:
        return False, "uv/pytest not found on PATH"


def validate_cli_works(project_path: Path) -> tuple[bool, str]:
    """Check that the generated CLI entry point works."""
    try:
        proc = subprocess.run(
            ["uv", "run", "task-cli", "--help"],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=30,
        )
        if proc.returncode == 0:
            return True, "CLI --help works"
        return False, f"CLI --help failed (exit {proc.returncode}):\n{proc.stderr[:300]}"
    except FileNotFoundError:
        return False, "uv not found on PATH"


def validate_no_import_errors(project_path: Path) -> tuple[bool, str]:
    """Check for cross-file naming mismatches by importing the package."""
    script = 'import task_tracker; print("OK")'
    try:
        proc = subprocess.run(
            ["uv", "run", "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=30,
        )
        if proc.returncode == 0 and "OK" in proc.stdout:
            return True, "Package imports cleanly"
        return False, f"Import error:\n{proc.stderr[:300]}"
    except FileNotFoundError:
        return False, "uv/python not found"


def validate_iteration_counts(
    run: ValidationRun,
    max_iterations: int = 30,
) -> tuple[bool, str]:
    """Ensure all tasks completed within the iteration limit."""
    over_limit = []
    for t in run.task_results:
        if t.iterations is not None and t.iterations > max_iterations:
            over_limit.append(f"  {t.task_id[:8]}: {t.iterations} iterations")
    if not over_limit:
        return True, f"All tasks within {max_iterations}-iteration limit"
    return False, f"Tasks exceeded {max_iterations} iterations:\n" + "\n".join(
        over_limit
    )


def validate_files_generated(project_path: Path) -> tuple[bool, str]:
    """Check that source files were actually generated."""
    src_dir = project_path / "src" / "task_tracker"
    if not src_dir.exists():
        return False, "src/task_tracker/ directory not found"

    py_files = list(src_dir.glob("*.py"))
    # Expect at least models + cli + storage (or similar)
    non_init = [f for f in py_files if f.name != "__init__.py"]
    if len(non_init) >= 2:
        names = [f.name for f in non_init]
        return True, f"Generated {len(non_init)} source files: {', '.join(names)}"
    return False, f"Only {len(non_init)} source file(s) generated — expected at least 2"


def validate_tests_generated(project_path: Path) -> tuple[bool, str]:
    """Check that test files were generated."""
    tests_dir = project_path / "tests"
    if not tests_dir.exists():
        return False, "tests/ directory not found"

    test_files = list(tests_dir.glob("test_*.py"))
    if test_files:
        names = [f.name for f in test_files]
        return True, f"Generated {len(test_files)} test file(s): {', '.join(names)}"
    return False, "No test files generated"


def run_all_validators(
    project_path: Path,
    run: ValidationRun,
    original_pyproject_hash: str,
    max_iterations: int = 30,
) -> dict[str, tuple[bool, str]]:
    """Run all validators and return results keyed by name."""
    return {
        "ruff_lint": validate_ruff_lint(project_path),
        "pyproject_preserved": validate_pyproject_preserved(
            project_path, original_pyproject_hash
        ),
        "tests_pass": validate_tests_pass(project_path),
        "cli_works": validate_cli_works(project_path),
        "no_import_errors": validate_no_import_errors(project_path),
        "iteration_counts": validate_iteration_counts(run, max_iterations),
        "files_generated": validate_files_generated(project_path),
        "tests_generated": validate_tests_generated(project_path),
    }
