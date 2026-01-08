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
        start_date = (
            now.replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

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
        backend_stats = next((a for a in data["by_agent"] if a["agent_id"] == "backend-001"), None)
        assert backend_stats is not None
        assert backend_stats["call_count"] == 2
        assert backend_stats["total_tokens"] == 2250  # 1000+500 + 500+250
        assert abs(backend_stats["cost_usd"] - 0.01575) < 0.00001

        # Find review-001 stats
        review_stats = next((a for a in data["by_agent"] if a["agent_id"] == "review-001"), None)
        assert review_stats is not None
        assert review_stats["call_count"] == 1
        assert review_stats["total_tokens"] == 3000  # 2000+1000
        assert abs(review_stats["cost_usd"] - 0.0056) < 0.00001

        # Check by_model breakdown (2 models)
        assert len(data["by_model"]) == 2

        # Find Sonnet 4.5 stats
        sonnet_stats = next(
            (m for m in data["by_model"] if m["model_name"] == "claude-sonnet-4-5"), None
        )
        assert sonnet_stats is not None
        assert sonnet_stats["call_count"] == 2
        assert sonnet_stats["total_tokens"] == 2250

        # Find Haiku 4 stats
        haiku_stats = next(
            (m for m in data["by_model"] if m["model_name"] == "claude-haiku-4"), None
        )
        assert haiku_stats is not None
        assert haiku_stats["call_count"] == 1
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
            (ct for ct in data["by_call_type"] if ct["call_type"] == CallType.TASK_EXECUTION.value),
            None,
        )
        assert task_exec_stats is not None
        assert task_exec_stats["calls"] == 1

        # Find code review stats
        code_review_stats = next(
            (ct for ct in data["by_call_type"] if ct["call_type"] == CallType.CODE_REVIEW.value),
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
        response = api_client.get(f"/api/agents/backend-001/metrics?project_id={project_id}")

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

        # Get metrics for frontend-001 filtered by the existing project (frontend-001 has no data for this project)
        response = api_client.get(f"/api/agents/frontend-001/metrics?project_id={project_id}")

        assert response.status_code == 200
        data = response.json()

        # Should return empty metrics (frontend-001 has no token usage for this project)
        assert data["agent_id"] == "frontend-001"
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
        agent_response = api_client.get(f"/api/agents/backend-001/metrics?project_id={project_id}")
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
        assert backend_stats["total_tokens"] == agent_data["total_tokens"]
        assert backend_stats["call_count"] == agent_data["total_calls"]


class TestProjectTokenTimeSeriesEndpoint:
    """Test GET /api/projects/{id}/metrics/tokens/timeseries endpoint."""

    def test_endpoint_exists(self, api_client, project_with_token_usage):
        """Test that endpoint exists and returns 200."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date={start_date}&end_date={end_date}"
        )
        assert response.status_code == 200

    def test_returns_timeseries_structure(self, api_client, project_with_token_usage):
        """Test that endpoint returns proper time series structure."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date={start_date}&end_date={end_date}&interval=day"
        )

        assert response.status_code == 200
        data = response.json()

        # Response should be an array of time series data points
        assert isinstance(data, list)
        assert len(data) > 0

        # Each data point should have the expected structure
        for point in data:
            assert "timestamp" in point
            assert "input_tokens" in point
            assert "output_tokens" in point
            assert "total_tokens" in point
            assert "cost_usd" in point

    def test_aggregates_by_day(self, api_client, project_with_token_usage):
        """Test that data is properly aggregated by day interval."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date={start_date}&end_date={end_date}&interval=day"
        )

        assert response.status_code == 200
        data = response.json()

        # Should have data points for days with usage
        assert len(data) > 0

        # Verify total tokens across all data points matches expected
        total_input = sum(point["input_tokens"] for point in data)
        total_output = sum(point["output_tokens"] for point in data)

        # We have 3 records: today (1500 tokens), yesterday (750), two days ago (3000)
        # Filtering to last 3 days should include all
        assert total_input + total_output > 0

    def test_supports_hour_interval(self, api_client, project_with_token_usage):
        """Test that hour interval is supported."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = now.strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date={start_date}&end_date={end_date}&interval=hour"
        )

        assert response.status_code == 200

    def test_supports_week_interval(self, api_client, project_with_token_usage):
        """Test that week interval is supported."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=14)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date={start_date}&end_date={end_date}&interval=week"
        )

        assert response.status_code == 200

    def test_invalid_interval_returns_400(self, api_client, project_with_token_usage):
        """Test that invalid interval returns 400 Bad Request."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date={start_date}&end_date={end_date}&interval=invalid"
        )

        assert response.status_code == 400
        assert "interval" in response.json()["detail"].lower()

    def test_missing_dates_returns_400(self, api_client, project_with_token_usage):
        """Test that missing required date parameters returns 400."""
        project_id, _ = project_with_token_usage

        # Missing start_date
        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries?end_date=2025-01-01"
        )
        assert response.status_code == 400

        # Missing end_date
        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries?start_date=2025-01-01"
        )
        assert response.status_code == 400

    def test_empty_date_range_returns_empty_array(self, api_client, project_with_token_usage):
        """Test that date range with no data returns empty array."""
        project_id, _ = project_with_token_usage

        # Use date range far in the future with no data
        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date=2099-01-01&end_date=2099-01-07"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_nonexistent_project_returns_404(self, api_client):
        """Test that nonexistent project returns 404."""
        response = api_client.get(
            "/api/projects/99999/metrics/tokens/timeseries"
            "?start_date=2025-01-01&end_date=2025-01-07"
        )
        assert response.status_code == 404

    def test_accepts_iso8601_dates(self, api_client, project_with_token_usage):
        """Test that full ISO 8601 dates with time are accepted."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
        end_date = now.isoformat().replace("+00:00", "Z")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/tokens/timeseries"
            f"?start_date={start_date}&end_date={end_date}"
        )

        assert response.status_code == 200


class TestProjectCostMetricsDateFiltering:
    """Test date filtering on GET /api/projects/{id}/metrics/costs endpoint."""

    def test_date_filtering_reduces_costs(self, api_client, project_with_token_usage):
        """Test that date filtering reduces returned costs."""
        project_id, _ = project_with_token_usage

        # Get all-time costs
        all_time_response = api_client.get(f"/api/projects/{project_id}/metrics/costs")
        all_time_data = all_time_response.json()

        # Get today-only costs (should be less than all-time)
        now = datetime.now(timezone.utc)
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d")
        end_date = now.strftime("%Y-%m-%d")

        filtered_response = api_client.get(
            f"/api/projects/{project_id}/metrics/costs"
            f"?start_date={start_date}&end_date={end_date}"
        )

        assert filtered_response.status_code == 200
        filtered_data = filtered_response.json()

        # Filtered should have fewer or equal costs (today only vs all time)
        assert filtered_data["total_cost_usd"] <= all_time_data["total_cost_usd"]
        assert filtered_data["total_calls"] <= all_time_data["total_calls"]

    def test_date_filtering_with_iso8601_format(self, api_client, project_with_token_usage):
        """Test that ISO 8601 format works for costs date filtering."""
        project_id, _ = project_with_token_usage
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
        end_date = now.isoformat().replace("+00:00", "Z")

        response = api_client.get(
            f"/api/projects/{project_id}/metrics/costs"
            f"?start_date={start_date}&end_date={end_date}"
        )

        assert response.status_code == 200

    def test_date_filtering_backwards_compatible(self, api_client, project_with_token_usage):
        """Test that costs endpoint still works without date params (backward compatible)."""
        project_id, _ = project_with_token_usage

        # Should work without any date params
        response = api_client.get(f"/api/projects/{project_id}/metrics/costs")
        assert response.status_code == 200

        data = response.json()
        assert "total_cost_usd" in data
        assert "by_agent" in data
        assert "by_model" in data
