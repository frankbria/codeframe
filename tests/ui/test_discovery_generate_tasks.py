"""POST /api/v2/discovery/generate-tasks must honor the provider chain (#768).

The endpoint previously called ``tasks.generate_from_prd`` with no provider,
falling through to the hardcoded-Anthropic ``get_provider()`` default and
ignoring CODEFRAME_LLM_PROVIDER / ``.codeframe/config.yaml``.
"""

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


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    workspace = create_or_load_workspace(workspace_path)
    prd_module.store(workspace, content="# PRD\n\n## Feature: Login\n- Add login")
    yield workspace
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import discovery_v2

    app = FastAPI()
    app.include_router(discovery_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return TestClient(app)


class TestGenerateTasksProviderResolution:
    def test_resolved_provider_is_passed_to_generation(
        self, test_client, monkeypatch
    ):
        """With CODEFRAME_LLM_PROVIDER set, the endpoint builds that provider
        and threads it into generate_from_prd — no Anthropic key needed."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "ollama")

        fake_provider = MagicMock()
        with (
            patch(
                "codeframe.core.llm_resolution.create_provider",
                return_value=fake_provider,
            ) as mock_create,
            patch(
                "codeframe.core.tasks._generate_tasks_with_llm",
                return_value=[{"title": "Task A", "description": "do a"}],
            ) as mock_llm_gen,
        ):
            response = test_client.post("/api/v2/discovery/generate-tasks")

        assert response.status_code == 200, response.text
        assert response.json()["task_count"] == 1
        mock_create.assert_called_once()
        assert mock_llm_gen.call_args.args[1] is fake_provider

    def test_no_llm_skips_provider_resolution(self, test_client, monkeypatch):
        """use_llm=false must not construct any provider."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with patch(
            "codeframe.core.llm_resolution.create_provider"
        ) as mock_create:
            response = test_client.post(
                "/api/v2/discovery/generate-tasks?use_llm=false"
            )
        assert response.status_code == 200, response.text
        mock_create.assert_not_called()


class TestUnusableLLMOutputIsAnUpstreamFailure:
    """#1115: the endpoint must report a failed decomposition, not a 200 or a 500.

    Before, a truncated/garbage response degraded silently to bullet extraction
    and returned 200 with a list of unimplementable "tasks" — the caller could
    not tell it had failed. TaskGenerationError now maps to 502, matching how the
    repo already remaps upstream GitHub failures.
    """

    def _post_with_llm_returning(self, test_client, monkeypatch, payload):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "ollama")
        provider = MagicMock()
        provider.complete.return_value = MagicMock(content=payload)
        with patch(
            "codeframe.core.llm_resolution.create_provider", return_value=provider
        ):
            return test_client.post("/api/v2/discovery/generate-tasks")

    def test_truncated_json_returns_502(self, test_client, monkeypatch):
        truncated = '[{"title": "Define the model", "description": "x"}, {"title": "Imple'
        response = self._post_with_llm_returning(test_client, monkeypatch, truncated)

        assert response.status_code == 502, response.text
        assert "truncated" in response.json()["detail"].lower()

    def test_garbage_returns_502_not_200(self, test_client, monkeypatch):
        response = self._post_with_llm_returning(
            test_client, monkeypatch, "I'm afraid I can't do that"
        )

        assert response.status_code == 502, response.text
        assert response.json()["detail"].startswith("Task generation failed")

    def test_the_detail_does_not_tell_a_web_user_to_run_a_cli_command(
        self, test_client, monkeypatch
    ):
        """This detail is toasted verbatim by /prd — `cf tasks generate` is useless there."""
        response = self._post_with_llm_returning(test_client, monkeypatch, "nonsense")

        assert "cf tasks generate" not in response.json()["detail"]
