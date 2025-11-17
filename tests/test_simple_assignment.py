"""Tests for simple agent assignment logic."""

from codeframe.agents.simple_assignment import SimpleAgentAssigner, assign_task_to_agent


class TestSimpleAgentAssigner:
    """Test the SimpleAgentAssigner class."""

    def test_frontend_assignment(self):
        """Test assignment to frontend agent."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 1,
            "title": "Create login form component",
            "description": "Build a React component for user authentication with Tailwind CSS",
        }

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "frontend-specialist"

    def test_backend_assignment(self):
        """Test assignment to backend agent."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 2,
            "title": "Implement JWT authentication middleware",
            "description": "Create Express.js middleware for JWT token validation",
        }

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "backend-worker"

    def test_test_assignment(self):
        """Test assignment to test agent."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 3,
            "title": "Write unit tests for auth service",
            "description": "Add pytest tests with 90% coverage for authentication",
        }

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "test-engineer"

    def test_review_assignment(self):
        """Test assignment to code review agent."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 4,
            "title": "Refactor authentication code",
            "description": "Clean up auth module, improve code quality and security",
        }

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "code-reviewer"

    def test_default_assignment(self):
        """Test default assignment when no keywords match."""
        assigner = SimpleAgentAssigner()

        task = {"id": 5, "title": "Do something", "description": "This is vague"}

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "backend-worker"  # Default

    def test_mixed_keywords_frontend_wins(self):
        """Test that highest scoring agent wins."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 6,
            "title": "Build dashboard UI with API integration",
            "description": "Create React dashboard component that fetches data from backend API",
        }

        # "dashboard", "ui", "component", "react" = 4 frontend keywords
        # "api", "backend" = 2 backend keywords
        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "frontend-specialist"

    def test_missing_title(self):
        """Test handling of missing title field."""
        assigner = SimpleAgentAssigner()

        task = {"id": 7, "description": "Build an API endpoint"}

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "backend-worker"

    def test_missing_description(self):
        """Test handling of missing description field."""
        assigner = SimpleAgentAssigner()

        task = {"id": 8, "title": "Create React component"}

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "frontend-specialist"

    def test_empty_task(self):
        """Test handling of completely empty task."""
        assigner = SimpleAgentAssigner()

        task = {}

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "backend-worker"  # Default

    def test_case_insensitive_matching(self):
        """Test that keyword matching is case-insensitive."""
        assigner = SimpleAgentAssigner()

        task = {"id": 9, "title": "CREATE FRONTEND COMPONENT", "description": "BUILD REACT UI"}

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "frontend-specialist"

    def test_multiple_test_keywords(self):
        """Test task with multiple test-related keywords."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 10,
            "title": "Write end-to-end tests",
            "description": "Create e2e test suite with jest, add integration tests and unit tests",
        }

        # e2e, test (2x), jest, integration test, unit test = high score
        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "test-engineer"

    def test_get_assignment_explanation(self):
        """Test explanation generation."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 11,
            "title": "Build React dashboard",
            "description": "Create responsive UI with components",
        }

        agent_type = assigner.assign_agent_type(task)
        explanation = assigner.get_assignment_explanation(task, agent_type)

        assert "frontend-specialist" in explanation
        assert "dashboard" in explanation or "react" in explanation or "ui" in explanation

    def test_convenience_function(self):
        """Test the convenience wrapper function."""
        task = {"id": 12, "title": "Create API endpoint", "description": "Build REST API"}

        agent_type = assign_task_to_agent(task)
        assert agent_type == "backend-worker"

    def test_accessibility_keywords(self):
        """Test accessibility-related tasks go to frontend."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 13,
            "title": "Improve WCAG compliance",
            "description": "Add a11y features and aria labels to UI",
        }

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "frontend-specialist"

    def test_security_review_keywords(self):
        """Test security review tasks go to code-reviewer."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 14,
            "title": "Security audit",
            "description": "Review code for vulnerabilities and security best practices",
        }

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "code-reviewer"

    def test_database_backend_keywords(self):
        """Test database tasks go to backend."""
        assigner = SimpleAgentAssigner()

        task = {
            "id": 15,
            "title": "Create database migration",
            "description": "Add new SQL schema and ORM models",
        }

        agent_type = assigner.assign_agent_type(task)
        assert agent_type == "backend-worker"
