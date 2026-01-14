"""Code execution engine for CodeFRAME v2.

Executes implementation plan steps by generating and applying code changes.
Handles file operations, shell commands, and tracks changes for rollback.

This module is headless - no FastAPI or HTTP dependencies.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from codeframe.core.planner import PlanStep, StepType, ImplementationPlan
from codeframe.core.context import TaskContext
from codeframe.adapters.llm import LLMProvider, Purpose


class ExecutionStatus(str, Enum):
    """Status of a step execution."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FileChange:
    """Record of a file change for rollback.

    Attributes:
        path: Path to the file
        operation: Type of operation (create, edit, delete)
        original_content: Original content (None for new files)
        new_content: New content after change
        timestamp: When the change was made
    """

    path: str
    operation: str
    original_content: Optional[str]
    new_content: Optional[str]
    timestamp: datetime


@dataclass
class StepResult:
    """Result of executing a single step.

    Attributes:
        step: The step that was executed
        status: Execution status
        output: Output or result message
        error: Error message if failed
        file_changes: Files modified by this step
        duration_ms: Execution time in milliseconds
    """

    step: PlanStep
    status: ExecutionStatus
    output: str = ""
    error: str = ""
    file_changes: list[FileChange] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class ExecutionResult:
    """Result of executing an entire plan.

    Attributes:
        plan: The plan that was executed
        step_results: Results for each step
        success: Whether all steps succeeded
        total_duration_ms: Total execution time
    """

    plan: ImplementationPlan
    step_results: list[StepResult]
    success: bool = True
    total_duration_ms: int = 0

    @property
    def failed_steps(self) -> list[StepResult]:
        """Get steps that failed."""
        return [r for r in self.step_results if r.status == ExecutionStatus.FAILED]

    @property
    def file_changes(self) -> list[FileChange]:
        """Get all file changes across all steps."""
        changes = []
        for result in self.step_results:
            changes.extend(result.file_changes)
        return changes


# System prompt for code generation
CODE_GENERATION_PROMPT = """You are a code generator. Generate clean, well-structured code based on the requirements.

Guidelines:
1. Follow the existing code style in the project
2. Include appropriate error handling
3. Add brief comments for complex logic
4. Use type hints for Python code
5. Keep code focused and minimal - don't over-engineer

Return ONLY the code, no explanations or markdown formatting."""

EDIT_GENERATION_PROMPT = """You are a code editor. Given the current file content and requested changes, generate the updated file content.

Guidelines:
1. Preserve the existing code style and formatting
2. Make minimal changes to achieve the goal
3. Don't change unrelated code
4. Maintain all imports and dependencies

Return ONLY the complete updated file content, no explanations or markdown formatting."""


