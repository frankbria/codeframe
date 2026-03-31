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


@pytest.fixture
def client():
    """Create a test app with the interactive sessions router and real in-memory DB.

    Function-scoped to prevent cross-test state pollution.
    """
    app = FastAPI()
    app.include_router(router)

    db = Database(":memory:")
    db.initialize()
    app.state.db = db

    with TestClient(app, raise_server_exceptions=True) as c:
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
        assert data["task_id"] is None
        assert data["cost_usd"] == 0.0
        assert data["input_tokens"] == 0
        assert data["output_tokens"] == 0
        assert "id" in data
        assert data["ended_at"] is None

    def test_create_session_full(self, client):
        """Create a session with all fields specified; task_id is returned."""
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
        assert data["task_id"] == "task-abc-123"

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
        """List returns exactly the created sessions."""
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/list-ws"})
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/list-ws"})

        response = client.get("/api/v2/sessions?workspace_path=/tmp/list-ws")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_filter_by_workspace(self, client):
        """Filter sessions by workspace_path returns only matching sessions."""
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/ws-a"})
        client.post("/api/v2/sessions", json={"workspace_path": "/tmp/ws-b"})

        response = client.get("/api/v2/sessions?workspace_path=/tmp/ws-a")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["workspace_path"] == "/tmp/ws-a"

    def test_list_filter_by_state(self, client):
        """Filter sessions by state returns only matching sessions."""
        r = client.post("/api/v2/sessions", json={"workspace_path": "/tmp/ws-state"})
        session_id = r.json()["id"]
        client.delete(f"/api/v2/sessions/{session_id}")

        ended_resp = client.get(
            "/api/v2/sessions?workspace_path=/tmp/ws-state&state=ended"
        )
        assert ended_resp.status_code == 200
        data = ended_resp.json()
        assert len(data) == 1
        assert data[0]["state"] == "ended"


class TestDeleteSession:
    """Tests for DELETE /api/v2/sessions/{id}."""

    def test_end_session(self, client):
        """End a session sets state to ended and sets ended_at."""
        create_resp = client.post(
            "/api/v2/sessions", json={"workspace_path": "/tmp/ws-end"}
        )
        session_id = create_resp.json()["id"]

        response = client.delete(f"/api/v2/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
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


class TestRepositoryOperations:
    """Tests for repository methods not covered by API endpoints."""

    def test_update_state(self, client):
        """update_state transitions session state correctly."""
        app = client.app
        repo = app.state.db.interactive_sessions

        session = repo.create(workspace_path="/tmp/ws-state-update")
        assert session["state"] == "active"

        repo.update_state(session["id"], "paused")
        updated = repo.get(session["id"])
        assert updated["state"] == "paused"

    def test_update_cost(self, client):
        """update_cost accumulates cost and token counts."""
        repo = client.app.state.db.interactive_sessions
        session = repo.create(workspace_path="/tmp/ws-cost")

        repo.update_cost(session["id"], cost_usd=0.05, input_tokens=1000, output_tokens=200)
        repo.update_cost(session["id"], cost_usd=0.03, input_tokens=500, output_tokens=100)

        updated = repo.get(session["id"])
        assert abs(updated["cost_usd"] - 0.08) < 0.001
        assert updated["input_tokens"] == 1500
        assert updated["output_tokens"] == 300

    def test_add_and_get_messages(self, client):
        """add_message and get_messages work as a round-trip."""
        repo = client.app.state.db.interactive_sessions
        session = repo.create(workspace_path="/tmp/ws-messages")

        repo.add_message(session["id"], role="user", content="Hello agent")
        repo.add_message(
            session["id"],
            role="assistant",
            content="Hello!",
            metadata={"model": "claude-opus-4-6", "tokens": 10},
        )

        messages = repo.get_messages(session["id"])
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello agent"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["metadata"]["model"] == "claude-opus-4-6"

    def test_get_messages_pagination(self, client):
        """get_messages respects limit and offset."""
        repo = client.app.state.db.interactive_sessions
        session = repo.create(workspace_path="/tmp/ws-pagination")

        for i in range(5):
            repo.add_message(session["id"], role="user", content=f"msg {i}")

        page1 = repo.get_messages(session["id"], limit=3, offset=0)
        page2 = repo.get_messages(session["id"], limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 2
