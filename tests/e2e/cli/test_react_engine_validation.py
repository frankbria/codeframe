"""End-to-end validation of the ReAct engine against the cf-test project.

This test exercises the full Golden Path workflow:
    init → prd add → tasks generate → mark ready → execute each task

Run explicitly (requires real API calls):
    uv run pytest tests/e2e/cli/test_react_engine_validation.py -v -s

The -s flag is important for seeing real-time progress output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .golden_path_runner import GoldenPathRunner, ValidationRun
from .validators import run_all_validators

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_llm]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def react_run(
    clean_cf_test: Path,
    anthropic_api_key: str,
    pyproject_snapshot: dict,
) -> ValidationRun:
    """Execute the full Golden Path with the ReAct engine.

    This fixture is module-scoped so all tests in this file share a single
    (expensive) validation run.
    """
    runner = GoldenPathRunner(
        project_path=clean_cf_test,
        engine="react",
        verbose=True,
        timeout_per_task=600,
    )
    return runner.execute()


@pytest.fixture(scope="module")
def react_validation(
    react_run: ValidationRun,
    cf_test_path: Path,
    pyproject_snapshot: dict,
) -> dict[str, tuple[bool, str]]:
    """Run all validators against the post-execution project state."""
    return run_all_validators(
        project_path=cf_test_path,
        run=react_run,
        original_pyproject_hash=pyproject_snapshot["hash"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGoldenPathWorkflow:
    """Verify the Golden Path steps succeed."""

    def test_init_succeeds(self, react_run: ValidationRun):
        assert react_run.init_result is not None
        assert react_run.init_result.success, (
            f"cf init failed: {react_run.init_result.stderr}"
        )

    def test_prd_add_succeeds(self, react_run: ValidationRun):
        assert react_run.prd_result is not None
        assert react_run.prd_result.success, (
            f"cf prd add failed: {react_run.prd_result.stderr}"
        )

    def test_tasks_generated(self, react_run: ValidationRun):
        assert react_run.generate_result is not None
        assert react_run.generate_result.success, (
            f"cf tasks generate failed: {react_run.generate_result.stderr}"
        )

    def test_tasks_marked_ready(self, react_run: ValidationRun):
        assert react_run.mark_ready_result is not None
        assert react_run.mark_ready_result.success, (
            f"Mark ready failed: {react_run.mark_ready_result.stderr}"
        )

    def test_at_least_one_task_executed(self, react_run: ValidationRun):
        assert len(react_run.task_results) > 0, "No tasks were executed"

    def test_no_workflow_error(self, react_run: ValidationRun):
        assert react_run.error is None, f"Workflow error: {react_run.error}"


class TestSuccessCriteria:
    """Validate the 6 success criteria from AGENT_V3_UNIFIED_PLAN.md."""

    def test_all_tasks_succeed(self, react_run: ValidationRun):
        """Build working task tracker CLI with tests, on first attempt."""
        failed = [t for t in react_run.task_results if not t.success]
        assert not failed, (
            f"{len(failed)} task(s) failed: "
            + ", ".join(f"{t.task_id[:8]} ({t.task_title})" for t in failed)
        )

    def test_zero_ruff_lint_errors(self, react_validation: dict):
        """0 ruff lint errors."""
        passed, detail = react_validation["ruff_lint"]
        assert passed, detail

    def test_pyproject_preserved(self, react_validation: dict):
        """pyproject.toml preserved (not overwritten)."""
        passed, detail = react_validation["pyproject_preserved"]
        assert passed, detail

    def test_no_naming_mismatches(self, react_validation: dict):
        """No cross-file naming mismatches."""
        passed, detail = react_validation["no_import_errors"]
        assert passed, detail

    def test_within_iteration_limit(self, react_validation: dict):
        """Each task completes within 30 iterations."""
        passed, detail = react_validation["iteration_counts"]
        assert passed, detail

    def test_files_generated(self, react_validation: dict):
        """Source files were actually created."""
        passed, detail = react_validation["files_generated"]
        assert passed, detail

    def test_tests_generated(self, react_validation: dict):
        """Test files were created."""
        passed, detail = react_validation["tests_generated"]
        assert passed, detail

    def test_cli_works(self, react_validation: dict):
        """Generated CLI entry point is functional."""
        passed, detail = react_validation["cli_works"]
        assert passed, detail

    def test_tests_pass(self, react_validation: dict):
        """Generated tests pass."""
        passed, detail = react_validation["tests_pass"]
        assert passed, detail


class TestMetrics:
    """Capture metrics for the validation report (these always pass)."""

    def test_report_success_rate(self, react_run: ValidationRun):
        print("\n=== METRICS ===")
        print(f"Engine: {react_run.engine}")
        print(f"Success rate: {react_run.success_rate:.0%}")
        print(f"Tasks: {react_run.tasks_succeeded}/{len(react_run.task_results)}")
        print(f"Total duration: {react_run.total_duration:.1f}s")
        for t in react_run.task_results:
            status = "PASS" if t.success else "FAIL"
            iter_str = f", {t.iterations} iter" if t.iterations else ""
            print(
                f"  [{status}] {t.task_id[:8]}: {t.task_title} "
                f"({t.duration_seconds:.1f}s{iter_str})"
            )

    def test_save_metrics_json(self, react_run: ValidationRun, tmp_path: Path):
        """Save metrics to a JSON file for later comparison."""
        metrics_file = tmp_path / "react_metrics.json"
        metrics_file.write_text(json.dumps(react_run.to_dict(), indent=2))
        print(f"\nMetrics saved to: {metrics_file}")
