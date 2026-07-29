"""POST /api/v2/review/{files,task} cannot read outside the workspace (#899 / P0.5).

``ReviewFilesRequest.files`` is an unvalidated ``list[str]`` forwarded verbatim
into ``review.review_files``, which joined it straight onto the repo path. An
absolute path replaces the base and ``../`` walks out, so any authenticated
principal could scan any ``.py`` file the server user can read and get back
existence plus per-line findings — including the literal secret strings the
security scanner quotes. Cross-tenant read in hosted mode.

These are the end-to-end counterparts to the unit tests in
``tests/core/test_review.py::TestWorkspaceContainment``: they exercise the real
request path the issue names, so a future refactor that validates in the router
instead of the core would still be covered.
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.lib.quality.complexity_analyzer import ComplexityAnalyzer
from codeframe.lib.quality.owasp_patterns import OWASPPatterns
from codeframe.lib.quality.security_scanner import SecurityScanner

pytestmark = pytest.mark.v2


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "ws"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)
    yield workspace
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def outsider(test_workspace):
    """A readable .py file in the workspace's PARENT.

    It must be a real file one level up, not just any out-of-tree path:
    ``../secrets.py`` resolves relative to the workspace, so pointing it at an
    unrelated temp dir would make the request fail on "not found" and the test
    would pass with the guard removed.
    """
    secret = Path(test_workspace.repo_path).resolve().parent / "secrets.py"
    secret.write_text('AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7"\n')
    return secret


@pytest.fixture
def analyzed(monkeypatch):
    """Record every path an analyzer is handed.

    The assertion that matters is *which file was opened*, not whether findings
    came back: a path that escapes but happens to yield no findings is still a
    successful probe of the host filesystem.
    """
    seen: list = []

    def _record(self, path):
        seen.append(Path(path))
        return []

    monkeypatch.setattr(ComplexityAnalyzer, "analyze_file", _record)
    monkeypatch.setattr(SecurityScanner, "analyze_file", _record)
    monkeypatch.setattr(OWASPPatterns, "check_file", _record)
    return seen


@pytest.fixture
def client(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import review_v2

    app = FastAPI()
    app.include_router(review_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return TestClient(app)


class TestReviewFilesEndpoint:
    def test_parent_traversal_is_rejected(self, client, outsider, analyzed):
        resp = client.post("/api/v2/review/files", json={"files": ["../secrets.py"]})

        assert resp.status_code == 200, resp.text
        assert analyzed == [], f"analyzer opened {analyzed}"
        assert resp.json()["findings"] == []

    def test_absolute_path_is_rejected(self, client, outsider, analyzed):
        resp = client.post(
            "/api/v2/review/files",
            json={"files": [str(outsider)]},
        )

        assert resp.status_code == 200, resp.text
        assert analyzed == [], f"analyzer opened {analyzed}"
        assert resp.json()["findings"] == []

    def test_absolute_system_path_is_rejected(self, client, analyzed):
        resp = client.post("/api/v2/review/files", json={"files": ["/etc/hosts.py"]})

        assert resp.status_code == 200, resp.text
        assert analyzed == []

    def test_in_workspace_file_is_still_reviewed(
        self, client, test_workspace, analyzed
    ):
        (test_workspace.repo_path / "mod.py").write_text("def f():\n    return 1\n")

        resp = client.post("/api/v2/review/files", json={"files": ["mod.py"]})

        assert resp.status_code == 200, resp.text
        assert analyzed, "a legitimate in-workspace file must still be analyzed"
        for path in analyzed:
            assert path.is_relative_to(Path(test_workspace.repo_path).resolve())


class TestReviewTaskEndpoint:
    """The issue names review_task as sharing the vulnerable code path."""

    def test_parent_traversal_is_rejected(self, client, outsider, analyzed):
        resp = client.post(
            "/api/v2/review/task",
            json={"task_id": "T-1", "files_modified": ["../secrets.py"]},
        )

        assert resp.status_code == 200, resp.text
        assert analyzed == [], f"analyzer opened {analyzed}"

    def test_absolute_path_is_rejected(self, client, outsider, analyzed):
        resp = client.post(
            "/api/v2/review/task",
            json={
                "task_id": "T-1",
                "files_modified": [str(outsider)],
            },
        )

        assert resp.status_code == 200, resp.text
        assert analyzed == [], f"analyzer opened {analyzed}"
