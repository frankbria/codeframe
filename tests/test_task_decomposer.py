"""Tests for Task Decomposition from Issues.

Following TDD: These tests are written FIRST, before implementation.
Target: >85% coverage for task_decomposer.py module.

Tests cover:
- Decomposing issues into 3-8 tasks
- Sequential task numbering (2.1.1, 2.1.2, 2.1.3)
- Dependency chain creation (2.1.2 depends on 2.1.1)
- can_parallelize always FALSE within issue
- Priority inheritance from issue
- Task validation
- Claude API mocking
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from codeframe.planning.task_decomposer import TaskDecomposer
from codeframe.core.models import Issue, Task, TaskStatus
from codeframe.providers.anthropic import AnthropicProvider


@pytest.fixture
def sample_issue():
    """Provide a sample issue for testing."""
    return Issue(
        id=1,
        project_id=1,
        issue_number="2.1",
        title="User Authentication System",
        description="Implement a complete user authentication system with login, logout, and session management.",
        status=TaskStatus.PENDING,
        priority=1,
        workflow_step=1
    )


@pytest.fixture
def complex_issue():
    """Provide a complex issue for testing."""
    return Issue(
        id=2,
        project_id=1,
        issue_number="3.5",
        title="E-commerce Checkout Flow",
        description="""Implement complete e-commerce checkout flow including:
        - Shopping cart management
        - Payment processing integration
        - Order confirmation emails
        - Inventory management
        - Receipt generation
        - Error handling for failed payments
        """,
        status=TaskStatus.PENDING,
        priority=0,
        workflow_step=2
    )


@pytest.fixture
def simple_issue():
    """Provide a simple issue for testing."""
    return Issue(
        id=3,
        project_id=1,
        issue_number="1.2",
        title="Add Logging",
        description="Add structured logging to the application.",
        status=TaskStatus.PENDING,
        priority=3,
        workflow_step=1
    )


@pytest.fixture
def mock_provider():
    """Provide a mock Anthropic provider."""
    provider = Mock(spec=AnthropicProvider)
    return provider


@pytest.mark.unit
class TestTaskDecomposerInitialization:
    """Test TaskDecomposer initialization."""

    def test_task_decomposer_initializes_successfully(self):
        """Test that TaskDecomposer initializes without errors."""
        # ACT
        decomposer = TaskDecomposer()

        # ASSERT
        assert decomposer is not None
        assert isinstance(decomposer, TaskDecomposer)


@pytest.mark.unit
class TestTaskDecomposition:
    """Test task decomposition from issues."""

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_returns_list_of_tasks(self, mock_provider_class, sample_issue, mock_provider):
        """Test that decompose_issue returns a list of Task objects."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model with fields (username, email, password_hash)
            2. Implement password hashing with bcrypt
            3. Create login endpoint with JWT token generation
            4. Create logout endpoint with token invalidation
            5. Add session management middleware
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert isinstance(tasks, list)
        assert len(tasks) >= 3  # Minimum 3 tasks
        assert len(tasks) <= 8  # Maximum 8 tasks
        assert all(isinstance(task, Task) for task in tasks)

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_creates_sequential_task_numbers(self, mock_provider_class, sample_issue, mock_provider):
        """Test that tasks are numbered sequentially (2.1.1, 2.1.2, 2.1.3)."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            4. Create logout endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert tasks[0].task_number == "2.1.1"
        assert tasks[1].task_number == "2.1.2"
        assert tasks[2].task_number == "2.1.3"
        assert tasks[3].task_number == "2.1.4"

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_sets_parent_issue_number(self, mock_provider_class, sample_issue, mock_provider):
        """Test that all tasks have correct parent_issue_number."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert all(task.parent_issue_number == "2.1" for task in tasks)

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_creates_dependency_chain(self, mock_provider_class, sample_issue, mock_provider):
        """Test that tasks have correct dependency chain (2.1.2 depends on 2.1.1)."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            4. Create logout endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert tasks[0].depends_on == ""  # First task has no dependencies
        assert tasks[1].depends_on == "2.1.1"  # Second depends on first
        assert tasks[2].depends_on == "2.1.2"  # Third depends on second
        assert tasks[3].depends_on == "2.1.3"  # Fourth depends on third

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_sets_can_parallelize_to_false(self, mock_provider_class, sample_issue, mock_provider):
        """Test that all tasks have can_parallelize=False."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert all(task.can_parallelize is False for task in tasks)

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_inherits_priority_from_issue(self, mock_provider_class, sample_issue, mock_provider):
        """Test that tasks inherit priority from parent issue."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert all(task.priority == sample_issue.priority for task in tasks)

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_sets_issue_id(self, mock_provider_class, sample_issue, mock_provider):
        """Test that tasks have correct issue_id foreign key."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert all(task.issue_id == sample_issue.id for task in tasks)

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_sets_project_id(self, mock_provider_class, sample_issue, mock_provider):
        """Test that tasks have correct project_id."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert all(task.project_id == sample_issue.project_id for task in tasks)


@pytest.mark.unit
class TestTaskValidation:
    """Test task validation and error handling."""

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_validates_task_has_title(self, mock_provider_class, sample_issue, mock_provider):
        """Test that all generated tasks have non-empty titles."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model
            2. Implement password hashing
            3. Create login endpoint
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert all(task.title for task in tasks)
        assert all(len(task.title) > 0 for task in tasks)

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_validates_task_has_description(self, mock_provider_class, sample_issue, mock_provider):
        """Test that all generated tasks have descriptions."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model with username, email, password_hash fields
            2. Implement password hashing using bcrypt library
            3. Create login endpoint with JWT token generation
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT
        assert all(task.description for task in tasks)
        assert all(len(task.description) > 0 for task in tasks)

    def test_decompose_issue_raises_error_for_invalid_issue(self, mock_provider):
        """Test that decompose_issue raises error for invalid issue."""
        # ARRANGE
        decomposer = TaskDecomposer()
        invalid_issue = Issue()  # Missing required fields

        # ACT & ASSERT
        with pytest.raises(ValueError) as exc_info:
            decomposer.decompose_issue(invalid_issue, mock_provider)

        assert "issue_number" in str(exc_info.value).lower() or "title" in str(exc_info.value).lower()


@pytest.mark.unit
class TestAdaptiveTaskCount:
    """Test adaptive task count based on issue complexity."""

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_simple_issue_generates_fewer_tasks(self, mock_provider_class, simple_issue, mock_provider):
        """Test that simple issues generate 3-4 tasks."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Add logging configuration file
            2. Implement structured logger class
            3. Add logging to existing modules
            """,
            "usage": {"input_tokens": 50, "output_tokens": 40}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(simple_issue, mock_provider)

        # ASSERT
        assert len(tasks) >= 3
        assert len(tasks) <= 5  # Simple issues should have fewer tasks

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_complex_issue_generates_more_tasks(self, mock_provider_class, complex_issue, mock_provider):
        """Test that complex issues generate 6-8 tasks."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create shopping cart database models
            2. Implement cart CRUD operations
            3. Integrate Stripe payment gateway
            4. Create payment processing endpoints
            5. Implement order confirmation email service
            6. Add inventory management logic
            7. Create receipt generation service
            8. Add error handling for payment failures
            """,
            "usage": {"input_tokens": 150, "output_tokens": 120}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(complex_issue, mock_provider)

        # ASSERT
        assert len(tasks) >= 6
        assert len(tasks) <= 8  # Complex issues should have more tasks


@pytest.mark.unit
class TestPromptGeneration:
    """Test decomposition prompt generation."""

    def test_build_decomposition_prompt_includes_issue_title(self, sample_issue):
        """Test that prompt includes issue title."""
        # ARRANGE
        decomposer = TaskDecomposer()

        # ACT
        prompt = decomposer.build_decomposition_prompt(sample_issue)

        # ASSERT
        assert sample_issue.title in prompt

    def test_build_decomposition_prompt_includes_issue_description(self, sample_issue):
        """Test that prompt includes issue description."""
        # ARRANGE
        decomposer = TaskDecomposer()

        # ACT
        prompt = decomposer.build_decomposition_prompt(sample_issue)

        # ASSERT
        assert sample_issue.description in prompt

    def test_build_decomposition_prompt_requests_3_to_8_tasks(self, sample_issue):
        """Test that prompt requests 3-8 atomic tasks."""
        # ARRANGE
        decomposer = TaskDecomposer()

        # ACT
        prompt = decomposer.build_decomposition_prompt(sample_issue)

        # ASSERT
        assert "3-8" in prompt or ("3" in prompt and "8" in prompt)
        assert "atomic" in prompt.lower() or "task" in prompt.lower()


@pytest.mark.unit
class TestResponseParsing:
    """Test Claude response parsing."""

    def test_parse_claude_response_extracts_tasks(self, sample_issue):
        """Test that parser extracts tasks from Claude response."""
        # ARRANGE
        decomposer = TaskDecomposer()
        response = """
        1. Create User model - Implement User database model with fields
        2. Implement password hashing - Use bcrypt library for secure storage
        3. Create login endpoint - Implement POST /api/login with JWT
        4. Create logout endpoint - Handle token invalidation
        """

        # ACT
        tasks = decomposer.parse_claude_response(response, sample_issue)

        # ASSERT
        assert len(tasks) == 4
        assert tasks[0].title == "Create User model"
        assert tasks[1].title == "Implement password hashing"
        assert tasks[2].title == "Create login endpoint"
        assert tasks[3].title == "Create logout endpoint"

    def test_parse_claude_response_handles_various_formats(self, sample_issue):
        """Test that parser handles various response formats."""
        # ARRANGE
        decomposer = TaskDecomposer()
        response = """
        Task 1: Create User model - with username, email, password_hash
        Task 2: Implement password hashing - using bcrypt
        Task 3: Create login endpoint - with JWT tokens
        """

        # ACT
        tasks = decomposer.parse_claude_response(response, sample_issue)

        # ASSERT
        assert len(tasks) == 3
        assert all(isinstance(task, Task) for task in tasks)

    def test_parse_claude_response_handles_multiline_descriptions(self, sample_issue):
        """Test that parser handles multiline task descriptions."""
        # ARRANGE
        decomposer = TaskDecomposer()
        response = """
        1. Create User model
           - Add username field
           - Add email field
           - Add password_hash field

        2. Implement password hashing
           - Use bcrypt library
           - Add salt generation
        """

        # ACT
        tasks = decomposer.parse_claude_response(response, sample_issue)

        # ASSERT
        assert len(tasks) >= 2
        assert tasks[0].description != ""

    def test_parse_claude_response_handles_empty_response(self, sample_issue):
        """Test that parser handles empty response gracefully."""
        # ARRANGE
        decomposer = TaskDecomposer()
        response = ""

        # ACT & ASSERT
        with pytest.raises(ValueError) as exc_info:
            decomposer.parse_claude_response(response, sample_issue)

        assert "empty" in str(exc_info.value).lower() or "no tasks" in str(exc_info.value).lower()


@pytest.mark.unit
class TestDependencyChainCreation:
    """Test dependency chain creation."""

    def test_create_dependency_chain_sets_first_task_no_dependency(self):
        """Test that first task has no dependency."""
        # ARRANGE
        decomposer = TaskDecomposer()
        tasks = [
            Task(task_number="2.1.1", title="Task 1"),
            Task(task_number="2.1.2", title="Task 2"),
            Task(task_number="2.1.3", title="Task 3"),
        ]

        # ACT
        chained_tasks = decomposer.create_dependency_chain(tasks)

        # ASSERT
        assert chained_tasks[0].depends_on == ""

    def test_create_dependency_chain_links_sequential_tasks(self):
        """Test that sequential tasks are properly linked."""
        # ARRANGE
        decomposer = TaskDecomposer()
        tasks = [
            Task(task_number="2.1.1", title="Task 1"),
            Task(task_number="2.1.2", title="Task 2"),
            Task(task_number="2.1.3", title="Task 3"),
        ]

        # ACT
        chained_tasks = decomposer.create_dependency_chain(tasks)

        # ASSERT
        assert chained_tasks[1].depends_on == "2.1.1"
        assert chained_tasks[2].depends_on == "2.1.2"

    def test_create_dependency_chain_preserves_task_order(self):
        """Test that task order is preserved."""
        # ARRANGE
        decomposer = TaskDecomposer()
        tasks = [
            Task(task_number="2.1.1", title="First"),
            Task(task_number="2.1.2", title="Second"),
            Task(task_number="2.1.3", title="Third"),
        ]

        # ACT
        chained_tasks = decomposer.create_dependency_chain(tasks)

        # ASSERT
        assert chained_tasks[0].title == "First"
        assert chained_tasks[1].title == "Second"
        assert chained_tasks[2].title == "Third"


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling and edge cases."""

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_handles_provider_exception(self, mock_provider_class, sample_issue, mock_provider):
        """Test that decompose_issue handles provider exceptions gracefully."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.side_effect = Exception("API connection failed")

        decomposer = TaskDecomposer()

        # ACT & ASSERT
        with pytest.raises(Exception) as exc_info:
            decomposer.decompose_issue(sample_issue, mock_provider)

        assert "API connection failed" in str(exc_info.value)

    def test_create_dependency_chain_with_empty_list(self):
        """Test that create_dependency_chain handles empty list."""
        # ARRANGE
        decomposer = TaskDecomposer()
        tasks = []

        # ACT
        result = decomposer.create_dependency_chain(tasks)

        # ASSERT
        assert result == []

    def test_parse_claude_response_truncates_too_many_tasks(self, sample_issue):
        """Test that parser truncates response with >8 tasks."""
        # ARRANGE
        decomposer = TaskDecomposer()
        response = """
        1. Task 1 - Description 1
        2. Task 2 - Description 2
        3. Task 3 - Description 3
        4. Task 4 - Description 4
        5. Task 5 - Description 5
        6. Task 6 - Description 6
        7. Task 7 - Description 7
        8. Task 8 - Description 8
        9. Task 9 - Description 9
        10. Task 10 - Description 10
        """

        # ACT
        tasks = decomposer.parse_claude_response(response, sample_issue)

        # ASSERT
        assert len(tasks) == 8  # Truncated to maximum
        assert tasks[7].task_number == "2.1.8"


@pytest.mark.unit
class TestTaskCountEstimation:
    """Test adaptive task count estimation."""

    def test_estimate_task_count_for_short_description(self):
        """Test that short descriptions suggest 3-4 tasks."""
        # ARRANGE
        decomposer = TaskDecomposer()
        issue = Issue(
            issue_number="1.1",
            title="Simple Task",
            description="Short description here",  # < 100 chars
            priority=2
        )

        # ACT
        count = decomposer._estimate_task_count(issue)

        # ASSERT
        assert count == "3-4"

    def test_estimate_task_count_for_medium_description(self):
        """Test that medium descriptions suggest 4-6 tasks."""
        # ARRANGE
        decomposer = TaskDecomposer()
        issue = Issue(
            issue_number="1.1",
            title="Medium Task",
            description="This is a medium length description that goes into more detail about what needs to be done. " * 2,  # 100-300 chars
            priority=2
        )

        # ACT
        count = decomposer._estimate_task_count(issue)

        # ASSERT
        assert count == "4-6"

    def test_estimate_task_count_for_long_description(self):
        """Test that long descriptions suggest 6-8 tasks."""
        # ARRANGE
        decomposer = TaskDecomposer()
        issue = Issue(
            issue_number="1.1",
            title="Complex Task",
            description="This is a very long and detailed description that explains the complex requirements. " * 10,  # > 300 chars
            priority=2
        )

        # ACT
        count = decomposer._estimate_task_count(issue)

        # ASSERT
        assert count == "6-8"

    def test_estimate_task_count_with_no_description(self):
        """Test that issues with no description default to 3-4 tasks."""
        # ARRANGE
        decomposer = TaskDecomposer()
        issue = Issue(
            issue_number="1.1",
            title="Simple Task",
            description=None,
            priority=2
        )

        # ACT
        count = decomposer._estimate_task_count(issue)

        # ASSERT
        assert count == "3-4"


@pytest.mark.integration
class TestTaskDecomposerIntegration:
    """Integration tests for task decomposition."""

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_complete_decomposition_workflow(self, mock_provider_class, sample_issue, mock_provider):
        """Test complete workflow from issue to tasks."""
        # ARRANGE
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model with fields (username, email, password_hash)
            2. Implement password hashing with bcrypt library
            3. Create login endpoint with JWT token generation
            4. Create logout endpoint with token invalidation
            5. Add session management middleware
            """,
            "usage": {"input_tokens": 100, "output_tokens": 80}
        }

        decomposer = TaskDecomposer()

        # ACT
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # ASSERT - Verify all requirements
        assert len(tasks) == 5
        assert all(isinstance(task, Task) for task in tasks)

        # Sequential numbering
        assert tasks[0].task_number == "2.1.1"
        assert tasks[4].task_number == "2.1.5"

        # Parent issue number
        assert all(task.parent_issue_number == "2.1" for task in tasks)

        # Dependency chain
        assert tasks[0].depends_on == ""
        assert tasks[1].depends_on == "2.1.1"
        assert tasks[4].depends_on == "2.1.4"

        # can_parallelize
        assert all(task.can_parallelize is False for task in tasks)

        # Priority inheritance
        assert all(task.priority == sample_issue.priority for task in tasks)

        # Foreign keys
        assert all(task.issue_id == sample_issue.id for task in tasks)
        assert all(task.project_id == sample_issue.project_id for task in tasks)

        # Validation
        assert all(task.title for task in tasks)
        assert all(task.description for task in tasks)
