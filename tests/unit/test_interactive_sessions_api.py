"""Tests for interactive sessions API endpoints (issue #501).

Tests CRUD operations for /api/v2/sessions endpoints using a real in-memory
SQLite database with the InteractiveSessionRepository.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.ui.routers.interactive_sessions_v2 import router
from codeframe.persistence.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture(scope="class")
def client():
    """Create a test app with the interactive sessions router and real in-memory DB."""
    app = FastAPI()
    app.include_router(router)

    db = Database(":memory:")
    db.initialize()
    app.state.db = db

    with TestClient(app) as c:
        yield c


class TestCreateSession:
    """Tests for POST /api/v2/sessions."""

    def test_create_session_minimal(self, client):
        """Create a session with only required fields."""
        response = client.post(
            "/api/v2/sessions",
            json={"workspace_path": "/tmp/test-workspace"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["workspace_path"] == "/tmp/test-workspace"
        assert data["state"] == "active"
        assert data["agent_type"] == "claude"
        assert data["model"] is None
        assert data["cost_usd"] == 0.0
        assert data["input_tokens"] == 0
        assert data["output_tokens"] == 0
        assert "id" in data
        assert data["ended_at"] is None

    def test_create_session_full(self, client):
        """Create a session with all fields specified."""
        response = client.post(
            "/api/v2/sessions",
            json={
                "workspace_path": "/home/user/project",
                "task_id": "task-abc-123",
                "agent_type": "codex",
                "model": "claude-opus-4-6",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["workspace_path"] == "/home/user/project"
        assert data["agent_type"] == "codex"
        assert data["model"] == "claude-opus-4-6"

    def test_create_session_missing_workspace_path(self, client):
        """Return 422 when workspace_path is missing."""
        response = client.post("/api/v2/sessions", json={})
        assert response.status_code == 422


class TestGetSession:
    """Tests for GET /api/v2/sessions/{id}."""

    def test_get_existing_session(self, client):
        """Get a session by ID."""
        create_resp = client.post(
            "/api/v2/sessions",
            json={"workspace_path": "/tmp/ws-get"},
        )
        session_id = create_resp.json()["id"]

        response = client.get(f"/api/v2/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["workspace_path"] == "/tmp/ws-get"

    def test_get_nonexistent_session(self, client):
        """Return 404 for unknown session ID."""
        response = client.get("/api/v2/sessions/nonexistent-id")
        assert response.status_code == 404


class TestListSessions:
    """Tests for GET /api/v2/sessions."""

    def test_list_returns_sessions(self, client):
        """List returns created sessions."""
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/list-ws"})
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/list-ws"})

        response = client.get("/api/v2/sessions?workspace_path=/tmp/list-ws")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2

    def test_list_filter_by_workspace(self, client):
        """Filter sessions by workspace_path returns only matching sessions."""
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/ws-filter-a"})
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/ws-filter-b"})

        response = client.get("/api/v2/sessions?workspace_path=/tmp/ws-filter-a")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert all(s["workspace_path"] == "/tmp/ws-filter-a" for s in data)

    def test_list_filter_by_state(self, client):
        """Filter sessions by state returns only matching sessions."""
        r = client.post("/api/v2/sessions", json={"workspace_path": "/tmp/ws-state-filter"})
        session_id = r.json()["id"]
        client.delete(f"/api/v2/sessions/{session_id}")

        ended_resp = client.get(
            "/api/v2/sessions?workspace_path=/tmp/ws-state-filter&state=ended"
        )
        assert ended_resp.status_code == 200
        response_data = ended_resp.json()
        assert all(s["state"] == "ended" for s in response_data)


class TestDeleteSession:
    """Tests for DELETE /api/v2/sessions/{id}."""

    def test_end_session(self, client):
        """End a session sets state to ended."""
        create_resp = client.post(
            "/api/v2/sessions", json={"workspace_path": "/tmp/ws-end"}
        )
        session_id = create_resp.json()["id"]

        response = client.delete(f"/api/v2/sessions/{session_id}")
        assert response.status_code == 200

        get_resp = client.get(f"/api/v2/sessions/{session_id}")
        data = get_resp.json()
        assert data["state"] == "ended"
        assert data["ended_at"] is not None

    def test_end_nonexistent_session(self, client):
        """Return 404 when ending unknown session."""
        response = client.delete("/api/v2/sessions/no-such-id")
        assert response.status_code == 404


class TestSessionMessages:
    """Tests for GET /api/v2/sessions/{id}/messages."""

    def test_get_messages_empty(self, client):
        """Return empty list for session with no messages."""
        create_resp = client.post(
            "/api/v2/sessions", json={"workspace_path": "/tmp/ws-msg"}
        )
        session_id = create_resp.json()["id"]

        response = client.get(f"/api/v2/sessions/{session_id}/messages")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_messages_nonexistent_session(self, client):
        """Return 404 for unknown session."""
        response = client.get("/api/v2/sessions/no-such-id/messages")
        assert response.status_code == 404
