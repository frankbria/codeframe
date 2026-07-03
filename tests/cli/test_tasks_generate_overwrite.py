"""`cf tasks generate --overwrite` must not lose tasks on a failed gen (#725/P0.14).

Previously --overwrite called delete_all() (committed) and only then ran LLM
generation. A transient LLM failure irreversibly wiped the task list. The fix
generates first and deletes the originals only on success.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import prd, tasks
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def ws_with_prd_and_tasks(tmp_path: Path):
    ws = create_or_load_workspace(tmp_path)
    prd.store(ws, content="# Demo PRD\n\nBuild a thing.", title="Demo")
    tasks.create(ws, title="Existing 1", description="keep me")
    tasks.create(ws, title="Existing 2", description="keep me too")
    return ws, tmp_path


def test_overwrite_preserves_tasks_when_generation_fails(ws_with_prd_and_tasks):
    ws, path = ws_with_prd_and_tasks
    before = {t.id for t in tasks.list_tasks(ws)}
    assert len(before) == 2

    # Simulate a transient generation failure (rate limit / timeout / bad response).
    with patch.object(
        tasks, "generate_from_prd", side_effect=RuntimeError("LLM timeout")
    ):
        result = runner.invoke(
            app,
            ["tasks", "generate", "--overwrite", "--no-llm", "-w", str(path)],
        )

    assert result.exit_code != 0  # the failure surfaces
    # ...and the pre-existing tasks are intact (not wiped).
    after = {t.id for t in tasks.list_tasks(ws)}
    assert after == before


def test_overwrite_preserves_tasks_when_recursive_generation_fails(ws_with_prd_and_tasks):
    """The --recursive path (generate_task_tree) shares the same rollback."""
    import codeframe.core.task_tree as task_tree
    import codeframe.cli.validators as validators

    ws, path = ws_with_prd_and_tasks
    before = {t.id for t in tasks.list_tasks(ws)}

    with patch.object(validators, "require_anthropic_api_key", lambda: None), patch.object(
        task_tree, "generate_task_tree", side_effect=RuntimeError("LLM timeout")
    ):
        result = runner.invoke(
            app,
            ["tasks", "generate", "--overwrite", "--recursive", "-w", str(path)],
        )

    assert result.exit_code != 0
    assert {t.id for t in tasks.list_tasks(ws)} == before


def test_overwrite_replaces_tasks_on_success(ws_with_prd_and_tasks):
    ws, path = ws_with_prd_and_tasks
    before = {t.id for t in tasks.list_tasks(ws)}

    def _fake_generate(workspace, prd_record, use_llm=True):
        return [tasks.create(workspace, title="Fresh task", description="new")]

    with patch.object(tasks, "generate_from_prd", side_effect=_fake_generate):
        result = runner.invoke(
            app,
            ["tasks", "generate", "--overwrite", "--no-llm", "-w", str(path)],
        )

    assert result.exit_code == 0, result.output
    titles = {t.title for t in tasks.list_tasks(ws)}
    # Originals cleared, only the freshly generated task remains.
    assert titles == {"Fresh task"}
    assert not (before & {t.id for t in tasks.list_tasks(ws)})
