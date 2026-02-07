"""Tests for code execution engine."""

import pytest
from datetime import datetime, timezone

from codeframe.core.executor import (
    Executor,
    ExecutionResult,
    StepResult,
    FileChange,
    ExecutionStatus,
)
from codeframe.core.planner import (
    PlanStep,
    StepType,
    ImplementationPlan,
)
from codeframe.core.context import TaskContext
from codeframe.core.tasks import Task, TaskStatus
from codeframe.adapters.llm import MockProvider, LLMResponse


def _utc_now():
    return datetime.now(timezone.utc)


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_create_change(self):
        """Can record a file creation."""
        change = FileChange(
            path="src/new.py",
            operation="create",
            original_content=None,
            new_content="print('hello')",
            timestamp=_utc_now(),
        )
        assert change.operation == "create"
        assert change.original_content is None

    def test_edit_change(self):
        """Can record a file edit."""
        change = FileChange(
            path="src/app.py",
            operation="edit",
            original_content="old code",
            new_content="new code",
            timestamp=_utc_now(),
        )
        assert change.operation == "edit"
        assert change.original_content == "old code"


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_success_result(self):
        """Can create a success result."""
        step = PlanStep(1, StepType.FILE_CREATE, "Create file", "test.py")
        result = StepResult(
            step=step,
            status=ExecutionStatus.SUCCESS,
            output="Created test.py",
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.error == ""

    def test_failed_result(self):
        """Can create a failed result."""
        step = PlanStep(1, StepType.SHELL_COMMAND, "Run tests", "pytest")
        result = StepResult(
            step=step,
            status=ExecutionStatus.FAILED,
            error="Tests failed",
        )
        assert result.status == ExecutionStatus.FAILED
        assert "failed" in result.error.lower()


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    @pytest.fixture
    def sample_plan(self):
        return ImplementationPlan(
            task_id="task-1",
            summary="Test plan",
            steps=[
                PlanStep(1, StepType.FILE_CREATE, "Create", "a.py"),
                PlanStep(2, StepType.FILE_EDIT, "Edit", "b.py"),
            ],
        )

    def test_failed_steps(self, sample_plan):
        """Can get failed steps."""
        results = [
            StepResult(sample_plan.steps[0], ExecutionStatus.SUCCESS, "ok"),
            StepResult(sample_plan.steps[1], ExecutionStatus.FAILED, error="fail"),
        ]
        exec_result = ExecutionResult(
            plan=sample_plan,
            step_results=results,
            success=False,
        )
        assert len(exec_result.failed_steps) == 1

    def test_file_changes(self, sample_plan):
        """Can aggregate file changes."""
        change1 = FileChange("a.py", "create", None, "code", _utc_now())
        change2 = FileChange("b.py", "edit", "old", "new", _utc_now())
        results = [
            StepResult(sample_plan.steps[0], ExecutionStatus.SUCCESS, file_changes=[change1]),
            StepResult(sample_plan.steps[1], ExecutionStatus.SUCCESS, file_changes=[change2]),
        ]
        exec_result = ExecutionResult(
            plan=sample_plan,
            step_results=results,
            success=True,
        )
        assert len(exec_result.file_changes) == 2


class TestExecutorFileOperations:
    """Tests for Executor file operations."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        # Default response for code generation
        provider.set_response_handler(
            lambda msgs: LLMResponse(content="# Generated code\nprint('hello')")
        )
        return provider

    @pytest.fixture
    def sample_context(self):
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test task", description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        return TaskContext(task=task)

    def test_file_create(self, tmp_path, mock_provider, sample_context):
        """Can create a new file."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_CREATE, "Create main", "main.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert (tmp_path / "main.py").exists()
        assert len(result.file_changes) == 1

    def test_file_create_falls_back_when_exists(self, tmp_path, mock_provider, sample_context):
        """File create falls back to edit when file exists with different content."""
        (tmp_path / "existing.py").write_text("# existing")
        mock_provider.set_response_handler(
            lambda msgs: LLMResponse(content="# Updated content\nprint('updated')")
        )
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_CREATE, "Create", "existing.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "existing.py" in result.output
        content = (tmp_path / "existing.py").read_text()
        assert "Updated content" in content
        assert len(result.file_changes) == 1
        assert result.file_changes[0].original_content == "# existing"
        assert result.file_changes[0].operation == "edit"

    def test_file_create_nested(self, tmp_path, mock_provider, sample_context):
        """Can create file in nested directory."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_CREATE, "Create", "src/utils/helpers.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert (tmp_path / "src" / "utils" / "helpers.py").exists()

    def test_file_edit(self, tmp_path, mock_provider, sample_context):
        """Can edit an existing file."""
        (tmp_path / "app.py").write_text("# Original content")
        mock_provider.set_response_handler(
            lambda msgs: LLMResponse(content="# Updated content\nprint('updated')")
        )
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_EDIT, "Update app", "app.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "Updated content" in (tmp_path / "app.py").read_text()
        assert len(result.file_changes) == 1
        assert result.file_changes[0].original_content == "# Original content"

    def test_file_edit_not_found(self, tmp_path, mock_provider, sample_context):
        """File edit fails if file doesn't exist."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_EDIT, "Edit", "nonexistent.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.FAILED
        assert "not found" in result.error.lower()

    def test_file_delete(self, tmp_path, mock_provider, sample_context):
        """Can delete a file."""
        (tmp_path / "to_delete.py").write_text("# Delete me")
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_DELETE, "Remove", "to_delete.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert not (tmp_path / "to_delete.py").exists()

    def test_file_delete_already_gone(self, tmp_path, mock_provider, sample_context):
        """File delete succeeds if file already gone."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_DELETE, "Remove", "already_gone.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS


class TestFileCreateConflictHandling:
    """Tests for file_create fallback when file already exists."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        provider.set_response_handler(
            lambda msgs: LLMResponse(content="# Generated code\nprint('hello')")
        )
        return provider

    @pytest.fixture
    def sample_context(self):
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test task", description="Test",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        return TaskContext(task=task)

    def test_file_create_falls_back_to_edit_when_content_differs(
        self, tmp_path, mock_provider, sample_context
    ):
        """file_create falls back to file_edit when file exists with different content."""
        (tmp_path / "existing.py").write_text("# old content")
        mock_provider.set_response_handler(
            lambda msgs: LLMResponse(content="# Updated content\nprint('updated')")
        )
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_CREATE, "Create", "existing.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "existing.py" in result.output
        # File should have new content via edit fallback
        content = (tmp_path / "existing.py").read_text()
        assert "Updated content" in content
        # Should have a file change recorded with original content
        assert len(result.file_changes) == 1
        assert result.file_changes[0].original_content == "# old content"
        assert result.file_changes[0].operation == "edit"

    def test_file_create_fallback_passes_existing_content_to_llm(
        self, tmp_path, mock_provider, sample_context
    ):
        """file_create fallback sends existing content to LLM via edit prompt."""
        (tmp_path / "config.toml").write_text("[project]\nname = 'my-app'")
        captured_prompts = []
        mock_provider.set_response_handler(
            lambda msgs: (
                captured_prompts.append(msgs[-1]["content"]),
                LLMResponse(content="[project]\nname = 'my-app'\nversion = '1.0'"),
            )[-1]
        )
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_CREATE, "Create config", "config.toml")

        executor.execute_step(step, sample_context)

        assert len(captured_prompts) == 1
        # Edit prompt should include existing content
        assert "my-app" in captured_prompts[0]
        assert "Current File Content" in captured_prompts[0]

    def test_file_create_succeeds_when_identical_content(
        self, tmp_path, mock_provider, sample_context
    ):
        """file_create returns SUCCESS when file exists with identical content."""
        existing_content = "# Generated code\nprint('hello')"
        (tmp_path / "same.py").write_text(existing_content)
        mock_provider.set_response_handler(
            lambda msgs: LLMResponse(content=existing_content)
        )
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_CREATE, "Create", "same.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "already exists" in result.output.lower()
        # Content should remain unchanged
        assert (tmp_path / "same.py").read_text() == existing_content

    def test_file_create_dry_run_with_existing_file(
        self, tmp_path, mock_provider, sample_context
    ):
        """file_create dry run still works when file exists."""
        (tmp_path / "existing.py").write_text("# old")
        executor = Executor(mock_provider, tmp_path, dry_run=True)
        step = PlanStep(1, StepType.FILE_CREATE, "Create", "existing.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "DRY RUN" in result.output
        # Original content untouched
        assert (tmp_path / "existing.py").read_text() == "# old"


class TestExecutorDryRun:
    """Tests for dry run mode."""

    @pytest.fixture
    def mock_provider(self):
        return MockProvider(default_response="generated code")

    @pytest.fixture
    def sample_context(self):
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test", description="",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        return TaskContext(task=task)

    def test_dry_run_file_create(self, tmp_path, mock_provider, sample_context):
        """Dry run doesn't create files."""
        executor = Executor(mock_provider, tmp_path, dry_run=True)
        step = PlanStep(1, StepType.FILE_CREATE, "Create", "new.py")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "DRY RUN" in result.output
        assert not (tmp_path / "new.py").exists()

    def test_dry_run_shell_command(self, tmp_path, mock_provider, sample_context):
        """Dry run doesn't execute commands."""
        executor = Executor(mock_provider, tmp_path, dry_run=True)
        step = PlanStep(1, StepType.SHELL_COMMAND, "Run", "echo hello")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "DRY RUN" in result.output


class TestExecutorShellCommands:
    """Tests for shell command execution."""

    @pytest.fixture
    def mock_provider(self):
        return MockProvider()

    @pytest.fixture
    def sample_context(self):
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test", description="",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        return TaskContext(task=task)

    def test_shell_command_success(self, tmp_path, mock_provider, sample_context):
        """Can execute a simple command."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.SHELL_COMMAND, "Echo", "echo hello")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.SUCCESS
        assert "hello" in result.output

    def test_shell_command_failure(self, tmp_path, mock_provider, sample_context):
        """Handles command failure."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.SHELL_COMMAND, "Bad cmd", "exit 1")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.FAILED

    def test_dangerous_command_blocked(self, tmp_path, mock_provider, sample_context):
        """Blocks dangerous commands."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.SHELL_COMMAND, "Bad", "rm -rf /")

        result = executor.execute_step(step, sample_context)

        assert result.status == ExecutionStatus.FAILED
        assert "dangerous" in result.error.lower() or "blocked" in result.error.lower()


class TestExecutorRollback:
    """Tests for rollback functionality."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        provider.set_response_handler(
            lambda msgs: LLMResponse(content="# New content")
        )
        return provider

    @pytest.fixture
    def sample_context(self):
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test", description="",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        return TaskContext(task=task)

    def test_rollback_created_file(self, tmp_path, mock_provider, sample_context):
        """Rollback deletes created files."""
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_CREATE, "Create", "new.py")

        executor.execute_step(step, sample_context)
        assert (tmp_path / "new.py").exists()

        rolled_back = executor.rollback()
        assert not (tmp_path / "new.py").exists()
        assert len(rolled_back) == 1

    def test_rollback_edited_file(self, tmp_path, mock_provider, sample_context):
        """Rollback restores edited files."""
        original = "# Original code"
        (tmp_path / "app.py").write_text(original)
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_EDIT, "Edit", "app.py")

        executor.execute_step(step, sample_context)
        assert "New content" in (tmp_path / "app.py").read_text()

        executor.rollback()
        assert (tmp_path / "app.py").read_text() == original

    def test_rollback_deleted_file(self, tmp_path, mock_provider, sample_context):
        """Rollback recreates deleted files."""
        original = "# Don't delete me"
        (tmp_path / "keep.py").write_text(original)
        executor = Executor(mock_provider, tmp_path)
        step = PlanStep(1, StepType.FILE_DELETE, "Delete", "keep.py")

        executor.execute_step(step, sample_context)
        assert not (tmp_path / "keep.py").exists()

        executor.rollback()
        assert (tmp_path / "keep.py").exists()
        assert (tmp_path / "keep.py").read_text() == original