class Executor:
    """Executes implementation plan steps.

    Handles file operations, shell commands, and LLM-driven code generation.
    Tracks all changes for potential rollback.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        repo_path: Path,
        dry_run: bool = False,
        command_timeout: int = 60,
    ):
        """Initialize the executor.

        Args:
            llm_provider: LLM provider for code generation
            repo_path: Root path of the repository
            dry_run: If True, don't actually make changes
            command_timeout: Timeout for shell commands in seconds
        """
        self.llm = llm_provider
        self.repo_path = Path(repo_path)
        self.dry_run = dry_run
        self.command_timeout = command_timeout
        self.changes: list[FileChange] = []

    def execute_plan(
        self,
        plan: ImplementationPlan,
        context: TaskContext,
    ) -> ExecutionResult:
        """Execute all steps in a plan.

        Args:
            plan: Plan to execute
            context: Task context for code generation

        Returns:
            ExecutionResult with all step results
        """
        results = []
        success = True
        start_time = datetime.now(timezone.utc)

        for step in plan.steps:
            # Check dependencies
            if not self._dependencies_satisfied(step, results):
                results.append(StepResult(
                    step=step,
                    status=ExecutionStatus.SKIPPED,
                    output="Dependencies not satisfied",
                ))
                continue

            # Execute the step
            result = self.execute_step(step, context)
            results.append(result)

            if result.status == ExecutionStatus.FAILED:
                success = False
                break  # Stop on first failure

        end_time = datetime.now(timezone.utc)
        duration = int((end_time - start_time).total_seconds() * 1000)

        return ExecutionResult(
            plan=plan,
            step_results=results,
            success=success,
            total_duration_ms=duration,
        )

    def execute_step(
        self,
        step: PlanStep,
        context: TaskContext,
    ) -> StepResult:
        """Execute a single plan step.

        Args:
            step: Step to execute
            context: Task context for code generation

        Returns:
            StepResult with execution outcome
        """
        start_time = datetime.now(timezone.utc)

        try:
            if step.type == StepType.FILE_CREATE:
                result = self._execute_file_create(step, context)
            elif step.type == StepType.FILE_EDIT:
                result = self._execute_file_edit(step, context)
            elif step.type == StepType.FILE_DELETE:
                result = self._execute_file_delete(step)
            elif step.type == StepType.SHELL_COMMAND:
                result = self._execute_shell_command(step)
            elif step.type == StepType.VERIFICATION:
                result = self._execute_verification(step)
            else:
                result = StepResult(
                    step=step,
                    status=ExecutionStatus.FAILED,
                    error=f"Unknown step type: {step.type}",
                )
        except Exception as e:
            result = StepResult(
                step=step,
                status=ExecutionStatus.FAILED,
                error=str(e),
            )

        end_time = datetime.now(timezone.utc)
        result.duration_ms = int((end_time - start_time).total_seconds() * 1000)

        return result

    def _execute_file_create(
        self,
        step: PlanStep,
        context: TaskContext,
    ) -> StepResult:
        """Create a new file with generated content."""
        file_path = self.repo_path / step.target

        # Check if file already exists
        if file_path.exists():
            return StepResult(
                step=step,
                status=ExecutionStatus.FAILED,
                error=f"File already exists: {step.target}",
            )

        # Generate file content using LLM
        content = self._generate_file_content(step, context)

        if self.dry_run:
            return StepResult(
                step=step,
                status=ExecutionStatus.SUCCESS,
                output=f"[DRY RUN] Would create: {step.target}",
            )

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        file_path.write_text(content, encoding="utf-8")

        # Record the change
        change = FileChange(
            path=step.target,
            operation="create",
            original_content=None,
            new_content=content,
            timestamp=datetime.now(timezone.utc),
        )
        self.changes.append(change)

        return StepResult(
            step=step,
            status=ExecutionStatus.SUCCESS,
            output=f"Created: {step.target}",
            file_changes=[change],
        )

    def _execute_file_edit(
        self,
        step: PlanStep,
        context: TaskContext,
    ) -> StepResult:
        """Edit an existing file."""
        file_path = self.repo_path / step.target

        # Check if file exists
        if not file_path.exists():
            return StepResult(
                step=step,
                status=ExecutionStatus.FAILED,
                error=f"File not found: {step.target}",
            )

        # Read current content
        original_content = file_path.read_text(encoding="utf-8")

        # Generate edited content using LLM
        new_content = self._generate_edit_content(step, context, original_content)

        if self.dry_run:
            return StepResult(
                step=step,
                status=ExecutionStatus.SUCCESS,
                output=f"[DRY RUN] Would edit: {step.target}",
            )

        # Write the updated content
        file_path.write_text(new_content, encoding="utf-8")

        # Record the change
        change = FileChange(
            path=step.target,
            operation="edit",
            original_content=original_content,
            new_content=new_content,
            timestamp=datetime.now(timezone.utc),
        )
        self.changes.append(change)

        return StepResult(
            step=step,
            status=ExecutionStatus.SUCCESS,
            output=f"Edited: {step.target}",
            file_changes=[change],
        )

    def _execute_file_delete(self, step: PlanStep) -> StepResult:
        """Delete a file."""
        file_path = self.repo_path / step.target

        if not file_path.exists():
            return StepResult(
                step=step,
                status=ExecutionStatus.SUCCESS,
                output=f"File already deleted: {step.target}",
            )

        original_content = file_path.read_text(encoding="utf-8")

        if self.dry_run:
            return StepResult(
                step=step,
                status=ExecutionStatus.SUCCESS,
                output=f"[DRY RUN] Would delete: {step.target}",
            )

        # Delete the file
        file_path.unlink()

        # Record the change
        change = FileChange(
            path=step.target,
            operation="delete",
            original_content=original_content,
            new_content=None,
            timestamp=datetime.now(timezone.utc),
        )
        self.changes.append(change)

        return StepResult(
            step=step,
            status=ExecutionStatus.SUCCESS,
            output=f"Deleted: {step.target}",
            file_changes=[change],
        )

    def _execute_shell_command(self, step: PlanStep) -> StepResult:
        """Execute a shell command."""
        command = step.target

        # Basic command sanitization - block dangerous patterns
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf ~",
            "> /dev/",
            "mkfs",
            ":(){",  # Fork bomb
            "dd if=",
        ]
        for pattern in dangerous_patterns:
            if pattern in command:
                return StepResult(
                    step=step,
                    status=ExecutionStatus.FAILED,
                    error=f"Blocked dangerous command pattern: {pattern}",
                )

        if self.dry_run:
            return StepResult(
                step=step,
                status=ExecutionStatus.SUCCESS,
                output=f"[DRY RUN] Would run: {command}",
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )

            if result.returncode == 0:
                return StepResult(
                    step=step,
                    status=ExecutionStatus.SUCCESS,
                    output=result.stdout[:2000] if result.stdout else "Command completed",
                )
            else:
                return StepResult(
                    step=step,
                    status=ExecutionStatus.FAILED,
                    output=result.stdout[:1000] if result.stdout else "",
                    error=result.stderr[:1000] if result.stderr else f"Exit code: {result.returncode}",
                )

        except subprocess.TimeoutExpired:
            return StepResult(
                step=step,
                status=ExecutionStatus.FAILED,
                error=f"Command timed out after {self.command_timeout}s",
            )

    def _execute_verification(self, step: PlanStep) -> StepResult:
        """Execute a verification step (tests, linting, file checks).

        Handles different verification scenarios:
        - If target is a .py file: verify it exists and has valid syntax
        - If target looks like a command: run it as shell command
        - Otherwise: check if target file/path exists
        """
        target = step.target

        # If target is a Python file, verify it exists and check syntax
        if target.endswith(".py"):
            file_path = self.repo_path / target
            if not file_path.exists():
                return StepResult(
                    step=step,
                    status=ExecutionStatus.FAILED,
                    error=f"File not found: {target}",
                )

            # Verify Python syntax
            try:
                import ast
                content = file_path.read_text()
                ast.parse(content)
                return StepResult(
                    step=step,
                    status=ExecutionStatus.SUCCESS,
                    output=f"Verified: {target} exists and has valid Python syntax",
                )
            except SyntaxError as e:
                return StepResult(
                    step=step,
                    status=ExecutionStatus.FAILED,
                    error=f"Syntax error in {target}: {e}",
                )

        # If target looks like a command (contains spaces or starts with known commands)
        command_prefixes = ("python", "pytest", "ruff", "npm", "make", "bash", "sh")
        if " " in target or target.split()[0] in command_prefixes:
            return self._execute_shell_command(step)

        # Otherwise just check if the path exists
        target_path = self.repo_path / target
        if target_path.exists():
            return StepResult(
                step=step,
                status=ExecutionStatus.SUCCESS,
                output=f"Verified: {target} exists",
            )
        else:
            return StepResult(
                step=step,
                status=ExecutionStatus.FAILED,
                error=f"Path not found: {target}",
            )

    def _generate_file_content(
        self,
        step: PlanStep,
        context: TaskContext,
    ) -> str:
        """Generate content for a new file using LLM."""
        prompt = self._build_generation_prompt(step, context)

        response = self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.EXECUTION,
            system=CODE_GENERATION_PROMPT,
            max_tokens=4096,
            temperature=0.0,
        )

        # Clean up response - remove markdown code blocks if present
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first and last lines (``` markers)
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        return content

    def _generate_edit_content(
        self,
        step: PlanStep,
        context: TaskContext,
        original_content: str,
    ) -> str:
        """Generate edited file content using LLM."""
        prompt = self._build_edit_prompt(step, context, original_content)

        response = self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.EXECUTION,
            system=EDIT_GENERATION_PROMPT,
            max_tokens=8192,
            temperature=0.0,
        )

        # Clean up response
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        return content

    def _build_generation_prompt(
        self,
        step: PlanStep,
        context: TaskContext,
    ) -> str:
        """Build prompt for file generation."""
        sections = [
            f"## Task: {context.task.title}",
            f"## File to Create: {step.target}",
            f"## Purpose: {step.description}",
        ]

        if step.details:
            sections.append(f"## Details: {step.details}")

        if context.prd:
            sections.append(f"## Requirements:\n{context.prd.content[:2000]}")

        # Include relevant existing files for context
        if context.loaded_files:
            sections.append("## Related Files:")
            for f in context.loaded_files[:3]:
                sections.append(f"### {f.path}")
                sections.append(f"```\n{f.content[:1500]}\n```")

        sections.append("\nGenerate the file content:")

        return "\n\n".join(sections)

    def _build_edit_prompt(
        self,
        step: PlanStep,
        context: TaskContext,
        original_content: str,
    ) -> str:
        """Build prompt for file editing."""
        sections = [
            f"## Task: {context.task.title}",
            f"## File to Edit: {step.target}",
            f"## Change Required: {step.description}",
        ]

        if step.details:
            sections.append(f"## Details: {step.details}")

        sections.append(f"## Current File Content:\n```\n{original_content[:6000]}\n```")

        sections.append("\nGenerate the complete updated file content:")

        return "\n\n".join(sections)

    def _dependencies_satisfied(
        self,
        step: PlanStep,
        previous_results: list[StepResult],
    ) -> bool:
        """Check if a step's dependencies are satisfied."""
        if not step.depends_on:
            return True

        for dep_index in step.depends_on:
            # Find the result for this dependency
            dep_result = None
            for result in previous_results:
                if result.step.index == dep_index:
                    dep_result = result
                    break

            if dep_result is None:
                return False  # Dependency not executed yet

            if dep_result.status != ExecutionStatus.SUCCESS:
                return False  # Dependency failed

        return True

    def rollback(self) -> list[str]:
        """Rollback all changes made by this executor.

        Returns:
            List of files that were rolled back
        """
        rolled_back = []

        # Process changes in reverse order
        for change in reversed(self.changes):
            file_path = self.repo_path / change.path

            try:
                if change.operation == "create":
                    # Delete the created file
                    if file_path.exists():
                        file_path.unlink()
                        rolled_back.append(f"Deleted: {change.path}")

                elif change.operation == "edit":
                    # Restore original content
                    if change.original_content is not None:
                        file_path.write_text(change.original_content, encoding="utf-8")
                        rolled_back.append(f"Restored: {change.path}")

                elif change.operation == "delete":
                    # Recreate the deleted file
                    if change.original_content is not None:
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(change.original_content, encoding="utf-8")
                        rolled_back.append(f"Recreated: {change.path}")

            except Exception as e:
                rolled_back.append(f"Failed to rollback {change.path}: {e}")

        self.changes.clear()
        return rolled_back
