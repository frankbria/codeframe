"""Side-by-side engine comparison: ReAct vs Plan-and-Execute.

Run explicitly (requires real API calls for BOTH engines):
    uv run pytest tests/e2e/cli/test_engine_comparison.py -v -s

This runs the Golden Path twice (once per engine) with a clean workspace
between runs, then compares metrics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .golden_path_runner import GoldenPathRunner, ValidationRun

pytestmark = [pytest.mark.e2e, pytest.mark.e2e_llm]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def react_run(
    clean_cf_test: Path,
    anthropic_api_key: str,
) -> ValidationRun:
    """Run Golden Path with ReAct engine."""
    runner = GoldenPathRunner(
        project_path=clean_cf_test,
        engine="react",
        verbose=True,
    )
    return runner.execute()


@pytest.fixture(scope="module")
def plan_run(
    react_run: ValidationRun,
    clean_cf_test: Path,
    anthropic_api_key: str,
) -> ValidationRun:
    """Run Golden Path with Plan-and-Execute engine (after cleaning)."""
    # clean_cf_test fixture already cleaned before react_run.
    # We need to re-clean for the plan engine run.
    import shutil

    project = clean_cf_test

    # Re-clean
    codeframe_dir = project / ".codeframe"
    if codeframe_dir.exists():
        shutil.rmtree(codeframe_dir)
    src_dir = project / "src" / "task_tracker"
    if src_dir.exists():
        for f in sorted(src_dir.rglob("*"), reverse=True):
            if f.name == "__pycache__":
                shutil.rmtree(f)
            elif f.name != "__init__.py" and f.is_file():
                f.unlink()
            elif f.is_dir() and not any(f.iterdir()):
                f.rmdir()
        (src_dir / "__init__.py").write_text("")
    tests_dir = project / "tests"
    if tests_dir.exists():
        for f in sorted(tests_dir.rglob("*"), reverse=True):
            if f.name == "__pycache__":
                shutil.rmtree(f)
            elif f.name != "__init__.py" and f.is_file():
                f.unlink()
            elif f.is_dir() and not any(f.iterdir()):
                f.rmdir()

    runner = GoldenPathRunner(
        project_path=project,
        engine="plan",
        verbose=True,
    )
    return runner.execute()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEngineComparison:
    """Compare ReAct and Plan-and-Execute engines."""

    def test_both_engines_complete(
        self,
        react_run: ValidationRun,
        plan_run: ValidationRun,
    ):
        """Both engines should complete the workflow."""
        assert react_run.error is None, f"ReAct error: {react_run.error}"
        assert plan_run.error is None, f"Plan error: {plan_run.error}"

    def test_print_comparison(
        self,
        react_run: ValidationRun,
        plan_run: ValidationRun,
    ):
        """Print a side-by-side comparison table."""
        print("\n" + "=" * 70)
        print("ENGINE COMPARISON: ReAct vs Plan-and-Execute")
        print("=" * 70)

        print(f"\n{'Metric':<30} {'ReAct':>15} {'Plan':>15}")
        print("-" * 60)
        print(
            f"{'Success rate':<30} "
            f"{react_run.success_rate:>14.0%} "
            f"{plan_run.success_rate:>14.0%}"
        )
        print(
            f"{'Tasks succeeded':<30} "
            f"{react_run.tasks_succeeded:>15} "
            f"{plan_run.tasks_succeeded:>15}"
        )
        print(
            f"{'Tasks failed':<30} "
            f"{react_run.tasks_failed:>15} "
            f"{plan_run.tasks_failed:>15}"
        )
        print(
            f"{'Total duration (s)':<30} "
            f"{react_run.total_duration:>14.1f}s "
            f"{plan_run.total_duration:>14.1f}s"
        )

        # Per-task iteration counts (ReAct only tracks these meaningfully)
        react_iters = [
            t.iterations for t in react_run.task_results if t.iterations is not None
        ]
        if react_iters:
            avg_iter = sum(react_iters) / len(react_iters)
            print(f"{'Avg iterations (ReAct)':<30} {avg_iter:>15.1f} {'N/A':>15}")

        print("=" * 70)

    def test_save_comparison_json(
        self,
        react_run: ValidationRun,
        plan_run: ValidationRun,
        tmp_path: Path,
    ):
        """Save comparison data for the validation report."""
        comparison = {
            "react": react_run.to_dict(),
            "plan": plan_run.to_dict(),
        }
        output = tmp_path / "engine_comparison.json"
        output.write_text(json.dumps(comparison, indent=2))
        print(f"\nComparison saved to: {output}")
