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


# ---------------------------------------------------------------------------
# Deployment reporting (#1160)
#
# The old assertions were key-presence only, which is why both fields could be
# wrong for a whole release cycle: `deployed_at` was `datetime.now()` evaluated
# per request, and `commit` shelled out to git against a source tree the image
# does not contain. These assert the values, not the keys.
# ---------------------------------------------------------------------------


def test_deployed_at_is_stable_across_requests(client):
    """`deployed_at` must not move between two calls seconds apart.

    It reported "deployed seconds ago" forever, so it could never show the one
    thing it exists to show: a stale deploy.
    """
    first = client.get("/health").json()["deployed_at"]
    second = client.get("/health").json()["deployed_at"]

    assert first == second


def test_deployed_at_is_iso_utc(client):
    """Still a parseable UTC instant, not just any stable string."""
    from datetime import datetime

    value = client.get("/health").json()["deployed_at"]

    assert value.endswith("Z")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_commit_comes_from_git_commit_env(client, monkeypatch):
    """The image build stamps GIT_COMMIT; /health reports it verbatim."""
    monkeypatch.setenv("GIT_COMMIT", "9024e44e1c0ffee0000000000000000000000000")

    assert client.get("/health").json()["commit"] == (
        "9024e44e1c0ffee0000000000000000000000000"
    )


def test_commit_is_read_per_request_not_at_import(client, monkeypatch):
    """Read at call time (#963) — the env arrives at container start."""
    monkeypatch.setenv("GIT_COMMIT", "aaaaaaa")
    assert client.get("/health").json()["commit"] == "aaaaaaa"

    monkeypatch.setenv("GIT_COMMIT", "bbbbbbb")
    assert client.get("/health").json()["commit"] == "bbbbbbb"


def test_commit_falls_back_to_unknown_outside_docker(client, monkeypatch):
    """A local `uv run codeframe serve` has no GIT_COMMIT and must still work."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)

    assert client.get("/health").json()["commit"] == "unknown"
