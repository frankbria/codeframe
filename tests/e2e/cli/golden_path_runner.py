"""Reusable Golden Path workflow runner for e2e CLI validation.

Automates the full CodeFRAME workflow:
    init → prd add → tasks generate → mark ready → execute each task

Collects structured metrics (timing, iterations, success/failure) for each
step and emits them as a JSON-serialisable report.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class StepResult:
    """Result of a single CLI step."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    success: bool


@dataclass
class TaskExecutionResult:
    """Result of executing a single task with the agent."""

    task_id: str
    task_title: str
    engine: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    success: bool
    iterations: Optional[int] = None


@dataclass
class ValidationRun:
    """Full results from one Golden Path run."""

    engine: str
    project_path: str
    started_at: float = 0.0
    finished_at: float = 0.0
    init_result: Optional[StepResult] = None
    prd_result: Optional[StepResult] = None
    generate_result: Optional[StepResult] = None
    mark_ready_result: Optional[StepResult] = None
    task_results: list[TaskExecutionResult] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def total_duration(self) -> float:
        return self.finished_at - self.started_at

    @property
    def tasks_succeeded(self) -> int:
        return sum(1 for t in self.task_results if t.success)

    @property
    def tasks_failed(self) -> int:
        return sum(1 for t in self.task_results if not t.success)

    @property
    def success_rate(self) -> float:
        if not self.task_results:
            return 0.0
        return self.tasks_succeeded / len(self.task_results)

    def to_dict(self) -> dict:
        """Serialise to a JSON-friendly dict."""
        return {
            "engine": self.engine,
            "project_path": self.project_path,
            "total_duration_seconds": round(self.total_duration, 1),
            "success_rate": round(self.success_rate, 3),
            "tasks_total": len(self.task_results),
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "task_results": [
                {
                    "task_id": t.task_id,
                    "task_title": t.task_title,
                    "success": t.success,
                    "duration_seconds": round(t.duration_seconds, 1),
                    "iterations": t.iterations,
                    "exit_code": t.exit_code,
                }
                for t in self.task_results
            ],
            "error": self.error,
        }


