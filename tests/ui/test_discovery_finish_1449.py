"""POST /api/v2/discovery/{session_id}/finish — the web UI's 'Finish now' (#1449).

The CLI got `/done` in #1443 (core `PrdDiscoverySession.finish_now`); the web UI
had no way to end discovery early. This route is that escape hatch over the same
core method: it needs at least one answer, and a finished session goes straight
to PRD generation.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.workspace import create_or_load_workspace
from tests.core.test_prd_discovery_bounded_1443 import FakeProvider, _coverage_json

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace():
    temp_dir = Path(tempfile.mkdtemp())
    path = temp_dir / "ws"
    path.mkdir()
    yield create_or_load_workspace(path)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def provider():
    return FakeProvider([_coverage_json(a) for a in range(10, 100, 6)])


@pytest.fixture
def client(workspace, provider, monkeypatch):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import discovery_v2

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    app = FastAPI()
    app.include_router(discovery_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    with patch("codeframe.core.llm_resolution.create_provider", return_value=provider):
        yield TestClient(app)


def _start(client) -> str:
    response = client.post("/api/v2/discovery/start")
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def test_finish_after_an_answer_completes_and_allows_prd_generation(client):
    session_id = _start(client)
    answered = client.post(f"/api/v2/discovery/{session_id}/answer", json={"answer": "A todo API."})
    assert answered.status_code == 200, answered.text
    assert answered.json()["is_complete"] is False

    response = client.post(f"/api/v2/discovery/{session_id}/finish")

    assert response.status_code == 200, response.text
    assert response.json() == {"is_complete": True, "answered": 1}
    status = client.get("/api/v2/discovery/status", params={"session_id": session_id}).json()
    assert status["progress"]["is_complete"] is True
    assert status["current_question"] is None
    generated = client.post(f"/api/v2/discovery/{session_id}/generate-prd")
    assert generated.status_code == 200, generated.text


def test_finish_before_any_answer_is_a_conflict(client):
    session_id = _start(client)

    response = client.post(f"/api/v2/discovery/{session_id}/finish")

    assert response.status_code == 409, response.text
    assert "at least one question" in response.json()["detail"]


def test_finish_an_unknown_session_is_not_found(client):
    response = client.post("/api/v2/discovery/no-such-session/finish")

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"].lower()
