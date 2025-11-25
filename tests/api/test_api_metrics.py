"""Tests for Metrics API endpoints (Sprint 10 Phase 5: T127-T129).

Sprint 10 - Phase 5: Metrics & Cost Tracking

Tests follow RED-GREEN-REFACTOR TDD cycle.

Endpoints tested:
- GET /api/projects/{id}/metrics/tokens (T127)
- GET /api/projects/{id}/metrics/costs (T128)
- GET /api/agents/{agent_id}/metrics (T129)
"""

import pytest
from datetime import datetime, timezone, timedelta
from codeframe.core.models import TokenUsage, CallType


def get_app():
    """Get the current app instance after module reload."""
    from codeframe.ui.server import app

    return app


@pytest.fixture(scope="function")
def project_with_token_usage(api_client):
    """Create test project with token usage records.

    Args:
        api_client: FastAPI test client from class-scoped fixture

    Returns:
        Tuple of (project_id, usage_ids)
    """
    # Create project
    project_id = get_app().state.db.create_project(
        name="Test Metrics Project", description="Test project for metrics API"
    )

    # Create token usage records (task_id=None is allowed)
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)

    usage_ids = []

    # Record 1: backend-001, Sonnet 4.5, task execution
    usage1 = TokenUsage(
        task_id=None,  # No task association required
        agent_id="backend-001",
        project_id=project_id,
        model_name="claude-sonnet-4-5",
        input_tokens=1000,
        output_tokens=500,
        estimated_cost_usd=0.0105,  # (1000 * 3.00 + 500 * 15.00) / 1M = 0.0105
        call_type=CallType.TASK_EXECUTION,
        timestamp=now,
    )
    usage_ids.append(get_app().state.db.save_token_usage(usage1))

    # Record 2: backend-001, Sonnet 4.5, code review
    usage2 = TokenUsage(
        task_id=None,
        agent_id="backend-001",
        project_id=project_id,
        model_name="claude-sonnet-4-5",
        input_tokens=500,
        output_tokens=250,
        estimated_cost_usd=0.00525,  # (500 * 3.00 + 250 * 15.00) / 1M = 0.00525
        call_type=CallType.CODE_REVIEW,
        timestamp=yesterday,
    )
    usage_ids.append(get_app().state.db.save_token_usage(usage2))

    # Record 3: review-001, Haiku 4, code review (older)
    usage3 = TokenUsage(
        task_id=None,
        agent_id="review-001",
        project_id=project_id,
        model_name="claude-haiku-4",
        input_tokens=2000,
        output_tokens=1000,
        estimated_cost_usd=0.0056,  # (2000 * 0.80 + 1000 * 4.00) / 1M = 0.0056
        call_type=CallType.CODE_REVIEW,
        timestamp=two_days_ago,
    )
    usage_ids.append(get_app().state.db.save_token_usage(usage3))

    return project_id, usage_ids


class TestProjectTokenMetricsEndpoint:
    """Test GET /api/projects/{id}/metrics/tokens endpoint (T127)."""

    def test_endpoint_exists(self, api_client, project_with_token_usage):
        """Test that endpoint exists and returns 200."""
        project_id, _ = project_with_token_usage
        response = api_client.get(f"/api/projects/{project_id}/metrics/tokens")
        assert response.status_code == 200

    def test_returns_all_usage_records(self, api_client, project_with_token_usage):
        """Test that endpoint returns all token usage records."""
        project_id, usage_ids = project_with_token_usage
        response = api_client.get(f"/api/projects/{project_id}/metrics/tokens")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "project_id" in data
        assert "total_tokens" in data
        assert "total_calls" in data
        assert "total_cost_usd" in data
        assert "date_range" in data
        assert "usage_records" in data

        # Check values
        assert data["project_id"] == project_id
        assert data["total_calls"] == 3
        assert data["total_tokens"] == 5250  # 1000+500 + 500+250 + 2000+1000
        assert abs(data["total_cost_usd"] - 0.02135) < 0.00001  # 0.0105 + 0.00525 + 0.0056

        # Check usage records
        assert len(data["usage_records"]) == 3

    def test_date_filtering(self, api_client, project_with_token_usage):
        """Test that date filtering works correctly."""
        project_id, _ = project_with_token_usage

        # Filter to only records from today (should get 1 record)
        now = datetime.now(timezone.utc)
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace('+00:00', 'Z')

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens?start_date={start_date}"
        )

        assert response.status_code == 200
        data = response.json()

        # Should only get today's record
        assert data["total_calls"] == 1
        assert len(data["usage_records"]) == 1

    def test_invalid_date_format_returns_400(self, api_client, project_with_token_usage):
        """Test that invalid date format returns 400 Bad Request."""
        project_id, _ = project_with_token_usage

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens?start_date=invalid-date"
        )

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    def test_nonexistent_project_returns_404(self, api_client):
        """Test that nonexistent project returns 404."""
        response = api_client.get("/api/projects/99999/metrics/tokens")
        assert response.status_code == 404


