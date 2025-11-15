"""Tests for health check endpoint."""

import pytest
from fastapi.testclient import TestClient
from codeframe.ui.server import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_endpoint_exists(client):
    """Test that /health endpoint exists."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_returns_json(client):
    """Test that /health returns JSON."""
    response = client.get("/health")
    assert response.headers["content-type"] == "application/json"


def test_health_endpoint_structure(client):
    """Test that /health returns expected structure."""
    response = client.get("/health")
    data = response.json()

    # Test required fields
    assert "status" in data
    assert data["status"] == "healthy"
    assert "service" in data
    assert data["service"] == "CodeFRAME Status Server"

    # Test deployment info fields
    assert "version" in data
    assert "commit" in data
    assert "deployed_at" in data
    assert "database" in data
