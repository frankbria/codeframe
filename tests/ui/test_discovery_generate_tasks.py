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