class GoldenPathRunner:
    """Automates the CodeFRAME Golden Path workflow.

    Usage::

        runner = GoldenPathRunner(
            project_path=Path("~/projects/cf-test"),
            engine="react",
            verbose=True,
        )
        run = runner.execute()
        print(json.dumps(run.to_dict(), indent=2))
    """

    def __init__(
        self,
        project_path: Path,
        engine: str = "react",
        verbose: bool = True,
        dry_run: bool = False,
        timeout_per_task: int = 600,
        cf_binary: str = "codeframe",
    ) -> None:
        self.project_path = project_path.expanduser().resolve()
        self.engine = engine
        self.verbose = verbose
        self.dry_run = dry_run
        self.timeout_per_task = timeout_per_task
        self.cf_binary = cf_binary

    def _run_cmd(
        self,
        args: list[str],
        timeout: int = 120,
        cwd: Optional[Path] = None,
    ) -> StepResult:
        """Run a shell command and return structured result."""
        cmd_str = " ".join(args)
        start = time.time()
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or self.project_path,
                env=self._build_env(),
            )
            duration = time.time() - start
            return StepResult(
                command=cmd_str,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=duration,
                success=proc.returncode == 0,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            return StepResult(
                command=cmd_str,
                exit_code=-1,
                stdout="",
                stderr=f"Timed out after {timeout}s",
                duration_seconds=duration,
                success=False,
            )

    def _build_env(self) -> dict:
        """Build environment with API key from .env if needed."""
        import os

        env = os.environ.copy()
        if "ANTHROPIC_API_KEY" not in env:
            codeframe_root = Path(
                os.getenv(
                    "CODEFRAME_ROOT",
                    str(Path(__file__).parents[3]),
                )
            )
            search_paths = [
                Path.cwd() / ".env",
                codeframe_root / ".env",
            ]
            for env_path in search_paths:
                if env_path.exists():
                    for line in env_path.read_text().splitlines():
                        line = line.strip()
                        if line.startswith("ANTHROPIC_API_KEY="):
                            key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            env["ANTHROPIC_API_KEY"] = key
                            break
                    if "ANTHROPIC_API_KEY" in env:
                        break
        return env

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[GoldenPath] {msg}", flush=True)

    # ------------------------------------------------------------------
    # Workflow steps
    # ------------------------------------------------------------------

    def run_init(self) -> StepResult:
        """Step 1: cf init <project> --detect"""
        self._log(f"Initializing workspace: {self.project_path}")
        return self._run_cmd(
            [self.cf_binary, "init", str(self.project_path), "--detect"],
        )

    def run_prd_add(self, prd_file: str = "requirements.md") -> StepResult:
        """Step 2: cf prd add <file>"""
        self._log(f"Adding PRD: {prd_file}")
        return self._run_cmd(
            [self.cf_binary, "prd", "add", prd_file],
        )

    def run_tasks_generate(self) -> StepResult:
        """Step 3: cf tasks generate"""
        self._log("Generating tasks from PRD")
        return self._run_cmd(
            [self.cf_binary, "tasks", "generate"],
            timeout=180,  # LLM call, give it more time
        )

    def run_mark_all_ready(self) -> StepResult:
        """Step 4: cf tasks set status READY --all"""
        self._log("Marking all tasks READY")
        return self._run_cmd(
            [self.cf_binary, "tasks", "set", "status", "--all", "READY"],
        )

    def get_task_list(self) -> list[dict]:
        """Parse task list to extract IDs and titles.

        Uses the core module directly (via a Python subprocess) since
        the CLI table output is hard to parse reliably.
        """
        import os

        codeframe_root = os.getenv(
            "CODEFRAME_ROOT",
            str(Path(__file__).parents[3]),
        )
        script = f"""
import json, sys
sys.path.insert(0, "{codeframe_root}")
from pathlib import Path
from codeframe.core.workspace import get_workspace
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus

ws = get_workspace(Path("{self.project_path}"))
task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
result = [{{"id": t.id, "title": t.title}} for t in task_list]
print(json.dumps(result))
"""
        result = self._run_cmd(
            ["python", "-c", script],
            timeout=30,
        )
        if result.success and result.stdout.strip():
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                self._log(f"Failed to parse task list: {result.stdout[:200]}")
                return []
        return []

    def run_execute_task(self, task_id: str, task_title: str) -> TaskExecutionResult:
        """Step 5 (per task): cf work start <id> --execute --engine <engine>"""
        self._log(f"Executing task {task_id[:8]}: {task_title}")

        cmd = [
            self.cf_binary,
            "work",
            "start",
            task_id,
            "--execute",
            "--engine",
            self.engine,
        ]
        if self.verbose:
            cmd.append("--verbose")
        if self.dry_run:
            cmd.append("--dry-run")

        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_per_task,
                cwd=self.project_path,
                env=self._build_env(),
            )
            duration = time.time() - start

            combined = proc.stdout + proc.stderr
            iterations = self._extract_iterations(combined)
            success = self._detect_success(proc.returncode, combined)

            return TaskExecutionResult(
                task_id=task_id,
                task_title=task_title,
                engine=self.engine,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=duration,
                success=success,
                iterations=iterations,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            return TaskExecutionResult(
                task_id=task_id,
                task_title=task_title,
                engine=self.engine,
                exit_code=-1,
                stdout="",
                stderr=f"Timed out after {self.timeout_per_task}s",
                duration_seconds=duration,
                success=False,
                iterations=None,
            )

    def _detect_success(self, exit_code: int, output: str) -> bool:
        """Determine actual success from CLI output patterns.

        Uses conservative detection: only returns True when an explicit
        success pattern is found AND no failure patterns are present.
        Returns False when output is ambiguous (no patterns matched).
        """
        if exit_code != 0:
            return False

        failure_patterns = [
            "Task execution failed",
            "ANTHROPIC_API_KEY environment variable is required",
            "Error:",
            "Task blocked",
        ]
        success_patterns = [
            "Task completed successfully",
        ]

        # Check failure patterns first — failure takes precedence
        for pattern in failure_patterns:
            if pattern in output:
                return False

        for pattern in success_patterns:
            if pattern in output:
                return True

        # No clear signal — conservative default: treat as failure
        return False

    def _extract_iterations(self, output: str) -> Optional[int]:
        """Extract iteration count from agent output."""
        # ReactAgent logs: "Iteration 15/30" or "completed in 15 iterations"
        patterns = [
            r"completed in (\d+) iterations",
            r"Iteration (\d+)/\d+",
            r"iterations:\s*(\d+)",
        ]
        max_iter = None
        for pattern in patterns:
            for match in re.finditer(pattern, output, re.IGNORECASE):
                val = int(match.group(1))
                if max_iter is None or val > max_iter:
                    max_iter = val
        return max_iter

    # ------------------------------------------------------------------
    # Full workflow
    # ------------------------------------------------------------------

    def execute(self, prd_file: str = "requirements.md") -> ValidationRun:
        """Run the complete Golden Path workflow and return results."""
        run = ValidationRun(
            engine=self.engine,
            project_path=str(self.project_path),
        )
        run.started_at = time.time()

        try:
            # Step 1: Init
            run.init_result = self.run_init()
            if not run.init_result.success:
                run.error = f"Init failed: {run.init_result.stderr}"
                run.finished_at = time.time()
                return run
            self._log(f"  Init: OK ({run.init_result.duration_seconds:.1f}s)")

            # Step 2: PRD
            run.prd_result = self.run_prd_add(prd_file)
            if not run.prd_result.success:
                run.error = f"PRD add failed: {run.prd_result.stderr}"
                run.finished_at = time.time()
                return run
            self._log(f"  PRD: OK ({run.prd_result.duration_seconds:.1f}s)")

            # Step 3: Generate
            run.generate_result = self.run_tasks_generate()
            if not run.generate_result.success:
                run.error = f"Task generation failed: {run.generate_result.stderr}"
                run.finished_at = time.time()
                return run
            self._log(
                f"  Generate: OK ({run.generate_result.duration_seconds:.1f}s)"
            )

            # Step 4: Mark ready
            run.mark_ready_result = self.run_mark_all_ready()
            if not run.mark_ready_result.success:
                run.error = f"Mark ready failed: {run.mark_ready_result.stderr}"
                run.finished_at = time.time()
                return run

            # Get task list
            tasks = self.get_task_list()
            self._log(f"  Found {len(tasks)} tasks to execute")

            if not tasks:
                run.error = "No READY tasks found after generation"
                run.finished_at = time.time()
                return run

            # Step 5: Execute each task
            for i, task in enumerate(tasks, 1):
                self._log(f"\n--- Task {i}/{len(tasks)} ---")
                result = self.run_execute_task(task["id"], task["title"])
                run.task_results.append(result)

                status = "OK" if result.success else "FAILED"
                iter_str = (
                    f", {result.iterations} iterations"
                    if result.iterations
                    else ""
                )
                self._log(
                    f"  {status} ({result.duration_seconds:.1f}s{iter_str})"
                )

        except Exception as e:
            run.error = f"Unexpected error: {e}"

        run.finished_at = time.time()

        self._log("\n=== Run complete ===")
        self._log(f"Engine: {self.engine}")
        self._log(f"Success rate: {run.success_rate:.0%}")
        self._log(f"Total time: {run.total_duration:.1f}s")

        return run
