"""Tests for agent planning module."""

import pytest
import json
from datetime import datetime, timezone

from codeframe.core.planner import (
    Planner,
    ImplementationPlan,
    PlanStep,
    StepType,
    Complexity,
    PLANNING_SYSTEM_PROMPT,
)
from codeframe.core.context import TaskContext
from codeframe.core.tasks import Task, TaskStatus
from codeframe.core.prd import PrdRecord
from codeframe.adapters.llm import MockProvider, LLMResponse, Purpose


def _utc_now():
    return datetime.now(timezone.utc)


class TestPlanStep:
    """Tests for PlanStep dataclass."""

    def test_basic_step(self):
        """Can create a basic step."""
        step = PlanStep(
            index=1,
            type=StepType.FILE_CREATE,
            description="Create main.py",
            target="src/main.py",
        )
        assert step.index == 1
        assert step.type == StepType.FILE_CREATE
        assert step.depends_on == []

    def test_step_with_dependencies(self):
        """Can create step with dependencies."""
        step = PlanStep(
            index=3,
            type=StepType.FILE_EDIT,
            description="Update imports",
            target="src/app.py",
            depends_on=[1, 2],
        )
        assert step.depends_on == [1, 2]

    def test_to_dict(self):
        """Can convert step to dict."""
        step = PlanStep(
            index=1,
            type=StepType.SHELL_COMMAND,
            description="Install deps",
            target="pip install requests",
            details="Required for HTTP client",
        )
        d = step.to_dict()
        assert d["type"] == "shell_command"
        assert d["target"] == "pip install requests"


class TestImplementationPlan:
    """Tests for ImplementationPlan dataclass."""

    @pytest.fixture
    def sample_plan(self):
        return ImplementationPlan(
            task_id="task-1",
            summary="Implement user login",
            steps=[
                PlanStep(1, StepType.FILE_CREATE, "Create auth module", "src/auth.py"),
                PlanStep(2, StepType.FILE_EDIT, "Add routes", "src/app.py", depends_on=[1]),
                PlanStep(3, StepType.SHELL_COMMAND, "Run tests", "pytest"),
                PlanStep(4, StepType.VERIFICATION, "Verify", "ruff check"),
            ],
            files_to_create=["src/auth.py"],
            files_to_modify=["src/app.py"],
            estimated_complexity=Complexity.MEDIUM,
            considerations=["Need to handle session expiry"],
        )

    def test_total_steps(self, sample_plan):
        """Counts total steps correctly."""
        assert sample_plan.total_steps == 4

    def test_file_operations(self, sample_plan):
        """Filters file operations correctly."""
        ops = sample_plan.file_operations
        assert len(ops) == 2
        assert ops[0].type == StepType.FILE_CREATE
        assert ops[1].type == StepType.FILE_EDIT

    def test_commands(self, sample_plan):
        """Filters commands correctly."""
        cmds = sample_plan.commands
        assert len(cmds) == 1
        assert cmds[0].target == "pytest"

    def test_to_dict(self, sample_plan):
        """Can convert to dict."""
        d = sample_plan.to_dict()
        assert d["task_id"] == "task-1"
        assert len(d["steps"]) == 4
        assert d["estimated_complexity"] == "medium"

    def test_to_markdown(self, sample_plan):
        """Can convert to markdown."""
        md = sample_plan.to_markdown()
        assert "# Implementation Plan" in md
        assert "task-1" in md
        assert "medium" in md
        assert "src/auth.py" in md
        assert "depends on: [1]" in md


