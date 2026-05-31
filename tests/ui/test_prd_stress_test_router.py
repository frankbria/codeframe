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
        # Ambiguity resolution (refine) — return a clearly-rewritten PRD that is
        # long enough to pass resolve_ambiguities_into_prd's truncation guard.
        elif "update the prd" in (system or "").lower():
            response.content = (
                "# Invoice SaaS (Updated)\n\n"
                "## Authentication\nEmail/password with JWT sessions.\n\n"
                + SAMPLE_PRD
            )
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
    @patch("codeframe.adapters.llm.get_provider")
    def test_streams_event_sequence(
        self, mock_get_provider, test_client, mock_provider, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        mock_get_provider.return_value = mock_provider
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

    @patch("codeframe.adapters.llm.get_provider")
    def test_no_prd_emits_error_event(
        self, mock_get_provider, test_client, mock_provider, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        mock_get_provider.return_value = mock_provider

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

    @patch("codeframe.adapters.llm.get_provider")
    def test_non_anthropic_provider_does_not_require_anthropic_key(
        self, mock_get_provider, test_client, mock_provider, monkeypatch
    ):
        # A local/OpenAI-compatible provider is selected via env; the Anthropic
        # key gate must not apply and the stream should run to completion.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "ollama")
        mock_get_provider.return_value = mock_provider
        prd_module.store(test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {})

        response = test_client.get("/api/v2/prd/stress-test")
        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert events[-1]["type"] == "complete"
        # Provider was resolved via the chain, not hardcoded to Anthropic.
        assert mock_get_provider.call_args.args[0] == "ollama"


class TestStressTestDisconnect:
    """The stream must stop issuing LLM calls once the client disconnects."""

    async def test_aborts_when_client_disconnects(
        self, test_workspace, mock_provider, monkeypatch
    ):
        from codeframe.ui.routers.prd_v2 import _stress_test_event_stream

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        monkeypatch.setattr(
            "codeframe.adapters.llm.get_provider", lambda *a, **k: mock_provider
        )
        prd_module.store(test_workspace, SAMPLE_PRD, "Invoice SaaS", {})

        class FakeRequest:
            """Reports connected for the first event, then disconnected."""

            def __init__(self):
                self.calls = 0

            async def is_disconnected(self):
                self.calls += 1
                return self.calls > 1

        frames = [
            frame
            async for frame in _stress_test_event_stream(
                test_workspace, max_depth=3, request=FakeRequest()
            )
        ]

        # Only the first frame (goals_extracted) is emitted before the
        # disconnect is detected; no `complete` frame is sent.
        types = [json.loads(f[len("data:"):].strip())["type"] for f in frames]
        assert types == ["goals_extracted"]
        # The abort stops further decomposition. A full run of this fixture is 4
        # calls (extract + 3 atomic goals); aborting after goal 1 is at most 2
        # (extract + first goal's classification).
        assert mock_provider.complete.call_count <= 2

    async def test_completes_when_client_stays_connected(
        self, test_workspace, mock_provider, monkeypatch
    ):
        from codeframe.ui.routers.prd_v2 import _stress_test_event_stream

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        monkeypatch.setattr(
            "codeframe.adapters.llm.get_provider", lambda *a, **k: mock_provider
        )
        prd_module.store(test_workspace, SAMPLE_PRD, "Invoice SaaS", {})

        class ConnectedRequest:
            async def is_disconnected(self):
                return False

        frames = [
            frame
            async for frame in _stress_test_event_stream(
                test_workspace, max_depth=3, request=ConnectedRequest()
            )
        ]
        types = [json.loads(f[len("data:"):].strip())["type"] for f in frames]
        assert types[-1] == "complete"


class TestRefineEndpoint:
    """POST /api/v2/prd/stress-test/refine folds answers into a new PRD version."""

    @patch("codeframe.adapters.llm.get_provider")
    def test_refine_creates_new_version(
        self, mock_get_provider, test_client, mock_provider, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        mock_get_provider.return_value = mock_provider
        record = prd_module.store(
            test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {}
        )

        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": record.id,
                "answers": [
                    {
                        "label": "AUTH SCOPE",
                        "questions": ["Email/password or OAuth?"],
                        "answer": "Email/password with JWT sessions",
                    }
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        # A new version was created and its content is the LLM-refined PRD.
        assert body["version"] == record.version + 1
        assert "Updated" in body["content"]

    def test_refine_unknown_prd_returns_404(self, test_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": "does-not-exist",
                "answers": [
                    {"label": "X", "questions": ["?"], "answer": "y"}
                ],
            },
        )
        assert response.status_code == 404

    def test_refine_missing_api_key_returns_503(self, test_client, monkeypatch):
        # Missing server-side LLM config is a service-availability problem, not a
        # malformed request → 503, not 400.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        record = prd_module.store(
            test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {}
        )
        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": record.id,
                "answers": [
                    {"label": "X", "questions": ["?"], "answer": "y"}
                ],
            },
        )
        assert response.status_code == 503

    @patch("codeframe.adapters.llm.get_provider")
    def test_refine_no_change_returns_502(
        self, mock_get_provider, test_client, monkeypatch
    ):
        # When the LLM rewrite is truncated, resolve_ambiguities_into_prd returns
        # the original content; the endpoint must surface that instead of saving
        # a no-op version.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        record = prd_module.store(
            test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {}
        )

        truncating = MagicMock()
        # A short rewrite trips resolve_ambiguities_into_prd's truncation guard,
        # so it falls back to the original content (no change).
        truncating.complete.return_value = MagicMock(content="too short")
        mock_get_provider.return_value = truncating

        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": record.id,
                "answers": [
                    {"label": "X", "questions": ["?"], "answer": "y"}
                ],
            },
        )
        assert response.status_code == 502
        # No extra version should have been persisted.
        versions = prd_module.get_versions(test_client.workspace, record.id)
        assert len(versions) == 1

    def test_refine_rejects_whitespace_only_answer(self, test_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        record = prd_module.store(
            test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {}
        )
        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": record.id,
                "answers": [
                    {"label": "X", "questions": ["?"], "answer": "   "}
                ],
            },
        )
        assert response.status_code == 422

    @patch("codeframe.adapters.llm.get_provider")
    @patch("codeframe.core.prd.create_new_version", return_value=None)
    def test_refine_persistence_failure_returns_500(
        self, _mock_create, mock_get_provider, test_client, mock_provider, monkeypatch
    ):
        # The PRD exists (get_by_id succeeds) but persistence returns None — a
        # server fault, surfaced as 500 rather than a misleading 404.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        mock_get_provider.return_value = mock_provider
        record = prd_module.store(
            test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {}
        )
        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": record.id,
                "answers": [
                    {"label": "AUTH SCOPE", "questions": ["?"], "answer": "y"}
                ],
            },
        )
        assert response.status_code == 500

    def test_refine_rejects_empty_label(self, test_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        record = prd_module.store(
            test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {}
        )
        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": record.id,
                "answers": [{"label": "", "questions": ["?"], "answer": "y"}],
            },
        )
        assert response.status_code == 422

    def test_refine_requires_at_least_one_answer(self, test_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        record = prd_module.store(
            test_client.workspace, SAMPLE_PRD, "Invoice SaaS", {}
        )
        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={"prd_id": record.id, "answers": []},
        )
        assert response.status_code == 422

    def test_refine_route_not_shadowed_by_prd_id(
        self, test_client, monkeypatch
    ):
        # "stress-test/refine" must not be matched as GET /{prd_id}; a POST to
        # the refine path with a missing PRD should 404 from the refine handler
        # (not 405 method-not-allowed from a different route).
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
        response = test_client.post(
            "/api/v2/prd/stress-test/refine",
            json={
                "prd_id": "missing",
                "answers": [{"label": "X", "questions": [], "answer": "y"}],
            },
        )
        assert response.status_code == 404
