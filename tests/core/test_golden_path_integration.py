"""Integration tests for CodeFRAME v2 Golden Path (Phases 1-2).

These tests verify the complete workflow from workspace initialization
through task generation and status management.
"""

from pathlib import Path

import pytest

from codeframe.core import workspace, prd, tasks, events
from codeframe.core.state_machine import TaskStatus


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary directory to use as a repo."""
    repo = tmp_path / "test-project"
    repo.mkdir()
    return repo


@pytest.fixture
def sample_prd(temp_repo: Path) -> Path:
    """Create a sample PRD file."""
    prd_path = temp_repo / "requirements.md"
    prd_path.write_text("""# Todo App MVP

Build a simple todo application.

## Features

- Create new todo items
- Mark todos as complete
- Delete todo items
- List all todos

## Technical Requirements

- Use SQLite for storage
- Provide REST API
""")
    return prd_path


class TestGoldenPathPhase1:
    """Phase 1: Workspace initialization."""

    def test_init_creates_workspace(self, temp_repo: Path):
        """codeframe init creates a functional workspace."""
        ws = workspace.create_or_load_workspace(temp_repo)

        assert ws.id is not None
        assert ws.repo_path == temp_repo
        assert ws.state_dir.exists()
        assert ws.db_path.exists()

    def test_init_is_idempotent(self, temp_repo: Path):
        """Running init twice returns same workspace."""
        ws1 = workspace.create_or_load_workspace(temp_repo)
        ws2 = workspace.create_or_load_workspace(temp_repo)

        assert ws1.id == ws2.id

    def test_workspace_can_store_events(self, temp_repo: Path):
        """Workspace can record events."""
        ws = workspace.create_or_load_workspace(temp_repo)

        event = events.emit_for_workspace(
            ws,
            events.EventType.WORKSPACE_INIT,
            {"path": str(temp_repo)},
            print_event=False,
        )

        assert event.id is not None
        assert event.event_type == events.EventType.WORKSPACE_INIT

        # Can retrieve events
        recent = events.list_recent(ws, limit=10)
        assert len(recent) >= 1
        assert recent[0].event_type == events.EventType.WORKSPACE_INIT


class TestGoldenPathPhase2:
    """Phase 2: PRD and task management."""

    def test_prd_add_stores_document(self, temp_repo: Path, sample_prd: Path):
        """codeframe prd add stores PRD in workspace."""
        ws = workspace.create_or_load_workspace(temp_repo)

        content = prd.load_file(sample_prd)
        record = prd.store(ws, content, source_path=sample_prd)

        assert record.id is not None
        assert record.title == "Todo App MVP"
        assert "todo application" in record.content

    def test_prd_get_latest(self, temp_repo: Path, sample_prd: Path):
        """Can retrieve the latest PRD."""
        ws = workspace.create_or_load_workspace(temp_repo)
        content = prd.load_file(sample_prd)
        stored = prd.store(ws, content, source_path=sample_prd)

        latest = prd.get_latest(ws)

        assert latest is not None
        assert latest.id == stored.id
        assert latest.title == stored.title

    def test_tasks_generate_creates_tasks(self, temp_repo: Path, sample_prd: Path):
        """codeframe tasks generate creates tasks from PRD."""
        ws = workspace.create_or_load_workspace(temp_repo)
        content = prd.load_file(sample_prd)
        prd_record = prd.store(ws, content, source_path=sample_prd)

        # Use simple extraction (no LLM) for test reliability
        created = tasks.generate_from_prd(ws, prd_record, use_llm=False)

        assert len(created) > 0
        # All tasks should be in BACKLOG status
        for task in created:
            assert task.status == TaskStatus.BACKLOG
            assert task.prd_id == prd_record.id

    def test_tasks_list_returns_all(self, temp_repo: Path, sample_prd: Path):
        """codeframe tasks list shows all tasks."""
        ws = workspace.create_or_load_workspace(temp_repo)
        content = prd.load_file(sample_prd)
        prd_record = prd.store(ws, content, source_path=sample_prd)
        tasks.generate_from_prd(ws, prd_record, use_llm=False)

        all_tasks = tasks.list_tasks(ws)

        assert len(all_tasks) > 0

    def test_tasks_list_filters_by_status(self, temp_repo: Path, sample_prd: Path):
        """codeframe tasks list --status filters correctly."""
        ws = workspace.create_or_load_workspace(temp_repo)
        content = prd.load_file(sample_prd)
        prd_record = prd.store(ws, content, source_path=sample_prd)
        tasks.generate_from_prd(ws, prd_record, use_llm=False)

        # All should be BACKLOG initially
        backlog = tasks.list_tasks(ws, status=TaskStatus.BACKLOG)
        ready = tasks.list_tasks(ws, status=TaskStatus.READY)

        assert len(backlog) > 0
        assert len(ready) == 0

    def test_task_status_transition(self, temp_repo: Path, sample_prd: Path):
        """codeframe tasks set status changes task status."""
        ws = workspace.create_or_load_workspace(temp_repo)
        content = prd.load_file(sample_prd)
        prd_record = prd.store(ws, content, source_path=sample_prd)
        created = tasks.generate_from_prd(ws, prd_record, use_llm=False)

        task = created[0]
        assert task.status == TaskStatus.BACKLOG

        # Transition BACKLOG -> READY
        updated = tasks.update_status(ws, task.id, TaskStatus.READY)
        assert updated.status == TaskStatus.READY

        # Transition READY -> IN_PROGRESS
        updated = tasks.update_status(ws, task.id, TaskStatus.IN_PROGRESS)
        assert updated.status == TaskStatus.IN_PROGRESS

        # Transition IN_PROGRESS -> DONE
        updated = tasks.update_status(ws, task.id, TaskStatus.DONE)
        assert updated.status == TaskStatus.DONE

    def test_task_invalid_transition_fails(self, temp_repo: Path, sample_prd: Path):
        """Invalid status transitions are rejected."""
        from codeframe.core.state_machine import InvalidTransitionError

        ws = workspace.create_or_load_workspace(temp_repo)
        content = prd.load_file(sample_prd)
        prd_record = prd.store(ws, content, source_path=sample_prd)
        created = tasks.generate_from_prd(ws, prd_record, use_llm=False)

        task = created[0]
        assert task.status == TaskStatus.BACKLOG

        # BACKLOG -> DONE should fail (must go through READY, IN_PROGRESS)
        with pytest.raises(InvalidTransitionError):
            tasks.update_status(ws, task.id, TaskStatus.DONE)


class TestGoldenPathFullFlow:
    """Full workflow integration test."""

    def test_complete_phase_1_2_flow(self, temp_repo: Path, sample_prd: Path):
        """Complete Golden Path flow through Phases 1-2.

        Simulates:
        1. codeframe init
        2. codeframe prd add
        3. codeframe tasks generate
        4. codeframe tasks list
        5. codeframe tasks set status (multiple transitions)
        6. codeframe status (check counts)
        """
        # Phase 1: Initialize
        ws = workspace.create_or_load_workspace(temp_repo)
        events.emit_for_workspace(ws, events.EventType.WORKSPACE_INIT, print_event=False)

        # Phase 2: Add PRD
        content = prd.load_file(sample_prd)
        prd_record = prd.store(ws, content, source_path=sample_prd)
        events.emit_for_workspace(
            ws,
            events.EventType.PRD_ADDED,
            {"prd_id": prd_record.id},
            print_event=False,
        )

        # Generate tasks
        created = tasks.generate_from_prd(ws, prd_record, use_llm=False)
        events.emit_for_workspace(
            ws,
            events.EventType.TASKS_GENERATED,
            {"count": len(created)},
            print_event=False,
        )

        assert len(created) > 0

        # Move first task through workflow
        task1 = created[0]
        tasks.update_status(ws, task1.id, TaskStatus.READY)
        tasks.update_status(ws, task1.id, TaskStatus.IN_PROGRESS)
        tasks.update_status(ws, task1.id, TaskStatus.DONE)

        # Check counts
        counts = tasks.count_by_status(ws)
        assert counts.get("DONE", 0) == 1
        assert counts.get("BACKLOG", 0) == len(created) - 1

        # Verify events were recorded
        recent = events.list_recent(ws, limit=20)
        event_types = [e.event_type for e in recent]
        assert events.EventType.WORKSPACE_INIT in event_types
        assert events.EventType.PRD_ADDED in event_types
        assert events.EventType.TASKS_GENERATED in event_types
