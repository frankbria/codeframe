"""Tests for Context Management API endpoints (User Story 007).

Covers context item CRUD operations, scoring, tiering, and flash save functionality.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, UTC

from codeframe.core.models import (
    TaskStatus,
    Task,
    ContextItemType,
    AgentMaturity,
)


def get_app():
    """Get the current app instance after module reload."""
    from codeframe.ui.server import app
    return app


class TestCreateContextItem:
    """Test POST /api/agents/{agent_id}/context endpoint."""

    def test_create_context_item_success(self, api_client):
        """Test creating a context item successfully."""
        # Arrange: Create project
        project_id = get_app().state.db.create_project(
            name="Test Context",
            description="Test context item creation"
        )

        agent_id = "test-agent-001"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Act
        response = api_client.post(
            f"/api/agents/{agent_id}/context",
            params={"project_id": project_id},
            json={
                "item_type": "task",
                "content": "Implement user authentication",
                "metadata": {"priority": "high"}
            }
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["item_type"] == "task"
        assert data["content"] == "Implement user authentication"

    def test_create_context_item_missing_project_id(self, api_client):
        """Test creating context item without project_id returns 422."""
        agent_id = "test-agent-002"

        # Act
        response = api_client.post(
            f"/api/agents/{agent_id}/context",
            json={
                "item_type": "task",
                "content": "Some content"
            }
        )

        # Assert
        assert response.status_code == 422

    def test_create_context_item_invalid_type(self, api_client):
        """Test creating context item with invalid type."""
        project_id = get_app().state.db.create_project(
            name="Test Invalid Type",
            description="Test invalid context type"
        )

        agent_id = "test-agent-003"

        # Act
        response = api_client.post(
            f"/api/agents/{agent_id}/context",
            params={"project_id": project_id},
            json={
                "item_type": "invalid_type",
                "content": "Some content"
            }
        )

        # Assert
        assert response.status_code == 422


class TestGetContextItem:
    """Test GET /api/agents/{agent_id}/context/{item_id} endpoint."""

    def test_get_context_item_success(self, api_client):
        """Test getting a specific context item."""
        # Arrange: Create project and context item
        project_id = get_app().state.db.create_project(
            name="Test Get Context",
            description="Test getting context item"
        )

        agent_id = "test-agent-004"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create context item
        item_id = get_app().state.db.save_context_item(
            project_id=project_id,
            agent_id=agent_id,
            item_type=ContextItemType.CODE,
            content="def hello(): pass",
            metadata={"language": "python"}
        )

        # Act
        response = api_client.get(f"/api/agents/{agent_id}/context/{item_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == item_id
        assert data["content"] == "def hello(): pass"

    def test_get_context_item_not_found(self, api_client):
        """Test getting non-existent context item."""
        agent_id = "test-agent-005"

        # Act
        response = api_client.get(f"/api/agents/{agent_id}/context/nonexistent-id")

        # Assert
        assert response.status_code == 404


class TestListContextItems:
    """Test GET /api/agents/{agent_id}/context endpoint (list)."""

    def test_list_context_items_success(self, api_client):
        """Test listing context items for an agent."""
        # Arrange: Create project and context items
        project_id = get_app().state.db.create_project(
            name="Test List Context",
            description="Test listing context items"
        )

        agent_id = "test-agent-006"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create multiple context items
        for i in range(5):
            get_app().state.db.save_context_item(
                project_id=project_id,
                agent_id=agent_id,
                item_type=ContextItemType.TASK,
                content=f"Task {i}",
                metadata={}
            )

        # Act
        response = api_client.get(
            f"/api/agents/{agent_id}/context",
            params={"project_id": project_id}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 5

    def test_list_context_items_with_tier_filter(self, api_client):
        """Test listing context items filtered by tier."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Tier Filter",
            description="Test tier filtering"
        )

        agent_id = "test-agent-007"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Act
        response = api_client.get(
            f"/api/agents/{agent_id}/context",
            params={"project_id": project_id, "tier": "hot"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_list_context_items_with_limit(self, api_client):
        """Test listing context items with limit."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Limit",
            description="Test limit parameter"
        )

        agent_id = "test-agent-008"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create 10 items
        for i in range(10):
            get_app().state.db.save_context_item(
                project_id=project_id,
                agent_id=agent_id,
                item_type=ContextItemType.TASK,
                content=f"Task {i}",
                metadata={}
            )

        # Act
        response = api_client.get(
            f"/api/agents/{agent_id}/context",
            params={"project_id": project_id, "limit": 5}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 5


class TestDeleteContextItem:
    """Test DELETE /api/agents/{agent_id}/context/{item_id} endpoint."""

    def test_delete_context_item_success(self, api_client):
        """Test deleting a context item."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Delete Context",
            description="Test deleting context item"
        )

        agent_id = "test-agent-009"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create context item
        item_id = get_app().state.db.save_context_item(
            project_id=project_id,
            agent_id=agent_id,
            item_type=ContextItemType.TASK,
            content="To be deleted",
            metadata={}
        )

        # Act
        response = api_client.delete(f"/api/agents/{agent_id}/context/{item_id}")

        # Assert
        assert response.status_code == 204

        # Verify deletion
        item = get_app().state.db.get_context_item(item_id)
        assert item is None

    def test_delete_context_item_not_found(self, api_client):
        """Test deleting non-existent context item."""
        agent_id = "test-agent-010"

        # Act
        response = api_client.delete(f"/api/agents/{agent_id}/context/nonexistent")

        # Assert
        assert response.status_code == 404


class TestUpdateContextScores:
    """Test POST /api/agents/{agent_id}/context/update-scores endpoint."""

    def test_update_context_scores_success(self, api_client):
        """Test updating importance scores for context items."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Update Scores",
            description="Test score updates"
        )

        agent_id = "test-agent-011"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create context items
        for i in range(3):
            get_app().state.db.save_context_item(
                project_id=project_id,
                agent_id=agent_id,
                item_type=ContextItemType.TASK,
                content=f"Task {i}",
                metadata={}
            )

        # Act
        response = api_client.post(
            f"/api/agents/{agent_id}/context/update-scores",
            params={"project_id": project_id}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "updated_count" in data
        assert data["updated_count"] >= 0

    def test_update_context_scores_missing_project_id(self, api_client):
        """Test updating scores without project_id."""
        agent_id = "test-agent-012"

        # Act
        response = api_client.post(f"/api/agents/{agent_id}/context/update-scores")

        # Assert
        assert response.status_code == 422


class TestUpdateContextTiers:
    """Test POST /api/agents/{agent_id}/context/update-tiers endpoint."""

    def test_update_context_tiers_success(self, api_client):
        """Test updating tier assignments for context items."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Update Tiers",
            description="Test tier updates"
        )

        agent_id = "test-agent-013"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Act
        response = api_client.post(
            f"/api/agents/{agent_id}/context/update-tiers",
            params={"project_id": project_id}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "updated_count" in data


class TestFlashSave:
    """Test POST /api/agents/{agent_id}/flash-save endpoint."""

    def test_flash_save_success(self, api_client):
        """Test flash save operation."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Flash Save",
            description="Test flash save",
            project_path="/tmp/test-flash-save"
        )

        agent_id = "test-agent-014"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create context items to archive
        for i in range(10):
            get_app().state.db.save_context_item(
                project_id=project_id,
                agent_id=agent_id,
                item_type=ContextItemType.TASK,
                content=f"Task {i}",
                metadata={},
                tier="cold"  # Mark as cold so it gets archived
            )

        # Act
        response = api_client.post(
            f"/api/agents/{agent_id}/flash-save",
            params={"project_id": project_id, "force": True}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "checkpoint_id" in data
        assert "items_archived" in data

    def test_flash_save_missing_project_id(self, api_client):
        """Test flash save without project_id."""
        agent_id = "test-agent-015"

        # Act
        response = api_client.post(f"/api/agents/{agent_id}/flash-save")

        # Assert
        assert response.status_code == 422


class TestFlashSaveCheckpoints:
    """Test GET /api/agents/{agent_id}/flash-save/checkpoints endpoint."""

    def test_list_flash_save_checkpoints(self, api_client):
        """Test listing flash save checkpoints."""
        # Arrange
        agent_id = "test-agent-016"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Act
        response = api_client.get(f"/api/agents/{agent_id}/flash-save/checkpoints")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "checkpoints" in data
        assert isinstance(data["checkpoints"], list)

    def test_list_flash_save_checkpoints_with_limit(self, api_client):
        """Test listing checkpoints with limit."""
        agent_id = "test-agent-017"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Act
        response = api_client.get(
            f"/api/agents/{agent_id}/flash-save/checkpoints",
            params={"limit": 5}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["checkpoints"]) <= 5


class TestContextStats:
    """Test GET /api/agents/{agent_id}/context/stats endpoint."""

    def test_get_context_stats_success(self, api_client):
        """Test getting context statistics."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Context Stats",
            description="Test context statistics"
        )

        agent_id = "test-agent-018"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create context items with different tiers
        for tier in ["hot", "warm", "cold"]:
            for i in range(3):
                get_app().state.db.save_context_item(
                    project_id=project_id,
                    agent_id=agent_id,
                    item_type=ContextItemType.TASK,
                    content=f"{tier} task {i}",
                    metadata={},
                    tier=tier
                )

        # Act
        response = api_client.get(
            f"/api/agents/{agent_id}/context/stats",
            params={"project_id": project_id}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "hot_count" in data
        assert "warm_count" in data
        assert "cold_count" in data
        assert "total_tokens" in data

    def test_get_context_stats_missing_project_id(self, api_client):
        """Test getting stats without project_id."""
        agent_id = "test-agent-019"

        # Act
        response = api_client.get(f"/api/agents/{agent_id}/context/stats")

        # Assert
        assert response.status_code == 422


class TestGetContextItems:
    """Test GET /api/agents/{agent_id}/context/items endpoint."""

    def test_get_context_items_with_pagination(self, api_client):
        """Test getting context items with pagination."""
        # Arrange
        project_id = get_app().state.db.create_project(
            name="Test Pagination",
            description="Test pagination"
        )

        agent_id = "test-agent-020"

        # Create agent
        get_app().state.db.create_agent(
            agent_id=agent_id,
            agent_type="backend",
            provider="anthropic",
            maturity_level=AgentMaturity.D3
        )

        # Create 20 items
        for i in range(20):
            get_app().state.db.save_context_item(
                project_id=project_id,
                agent_id=agent_id,
                item_type=ContextItemType.TASK,
                content=f"Task {i}",
                metadata={}
            )

        # Act: Get first page
        response = api_client.get(
            f"/api/agents/{agent_id}/context/items",
            params={"project_id": project_id, "limit": 10, "offset": 0}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 10

        # Get second page
        response2 = api_client.get(
            f"/api/agents/{agent_id}/context/items",
            params={"project_id": project_id, "limit": 10, "offset": 10}
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 10