class TestProjectCostMetricsEndpoint:
    """Test GET /api/projects/{id}/metrics/costs endpoint (T128)."""

    def test_endpoint_exists(self, api_client, project_with_token_usage):
        """Test that endpoint exists and returns 200."""
        project_id, _ = project_with_token_usage
        response = api_client.get(f"/api/projects/{project_id}/metrics/costs")
        assert response.status_code == 200

    def test_returns_cost_breakdown(self, api_client, project_with_token_usage):
        """Test that endpoint returns cost breakdown by agent and model."""
        project_id, _ = project_with_token_usage
        response = api_client.get(f"/api/projects/{project_id}/metrics/costs")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "project_id" in data
        assert "total_cost_usd" in data
        assert "total_tokens" in data
        assert "total_calls" in data
        assert "by_agent" in data
        assert "by_model" in data

        # Check values
        assert data["project_id"] == project_id
        assert data["total_calls"] == 3
        assert data["total_tokens"] == 5250
        assert abs(data["total_cost_usd"] - 0.02135) < 0.00001

        # Check by_agent breakdown (2 agents)
        assert len(data["by_agent"]) == 2

        # Find backend-001 stats
        backend_stats = next(
            (a for a in data["by_agent"] if a["agent_id"] == "backend-001"), None
        )
        assert backend_stats is not None
        assert backend_stats["calls"] == 2
        assert backend_stats["tokens"] == 2250  # 1000+500 + 500+250
        assert abs(backend_stats["cost_usd"] - 0.01575) < 0.00001

        # Find review-001 stats
        review_stats = next(
            (a for a in data["by_agent"] if a["agent_id"] == "review-001"), None
        )
        assert review_stats is not None
        assert review_stats["calls"] == 1
        assert review_stats["tokens"] == 3000  # 2000+1000
        assert abs(review_stats["cost_usd"] - 0.0056) < 0.00001

        # Check by_model breakdown (2 models)
        assert len(data["by_model"]) == 2

        # Find Sonnet 4.5 stats
        sonnet_stats = next(
            (m for m in data["by_model"] if m["model_name"] == "claude-sonnet-4-5"), None
        )
        assert sonnet_stats is not None
        assert sonnet_stats["total_calls"] == 2
        assert sonnet_stats["total_tokens"] == 2250

        # Find Haiku 4 stats
        haiku_stats = next(
            (m for m in data["by_model"] if m["model_name"] == "claude-haiku-4"), None
        )
        assert haiku_stats is not None
        assert haiku_stats["total_calls"] == 1
        assert haiku_stats["total_tokens"] == 3000

    def test_nonexistent_project_returns_404(self, api_client):
        """Test that nonexistent project returns 404."""
        response = api_client.get("/api/projects/99999/metrics/costs")
        assert response.status_code == 404


