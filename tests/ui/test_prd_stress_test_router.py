"""Tests for the PRD stress-test SSE endpoint (issue #561).

Covers GET /api/v2/prd/stress-test:
- Streams the core stress_test_prd_stream events as SSE
- Emits an in-stream error event when no PRD exists
- Emits an in-stream error event when ANTHROPIC_API_KEY is missing

The endpoint is GET (not POST) so it is reachable from a browser EventSource,
matching the existing GET /api/v2/tasks/{task_id}/stream pattern.
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import prd as prd_module
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


SAMPLE_PRD = """# Invoice SaaS

## Core Features
1. User Authentication - users can register and log in
2. Invoice Management - CRUD operations for invoices
3. PDF Export - generate PDF invoices
"""


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    workspace = create_or_load_workspace(workspace_path)
    yield workspace
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import prd_v2

    app = FastAPI()
    app.include_router(prd_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace

    client = TestClient(app)
    client.workspace = test_workspace
    return client


@pytest.fixture
def mock_provider():
    """Mock LLM provider returning predictable decomposition responses."""
    mock = MagicMock()

    def complete_side_effect(messages, purpose=None, system=None, **kwargs):
        content = messages[0]["content"] if messages else ""
        response = MagicMock()
        if "high-level deliverable goals" in (system or "").lower():
            response.content = json.dumps(
                ["User Authentication", "Invoice Management", "PDF Export"]
            )
        elif "classify" in (system or "").lower():
            goal_line = ""
            for line in content.splitlines():
                if line.startswith("Goal: "):
                    goal_line = line[6:].strip()
                    break
            if "Authentication" in goal_line:
                response.content = json.dumps({
                    "classification": "ambiguous",
                    "ambiguity_label": "AUTH SCOPE",
                    "questions": ["Email/password or OAuth?"],
                    "recommendation": "Add auth section",
                    "complexity_hint": "Medium",
                })
            else:
                response.content = json.dumps({
                    "classification": "atomic",
                    "complexity_hint": "Low",
                })
        else:
            response.content = json.dumps(
                {"classification": "atomic", "complexity_hint": "Low"}
            )
        return response

    mock.complete.side_effect = complete_side_effect
    return mock


def _parse_sse(text: str) -> list[dict]:
    """Extract JSON payloads from SSE `data:` lines (ignoring heartbeats)."""
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                events.append(json.loads(payload))
    return events


class TestStressTestEndpoint:
    @patch("codeframe.adapters.llm.anthropic.AnthropicProvider")
    def test_streams_event_sequence(
        self, mock_provider_cls, test_client, mock_provider, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        mock_provider_cls.return_value = mock_provider
        prd_module.store(test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {})

        response = test_client.get("/api/v2/prd/stress-test")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        events = _parse_sse(response.text)
        types = [e["type"] for e in events]
        assert types[0] == "goals_extracted"
        assert types[-1] == "complete"
        assert types.count("goal_analyzed") == 3
        assert events[-1]["ambiguity_count"] == 1

    @patch("codeframe.adapters.llm.anthropic.AnthropicProvider")
    def test_no_prd_emits_error_event(
        self, mock_provider_cls, test_client, mock_provider, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        mock_provider_cls.return_value = mock_provider

        response = test_client.get("/api/v2/prd/stress-test")
        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1]["type"] == "error"
        assert "prd" in events[-1]["message"].lower()

    def test_missing_api_key_emits_error_event(self, test_client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        prd_module.store(test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {})

        response = test_client.get("/api/v2/prd/stress-test")
        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1]["type"] == "error"
        assert "ANTHROPIC_API_KEY" in events[-1]["message"]
