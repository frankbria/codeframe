"""Tests for task tree schema fields (parent_id, lineage, is_leaf, hierarchical_id).

Part of issue #420 - Richer Task Generation, Step 1: Schema + Model Extension.
"""

import pytest

from codeframe.core import tasks
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


class TestTaskTreeSchemaFields:
    """Test the new tree-structure fields on Task model."""

    def test_create_task_with_parent_id(self, workspace):
        """Create a task with parent_id, verify retrieval."""
        parent = tasks.create(workspace, title="Parent task")
        child = tasks.create(
            workspace,
            title="Child task",
            parent_id=parent.id,
        )

        assert child.parent_id == parent.id

        # Verify persistence
        retrieved = tasks.get(workspace, child.id)
        assert retrieved.parent_id == parent.id

    def test_create_leaf_task(self, workspace):
        """Default is_leaf should be True."""
        task = tasks.create(workspace, title="Leaf task")
        assert task.is_leaf is True

        retrieved = tasks.get(workspace, task.id)
        assert retrieved.is_leaf is True

    def test_create_composite_task(self, workspace):
        """Composite tasks have is_leaf=False."""
        task = tasks.create(
            workspace,
            title="Composite task",
            is_leaf=False,
        )
        assert task.is_leaf is False

        retrieved = tasks.get(workspace, task.id)
        assert retrieved.is_leaf is False

    def test_create_task_with_lineage(self, workspace):
        """Lineage stored and retrieved as list."""
        lineage = ["Epic: User Auth", "Story: Login Form"]
        task = tasks.create(
            workspace,
            title="Implement email field",
            lineage=lineage,
        )
        assert task.lineage == lineage

        retrieved = tasks.get(workspace, task.id)
        assert retrieved.lineage == lineage

    def test_create_task_with_hierarchical_id(self, workspace):
        """Verify '1.2.3' style hierarchical ID."""
        task = tasks.create(
            workspace,
            title="Sub-sub-task",
            hierarchical_id="1.2.3",
        )
        assert task.hierarchical_id == "1.2.3"

        retrieved = tasks.get(workspace, task.id)
        assert retrieved.hierarchical_id == "1.2.3"

    def test_backward_compat_no_new_fields(self, workspace):
        """Creating a task without new fields still works."""
        task = tasks.create(workspace, title="Simple task")

        assert task.parent_id is None
        assert task.lineage == []
        assert task.is_leaf is True
        assert task.hierarchical_id is None

        retrieved = tasks.get(workspace, task.id)
        assert retrieved.parent_id is None
        assert retrieved.lineage == []
        assert retrieved.is_leaf is True
        assert retrieved.hierarchical_id is None

    def test_list_tasks_includes_tree_fields(self, workspace):
        """list_tasks should return tree fields."""
        parent = tasks.create(
            workspace,
            title="Parent",
            is_leaf=False,
            hierarchical_id="1",
        )
        child = tasks.create(
            workspace,
            title="Child",
            parent_id=parent.id,
            lineage=["Parent"],
            hierarchical_id="1.1",
        )

        all_tasks = tasks.list_tasks(workspace)
        task_map = {t.title: t for t in all_tasks}

        assert task_map["Parent"].is_leaf is False
        assert task_map["Parent"].hierarchical_id == "1"
        assert task_map["Child"].parent_id == parent.id
        assert task_map["Child"].lineage == ["Parent"]
        assert task_map["Child"].hierarchical_id == "1.1"
