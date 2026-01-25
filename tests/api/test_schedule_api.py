"""Tests for Schedule API endpoints.

TDD tests for the schedule API:
- GET /api/schedule/{project_id} - Get project schedule
- GET /api/schedule/{project_id}/predict - Predict completion
- GET /api/schedule/{project_id}/bottlenecks - Identify bottlenecks
"""

import pytest

pytestmark = pytest.mark.v2


@pytest.mark.unit
class TestScheduleAPI:
    """Test schedule API endpoints."""

    def test_schedule_router_imports(self):
        """Test schedule router can be imported."""
        from codeframe.ui.routers.schedule import router

        assert router is not None
        assert router.prefix == "/api/schedule"

    def test_schedule_response_models_exist(self):
        """Test response models are defined."""
        from codeframe.ui.routers.schedule import (
            TaskAssignmentResponse,
            ScheduleResponse,
            CompletionPredictionResponse,
            BottleneckResponse,
        )

        assert TaskAssignmentResponse is not None
        assert ScheduleResponse is not None
        assert CompletionPredictionResponse is not None
        assert BottleneckResponse is not None


@pytest.mark.unit
class TestScheduleEndpoints:
    """Test schedule endpoint functions exist."""

    def test_get_project_schedule_exists(self):
        """Test get_project_schedule endpoint function exists."""
        from codeframe.ui.routers.schedule import get_project_schedule

        assert callable(get_project_schedule)

    def test_predict_completion_exists(self):
        """Test predict_completion endpoint function exists."""
        from codeframe.ui.routers.schedule import predict_completion

        assert callable(predict_completion)

    def test_get_bottlenecks_exists(self):
        """Test get_bottlenecks endpoint function exists."""
        from codeframe.ui.routers.schedule import get_bottlenecks

        assert callable(get_bottlenecks)
