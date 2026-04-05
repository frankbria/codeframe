"""
Acceptance checks for the csv-stats lifecycle test project.

Run after the agent completes to verify the output actually works —
not just that API calls succeeded.

Usage:
    from tests.lifecycle.sample_project.acceptance import run_acceptance_checks
    passed, report = run_acceptance_checks(project_dir)
"""

import subprocess
import sys
import textwrap
from pathlib import Path


SAMPLE_CSV_CONTENT = textwrap.dedent("""\
    name,age,score,city
    Alice,30,88.5,NYC
    Bob,25,72.0,LA
    Carol,35,95.5,Chicago
    Dave,,81.0,NYC
    Eve,28,67.5,LA
""")

EXPECTED_ROWS = 5
EXPECTED_NUMERIC_COLS = {"age", "score"}


def run_acceptance_checks(project_dir: Path) -> tuple[bool, str]:
    """
    Run all acceptance checks against the generated project.

    Returns (passed: bool, report: str).
    """
    project_dir = Path(project_dir)
    results = []
    all_passed = True

    def check(name: str, passed: bool, detail: str = ""):
        nonlocal all_passed
        status = "PASS" if passed else "FAIL"
        results.append(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
        if not passed:
            all_passed = False

    # 1. Required files exist
    check("csv_stats.py exists", (project_dir / "csv_stats.py").exists())
    check("test_csv_stats.py exists", (project_dir / "test_csv_stats.py").exists())

    if not (project_dir / "csv_stats.py").exists():
        report = "FAILED — csv_stats.py not created\n" + "\n".join(results)
        return False, report

    # 2. Write sample CSV and run the script
    sample_csv = project_dir / "_test_sample.csv"
    sample_csv.write_text(SAMPLE_CSV_CONTENT)

    try:
        result = subprocess.run(
            [sys.executable, "csv_stats.py", str(sample_csv)],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        check("Script exits with code 0", result.returncode == 0,
              f"exit={result.returncode} stderr={result.stderr[:200]}")
        check("Output contains 'Rows: 5'", "Rows: 5" in output, repr(output[:300]))
        check("Output contains numeric stats for 'age'", "age:" in output, repr(output[:300]))
        check("Output contains numeric stats for 'score'", "score:" in output, repr(output[:300]))
        check("Output contains min/max/mean labels",
              all(x in output for x in ["min:", "max:", "mean:"]), repr(output[:300]))
    except subprocess.TimeoutExpired:
        check("Script completes within 30s", False, "timed out")

    # 3. File-not-found error handling
    try:
        err_result = subprocess.run(
            [sys.executable, "csv_stats.py", "nonexistent_file.csv"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        check("Exit code 1 on missing file", err_result.returncode == 1,
              f"exit={err_result.returncode}")
        check("Error message on missing file",
              "error" in (err_result.stderr + err_result.stdout).lower(),
              repr(err_result.stderr[:100]))
    except subprocess.TimeoutExpired:
        check("Missing-file error handled within 10s", False, "timed out")

    # 4. Pytest passes
    if (project_dir / "test_csv_stats.py").exists():
        try:
            pytest_result = subprocess.run(
                [sys.executable, "-m", "pytest", "test_csv_stats.py", "-v", "--tb=short"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed_tests = pytest_result.returncode == 0
            check("pytest passes", passed_tests,
                  pytest_result.stdout[-500:] if not passed_tests else "")
        except subprocess.TimeoutExpired:
            check("pytest completes within 120s", False, "timed out")

    # 5. Ruff lint passes
    try:
        ruff_result = subprocess.run(
            ["ruff", "check", "csv_stats.py"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        check("ruff check passes", ruff_result.returncode == 0,
              ruff_result.stdout[:300] if ruff_result.returncode != 0 else "")
    except FileNotFoundError:
        check("ruff available", False, "ruff not installed — skipping lint check")
    except subprocess.TimeoutExpired:
        check("ruff completes within 30s", False, "timed out")

    # Cleanup sample CSV
    sample_csv.unlink(missing_ok=True)

    report = ("PASSED" if all_passed else "FAILED") + "\n" + "\n".join(results)
    return all_passed, report


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python acceptance.py <project_dir>")
        sys.exit(1)
    passed, report = run_acceptance_checks(Path(sys.argv[1]))
    print(report)
    sys.exit(0 if passed else 1)
