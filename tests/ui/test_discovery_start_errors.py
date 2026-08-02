"""POST /api/v2/discovery/start must not swallow its own 400 (#928).

The `session already active` HTTPException was raised inside a try whose blanket
`except Exception` re-raised it as a 500 with the structured detail mangled into
a string — the caller lost both the status code and the session_id/hint payload.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)
    yield create_or_load_workspace(workspace_path)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import discovery_v2

    app = FastAPI()
    app.include_router(discovery_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return TestClient(app)


class TestStartDiscoveryConflict:
    def test_active_session_returns_structured_400(self, test_client):
        active = MagicMock()
        active.is_complete.return_value = False
        active.session_id = "sess-123"
        active.answered_count = 2

        with patch(
            "codeframe.core.prd_discovery.get_active_session", return_value=active
        ):
            response = test_client.post("/api/v2/discovery/start")

        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert isinstance(detail, dict), f"detail was stringified: {detail!r}"
        assert detail["error"] == "Discovery session already active"
        assert detail["session_id"] == "sess-123"
        assert detail["answered_count"] == 2

    def test_unexpected_failure_is_still_a_500(self, test_client):
        """The blanket handler must keep working for genuine errors."""
        with patch(
            "codeframe.core.prd_discovery.get_active_session",
            side_effect=RuntimeError("db is on fire"),
        ):
            response = test_client.post("/api/v2/discovery/start")

        assert response.status_code == 500
        assert "db is on fire" in response.json()["detail"]
