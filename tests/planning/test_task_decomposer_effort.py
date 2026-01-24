"""Tests for Task Decomposition Effort Estimation.

TDD tests for enhanced effort estimation in TaskDecomposer.
These tests verify:
- Enhanced prompt requests effort estimation (complexity, hours, uncertainty)
- Response parsing extracts effort data
- Fallback to defaults when parsing fails
- Effort fields are stored in Task objects
"""

import pytest
from unittest.mock import Mock, patch
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
        workflow_step=1,
    )


@pytest.fixture
def mock_provider():
    """Provide a mock Anthropic provider."""
    provider = Mock(spec=AnthropicProvider)
    return provider


@pytest.mark.unit
class TestEffortEstimationPrompt:
    """Test that decomposition prompt requests effort estimation."""

    def test_build_decomposition_prompt_requests_complexity(self, sample_issue):
        """Test that prompt requests complexity score for each task."""
        decomposer = TaskDecomposer()

        prompt = decomposer.build_decomposition_prompt(sample_issue)

        # Prompt should request complexity scoring
        assert "complexity" in prompt.lower()

    def test_build_decomposition_prompt_requests_time_estimate(self, sample_issue):
        """Test that prompt requests time estimation in hours."""
        decomposer = TaskDecomposer()

        prompt = decomposer.build_decomposition_prompt(sample_issue)

        # Prompt should request hour estimates
        assert "hour" in prompt.lower() or "time" in prompt.lower()

    def test_build_decomposition_prompt_requests_uncertainty(self, sample_issue):
        """Test that prompt requests uncertainty assessment."""
        decomposer = TaskDecomposer()

        prompt = decomposer.build_decomposition_prompt(sample_issue)

        # Prompt should request uncertainty level
        assert "uncertainty" in prompt.lower() or "confidence" in prompt.lower()


@pytest.mark.unit
class TestEffortEstimationParsing:
    """Test parsing effort estimation data from Claude response."""

    def test_parse_response_extracts_complexity_score(self, sample_issue):
        """Test that parser extracts complexity score from response."""
        decomposer = TaskDecomposer()
        response = """
        1. Create User model - Database model with username, email, password_hash
           Complexity: 2
           Estimated Hours: 2
           Uncertainty: low

        2. Implement password hashing - Use bcrypt library for secure storage
           Complexity: 3
           Estimated Hours: 3
           Uncertainty: low

        3. Create login endpoint - Implement POST /api/login with JWT
           Complexity: 4
           Estimated Hours: 5
           Uncertainty: medium
        """

        tasks = decomposer.parse_claude_response(response, sample_issue)

        assert tasks[0].complexity_score == 2
        assert tasks[1].complexity_score == 3
        assert tasks[2].complexity_score == 4

    def test_parse_response_extracts_estimated_hours(self, sample_issue):
        """Test that parser extracts estimated hours from response."""
        decomposer = TaskDecomposer()
        response = """
        1. Create User model - Database model
           Complexity: 2
           Estimated Hours: 2.5
           Uncertainty: low

        2. Implement password hashing - bcrypt
           Complexity: 3
           Estimated Hours: 3
           Uncertainty: low

        3. Create login endpoint - JWT authentication
           Complexity: 4
           Estimated Hours: 5.5
           Uncertainty: medium
        """

        tasks = decomposer.parse_claude_response(response, sample_issue)

        assert tasks[0].estimated_hours == 2.5
        assert tasks[1].estimated_hours == 3.0
        assert tasks[2].estimated_hours == 5.5

    def test_parse_response_extracts_uncertainty_level(self, sample_issue):
        """Test that parser extracts uncertainty level from response."""
        decomposer = TaskDecomposer()
        response = """
        1. Create User model - Database model
           Complexity: 2
           Estimated Hours: 2
           Uncertainty: low

        2. Implement password hashing - bcrypt library
           Complexity: 3
           Estimated Hours: 3
           Uncertainty: medium

        3. Create login endpoint - JWT auth
           Complexity: 4
           Estimated Hours: 5
           Uncertainty: high
        """

        tasks = decomposer.parse_claude_response(response, sample_issue)

        assert tasks[0].uncertainty_level == "low"
        assert tasks[1].uncertainty_level == "medium"
        assert tasks[2].uncertainty_level == "high"


@pytest.mark.unit
class TestEffortEstimationFallback:
    """Test fallback behavior when effort estimation parsing fails."""

    def test_parse_response_uses_defaults_when_no_effort_data(self, sample_issue):
        """Test that tasks get default values when no effort data in response."""
        decomposer = TaskDecomposer()
        # Response without effort estimation data (old format)
        response = """
        1. Create User model - Database model with username, email
        2. Implement password hashing - Use bcrypt library
        3. Create login endpoint - JWT token generation
        """

        tasks = decomposer.parse_claude_response(response, sample_issue)

        # Should use defaults
        for task in tasks:
            assert task.complexity_score is None or task.complexity_score == 2  # Default medium
            assert task.estimated_hours is None or task.estimated_hours == 2.0  # Default estimate
            assert task.uncertainty_level is None or task.uncertainty_level == "medium"

    def test_parse_response_handles_partial_effort_data(self, sample_issue):
        """Test that parser handles responses with partial effort data."""
        decomposer = TaskDecomposer()
        response = """
        1. Create User model - Database model
           Complexity: 2

        2. Implement password hashing - bcrypt
           Estimated Hours: 3

        3. Create login endpoint - JWT auth
           Uncertainty: high
        """

        tasks = decomposer.parse_claude_response(response, sample_issue)

        # Should extract what's available, use defaults for rest
        assert tasks[0].complexity_score == 2
        assert tasks[1].estimated_hours == 3.0
        assert tasks[2].uncertainty_level == "high"

    def test_parse_response_validates_complexity_range(self, sample_issue):
        """Test that complexity scores outside 1-5 range are normalized."""
        decomposer = TaskDecomposer()
        response = """
        1. Create User model - Database model
           Complexity: 0
           Estimated Hours: 2
           Uncertainty: low

        2. Implement password hashing - bcrypt
           Complexity: 10
           Estimated Hours: 3
           Uncertainty: low
        """

        tasks = decomposer.parse_claude_response(response, sample_issue)

        # Should normalize to valid range
        assert tasks[0].complexity_score in [1, 2, None]  # 0 normalized to 1 or default
        assert tasks[1].complexity_score in [5, None]  # 10 normalized to 5 or default


