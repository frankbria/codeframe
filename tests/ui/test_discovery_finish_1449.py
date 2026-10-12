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


def test_an_untrusted_base_url_is_a_logged_500_not_an_escape(client, workspace, caplog):
    """create_provider runs on session load and can refuse a repo's base_url (#903)."""
    from codeframe.core.llm_resolution import UntrustedBaseURLError

    session_id = _start(client)
    with patch(
        "codeframe.core.prd_discovery.get_session",
        side_effect=UntrustedBaseURLError("config.yaml names a non-loopback base_url"),
    ):
        response = client.post(f"/api/v2/discovery/{session_id}/finish")

    assert response.status_code == 500, response.text
    assert "base_url" in response.json()["detail"]
    assert "Failed to finish discovery" in caplog.text


def test_a_stale_finish_does_not_drop_an_answer_saved_meanwhile(workspace, provider):
    """Tab B loads the session, tab A's answer lands, then B finishes (#1449 review)."""
    from codeframe.core.prd_discovery import PrdDiscoverySession, get_session

    with patch("codeframe.core.prd_discovery.AnthropicProvider", return_value=provider):
        tab_a = PrdDiscoverySession(workspace, api_key="k")
        tab_a.start_discovery()
        tab_a.submit_answer("first")
        tab_b = get_session(workspace, tab_a.session_id, api_key="k")

        tab_a.submit_answer("second")  # lands after B loaded
        tab_b.finish_now()

        stored = get_session(workspace, tab_a.session_id, api_key="k")
    assert stored.is_complete()
    assert [qa["answer"] for qa in stored._qa_history] == ["first", "second"]


def test_a_slow_answer_cannot_unfinish_a_session_finished_meanwhile(workspace, provider):
    """Tab A's answer is in flight, tab B finishes, then A saves (#1449 review)."""
    from codeframe.core.prd_discovery import PrdDiscoverySession, SessionResetError, get_session

    with patch("codeframe.core.prd_discovery.AnthropicProvider", return_value=provider):
        tab_b = PrdDiscoverySession(workspace, api_key="k")
        tab_b.start_discovery()
        tab_b.submit_answer("first")
        tab_a = get_session(workspace, tab_b.session_id, api_key="k")  # loaded before the finish

        tab_b.finish_now()
        with pytest.raises(SessionResetError):
            tab_a.submit_answer("second")  # stale copy: is_complete False in memory

        stored = get_session(workspace, tab_b.session_id, api_key="k")
    assert stored.is_complete()
    assert stored.get_current_question() is None
    assert [qa["answer"] for qa in stored._qa_history] == ["first"]
