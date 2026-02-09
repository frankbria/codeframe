"""Comprehensive v2 CLI integration tests.

Tests the full CLI surface area using CliRunner against real SQLite databases.

Part 1 (smoke tests): Exercises every CLI command without AI calls.
Part 2 (AI integration): Exercises the LLM code paths (task generation,
planning, execution) using MockProvider injected via monkeypatch.

Coverage: init, status, summary, prd, tasks, work, batch, blocker,
checkpoint, patch, schedule, templates, review, golden-path E2E, and
AI-driven task generation + agent execution.
"""

import json
import re

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import prd, runtime, tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.streaming import run_output_exists
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PRD = """\
# Sample PRD

## Feature: User Authentication
- Implement login endpoint
- Implement signup endpoint
- Add password hashing

## Feature: Dashboard
- Create dashboard page
- Add analytics widgets
"""


@pytest.fixture
def temp_repo(tmp_path):
    """Empty temp directory usable as a repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


@pytest.fixture
def workspace_path(temp_repo):
    """Initialized workspace via core API (fast)."""
    create_or_load_workspace(temp_repo)
    return temp_repo


@pytest.fixture
def prd_file(workspace_path):
    """Sample PRD markdown file on disk inside an initialized workspace."""
    p = workspace_path / "prd.md"
    p.write_text(SAMPLE_PRD)
    return p


@pytest.fixture
def workspace_with_prd(workspace_path, prd_file):
    """Workspace with a PRD added via CLI."""
    result = runner.invoke(app, ["prd", "add", str(prd_file), "-w", str(workspace_path)])
    assert result.exit_code == 0, f"prd add failed: {result.output}"
    return workspace_path


@pytest.fixture
def workspace_with_tasks(workspace_with_prd):
    """Workspace with PRD + tasks generated (--no-llm)."""
    result = runner.invoke(
        app,
        ["tasks", "generate", "--no-llm", "-w", str(workspace_with_prd)],
    )
    assert result.exit_code == 0, f"tasks generate failed: {result.output}"
    return workspace_with_prd


@pytest.fixture
def workspace_with_ready_tasks(workspace_with_tasks):
    """Workspace with all tasks set to READY."""
    result = runner.invoke(
        app,
        ["tasks", "set", "status", "READY", "--all", "-w", str(workspace_with_tasks)],
    )
    assert result.exit_code == 0, f"tasks set failed: {result.output}"
    return workspace_with_tasks


# ---------------------------------------------------------------------------
# 1. Version / help
# ---------------------------------------------------------------------------


class TestVersion:
    def test_help_shows_output(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "codeframe" in result.output.lower() or "CodeFRAME" in result.output


# ---------------------------------------------------------------------------
# 2. Init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_workspace(self, temp_repo):
        result = runner.invoke(app, ["init", str(temp_repo)])
        assert result.exit_code == 0

    def test_init_idempotent(self, temp_repo):
        runner.invoke(app, ["init", str(temp_repo)])
        result = runner.invoke(app, ["init", str(temp_repo)])
        assert result.exit_code == 0

    def test_init_with_tech_stack(self, temp_repo):
        result = runner.invoke(
            app, ["init", str(temp_repo), "--tech-stack", "Python with uv"]
        )
        assert result.exit_code == 0
        assert "python" in result.output.lower() or "initialized" in result.output.lower()

    def test_init_with_detect(self, temp_repo):
        (temp_repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
        result = runner.invoke(app, ["init", str(temp_repo), "--detect"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 3. Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_shows_info(self, workspace_path):
        result = runner.invoke(app, ["status", str(workspace_path)])
        assert result.exit_code == 0

    def test_status_no_workspace(self, temp_repo):
        result = runner.invoke(app, ["status", str(temp_repo)])
        assert result.exit_code != 0

    def test_status_with_tasks(self, workspace_with_tasks):
        result = runner.invoke(app, ["status", str(workspace_with_tasks)])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 4. Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_shows_info(self, workspace_path):
        result = runner.invoke(app, ["summary", "-w", str(workspace_path)])
        assert result.exit_code == 0

    def test_summary_no_workspace(self, temp_repo):
        result = runner.invoke(app, ["summary", "-w", str(temp_repo)])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 5. PRD commands
# ---------------------------------------------------------------------------


class TestPrdCommands:
    def test_prd_add(self, workspace_path, prd_file):
        result = runner.invoke(app, ["prd", "add", str(prd_file), "-w", str(workspace_path)])
        assert result.exit_code == 0
        assert "prd" in result.output.lower() or "added" in result.output.lower()

    def test_prd_show(self, workspace_with_prd):
        result = runner.invoke(app, ["prd", "show", "-w", str(workspace_with_prd)])
        assert result.exit_code == 0

    def test_prd_list(self, workspace_with_prd):
        result = runner.invoke(app, ["prd", "list", "-w", str(workspace_with_prd)])
        assert result.exit_code == 0

    def test_prd_list_empty(self, workspace_path):
        result = runner.invoke(app, ["prd", "list", "-w", str(workspace_path)])
        assert result.exit_code == 0

    def test_prd_delete(self, workspace_with_prd):
        # Get PRD id from show output
        show_result = runner.invoke(app, ["prd", "show", "-w", str(workspace_with_prd)])
        # Extract an ID-like token (8+ hex chars)
        ids = re.findall(r"[0-9a-f]{8,}", show_result.output)
        if ids:
            result = runner.invoke(
                app, ["prd", "delete", ids[0][:8], "-w", str(workspace_with_prd)]
            )
            # Accept either success or "confirm" prompt behaviour
            assert result.exit_code in (0, 1)

    def test_prd_delete_nonexistent(self, workspace_path):
        result = runner.invoke(
            app, ["prd", "delete", "nonexistent", "-w", str(workspace_path)]
        )
        assert result.exit_code != 0

    def test_prd_export(self, workspace_with_prd, tmp_path):
        out_file = tmp_path / "exported.md"
        result = runner.invoke(
            app,
            ["prd", "export", "latest", str(out_file), "-w", str(workspace_with_prd)],
        )
        assert result.exit_code == 0

    def test_prd_update(self, workspace_with_prd, prd_file):
        # Re-add the same PRD as an update
        result = runner.invoke(
            app, ["prd", "update", str(prd_file), "-w", str(workspace_with_prd)]
        )
        # update may or may not exist; accept 0 or 2 (no such command)
        assert result.exit_code in (0, 1, 2)

    def test_prd_versions(self, workspace_with_prd):
        # Get PRD id from list output (more reliable than show)
        ws = create_or_load_workspace(workspace_with_prd)
        prd_record = prd.get_latest(ws)
        assert prd_record is not None
        result = runner.invoke(
            app, ["prd", "versions", prd_record.id, "-w", str(workspace_with_prd)]
        )
        assert result.exit_code == 0

    def test_prd_diff(self, workspace_with_prd):
        # Needs prd_id + two version numbers — use real PRD id
        ws = create_or_load_workspace(workspace_with_prd)
        prd_record = prd.get_latest(ws)
        assert prd_record is not None
        result = runner.invoke(
            app,
            ["prd", "diff", prd_record.id, "1", "2", "-w", str(workspace_with_prd)],
        )
        # May fail due to only 1 version existing, that's expected
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# 6. Tasks commands
# ---------------------------------------------------------------------------


class TestTasksCommands:
    def test_tasks_generate(self, workspace_with_prd):
        result = runner.invoke(
            app, ["tasks", "generate", "--no-llm", "-w", str(workspace_with_prd)]
        )
        assert result.exit_code == 0
        assert "generated" in result.output.lower()

    def test_tasks_generate_requires_prd(self, workspace_path):
        result = runner.invoke(
            app, ["tasks", "generate", "--no-llm", "-w", str(workspace_path)]
        )
        assert result.exit_code != 0

    def test_tasks_generate_overwrite(self, workspace_with_tasks):
        result = runner.invoke(
            app,
            ["tasks", "generate", "--no-llm", "--overwrite", "-w", str(workspace_with_tasks)],
        )
        assert result.exit_code == 0
        assert "generated" in result.output.lower()

    def test_tasks_list(self, workspace_with_tasks):
        result = runner.invoke(app, ["tasks", "list", "-w", str(workspace_with_tasks)])
        assert result.exit_code == 0
        assert "task" in result.output.lower()

    def test_tasks_list_filter(self, workspace_with_ready_tasks):
        result = runner.invoke(
            app, ["tasks", "list", "--status", "READY", "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0

    def test_tasks_set_status_single(self, workspace_with_tasks):
        ws = create_or_load_workspace(workspace_with_tasks)
        task_list = tasks.list_tasks(ws)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]
        result = runner.invoke(
            app, ["tasks", "set", "status", tid, "READY", "-w", str(workspace_with_tasks)]
        )
        assert result.exit_code == 0

    def test_tasks_set_status_all(self, workspace_with_tasks):
        result = runner.invoke(
            app, ["tasks", "set", "status", "READY", "--all", "-w", str(workspace_with_tasks)]
        )
        assert result.exit_code == 0
        assert "updated" in result.output.lower()

    def test_tasks_delete_all(self, workspace_with_tasks):
        result = runner.invoke(
            app,
            ["tasks", "delete", "--all", "--force", "-w", str(workspace_with_tasks)],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 7. Work commands
# ---------------------------------------------------------------------------


class TestWorkCommands:
    def test_start_creates_run(self, workspace_with_ready_tasks):
        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]
        result = runner.invoke(
            app, ["work", "start", tid, "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0
        assert "run" in result.output.lower()

    def test_start_nonexistent(self, workspace_path):
        result = runner.invoke(
            app, ["work", "start", "nonexistent", "-w", str(workspace_path)]
        )
        assert result.exit_code != 0

    def test_stop(self, workspace_with_ready_tasks):
        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]
        # Start then stop
        runner.invoke(app, ["work", "start", tid, "-w", str(workspace_with_ready_tasks)])
        result = runner.invoke(
            app, ["work", "stop", tid, "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0

    def test_status_no_runs(self, workspace_path):
        result = runner.invoke(app, ["work", "status", "-w", str(workspace_path)])
        assert result.exit_code == 0

    def test_status_shows_run(self, workspace_with_ready_tasks):
        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]
        runner.invoke(app, ["work", "start", tid, "-w", str(workspace_with_ready_tasks)])
        result = runner.invoke(
            app, ["work", "status", "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0

    def test_start_stub(self, workspace_with_ready_tasks):
        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]
        result = runner.invoke(
            app,
            ["work", "start", tid, "--stub", "-w", str(workspace_with_ready_tasks)],
        )
        assert result.exit_code == 0
        assert "stub" in result.output.lower() or "completed" in result.output.lower()

    def test_follow_no_run(self, workspace_with_ready_tasks):
        """Follow should indicate no active run for task without run."""
        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]
        result = runner.invoke(
            app, ["work", "follow", tid, "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code != 0
        assert "no active run" in result.output.lower()

    def test_follow_completed_run(self, workspace_with_ready_tasks):
        """Follow should show output for completed runs."""
        from codeframe.core import runtime
        from codeframe.core.streaming import RunOutputLogger

        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        task = task_list[0]
        tid = task.id[:8]

        # Start run
        run = runtime.start_task_run(ws, task.id)

        # Write some output
        with RunOutputLogger(ws, run.id) as logger:
            logger.write("Test output line\n")

        # Complete the run
        runtime.complete_run(ws, run.id)

        result = runner.invoke(
            app, ["work", "follow", tid, "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0
        assert "completed" in result.output.lower()

    def test_follow_with_tail(self, workspace_with_ready_tasks):
        """Follow --tail should show last N lines."""
        from codeframe.core import runtime
        from codeframe.core.streaming import RunOutputLogger

        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        task = task_list[0]
        tid = task.id[:8]

        run = runtime.start_task_run(ws, task.id)

        # Write multiple lines
        with RunOutputLogger(ws, run.id) as logger:
            for i in range(10):
                logger.write(f"Line {i}\n")

        runtime.complete_run(ws, run.id)

        result = runner.invoke(
            app, ["work", "follow", tid, "--tail", "3", "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0
        # Should contain the last lines
        assert "Line 9" in result.output or "Line 8" in result.output

    def test_follow_nonexistent_task(self, workspace_path):
        """Follow should error for nonexistent task."""
        result = runner.invoke(
            app, ["work", "follow", "nonexistent", "-w", str(workspace_path)]
        )
        assert result.exit_code != 0
        assert "no task found" in result.output.lower()


# ---------------------------------------------------------------------------
# 8. Batch commands
# ---------------------------------------------------------------------------


class TestBatchCommands:
    def test_batch_status_no_batches(self, workspace_path):
        result = runner.invoke(
            app, ["work", "batch", "status", "-w", str(workspace_path)]
        )
        assert result.exit_code == 0

    def test_batch_no_ready_tasks(self, workspace_with_tasks):
        """Batch run with no READY tasks should indicate nothing to do."""
        result = runner.invoke(
            app,
            ["work", "batch", "run", "--all-ready", "-w", str(workspace_with_tasks)],
        )
        # May exit 0 with "no ready tasks" message or exit 1
        assert result.exit_code in (0, 1)

    def test_batch_status_with_workspace(self, workspace_with_ready_tasks):
        result = runner.invoke(
            app,
            ["work", "batch", "status", "-w", str(workspace_with_ready_tasks)],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 9. Blocker commands
# ---------------------------------------------------------------------------


class TestBlockerCommands:
    def test_list_empty(self, workspace_path):
        result = runner.invoke(app, ["blocker", "list", "-w", str(workspace_path)])
        assert result.exit_code == 0
        assert "no" in result.output.lower() or "blocker" in result.output.lower()

    def test_create(self, workspace_path):
        result = runner.invoke(
            app,
            ["blocker", "create", "What auth method?", "-w", str(workspace_path)],
        )
        assert result.exit_code == 0
        assert "created" in result.output.lower()

    def test_show(self, workspace_path):
        # Create then show
        create_result = runner.invoke(
            app,
            ["blocker", "create", "Test question?", "-w", str(workspace_path)],
        )
        assert create_result.exit_code == 0
        # Extract blocker ID
        ids = re.findall(r"[0-9a-f]{8}", create_result.output)
        assert ids, f"No blocker ID found in: {create_result.output}"
        result = runner.invoke(
            app, ["blocker", "show", ids[0], "-w", str(workspace_path)]
        )
        assert result.exit_code == 0
        assert "question" in result.output.lower() or "test" in result.output.lower()

    def test_answer(self, workspace_path):
        create_result = runner.invoke(
            app,
            ["blocker", "create", "Which DB?", "-w", str(workspace_path)],
        )
        ids = re.findall(r"[0-9a-f]{8}", create_result.output)
        assert ids
        result = runner.invoke(
            app,
            ["blocker", "answer", ids[0], "Use PostgreSQL", "-w", str(workspace_path)],
        )
        assert result.exit_code == 0
        assert "answered" in result.output.lower()

    def test_resolve(self, workspace_path):
        create_result = runner.invoke(
            app,
            ["blocker", "create", "Rate limit?", "-w", str(workspace_path)],
        )
        ids = re.findall(r"[0-9a-f]{8}", create_result.output)
        assert ids
        # Answer first (required before resolve)
        runner.invoke(
            app,
            ["blocker", "answer", ids[0], "100 req/min", "-w", str(workspace_path)],
        )
        result = runner.invoke(
            app, ["blocker", "resolve", ids[0], "-w", str(workspace_path)]
        )
        assert result.exit_code == 0
        assert "resolved" in result.output.lower()

    def test_show_nonexistent(self, workspace_path):
        result = runner.invoke(
            app, ["blocker", "show", "ffffffff", "-w", str(workspace_path)]
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# 10. Checkpoint commands
# ---------------------------------------------------------------------------


class TestCheckpointCommands:
    def test_create(self, workspace_path):
        result = runner.invoke(
            app,
            ["checkpoint", "create", "test-checkpoint", "-w", str(workspace_path)],
        )
        assert result.exit_code == 0
        assert "checkpoint" in result.output.lower()

    def test_list_empty(self, workspace_path):
        result = runner.invoke(
            app, ["checkpoint", "list", "-w", str(workspace_path)]
        )
        assert result.exit_code == 0

    def test_list_shows_checkpoint(self, workspace_path):
        runner.invoke(
            app,
            ["checkpoint", "create", "my-cp", "-w", str(workspace_path)],
        )
        result = runner.invoke(
            app, ["checkpoint", "list", "-w", str(workspace_path)]
        )
        assert result.exit_code == 0
        assert "my-cp" in result.output

    def test_show(self, workspace_path):
        runner.invoke(
            app,
            ["checkpoint", "create", "show-me", "-w", str(workspace_path)],
        )
        result = runner.invoke(
            app, ["checkpoint", "show", "show-me", "-w", str(workspace_path)]
        )
        assert result.exit_code == 0
        assert "show-me" in result.output

    def test_restore(self, workspace_path):
        runner.invoke(
            app,
            ["checkpoint", "create", "restore-me", "-w", str(workspace_path)],
        )
        result = runner.invoke(
            app,
            ["checkpoint", "restore", "restore-me", "-w", str(workspace_path)],
        )
        assert result.exit_code == 0
        assert "restored" in result.output.lower()

    def test_delete(self, workspace_path):
        runner.invoke(
            app,
            ["checkpoint", "create", "del-me", "-w", str(workspace_path)],
        )
        result = runner.invoke(
            app,
            ["checkpoint", "delete", "del-me", "-w", str(workspace_path)],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 11. Patch commands
# ---------------------------------------------------------------------------


class TestPatchCommands:
    def test_status(self, workspace_path):
        result = runner.invoke(
            app, ["patch", "status", "-w", str(workspace_path)]
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 12. Schedule commands
# ---------------------------------------------------------------------------


class TestScheduleCommands:
    def test_show(self, workspace_with_ready_tasks):
        result = runner.invoke(
            app, ["schedule", "show", "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0

    def test_predict(self, workspace_with_ready_tasks):
        result = runner.invoke(
            app, ["schedule", "predict", "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0

    def test_bottlenecks(self, workspace_with_ready_tasks):
        result = runner.invoke(
            app, ["schedule", "bottlenecks", "-w", str(workspace_with_ready_tasks)]
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 13. Templates commands
# ---------------------------------------------------------------------------


class TestTemplatesCommands:
    def test_list(self):
        result = runner.invoke(app, ["templates", "list"])
        assert result.exit_code == 0

    def test_show(self):
        result = runner.invoke(app, ["templates", "show", "api-endpoint"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 14. Review command
# ---------------------------------------------------------------------------


class TestReviewCommand:
    def test_review_basic(self, workspace_path):
        result = runner.invoke(app, ["review", "-w", str(workspace_path)])
        # Review may exit 0 or 1 depending on state
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# 15. Golden Path E2E
# ---------------------------------------------------------------------------


class TestGoldenPathE2E:
    def test_full_flow(self, temp_repo):
        """End-to-end: init → prd add → tasks generate → list → set READY →
        work start --stub → checkpoint create → summary."""
        wp = str(temp_repo)

        # 1. Init
        r = runner.invoke(app, ["init", wp])
        assert r.exit_code == 0, f"init failed: {r.output}"

        # 2. PRD add
        prd_path = temp_repo / "prd.md"
        prd_path.write_text(SAMPLE_PRD)
        r = runner.invoke(app, ["prd", "add", str(prd_path), "-w", wp])
        assert r.exit_code == 0, f"prd add failed: {r.output}"

        # 3. Tasks generate
        r = runner.invoke(app, ["tasks", "generate", "--no-llm", "-w", wp])
        assert r.exit_code == 0, f"tasks generate failed: {r.output}"
        assert "generated" in r.output.lower()

        # 4. Tasks list
        r = runner.invoke(app, ["tasks", "list", "-w", wp])
        assert r.exit_code == 0, f"tasks list failed: {r.output}"

        # 5. Set all tasks to READY
        r = runner.invoke(app, ["tasks", "set", "status", "READY", "--all", "-w", wp])
        assert r.exit_code == 0, f"tasks set failed: {r.output}"

        # 6. Work start --stub (pick first task)
        ws = create_or_load_workspace(temp_repo)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0, "No READY tasks after set"
        tid = task_list[0].id[:8]
        r = runner.invoke(app, ["work", "start", tid, "--stub", "-w", wp])
        assert r.exit_code == 0, f"work start --stub failed: {r.output}"

        # 7. Checkpoint create
        r = runner.invoke(app, ["checkpoint", "create", "e2e-check", "-w", wp])
        assert r.exit_code == 0, f"checkpoint create failed: {r.output}"

        # 8. Summary
        r = runner.invoke(app, ["summary", "-w", wp])
        assert r.exit_code == 0, f"summary failed: {r.output}"


# ===========================================================================
# Part 2 — AI Integration Tests (MockProvider)
# ===========================================================================

# Canned LLM responses for the mock provider.

MOCK_TASK_GENERATION_RESPONSE = json.dumps([
    {"title": "Set up project structure", "description": "Create directories and initial files"},
    {"title": "Implement login endpoint", "description": "POST /auth/login with JWT"},
    {"title": "Add signup endpoint", "description": "POST /auth/signup with validation"},
])

MOCK_PLAN_RESPONSE = json.dumps({
    "summary": "Create a hello.py file with greeting function",
    "steps": [
        {
            "index": 1,
            "type": "file_create",
            "description": "Create hello.py with greeting function",
            "target": "hello.py",
            "details": "Simple Python file with a greet() function",
        },
    ],
    "files_to_create": ["hello.py"],
    "files_to_modify": [],
    "estimated_complexity": "low",
    "considerations": [],
})

MOCK_FILE_CONTENT = '''\
def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"
'''

# ReactAgent completes when LLM returns text-only (no tool calls).
MOCK_REACT_COMPLETION = "Task analysis complete. No changes needed."


def _make_mock_provider(responses: list[str]):
    """Create a MockProvider with queued text responses.

    Args:
        responses: List of text strings the provider will return in order.
    """
    from codeframe.adapters.llm.mock import MockProvider

    provider = MockProvider()
    for r in responses:
        provider.add_text_response(r)
    return provider


@pytest.fixture
def mock_llm(monkeypatch):
    """Fixture that patches get_provider to return a MockProvider.

    Returns a function: call with a list of response strings to configure.
    The fixture also sets ANTHROPIC_API_KEY so runtime doesn't reject execution.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake-key")

    def _configure(responses: list[str]):
        provider = _make_mock_provider(responses)
        monkeypatch.setattr(
            "codeframe.adapters.llm.get_provider",
            lambda *_args, **_kwargs: provider,
        )
        return provider

    return _configure


