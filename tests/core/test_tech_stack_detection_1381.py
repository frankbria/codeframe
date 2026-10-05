"""One tech-stack detector for every surface (#1381).

`cf init --detect` and the web UI (workspace init, the Settings auto-detect
toggle) each had their own detector, and they disagreed: the router's decided
"uv" with ``"uv" in content``, so any pyproject that mentioned uvicorn was
reported as "Python with uv". The agent reads this text, so the same repo got a
different description depending on where it was detected.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.tech_stack import detect_tech_stack
from codeframe.core.workspace import get_workspace

pytestmark = pytest.mark.v2

UVICORN_ONLY = """\
[project]
name = "svc"
dependencies = ["uvicorn>=0.30", "starlette"]
"""


def test_a_pyproject_that_only_mentions_uvicorn_is_not_uv(tmp_path):
    (tmp_path / "pyproject.toml").write_text(UVICORN_ONLY, encoding="utf-8")

    assert detect_tech_stack(tmp_path) == "Python with pip"


def test_uv_is_still_detected_from_its_lockfile(tmp_path):
    (tmp_path / "pyproject.toml").write_text(UVICORN_ONLY, encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    assert detect_tech_stack(tmp_path) == "Python with uv"


def test_the_cli_and_the_web_ui_agree_on_the_same_repo(tmp_path, monkeypatch):
    import subprocess

    from typer.testing import CliRunner

    from codeframe.cli.app import app as cli
    from codeframe.ui.routers import workspace_v2

    monkeypatch.delenv("DATABASE_PATH", raising=False)
    cli_repo, web_repo = tmp_path / "cli", tmp_path / "web"
    for repo in (cli_repo, web_repo):
        repo.mkdir()
        (repo / "pyproject.toml").write_text(UVICORN_ONLY + "\n[tool.ruff]\n", encoding="utf-8")
        (repo / ".python-version").write_text("3.12\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=cli_repo, check=True)

    assert CliRunner().invoke(cli, ["init", str(cli_repo), "--detect"]).exit_code == 0

    web = FastAPI()
    web.include_router(workspace_v2.router)
    with TestClient(web) as client:
        resp = client.post("/api/v2/workspaces", json={"repo_path": str(web_repo), "detect": True})
    assert resp.status_code in (200, 201), resp.text

    assert get_workspace(web_repo).tech_stack == get_workspace(cli_repo).tech_stack
    assert get_workspace(web_repo).tech_stack == "Python 3.12 with pip, ruff for linting"
