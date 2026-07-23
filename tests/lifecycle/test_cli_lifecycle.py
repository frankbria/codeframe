"""
CLI Lifecycle Test — full Think → Build → Prove loop via `cf` commands.

Tests that the ReAct agent can actually build a real project from a PRD,
not just that API calls succeed.

Runtime: 10–30 minutes. Cost: ~$0.50–2.00 per run (haiku/sonnet).
"""

import pytest

from tests.lifecycle.sample_project.acceptance import run_acceptance_checks

pytestmark = [pytest.mark.lifecycle, pytest.mark.slow]


class TestCLILifecycle:
    """Full lifecycle via CLI: init → prd → tasks → execute → verify."""

    def test_agent_builds_csv_stats_project(self, initialized_workspace, cf):
        """
        Agent can build the csv-stats project from scratch using the CLI.

        Pass criteria:
        - cf work batch run completes without error
        - csv_stats.py exists and produces correct output
        - pytest tests in the generated project pass
        - ruff check passes
        """
        project_dir = initialized_workspace

        # Show what tasks were generated (helpful for debugging failures)
        tasks_result = cf("tasks", "list")
        print("\n=== Generated tasks ===")
        print(tasks_result.stdout)

        # Execute all ready tasks
        result = cf(
            "work", "batch", "run",
            "--all-ready",
            "--engine", "react",
            "--retry", "1",
            timeout=1800,  # 30 min ceiling
        )

        print("\n=== Batch execution output ===")
        print(result.stdout[-3000:])  # last 3000 chars
        if result.stderr:
            print("--- stderr ---")
            print(result.stderr[-1000:])

        assert result.returncode == 0, (
            f"cf work batch run failed (exit {result.returncode}).\n"
            f"stdout tail:\n{result.stdout[-1000:]}\n"
            f"stderr:\n{result.stderr[-500:]}"
        )

        # Run acceptance checks — this is the real test
        passed, report = run_acceptance_checks(project_dir)
        print("\n=== Acceptance report ===")
        print(report)

        assert passed, f"Acceptance checks failed.\n{report}"

    def test_agent_task_status_after_execution(self, initialized_workspace, cf):
        """All tasks reach DONE or BLOCKED status — none stuck in IN_PROGRESS."""
        cf(
            "work", "batch", "run",
            "--all-ready", "--engine", "react",
            timeout=1800,
        )

        # Query IN_PROGRESS tasks via a supported Golden-Path command. A failure
        # of the command itself must FAIL the test, not silently skip it — a
        # broken `cf tasks list` is exactly the kind of Golden-Path regression
        # this lifecycle test exists to catch (#773). ``cf tasks list --output
        # json`` does not exist; ``--status`` filtering does.
        result = cf("tasks", "list", "--status", "IN_PROGRESS")
        assert result.returncode == 0, (
            f"`cf tasks list --status IN_PROGRESS` failed (exit {result.returncode}) — "
            f"a Golden-Path command must not fail.\n"
            f"stdout:\n{result.stdout[-1000:]}\nstderr:\n{result.stderr[-500:]}"
        )

        # With no IN_PROGRESS tasks the CLI prints the sentinel; any stuck task
        # instead renders in the tasks table, so the sentinel is absent.
        assert "No tasks with status IN_PROGRESS" in result.stdout, (
            "One or more tasks are still IN_PROGRESS after the batch run "
            f"(none should be):\n{result.stdout}"
        )