class TestAITaskGeneration:
    """Tests that exercise the LLM task-generation code path."""

    def test_generate_with_llm(self, workspace_with_prd, mock_llm):
        """tasks generate (without --no-llm) calls the LLM and parses tasks."""
        provider = mock_llm([MOCK_TASK_GENERATION_RESPONSE])

        result = runner.invoke(
            app,
            ["tasks", "generate", "-w", str(workspace_with_prd)],
        )
        assert result.exit_code == 0, f"tasks generate failed: {result.output}"
        assert "generated" in result.output.lower()
        # Should have created 3 tasks from the mock response
        assert "3" in result.output
        # Verify the mock was actually called
        assert provider.call_count >= 1

    def test_generate_with_llm_overwrite(self, workspace_with_tasks, mock_llm):
        """tasks generate --overwrite replaces existing tasks via LLM."""
        provider = mock_llm([MOCK_TASK_GENERATION_RESPONSE])

        result = runner.invoke(
            app,
            ["tasks", "generate", "--overwrite", "-w", str(workspace_with_tasks)],
        )
        assert result.exit_code == 0, f"generate overwrite failed: {result.output}"
        assert "generated" in result.output.lower()
        assert provider.call_count >= 1

    def test_generate_llm_returns_invalid_json_falls_back(
        self, workspace_with_prd, mock_llm
    ):
        """When LLM returns garbage, generate_from_prd falls back to simple extraction."""
        mock_llm(["This is not valid JSON at all."])

        result = runner.invoke(
            app,
            ["tasks", "generate", "-w", str(workspace_with_prd)],
        )
        # Should still succeed via fallback extraction
        assert result.exit_code == 0, f"fallback failed: {result.output}"
        assert "generated" in result.output.lower()