@pytest.mark.unit
class TestEffortEstimationIntegration:
    """Integration tests for effort estimation in decomposition workflow."""

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_with_effort_estimation(
        self, mock_provider_class, sample_issue, mock_provider
    ):
        """Test complete decomposition workflow with effort estimation."""
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Create User model - Database model with username, email, password_hash
               Complexity: 2
               Estimated Hours: 2
               Uncertainty: low

            2. Implement password hashing - Use bcrypt library for secure storage
               Complexity: 3
               Estimated Hours: 3
               Uncertainty: low

            3. Create login endpoint - Implement POST /api/login with JWT
               Complexity: 4
               Estimated Hours: 5
               Uncertainty: medium

            4. Create logout endpoint - Handle token invalidation
               Complexity: 2
               Estimated Hours: 1.5
               Uncertainty: low
            """,
            "usage": {"input_tokens": 100, "output_tokens": 150},
        }

        decomposer = TaskDecomposer()
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # Verify tasks were created
        assert len(tasks) == 4

        # Verify effort data was extracted
        assert tasks[0].complexity_score == 2
        assert tasks[0].estimated_hours == 2.0
        assert tasks[0].uncertainty_level == "low"

        assert tasks[2].complexity_score == 4
        assert tasks[2].estimated_hours == 5.0
        assert tasks[2].uncertainty_level == "medium"

    @patch("codeframe.planning.task_decomposer.AnthropicProvider")
    def test_decompose_issue_calculates_total_estimate(
        self, mock_provider_class, sample_issue, mock_provider
    ):
        """Test that decomposition can calculate total estimated hours."""
        mock_provider_class.return_value = mock_provider
        mock_provider.send_message.return_value = {
            "content": """
            1. Task 1 - Description
               Complexity: 2
               Estimated Hours: 2
               Uncertainty: low

            2. Task 2 - Description
               Complexity: 3
               Estimated Hours: 3
               Uncertainty: low

            3. Task 3 - Description
               Complexity: 2
               Estimated Hours: 4
               Uncertainty: low
            """,
            "usage": {"input_tokens": 100, "output_tokens": 100},
        }

        decomposer = TaskDecomposer()
        tasks = decomposer.decompose_issue(sample_issue, mock_provider)

        # Verify total can be calculated
        total_hours = sum(t.estimated_hours for t in tasks if t.estimated_hours)
        assert total_hours == 9.0


@pytest.mark.unit
class TestTaskModelEffortFields:
    """Test that Task model has effort estimation fields."""

    def test_task_has_estimated_hours_field(self):
        """Test that Task has estimated_hours field."""
        task = Task(
            task_number="1.1",
            title="Test Task",
            estimated_hours=4.5,
        )

        assert hasattr(task, "estimated_hours")
        assert task.estimated_hours == 4.5

    def test_task_has_complexity_score_field(self):
        """Test that Task has complexity_score field."""
        task = Task(
            task_number="1.1",
            title="Test Task",
            complexity_score=3,
        )

        assert hasattr(task, "complexity_score")
        assert task.complexity_score == 3

    def test_task_has_uncertainty_level_field(self):
        """Test that Task has uncertainty_level field."""
        task = Task(
            task_number="1.1",
            title="Test Task",
            uncertainty_level="medium",
        )

        assert hasattr(task, "uncertainty_level")
        assert task.uncertainty_level == "medium"

    def test_task_has_resource_requirements_field(self):
        """Test that Task has resource_requirements field."""
        task = Task(
            task_number="1.1",
            title="Test Task",
            resource_requirements='{"skills": ["python", "fastapi"]}',
        )

        assert hasattr(task, "resource_requirements")
        assert "python" in task.resource_requirements

    def test_task_to_dict_includes_effort_fields(self):
        """Test that to_dict() includes effort estimation fields."""
        task = Task(
            task_number="1.1",
            title="Test Task",
            estimated_hours=4.5,
            complexity_score=3,
            uncertainty_level="medium",
            resource_requirements='{"skills": ["python"]}',
        )

        task_dict = task.to_dict()

        assert "estimated_hours" in task_dict
        assert task_dict["estimated_hours"] == 4.5
        assert "complexity_score" in task_dict
        assert task_dict["complexity_score"] == 3
        assert "uncertainty_level" in task_dict
        assert task_dict["uncertainty_level"] == "medium"
        assert "resource_requirements" in task_dict

    def test_task_effort_fields_default_to_none(self):
        """Test that effort fields default to None."""
        task = Task(
            task_number="1.1",
            title="Test Task",
        )

        assert task.estimated_hours is None
        assert task.complexity_score is None
        assert task.uncertainty_level is None
        assert task.resource_requirements is None