class TestExecutorPlanExecution:
    """Tests for full plan execution."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        provider.set_response_handler(
            lambda msgs: LLMResponse(content="# Generated\npass")
        )
        return provider

    @pytest.fixture
    def sample_context(self):
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test", description="",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        return TaskContext(task=task)

    def test_execute_plan_all_success(self, tmp_path, mock_provider, sample_context):
        """Executes all steps successfully."""
        plan = ImplementationPlan(
            task_id="t1",
            summary="Test",
            steps=[
                PlanStep(1, StepType.FILE_CREATE, "Create", "a.py"),
                PlanStep(2, StepType.FILE_CREATE, "Create", "b.py"),
            ],
        )
        executor = Executor(mock_provider, tmp_path)

        result = executor.execute_plan(plan, sample_context)

        assert result.success
        assert len(result.step_results) == 2
        assert all(r.status == ExecutionStatus.SUCCESS for r in result.step_results)

    def test_execute_plan_stops_on_failure(self, tmp_path, mock_provider, sample_context):
        """Stops execution on first failure."""
        # Make second step fail by trying to edit non-existent file
        plan = ImplementationPlan(
            task_id="t1",
            summary="Test",
            steps=[
                PlanStep(1, StepType.FILE_CREATE, "Create", "a.py"),
                PlanStep(2, StepType.FILE_EDIT, "Edit missing", "missing.py"),
                PlanStep(3, StepType.FILE_CREATE, "Create", "c.py"),
            ],
        )
        executor = Executor(mock_provider, tmp_path)

        result = executor.execute_plan(plan, sample_context)

        assert not result.success
        assert len(result.step_results) == 2  # Stopped after failure
        assert result.step_results[0].status == ExecutionStatus.SUCCESS
        assert result.step_results[1].status == ExecutionStatus.FAILED

    def test_execute_plan_skips_unsatisfied_deps(self, tmp_path, mock_provider, sample_context):
        """Skips steps with unsatisfied dependencies."""
        plan = ImplementationPlan(
            task_id="t1",
            summary="Test",
            steps=[
                PlanStep(1, StepType.FILE_EDIT, "Edit missing", "missing.py"),
                PlanStep(2, StepType.FILE_CREATE, "Depends on 1", "b.py", depends_on=[1]),
            ],
        )
        executor = Executor(mock_provider, tmp_path)

        result = executor.execute_plan(plan, sample_context)

        assert not result.success
        # First step fails, stops execution
        assert len(result.step_results) == 1