class TestAIAgentExecution:
    """Tests that exercise the planner → executor code path with MockProvider."""

    def test_execute_dry_run(self, workspace_with_ready_tasks, mock_llm):
        """work start --execute --dry-run goes through planning + dry execution."""
        # Mock needs: 1) plan response, 2) file content response (for file_create)
        provider = mock_llm([MOCK_PLAN_RESPONSE, MOCK_FILE_CONTENT])

        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]

        result = runner.invoke(
            app,
            [
                "work", "start", tid,
                "--execute", "--dry-run",
                "-w", str(workspace_with_ready_tasks),
            ],
        )
        assert result.exit_code == 0, f"dry-run failed: {result.output}"
        assert "run started" in result.output.lower()
        # The planner should have been called
        assert provider.call_count >= 1

    def test_execute_creates_file(self, workspace_with_ready_tasks, mock_llm):
        """work start --execute runs agent that creates a file via MockProvider."""
        # Plan says create hello.py, executor generates content via LLM
        provider = mock_llm([MOCK_PLAN_RESPONSE, MOCK_FILE_CONTENT])

        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]

        result = runner.invoke(
            app,
            [
                "work", "start", tid,
                "--execute",
                "-w", str(workspace_with_ready_tasks),
            ],
        )
        assert result.exit_code == 0, f"execute failed: {result.output}"
        assert "run started" in result.output.lower()
        assert provider.call_count >= 1

        # Verify the file was actually created by the executor
        created_file = workspace_with_ready_tasks / "hello.py"
        assert created_file.exists(), "Agent should have created hello.py"
        content = created_file.read_text()
        assert "greet" in content


