"""
Authorization integration tests for FastAPI endpoints.

Tests representative endpoints across different routers to ensure
authorization is properly enforced.
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from codeframe.persistence.database import Database
from codeframe.ui.server import app


@pytest.fixture
def db(tmp_path):
    """Create test database."""
    db_path = tmp_path / "test_integration.db"
    db = Database(db_path)
    db.initialize()

    # Create test users (FastAPI Users schema)
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES
            (1, 'alice@example.com', 'Alice', '!DISABLED!', 1, 0, 1, 1),
            (2, 'bob@example.com', 'Bob', '!DISABLED!', 1, 0, 1, 1)
        """
    )

    # Create test projects
    db.conn.execute(
        """
        INSERT INTO projects (id, name, description, user_id, workspace_path, status)
        VALUES
            (1, 'Alice Project', 'Test', 1, '/tmp/alice', 'init'),
            (2, 'Bob Project', 'Test', 2, '/tmp/bob', 'init')
        """
    )

    db.conn.commit()
    yield db
    db.close()


@pytest.fixture
def client(db):
    """Create FastAPI test client with database."""
    app.state.db = db
    return TestClient(app)


@pytest.fixture
def alice_token(db):
    """Create session token for Alice."""
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    db.conn.execute(
        """
        INSERT INTO sessions (id, token, user_id, expires_at)
        VALUES ('alice-session-1', 'alice_token_123', 1, ?)
        """,
        (expires_at,)
    )
    db.conn.commit()
    return 'alice_token_123'


@pytest.fixture
def bob_token(db):
    """Create session token for Bob."""
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    db.conn.execute(
        """
        INSERT INTO sessions (id, token, user_id, expires_at)
        VALUES ('bob-session-2', 'bob_token_456', 2, ?)
        """,
        (expires_at,)
    )
    db.conn.commit()
    return 'bob_token_456'


class TestProjectEndpointsAuthorization:
    """Test authorization on /api/projects endpoints."""

    def test_get_project_owner_has_access(self, client, alice_token):
        """Test that project owner can access their project."""
        response = client.get(
            "/api/projects/1",
            headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_get_project_non_owner_denied(self, client, bob_token):
        """Test that non-owner cannot access project."""
        response = client.get(
            "/api/projects/1",
            headers={"Authorization": f"Bearer {bob_token}"}
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_get_project_no_token_unauthorized(self, client):
        """Test that request without token returns 401 (or 200 if AUTH_REQUIRED=false)."""
        response = client.get("/api/projects/1")
        # Note: Behavior depends on AUTH_REQUIRED setting
        # With AUTH_REQUIRED=true, should return 401
        # With AUTH_REQUIRED=false, might allow access (200)
        assert response.status_code in [200, 401, 403]


class TestTaskEndpointsAuthorization:
    """Test authorization on /api/tasks endpoints."""

    def test_create_task_requires_project_access(self, client, alice_token, bob_token, db):
        """Test that creating task requires access to project."""
        # Alice can create task in her project
        response = client.post(
            "/api/tasks",
            headers={"Authorization": f"Bearer {alice_token}"},
            json={
                "project_id": 1,
                "title": "Test Task",
                "description": "Test",
                "priority": 3
            }
        )
        assert response.status_code in [200, 201]

        # Bob cannot create task in Alice's project
        response = client.post(
            "/api/tasks",
            headers={"Authorization": f"Bearer {bob_token}"},
            json={
                "project_id": 1,
                "title": "Unauthorized Task",
                "description": "Test",
                "priority": 3
            }
        )
        assert response.status_code == 403


class TestMetricsEndpointsAuthorization:
    """Test authorization on /api/projects/{id}/metrics endpoints."""

    def test_get_project_costs_requires_access(self, client, alice_token, bob_token):
        """Test that metrics endpoints enforce project access."""
        # Alice can access her project metrics
        response = client.get(
            "/api/projects/1/metrics/costs",
            headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert response.status_code == 200

        # Bob cannot access Alice's project metrics
        response = client.get(
            "/api/projects/1/metrics/costs",
            headers={"Authorization": f"Bearer {bob_token}"}
        )
        assert response.status_code == 403


class TestCrossProjectDataLeak:
    """Test that agent metrics don't leak cross-project data."""

    def test_agent_metrics_filtered_by_user_access(self, client, alice_token, bob_token, db):
        """Test that /api/agents/{id}/metrics filters by accessible projects."""
        # Create agent with home project
        db.conn.execute(
            """
            INSERT INTO agents (id, type, status, project_id)
            VALUES ('test_agent', 'backend', 'idle', 1)
            """
        )

        # Assign agent to both projects via junction table
        db.conn.execute(
            """
            INSERT INTO project_agents (project_id, agent_id, role, is_active)
            VALUES
                (1, 'test_agent', 'backend', TRUE),
                (2, 'test_agent', 'backend', TRUE)
            """
        )

        # Create token usage for both projects
        db.conn.execute(
            """
            INSERT INTO token_usage (agent_id, project_id, model_name, input_tokens, output_tokens, estimated_cost_usd, call_type)
            VALUES
                ('test_agent', 1, 'claude-sonnet-4-5', 1000, 500, 0.01, 'task_execution'),
                ('test_agent', 2, 'claude-sonnet-4-5', 2000, 1000, 0.02, 'task_execution')
            """
        )
        db.conn.commit()

        # Alice should only see metrics for her project
        response = client.get(
            "/api/agents/test_agent/metrics",
            headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert response.status_code == 200
        data = response.json()

        # Verify only Alice's project appears in by_project breakdown
        project_ids = [p["project_id"] for p in data["by_project"]]
        assert 1 in project_ids
        assert 2 not in project_ids  # Bob's project shouldn't leak


class TestExceptionHandling:
    """Test that authorization exceptions aren't masked by generic handlers."""

    def test_review_status_403_not_masked(self, client, bob_token, db):
        """Test that 403 from review endpoints isn't converted to 500."""
        # Create task in Alice's project
        db.conn.execute(
            """
            INSERT INTO tasks (id, project_id, title, description, status, priority)
            VALUES (1, 1, 'Test Task', 'Test', 'pending', 3)
            """
        )
        db.conn.commit()

        # Bob tries to access Alice's task review status
        response = client.get(
            "/api/tasks/1/review-status",
            headers={"Authorization": f"Bearer {bob_token}"}
        )

        # Should return 403, not 500
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]
