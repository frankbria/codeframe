"""Tests for recursive task decomposition and tree operations."""

import json

import pytest

from codeframe.adapters.llm.mock import MockProvider
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.task_tree import (
    classify_task,
    decompose_task,
    display_task_tree,
    flatten_task_tree,
    generate_task_tree,
    propagate_status,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def provider():
    """Create a mock LLM provider."""
    return MockProvider()


class TestClassifyTask:
    """Test task classification (atomic vs composite)."""

    def test_classify_atomic(self, provider):
        """LLM returns 'atomic', verify result."""
        provider.add_text_response("atomic")
        result = classify_task(provider, "Add a login button", [])
        assert result == "atomic"

    def test_classify_composite(self, provider):
        """LLM returns 'composite', verify result."""
        provider.add_text_response("composite")
        result = classify_task(provider, "Build entire auth system", [])
        assert result == "composite"

    def test_classify_defaults_to_atomic(self, provider):
        """LLM returns garbage, verify 'atomic' default."""
        provider.add_text_response("I think this task is somewhere in between")
        result = classify_task(provider, "Some task", [])
        assert result == "atomic"

    def test_classify_uses_planning_purpose(self, provider):
        """Should use Purpose.PLANNING for classification."""
        from codeframe.adapters.llm.base import Purpose

        provider.add_text_response("atomic")
        classify_task(provider, "Test task", ["parent context"])

        assert provider.call_count == 1
        assert provider.last_call["purpose"] == Purpose.PLANNING

    def test_classify_includes_lineage_in_prompt(self, provider):
        """Should include lineage context in the user message."""
        provider.add_text_response("atomic")
        classify_task(provider, "Create schema", ["Build backend", "Set up database"])

        user_msg = provider.last_call["messages"][0]["content"]
        assert "Build backend" in user_msg
        assert "Set up database" in user_msg


class TestDecomposeTask:
    """Test task decomposition into subtasks."""

    def test_decompose_returns_subtasks(self, provider):
        """LLM returns JSON array, verify parsed result."""
        subtasks = [
            {"title": "Create user table", "description": "Define user schema"},
            {"title": "Add auth endpoints", "description": "Login and register"},
            {"title": "Write tests", "description": "Unit tests for auth"},
        ]
        provider.add_text_response(json.dumps(subtasks))

        result = decompose_task(provider, "Build auth system", [])

        assert len(result) == 3
        assert result[0]["title"] == "Create user table"
        assert result[1]["description"] == "Login and register"

    def test_decompose_clamps_to_7(self, provider):
        """LLM returns 10 items, verify truncated to 7."""
        subtasks = [{"title": f"Task {i}", "description": f"Desc {i}"} for i in range(10)]
        provider.add_text_response(json.dumps(subtasks))

        result = decompose_task(provider, "Huge task", [])

        assert len(result) == 7

    def test_decompose_handles_fewer_than_2(self, provider):
        """LLM returns 1 item, verify padded to at least 2."""
        subtasks = [{"title": "Only one", "description": "Single task"}]
        provider.add_text_response(json.dumps(subtasks))

        result = decompose_task(provider, "Small task", [])

        assert len(result) >= 2

    def test_decompose_handles_markdown_wrapped_json(self, provider):
        """LLM wraps JSON in markdown code block."""
        subtasks = [
            {"title": "Sub A", "description": "A"},
            {"title": "Sub B", "description": "B"},
        ]
        response = f"```json\n{json.dumps(subtasks)}\n```"
        provider.add_text_response(response)

        result = decompose_task(provider, "Task with markdown", [])

        assert len(result) == 2
        assert result[0]["title"] == "Sub A"

    def test_decompose_returns_empty_on_invalid_json(self, provider):
        """LLM returns garbage, should return fallback subtasks."""
        provider.add_text_response("This is not JSON at all")

        result = decompose_task(provider, "Bad response task", [])

        # Should return at least 2 fallback items
        assert len(result) >= 2


class TestGenerateTaskTree:
    """Test recursive task tree generation."""

    def test_generate_task_tree_leaf(self, provider):
        """Atomic task produces leaf node."""
        provider.add_text_response("atomic")

        result = generate_task_tree(provider, "Simple task")

        assert result["is_leaf"] is True
        assert result["children"] == []
        assert result["description"] == "Simple task"

    def test_generate_task_tree_composite(self, provider):
        """Composite task produces children."""
        # First call: classify as composite
        provider.add_text_response("composite")
        # Second call: decompose into subtasks
        subtasks = [
            {"title": "Child A", "description": "Do A"},
            {"title": "Child B", "description": "Do B"},
        ]
        provider.add_text_response(json.dumps(subtasks))
        # Third + fourth calls: classify children as atomic
        provider.add_text_response("atomic")
        provider.add_text_response("atomic")

        result = generate_task_tree(provider, "Parent task")

        assert result["is_leaf"] is False
        assert len(result["children"]) == 2
        assert result["children"][0]["description"] == "Do A"
        assert result["children"][0]["is_leaf"] is True
        assert result["children"][1]["description"] == "Do B"

    def test_generate_task_tree_max_depth(self, provider):
        """Respects max_depth — forces leaf at depth limit."""
        # Even though we don't set up classify responses,
        # max_depth=0 should immediately return leaf
        result = generate_task_tree(provider, "Deep task", depth=0, max_depth=0)

        assert result["is_leaf"] is True
        assert result["children"] == []
        # No LLM calls should have been made
        assert provider.call_count == 0

    def test_generate_task_tree_lineage_propagates(self, provider):
        """Lineage accumulates through recursion."""
        provider.add_text_response("composite")
        subtasks = [{"title": "Child", "description": "Child task"}]
        # Will be padded to 2
        provider.add_text_response(json.dumps(subtasks))
        provider.add_text_response("atomic")
        provider.add_text_response("atomic")

        result = generate_task_tree(provider, "Root", lineage=["Grandparent"])

        assert result["lineage"] == ["Grandparent"]
        for child in result["children"]:
            assert "Root" in child["lineage"]
            assert "Grandparent" in child["lineage"]


class TestFlattenTaskTree:
    """Test flattening tree into workspace tasks."""

    def test_flatten_creates_tasks(self, workspace):
        """Flatten tree into workspace, verify tasks exist."""
        tree = {
            "title": "Root task",
            "description": "Root description",
            "is_leaf": False,
            "children": [
                {
                    "title": "Child A",
                    "description": "Child A desc",
                    "is_leaf": True,
                    "children": [],
                    "lineage": ["Root description"],
                },
                {
                    "title": "Child B",
                    "description": "Child B desc",
                    "is_leaf": True,
                    "children": [],
                    "lineage": ["Root description"],
                },
            ],
            "lineage": [],
        }

        result = flatten_task_tree(tree, workspace)

        assert len(result) == 3  # root + 2 children
        all_tasks = tasks.list_tasks(workspace)
        assert len(all_tasks) == 3

    def test_flatten_sets_hierarchical_ids(self, workspace):
        """Verify hierarchical IDs like '1', '1.1', '1.2'."""
        tree = {
            "title": "Root",
            "description": "Root desc",
            "is_leaf": False,
            "children": [
                {
                    "title": "Child 1",
                    "description": "C1",
                    "is_leaf": True,
                    "children": [],
                    "lineage": ["Root desc"],
                },
                {
                    "title": "Child 2",
                    "description": "C2",
                    "is_leaf": True,
                    "children": [],
                    "lineage": ["Root desc"],
                },
            ],
            "lineage": [],
        }

        result = flatten_task_tree(tree, workspace)

        h_ids = [t.hierarchical_id for t in result]
        assert "1" in h_ids
        assert "1.1" in h_ids
        assert "1.2" in h_ids

    def test_flatten_sets_parent_ids(self, workspace):
        """Children should reference parent task ID."""
        tree = {
            "title": "Parent",
            "description": "Parent desc",
            "is_leaf": False,
            "children": [
                {
                    "title": "Child",
                    "description": "Child desc",
                    "is_leaf": True,
                    "children": [],
                    "lineage": ["Parent desc"],
                },
            ],
            "lineage": [],
        }

        result = flatten_task_tree(tree, workspace)

        parent = [t for t in result if t.title == "Parent"][0]
        child = [t for t in result if t.title == "Child"][0]
        assert child.parent_id == parent.id
        assert parent.parent_id is None

    def test_flatten_nested_hierarchical_ids(self, workspace):
        """Verify deeply nested IDs like '1.1.1'."""
        tree = {
            "title": "Root",
            "description": "Root",
            "is_leaf": False,
            "children": [
                {
                    "title": "Mid",
                    "description": "Mid",
                    "is_leaf": False,
                    "children": [
                        {
                            "title": "Leaf",
                            "description": "Leaf",
                            "is_leaf": True,
                            "children": [],
                            "lineage": ["Root", "Mid"],
                        },
                    ],
                    "lineage": ["Root"],
                },
            ],
            "lineage": [],
        }

        result = flatten_task_tree(tree, workspace)

        h_ids = [t.hierarchical_id for t in result]
        assert "1" in h_ids
        assert "1.1" in h_ids
        assert "1.1.1" in h_ids


class TestDisplayTaskTree:
    """Test ASCII tree display."""

    def test_display_task_tree_format(self, workspace):
        """Verify ASCII output contains expected elements."""
        # Create a parent and two children manually
        parent = tasks.create(
            workspace,
            title="Set up backend",
            description="Backend setup",
            status=TaskStatus.IN_PROGRESS,
        )
        # Manually update to add tree fields
        _update_tree_fields(workspace, parent.id, hierarchical_id="1", is_leaf=False)

        child1 = tasks.create(
            workspace,
            title="Create schema",
            description="DB schema",
            status=TaskStatus.DONE,
        )
        _update_tree_fields(
            workspace, child1.id, parent_id=parent.id, hierarchical_id="1.1", is_leaf=True
        )

        child2 = tasks.create(
            workspace,
            title="REST endpoints",
            description="API endpoints",
            status=TaskStatus.BACKLOG,
        )
        _update_tree_fields(
            workspace, child2.id, parent_id=parent.id, hierarchical_id="1.2", is_leaf=True
        )

        output = display_task_tree(workspace)

        assert "Set up backend" in output
        assert "Create schema" in output
        assert "REST endpoints" in output
        # Status icons
        assert "\u2713" in output  # DONE checkmark
        assert "\u25cf" in output  # IN_PROGRESS bullet
        assert "\u25cb" in output  # BACKLOG circle

    def test_display_empty_workspace(self, workspace):
        """Empty workspace should return informative message."""
        output = display_task_tree(workspace)
        assert "No tasks" in output or output.strip() == ""


class TestPropagateStatus:
    """Test status propagation from children to parents."""

    def test_propagate_status_all_done(self, workspace):
        """All children done -> parent done."""
        parent = tasks.create(
            workspace, title="Parent", status=TaskStatus.IN_PROGRESS
        )
        _update_tree_fields(workspace, parent.id, is_leaf=False)

        child1 = tasks.create(workspace, title="C1", status=TaskStatus.DONE)
        _update_tree_fields(workspace, child1.id, parent_id=parent.id, is_leaf=True)

        child2 = tasks.create(workspace, title="C2", status=TaskStatus.DONE)
        _update_tree_fields(workspace, child2.id, parent_id=parent.id, is_leaf=True)

        propagate_status(workspace, child1.id)

        updated_parent = tasks.get(workspace, parent.id)
        assert updated_parent.status == TaskStatus.DONE

    def test_propagate_status_any_failed(self, workspace):
        """Child failed -> parent failed."""
        parent = tasks.create(
            workspace, title="Parent", status=TaskStatus.IN_PROGRESS
        )
        _update_tree_fields(workspace, parent.id, is_leaf=False)

        child1 = tasks.create(workspace, title="C1", status=TaskStatus.DONE)
        _update_tree_fields(workspace, child1.id, parent_id=parent.id, is_leaf=True)

        child2 = tasks.create(workspace, title="C2", status=TaskStatus.IN_PROGRESS)
        _update_tree_fields(workspace, child2.id, parent_id=parent.id, is_leaf=True)
        # Transition to FAILED
        tasks.update_status(workspace, child2.id, TaskStatus.FAILED)

        propagate_status(workspace, child2.id)

        updated_parent = tasks.get(workspace, parent.id)
        assert updated_parent.status == TaskStatus.FAILED

    def test_propagate_status_recursive(self, workspace):
        """Propagates up multiple levels."""
        grandparent = tasks.create(
            workspace, title="GP", status=TaskStatus.IN_PROGRESS
        )
        _update_tree_fields(workspace, grandparent.id, is_leaf=False)

        parent = tasks.create(
            workspace, title="P", status=TaskStatus.IN_PROGRESS
        )
        _update_tree_fields(
            workspace, parent.id, parent_id=grandparent.id, is_leaf=False
        )

        child = tasks.create(workspace, title="C", status=TaskStatus.DONE)
        _update_tree_fields(workspace, child.id, parent_id=parent.id, is_leaf=True)

        propagate_status(workspace, child.id)

        updated_parent = tasks.get(workspace, parent.id)
        assert updated_parent.status == TaskStatus.DONE

        updated_gp = tasks.get(workspace, grandparent.id)
        assert updated_gp.status == TaskStatus.DONE

    def test_propagate_no_parent(self, workspace):
        """Root task with no parent should be a no-op."""
        root = tasks.create(workspace, title="Root", status=TaskStatus.DONE)
        # Should not raise
        propagate_status(workspace, root.id)

    def test_propagate_in_progress_child(self, workspace):
        """Any child IN_PROGRESS -> parent IN_PROGRESS."""
        parent = tasks.create(
            workspace, title="Parent", status=TaskStatus.IN_PROGRESS
        )
        _update_tree_fields(workspace, parent.id, is_leaf=False)

        child1 = tasks.create(workspace, title="C1", status=TaskStatus.DONE)
        _update_tree_fields(workspace, child1.id, parent_id=parent.id, is_leaf=True)

        child2 = tasks.create(workspace, title="C2", status=TaskStatus.IN_PROGRESS)
        _update_tree_fields(workspace, child2.id, parent_id=parent.id, is_leaf=True)

        propagate_status(workspace, child2.id)

        updated_parent = tasks.get(workspace, parent.id)
        assert updated_parent.status == TaskStatus.IN_PROGRESS


def _update_tree_fields(
    workspace,
    task_id: str,
    parent_id: str = None,
    hierarchical_id: str = None,
    is_leaf: bool = None,
    lineage: list = None,
):
    """Helper to update tree-specific fields directly in DB."""
    from codeframe.core.workspace import get_db_connection

    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        updates = []
        params = []
        if parent_id is not None:
            updates.append("parent_id = ?")
            params.append(parent_id)
        if hierarchical_id is not None:
            updates.append("hierarchical_id = ?")
            params.append(hierarchical_id)
        if is_leaf is not None:
            updates.append("is_leaf = ?")
            params.append(1 if is_leaf else 0)
        if lineage is not None:
            updates.append("lineage = ?")
            params.append(json.dumps(lineage))
        if updates:
            params.extend([workspace.id, task_id])
            cursor.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE workspace_id = ? AND id = ?",
                params,
            )
            conn.commit()
    finally:
        conn.close()