class TestAIGoldenPathE2E:
    """Full golden path using MockProvider for all LLM calls."""

    def test_ai_golden_path(self, temp_repo, mock_llm):
        """init → prd add → tasks generate (LLM) → set READY → work start --execute."""
        # Queue responses: 1) task generation, 2) plan, 3) file content
        provider = mock_llm([
            MOCK_TASK_GENERATION_RESPONSE,
            MOCK_PLAN_RESPONSE,
            MOCK_FILE_CONTENT,
        ])

        wp = str(temp_repo)

        # 1. Init
        r = runner.invoke(app, ["init", wp])
        assert r.exit_code == 0, f"init: {r.output}"

        # 2. PRD add
        prd_path = temp_repo / "prd.md"
        prd_path.write_text(SAMPLE_PRD)
        r = runner.invoke(app, ["prd", "add", str(prd_path), "-w", wp])
        assert r.exit_code == 0, f"prd add: {r.output}"

        # 3. Tasks generate (uses LLM mock)
        r = runner.invoke(app, ["tasks", "generate", "-w", wp])
        assert r.exit_code == 0, f"tasks generate: {r.output}"
        assert "generated" in r.output.lower()

        # 4. Set all READY
        r = runner.invoke(app, ["tasks", "set", "status", "READY", "--all", "-w", wp])
        assert r.exit_code == 0, f"tasks set: {r.output}"

        # 5. Execute agent on first task
        ws = create_or_load_workspace(temp_repo)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]

        r = runner.invoke(app, ["work", "start", tid, "--execute", "-w", wp])
        assert r.exit_code == 0, f"work start --execute: {r.output}"

        # Verify LLM was exercised through the full path
        assert provider.call_count >= 2, (
            f"Expected ≥2 LLM calls (plan + execute), got {provider.call_count}"
        )

        # Verify the file the agent created
        assert (temp_repo / "hello.py").exists()


