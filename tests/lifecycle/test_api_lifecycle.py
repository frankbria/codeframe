"""
API Lifecycle Test — full Think → Build → Prove loop via REST API.

Tests that the FastAPI server layer correctly delegates to core and that
SSE streaming, auth, and task execution all work together end-to-end.

Status: STUB — implement after CLI lifecycle is stable.
Runtime: 10–30 minutes. Cost: ~$0.50–2.00 per run.
"""

import pytest

pytestmark = [pytest.mark.lifecycle, pytest.mark.slow]


@pytest.mark.skip(reason="API lifecycle test — implement after CLI lifecycle is stable")
class TestAPILifecycle:
    """Full lifecycle via REST API: workspace init → PRD → tasks → execute via API."""

    def test_agent_builds_project_via_api(self, initialized_workspace):
        """
        Agent builds csv-stats via REST API calls.

        Plan:
        1. POST /api/v2/workspace/init
        2. POST /api/v2/prd (upload PRD.md)
        3. POST /api/v2/tasks/generate
        4. GET  /api/v2/tasks to find READY tasks
        5. POST /api/v2/batches/run with all ready task IDs
        6. GET  /api/v2/tasks/{id}/stream (SSE) to monitor
        7. Poll until all tasks complete
        8. Run acceptance checks
        """
        raise NotImplementedError

    def test_sse_streaming_delivers_events(self, initialized_workspace):
        """
        Task execution via API emits real-time SSE events.

        Plan:
        1. Start task via API
        2. Open SSE stream for the task
        3. Verify event types: task_started, tool_use, task_completed
        4. Verify final status in DB matches SSE final event
        """
        raise NotImplementedError