class TestAgentMetricsEndpoint:
    """Test GET /api/agents/{agent_id}/metrics endpoint (T129)."""

    def test_endpoint_exists(self, api_client, project_with_token_usage):
        """Test that endpoint exists and returns 200."""
        project_id, _ = project_with_token_usage
        response = api_client.get("/api/agents/backend-001/metrics")
        assert response.status_code == 200

    def test_returns_agent_metrics(self, api_client, project_with_token_usage):
        """Test that endpoint returns agent metrics across all projects."""
        project_id, _ = project_with_token_usage
        response = api_client.get("/api/agents/backend-001/metrics")

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "agent_id" in data
        assert "total_cost_usd" in data
        assert "total_tokens" in data
        assert "total_calls" in data
        assert "by_call_type" in data
        assert "by_project" in data

        # Check values
        assert data["agent_id"] == "backend-001"
        assert data["total_calls"] == 2
        assert data["total_tokens"] == 2250
        assert abs(data["total_cost_usd"] - 0.01575) < 0.00001

        # Check by_call_type breakdown
        assert len(data["by_call_type"]) == 2  # TASK_EXECUTION and CODE_REVIEW

        # Find task execution stats
        task_exec_stats = next(
            (
                ct
                for ct in data["by_call_type"]
                if ct["call_type"] == CallType.TASK_EXECUTION.value
            ),
            None,
        )
        assert task_exec_stats is not None
        assert task_exec_stats["calls"] == 1

        # Find code review stats
        code_review_stats = next(
            (
                ct
                for ct in data["by_call_type"]
                if ct["call_type"] == CallType.CODE_REVIEW.value
            ),
            None,
        )
        assert code_review_stats is not None
        assert code_review_stats["calls"] == 1

        # Check by_project breakdown
        assert len(data["by_project"]) == 1
        assert data["by_project"][0]["project_id"] == project_id

    def test_project_filtering(self, api_client, project_with_token_usage):
        """Test that project_id filtering works correctly."""
        project_id, _ = project_with_token_usage

        # Get metrics for backend-001 filtered by project_id
        response = api_client.get(
            f"/api/agents/backend-001/metrics?project_id={project_id}"
        )

        assert response.status_code == 200
        data = response.json()

        # Should only get records for this project
        assert data["agent_id"] == "backend-001"
        assert data["total_calls"] == 2
        assert len(data["by_project"]) == 1
        assert data["by_project"][0]["project_id"] == project_id

    def test_nonexistent_agent_returns_empty(self, api_client):
        """Test that nonexistent agent returns empty metrics."""
        response = api_client.get("/api/agents/nonexistent-agent/metrics")

        assert response.status_code == 200
        data = response.json()

        # Should return empty metrics
        assert data["agent_id"] == "nonexistent-agent"
        assert data["total_cost_usd"] == 0.0
        assert data["total_tokens"] == 0
        assert data["total_calls"] == 0
        assert len(data["by_call_type"]) == 0
        assert len(data["by_project"]) == 0

    def test_agent_with_no_data_for_project_returns_empty(
        self, api_client, project_with_token_usage
    ):
        """Test that agent with no data for project returns empty metrics."""
        project_id, _ = project_with_token_usage

        # Get metrics for review-001 filtered by a different project
        response = api_client.get("/api/agents/review-001/metrics?project_id=99999")

        assert response.status_code == 200
        data = response.json()

        # Should return empty metrics
        assert data["agent_id"] == "review-001"
        assert data["total_cost_usd"] == 0.0
        assert data["total_tokens"] == 0
        assert data["total_calls"] == 0
        assert len(data["by_call_type"]) == 0
        assert len(data["by_project"]) == 0


class TestMetricsEndpointIntegration:
    """Integration tests for metrics endpoints."""

    def test_all_endpoints_consistent(self, api_client, project_with_token_usage):
        """Test that all metrics endpoints return consistent data."""
        project_id, _ = project_with_token_usage

        # Get project costs
        project_response = api_client.get(f"/api/projects/{project_id}/metrics/costs")
        project_data = project_response.json()

        # Get agent costs for backend-001
        agent_response = api_client.get(
            f"/api/agents/backend-001/metrics?project_id={project_id}"
        )
        agent_data = agent_response.json()

        # Verify consistency
        # backend-001 should have 2 calls in project
        assert agent_data["total_calls"] == 2

        # backend-001's cost should be in project's by_agent breakdown
        backend_stats = next(
            (a for a in project_data["by_agent"] if a["agent_id"] == "backend-001"), None
        )
        assert backend_stats is not None
        assert backend_stats["cost_usd"] == agent_data["total_cost_usd"]
        assert backend_stats["tokens"] == agent_data["total_tokens"]
        assert backend_stats["calls"] == agent_data["total_calls"]