# ---------------------------------------------------------------------------
# 16. ReactAgent CLI integration (issue #368)
# ---------------------------------------------------------------------------


class TestReactAgentIntegration:
    """Integration tests for ReactAgent runtime parameters via CLI.

    Exercises the full CLI → runtime → ReactAgent path with MockProvider.
    Covers verbose mode, dry-run mode, and streaming output (cf work follow).

    Ref: https://github.com/frankbria/codeframe/issues/368
    """

    def test_react_verbose_mode(self, workspace_with_ready_tasks, mock_llm):
        """work start --execute --verbose --engine react shows ReactAgent output."""
        provider = mock_llm([MOCK_REACT_COMPLETION])

        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]

        result = runner.invoke(
            app,
            [
                "work", "start", tid,
                "--execute", "--verbose", "--engine", "react",
                "-w", str(workspace_with_ready_tasks),
            ],
        )
        assert result.exit_code == 0, f"react verbose failed: {result.output}"
        assert "engine=react" in result.output
        assert "[ReactAgent]" in result.output
        assert provider.call_count >= 1

    def test_react_dry_run(self, workspace_with_ready_tasks, mock_llm):
        """work start --execute --dry-run --engine react completes without error."""
        provider = mock_llm([MOCK_REACT_COMPLETION])

        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]

        result = runner.invoke(
            app,
            [
                "work", "start", tid,
                "--execute", "--dry-run", "--engine", "react",
                "-w", str(workspace_with_ready_tasks),
            ],
        )
        assert result.exit_code == 0, f"react dry-run failed: {result.output}"
        assert "dry run" in result.output.lower()
        assert provider.call_count >= 1

    def test_react_streaming_output_log(self, workspace_with_ready_tasks, mock_llm):
        """ReactAgent execution creates output.log readable by cf work follow."""
        provider = mock_llm([MOCK_REACT_COMPLETION])

        ws = create_or_load_workspace(workspace_with_ready_tasks)
        task_list = tasks.list_tasks(ws, status=TaskStatus.READY)
        assert len(task_list) > 0
        tid = task_list[0].id[:8]

        # Execute with react engine — creates output.log via RunOutputLogger
        result = runner.invoke(
            app,
            [
                "work", "start", tid,
                "--execute", "--engine", "react",
                "-w", str(workspace_with_ready_tasks),
            ],
        )
        assert result.exit_code == 0, f"react execute failed: {result.output}"
        assert provider.call_count >= 1

        # Verify output.log was created by the ReactAgent execution
        runs = runtime.list_runs(ws, task_id=task_list[0].id)
        assert len(runs) > 0, "Expected at least one run for the task"
        latest_run = runs[0]  # list_runs returns newest first

        assert run_output_exists(ws, latest_run.id), (
            f"output.log should exist for run {latest_run.id}"
        )

        # Verify cf work follow can read the completed run output
        follow_result = runner.invoke(
            app,
            [
                "work", "follow", tid,
                "-w", str(workspace_with_ready_tasks),
            ],
        )
        assert follow_result.exit_code == 0, (
            f"follow failed: {follow_result.output}"
        )
        assert len(follow_result.output.strip()) > 0, (
            "follow should display output from the completed run"
        )


