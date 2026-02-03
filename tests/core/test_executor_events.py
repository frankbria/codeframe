"""Tests for Executor event publishing integration.

TDD: Tests written first to define expected behavior of
event publishing during task execution.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from codeframe.core.executor import Executor, ExecutionStatus
from codeframe.core.planner import PlanStep, StepType, ImplementationPlan
from codeframe.core.context import TaskContext
from codeframe.core.streaming import EventPublisher
from codeframe.adapters.llm import MockProvider


@pytest.fixture
def mock_llm():
    """Create a mock LLM provider."""
    return MockProvider()


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary repository directory."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    return repo


@pytest.fixture
def mock_context():
    """Create a minimal mock TaskContext."""
    ctx = MagicMock(spec=TaskContext)
    ctx.task = MagicMock()
    ctx.task.id = "task-123"
    ctx.task.title = "Test Task"
    ctx.prd = None
    ctx.loaded_files = []
    return ctx


class TestExecutorWithEventPublisher:
    """Tests for Executor event publishing functionality."""

    def test_executor_accepts_event_publisher(self, mock_llm, temp_repo):
        """Executor should accept an optional event_publisher parameter."""
        publisher = EventPublisher()

        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
            event_publisher=publisher,
        )

        assert executor.event_publisher is publisher

    def test_executor_works_without_event_publisher(self, mock_llm, temp_repo):
        """Executor should work normally without an event publisher."""
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
        )

        assert executor.event_publisher is None

    @pytest.mark.asyncio
    async def test_execute_step_publishes_output_not_progress(
        self, mock_llm, temp_repo, mock_context
    ):
        """execute_step_async publishes output events, not progress events.

        Progress events are emitted by execute_plan_async which has access
        to total_steps. execute_step_async only emits output/error events.
        """
        publisher = EventPublisher()
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
            event_publisher=publisher,
        )

        step = PlanStep(
            index=1,
            type=StepType.SHELL_COMMAND,
            target="echo hello",
            description="Print hello",
        )

        # Subscribe to events for the task
        events_received = []

        async def collect_events():
            async for event in publisher.subscribe("task-123"):
                events_received.append(event)
                if len(events_received) >= 1:  # Just output event expected
                    break

        # Start collecting in background
        collector = asyncio.create_task(collect_events())

        # Give subscriber time to register
        await asyncio.sleep(0.05)

        # Execute the step (this publishes events)
        result = await executor.execute_step_async(step, mock_context, "task-123")

        # Complete the task to end subscription
        await publisher.complete_task("task-123")

        # Wait for collector with timeout
        try:
            await asyncio.wait_for(collector, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Verify we got output event but NOT progress event
        # (progress events come from execute_plan_async which knows total_steps)
        output_events = [e for e in events_received if e.event_type == "output"]
        progress_events = [e for e in events_received if e.event_type == "progress"]
        assert len(output_events) >= 1, "Should publish output event"
        assert len(progress_events) == 0, "Should NOT publish progress event (that's execute_plan_async's job)"

    @pytest.mark.asyncio
    async def test_shell_command_publishes_output_event(
        self, mock_llm, temp_repo, mock_context
    ):
        """Shell commands should publish output events with stdout/stderr."""
        publisher = EventPublisher()
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
            event_publisher=publisher,
        )

        step = PlanStep(
            index=1,
            type=StepType.SHELL_COMMAND,
            target="echo 'test output'",
            description="Echo test",
        )

        events_received = []

        async def collect_events():
            async for event in publisher.subscribe("task-123"):
                events_received.append(event)
                if event.event_type == "output":
                    break

        collector = asyncio.create_task(collect_events())
        await asyncio.sleep(0.05)

        await executor.execute_step_async(step, mock_context, "task-123")
        await publisher.complete_task("task-123")

        try:
            await asyncio.wait_for(collector, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Verify output event
        output_events = [e for e in events_received if e.event_type == "output"]
        assert len(output_events) >= 1
        assert output_events[0].stream in ("stdout", "stderr")

    @pytest.mark.asyncio
    async def test_failed_step_publishes_error_event(
        self, mock_llm, temp_repo, mock_context
    ):
        """Failed steps should publish error events."""
        publisher = EventPublisher()
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
            event_publisher=publisher,
        )

        # This command will fail (false always returns exit code 1)
        step = PlanStep(
            index=1,
            type=StepType.SHELL_COMMAND,
            target="false",
            description="Failing command",
        )

        events_received = []

        async def collect_events():
            async for event in publisher.subscribe("task-123"):
                events_received.append(event)
                if event.event_type == "error":
                    break

        collector = asyncio.create_task(collect_events())
        await asyncio.sleep(0.05)

        result = await executor.execute_step_async(step, mock_context, "task-123")
        await publisher.complete_task("task-123")

        try:
            await asyncio.wait_for(collector, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Verify error event
        error_events = [e for e in events_received if e.event_type == "error"]
        assert len(error_events) >= 1
        assert error_events[0].task_id == "task-123"


class TestExecutePlanWithEvents:
    """Tests for execute_plan event publishing."""

    @pytest.mark.asyncio
    async def test_execute_plan_async_publishes_progress_per_step(
        self, mock_llm, temp_repo, mock_context
    ):
        """execute_plan_async should publish progress for each step."""
        publisher = EventPublisher()
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
            event_publisher=publisher,
        )

        plan = ImplementationPlan(
            task_id="task-123",
            summary="Test plan",
            steps=[
                PlanStep(index=1, type=StepType.SHELL_COMMAND, target="echo 1", description="Step 1"),
                PlanStep(index=2, type=StepType.SHELL_COMMAND, target="echo 2", description="Step 2"),
            ],
        )

        events_received = []

        async def collect_events():
            async for event in publisher.subscribe("task-123"):
                events_received.append(event)

        collector = asyncio.create_task(collect_events())
        await asyncio.sleep(0.05)

        result = await executor.execute_plan_async(plan, mock_context)
        await publisher.complete_task("task-123")

        try:
            await asyncio.wait_for(collector, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Should have at least 2 progress events (one per step)
        progress_events = [e for e in events_received if e.event_type == "progress"]
        assert len(progress_events) >= 2

    @pytest.mark.asyncio
    async def test_execute_plan_async_publishes_completion(
        self, mock_llm, temp_repo, mock_context
    ):
        """execute_plan_async should publish completion event when done."""
        publisher = EventPublisher()
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
            event_publisher=publisher,
        )

        plan = ImplementationPlan(
            task_id="task-123",
            summary="Test plan",
            steps=[
                PlanStep(index=1, type=StepType.SHELL_COMMAND, target="echo done", description="Done"),
            ],
        )

        events_received = []

        async def collect_events():
            async for event in publisher.subscribe("task-123"):
                events_received.append(event)
                if event.event_type == "completion":
                    break

        collector = asyncio.create_task(collect_events())
        await asyncio.sleep(0.05)

        result = await executor.execute_plan_async(plan, mock_context)
        await publisher.complete_task("task-123")

        try:
            await asyncio.wait_for(collector, timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Verify completion event
        completion_events = [e for e in events_received if e.event_type == "completion"]
        assert len(completion_events) == 1
        assert completion_events[0].status == "completed"


class TestSyncExecutorMethods:
    """Tests that sync executor methods still work correctly."""

    def test_execute_step_sync_works_without_publisher(
        self, mock_llm, temp_repo, mock_context
    ):
        """Sync execute_step should work without event publisher."""
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
        )

        step = PlanStep(
            index=1,
            type=StepType.SHELL_COMMAND,
            target="echo hello",
            description="Print hello",
        )

        result = executor.execute_step(step, mock_context)

        assert result.status == ExecutionStatus.SUCCESS

    def test_execute_plan_sync_works_without_publisher(
        self, mock_llm, temp_repo, mock_context
    ):
        """Sync execute_plan should work without event publisher."""
        executor = Executor(
            llm_provider=mock_llm,
            repo_path=temp_repo,
        )

        plan = ImplementationPlan(
            task_id="task-123",
            summary="Test plan",
            steps=[
                PlanStep(index=1, type=StepType.SHELL_COMMAND, target="echo test", description="Test"),
            ],
        )

        result = executor.execute_plan(plan, mock_context)

        assert result.success is True
