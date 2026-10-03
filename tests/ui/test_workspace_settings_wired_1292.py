"""Settings -> Workspace values are read, not just saved (#1292).

The default branch and the tech-stack choice were written to
``workspace_config.json`` and nothing read them: a repo whose default branch is
``develop`` still got PRs against ``main``, and the override never reached the
workspace's ``tech_stack``, which is what the agent sees.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from codeframe.git.github_integration import PRDetails

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


@pytest.fixture
def client(workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import pr_v2, workspace_v2

    app = FastAPI()
    app.include_router(pr_v2.router)
    app.include_router(workspace_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app, raise_server_exceptions=False)


def _save_config(client, **overrides):
    body = {
        "workspace_root": "/ignored",
        "default_branch": "main",
        "auto_detect_tech_stack": True,
        "tech_stack_override": None,
        **overrides,
    }
    resp = client.put("/api/v2/workspaces/config", json=body)
    assert resp.status_code == 200, resp.text


def _pr(base_branch: str) -> PRDetails:
    return PRDetails(
        number=7, url="https://github.com/o/r/pull/7", state="open", title="T",
        body="B", created_at=datetime.now(timezone.utc), merged_at=None,
        head_branch="feature/x", base_branch=base_branch,
    )


def _create_pr(client, **extra) -> MagicMock:
    gh = MagicMock()
    gh.create_pull_request = AsyncMock(return_value=_pr("x"))
    gh.close = AsyncMock()
    with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=gh):
        resp = client.post("/api/v2/pr", json={"branch": "feature/x", "title": "T", **extra})
    assert resp.status_code == 201, resp.text
    return gh


class TestDefaultBranchIsThePrBase:
    def test_with_nothing_saved_it_is_main(self, client):
        gh = _create_pr(client)
        assert gh.create_pull_request.await_args.kwargs["base"] == "main"

    def test_the_saved_default_branch_is_used(self, client):
        _save_config(client, default_branch="develop")
        gh = _create_pr(client)
        assert gh.create_pull_request.await_args.kwargs["base"] == "develop"

    def test_an_explicit_base_still_wins(self, client):
        _save_config(client, default_branch="develop")
        gh = _create_pr(client, base="release")
        assert gh.create_pull_request.await_args.kwargs["base"] == "release"

    def test_the_cli_uses_it_too(self, client, workspace, monkeypatch):
        from codeframe.cli.pr_commands import pr_app

        _save_config(client, default_branch="develop")
        monkeypatch.chdir(workspace.repo_path)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.setenv("GITHUB_REPO", "o/r")
        with (
            patch("codeframe.cli.pr_commands.GitHubIntegration", autospec=True) as MockGH,
            patch("codeframe.cli.pr_commands.get_current_branch", return_value="feature/x"),
        ):
            MockGH.return_value.create_pull_request.return_value = _pr("develop")
            result = CliRunner().invoke(pr_app, ["create", "--title", "T", "--no-auto-description"])

        assert result.exit_code == 0, result.output
        assert MockGH.return_value.create_pull_request.call_args.kwargs["base"] == "develop"


class TestTechStackChoiceReachesTheWorkspace:
    def _tech_stack(self, workspace):
        from codeframe.core.workspace import get_workspace

        return get_workspace(workspace.repo_path).tech_stack

    def test_the_override_becomes_the_tech_stack(self, client, workspace):
        _save_config(client, auto_detect_tech_stack=False, tech_stack_override="Go 1.22 with chi")
        assert self._tech_stack(workspace) == "Go 1.22 with chi"

    def test_auto_detect_detects_from_the_repo(self, client, workspace):
        (workspace.repo_path / "pyproject.toml").write_text('[tool.uv]\n[project]\nname = "x"\n')
        _save_config(client, auto_detect_tech_stack=False, tech_stack_override="Go 1.22 with chi")
        _save_config(client, auto_detect_tech_stack=True)
        assert self._tech_stack(workspace).startswith("Python with uv")

    def test_saving_only_a_branch_change_keeps_a_hand_set_tech_stack(self, client, workspace):
        """Auto-detect defaults to on; re-detecting on every save would replace
        a stack set with `cf init --tech-stack` when the user only changed the
        branch."""
        from codeframe.core.workspace import update_workspace_tech_stack

        (workspace.repo_path / "pyproject.toml").write_text('[tool.uv]\n')
        update_workspace_tech_stack(workspace.repo_path, "Hand-written stack description")
        _save_config(client, default_branch="develop")
        assert self._tech_stack(workspace) == "Hand-written stack description"

    def test_clearing_the_override_clears_the_tech_stack(self, client, workspace):
        """codex review: a cleared override left the old stack in front of the agent."""
        _save_config(client, auto_detect_tech_stack=False, tech_stack_override="Go 1.22 with chi")
        _save_config(client, auto_detect_tech_stack=False, tech_stack_override="")
        assert self._tech_stack(workspace) is None

    def test_auto_detect_finding_nothing_clears_a_stale_override(self, client, workspace):
        _save_config(client, auto_detect_tech_stack=False, tech_stack_override="Go 1.22 with chi")
        _save_config(client, auto_detect_tech_stack=True)  # empty repo: nothing detected
        assert self._tech_stack(workspace) is None


@pytest.mark.parametrize(
    "stored",
    [
        {"auto_detect_tech_stack": None},
        {"default_branch": 7},
        {"tech_stack_override": ["a"]},
        ["not", "an", "object"],
    ],
)
def test_a_wrongly_typed_config_file_falls_back_to_defaults(client, workspace, stored):
    """codex review: valid JSON with bad types made GET a 500."""
    import json

    from codeframe.core.workspace import WORKSPACE_CONFIG_FILENAME

    (workspace.state_dir / WORKSPACE_CONFIG_FILENAME).write_text(json.dumps(stored))
    resp = client.get("/api/v2/workspaces/config")
    assert resp.status_code == 200, resp.text