class TestPlanner:
    """Tests for Planner class."""

    @pytest.fixture
    def mock_provider(self):
        return MockProvider()

    @pytest.fixture
    def sample_task(self):
        return Task(
            id="task-1",
            workspace_id="ws-1",
            prd_id=None,
            title="Add login endpoint",
            description="Create a /login endpoint that accepts username and password",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

    @pytest.fixture
    def sample_context(self, sample_task):
        return TaskContext(task=sample_task)

    def test_create_plan_calls_llm(self, mock_provider, sample_context):
        """Planner calls LLM with planning purpose."""
        # Set up mock response
        mock_response = json.dumps({
            "summary": "Create login endpoint",
            "steps": [
                {
                    "index": 1,
                    "type": "file_edit",
                    "description": "Add login route",
                    "target": "src/routes.py",
                    "details": "Add POST /login handler",
                    "depends_on": [],
                }
            ],
            "files_to_create": [],
            "files_to_modify": ["src/routes.py"],
            "estimated_complexity": "low",
            "considerations": [],
        })
        mock_provider.add_text_response(mock_response)

        planner = Planner(mock_provider)
        plan = planner.create_plan(sample_context)

        # Verify LLM was called with correct purpose
        assert mock_provider.call_count == 1
        assert mock_provider.last_call["purpose"] == Purpose.PLANNING

    def test_create_plan_parses_response(self, mock_provider, sample_context):
        """Planner parses LLM response correctly."""
        mock_response = json.dumps({
            "summary": "Implement authentication",
            "steps": [
                {
                    "index": 1,
                    "type": "file_create",
                    "description": "Create auth module",
                    "target": "src/auth.py",
                    "details": "Add User class and login function",
                    "depends_on": [],
                },
                {
                    "index": 2,
                    "type": "file_edit",
                    "description": "Add auth routes",
                    "target": "src/app.py",
                    "details": "Import auth and add /login route",
                    "depends_on": [1],
                },
                {
                    "index": 3,
                    "type": "verification",
                    "description": "Run tests",
                    "target": "pytest tests/",
                    "details": "",
                    "depends_on": [1, 2],
                },
            ],
            "files_to_create": ["src/auth.py"],
            "files_to_modify": ["src/app.py"],
            "estimated_complexity": "medium",
            "considerations": ["Consider rate limiting", "Add session timeout"],
        })
        mock_provider.add_text_response(mock_response)

        planner = Planner(mock_provider)
        plan = planner.create_plan(sample_context)

        assert plan.task_id == "task-1"
        assert plan.summary == "Implement authentication"
        assert plan.total_steps == 3
        assert plan.estimated_complexity == Complexity.MEDIUM
        assert "src/auth.py" in plan.files_to_create
        assert len(plan.considerations) == 2

    def test_create_plan_handles_json_in_markdown(self, mock_provider, sample_context):
        """Planner extracts JSON from markdown-wrapped response."""
        mock_response = """Here's the implementation plan:

```json
{
    "summary": "Simple fix",
    "steps": [
        {
            "index": 1,
            "type": "file_edit",
            "description": "Fix bug",
            "target": "src/main.py",
            "details": "Change line 42",
            "depends_on": []
        }
    ],
    "files_to_create": [],
    "files_to_modify": ["src/main.py"],
    "estimated_complexity": "low",
    "considerations": []
}
```

This should fix the issue."""
        mock_provider.add_text_response(mock_response)

        planner = Planner(mock_provider)
        plan = planner.create_plan(sample_context)

        assert plan.summary == "Simple fix"
        assert plan.total_steps == 1

    def test_create_plan_with_prd_context(self, mock_provider, sample_task):
        """Planner includes PRD in prompt when available."""
        prd = PrdRecord(
            id="prd-1",
            workspace_id="ws-1",
            title="Auth System",
            content="# Requirements\n- Login with email/password\n- JWT tokens",
            metadata={},
            created_at=_utc_now(),
        )
        context = TaskContext(task=sample_task, prd=prd)

        mock_response = json.dumps({
            "summary": "JWT auth implementation",
            "steps": [],
            "files_to_create": [],
            "files_to_modify": [],
            "estimated_complexity": "medium",
            "considerations": [],
        })
        mock_provider.add_text_response(mock_response)

        planner = Planner(mock_provider)
        planner.create_plan(context)

        # Check that PRD content was included in prompt
        prompt = mock_provider.last_call["messages"][0]["content"]
        assert "Product Requirements" in prompt
        assert "JWT tokens" in prompt

    def test_parse_step_type_defaults(self, mock_provider):
        """Unknown step types default to file_edit."""
        planner = Planner(mock_provider)
        assert planner._parse_step_type("unknown") == StepType.FILE_EDIT
        assert planner._parse_step_type("FILE_CREATE") == StepType.FILE_CREATE

    def test_parse_complexity_defaults(self, mock_provider):
        """Unknown complexity defaults to medium."""
        planner = Planner(mock_provider)
        assert planner._parse_complexity("unknown") == Complexity.MEDIUM
        assert planner._parse_complexity("HIGH") == Complexity.HIGH

    def test_create_plan_invalid_json_raises(self, mock_provider, sample_context):
        """Raises ValueError for invalid JSON response."""
        mock_provider.add_text_response("This is not valid JSON at all")

        planner = Planner(mock_provider)
        with pytest.raises(ValueError, match="No JSON object found"):
            planner.create_plan(sample_context)


class TestPlannerPromptBuilding:
    """Tests for prompt construction."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        # Default response for all calls
        provider.set_response_handler(lambda msgs: LLMResponse(
            content=json.dumps({
                "summary": "Test",
                "steps": [],
                "files_to_create": [],
                "files_to_modify": [],
                "estimated_complexity": "low",
                "considerations": [],
            })
        ))
        return provider

    def test_prompt_includes_task_title(self, mock_provider):
        """Prompt includes task title."""
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Implement feature X",
            description="",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        context = TaskContext(task=task)

        planner = Planner(mock_provider)
        planner.create_plan(context)

        prompt = mock_provider.last_call["messages"][0]["content"]
        assert "Implement feature X" in prompt

    def test_prompt_includes_task_description(self, mock_provider):
        """Prompt includes task description."""
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Task",
            description="Detailed requirements here",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        context = TaskContext(task=task)

        planner = Planner(mock_provider)
        planner.create_plan(context)

        prompt = mock_provider.last_call["messages"][0]["content"]
        assert "Detailed requirements here" in prompt

    def test_system_prompt_used(self, mock_provider):
        """Uses planning system prompt."""
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Task", description="",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        context = TaskContext(task=task)

        planner = Planner(mock_provider)
        planner.create_plan(context)

        assert mock_provider.last_call["system"] == PLANNING_SYSTEM_PROMPT