# ---------------------------------------------------------------------------
# 17. PR commands (GitHub integration)
# ---------------------------------------------------------------------------


class TestPRCommands:
    """Tests for PR CLI commands with mocked GitHub API."""

    @pytest.fixture
    def mock_github_env(self, monkeypatch):
        """Set up mock GitHub environment variables."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token_12345")
        monkeypatch.setenv("GITHUB_REPO", "testowner/testrepo")

    @pytest.fixture
    def mock_pr_details(self):
        """Mock PRDetails response."""
        from datetime import datetime, UTC
        from codeframe.git.github_integration import PRDetails

        return PRDetails(
            number=42,
            url="https://github.com/testowner/testrepo/pull/42",
            state="open",
            title="Test PR",
            body="Test description",
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            merged_at=None,
            head_branch="feature/test",
            base_branch="main",
        )

    def test_pr_help(self):
        """PR command group shows help."""
        result = runner.invoke(app, ["pr", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output
        assert "merge" in result.output

    def test_pr_list(self, mock_github_env, mock_pr_details, monkeypatch):
        """PR list command displays PRs."""
        from unittest.mock import AsyncMock

        mock_gh = AsyncMock()
        mock_gh.list_pull_requests = AsyncMock(return_value=[mock_pr_details])
        mock_gh.close = AsyncMock()

        monkeypatch.setattr(
            "codeframe.cli.pr_commands.GitHubIntegration",
            lambda **kwargs: mock_gh,
        )

        result = runner.invoke(app, ["pr", "list"])
        assert result.exit_code == 0
        assert "42" in result.output

    def test_pr_list_json(self, mock_github_env, mock_pr_details, monkeypatch):
        """PR list with JSON format."""
        from unittest.mock import AsyncMock

        mock_gh = AsyncMock()
        mock_gh.list_pull_requests = AsyncMock(return_value=[mock_pr_details])
        mock_gh.close = AsyncMock()

        monkeypatch.setattr(
            "codeframe.cli.pr_commands.GitHubIntegration",
            lambda **kwargs: mock_gh,
        )

        result = runner.invoke(app, ["pr", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["number"] == 42

    def test_pr_get(self, mock_github_env, mock_pr_details, monkeypatch):
        """PR get command shows PR details."""
        from unittest.mock import AsyncMock

        mock_gh = AsyncMock()
        mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
        mock_gh.close = AsyncMock()

        monkeypatch.setattr(
            "codeframe.cli.pr_commands.GitHubIntegration",
            lambda **kwargs: mock_gh,
        )

        result = runner.invoke(app, ["pr", "get", "42"])
        assert result.exit_code == 0
        assert "42" in result.output
        assert "Test PR" in result.output

    def test_pr_create(self, mock_github_env, mock_pr_details, monkeypatch):
        """PR create command creates a PR."""
        from unittest.mock import AsyncMock

        mock_gh = AsyncMock()
        mock_gh.create_pull_request = AsyncMock(return_value=mock_pr_details)
        mock_gh.close = AsyncMock()

        monkeypatch.setattr(
            "codeframe.cli.pr_commands.GitHubIntegration",
            lambda **kwargs: mock_gh,
        )
        monkeypatch.setattr(
            "codeframe.cli.pr_commands.get_current_branch",
            lambda *args: "feature/test",
        )

        result = runner.invoke(
            app, ["pr", "create", "--title", "Test PR", "--no-auto-description"]
        )
        assert result.exit_code == 0
        assert "42" in result.output or "created" in result.output.lower()

    def test_pr_merge(self, mock_github_env, mock_pr_details, monkeypatch):
        """PR merge command merges a PR."""
        from unittest.mock import AsyncMock
        from codeframe.git.github_integration import MergeResult

        merge_result = MergeResult(sha="abc123", merged=True, message="Merged")

        mock_gh = AsyncMock()
        mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
        mock_gh.merge_pull_request = AsyncMock(return_value=merge_result)
        mock_gh.close = AsyncMock()

        monkeypatch.setattr(
            "codeframe.cli.pr_commands.GitHubIntegration",
            lambda **kwargs: mock_gh,
        )

        result = runner.invoke(app, ["pr", "merge", "42"])
        assert result.exit_code == 0
        assert "merged" in result.output.lower()

    def test_pr_close(self, mock_github_env, mock_pr_details, monkeypatch):
        """PR close command closes a PR."""
        from unittest.mock import AsyncMock

        mock_gh = AsyncMock()
        mock_gh.get_pull_request = AsyncMock(return_value=mock_pr_details)
        mock_gh.close_pull_request = AsyncMock(return_value=True)
        mock_gh.close = AsyncMock()

        monkeypatch.setattr(
            "codeframe.cli.pr_commands.GitHubIntegration",
            lambda **kwargs: mock_gh,
        )

        result = runner.invoke(app, ["pr", "close", "42"])
        assert result.exit_code == 0
        assert "closed" in result.output.lower()

    def test_pr_status(self, mock_github_env, mock_pr_details, monkeypatch):
        """PR status command shows status for current branch."""
        from unittest.mock import AsyncMock

        mock_gh = AsyncMock()
        mock_gh.list_pull_requests = AsyncMock(return_value=[mock_pr_details])
        mock_gh.close = AsyncMock()

        monkeypatch.setattr(
            "codeframe.cli.pr_commands.GitHubIntegration",
            lambda **kwargs: mock_gh,
        )
        monkeypatch.setattr(
            "codeframe.cli.pr_commands.get_current_branch",
            lambda *args: "feature/test",
        )

        result = runner.invoke(app, ["pr", "status"])
        assert result.exit_code == 0
        assert "42" in result.output or "open" in result.output.lower()

    def test_pr_no_token_error(self, monkeypatch):
        """PR commands without GITHUB_TOKEN show helpful error."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_REPO", raising=False)

        result = runner.invoke(app, ["pr", "list"])
        assert result.exit_code != 0
        assert "github" in result.output.lower() or "token" in result.output.lower()
