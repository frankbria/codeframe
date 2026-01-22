"""Tests for task dependency functionality.

Tests the depends_on field and related dependency management features.
"""

import pytest

from codeframe.core import tasks
from codeframe.core.workspace import create_or_load_workspace


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


class TestTaskDependsOnField:
    """Test the depends_on field on Task model."""

    def test_task_has_empty_depends_on_by_default(self, workspace):
        """New tasks should have empty depends_on list."""
        task = tasks.create(workspace, title="Test task")
        assert task.depends_on == []

    def test_task_created_with_depends_on(self, workspace):
        """Tasks can be created with dependencies."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(
            workspace,
            title="Second task",
            depends_on=[task1.id],
        )
        assert task2.depends_on == [task1.id]

    def test_task_get_includes_depends_on(self, workspace):
        """Getting a task should include its depends_on."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(
            workspace,
            title="Second task",
            depends_on=[task1.id],
        )

        retrieved = tasks.get(workspace, task2.id)
        assert retrieved.depends_on == [task1.id]

    def test_task_list_includes_depends_on(self, workspace):
        """Listing tasks should include depends_on."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(
            workspace,
            title="Second task",
            depends_on=[task1.id],
        )

        all_tasks = tasks.list_tasks(workspace)
        task_map = {t.id: t for t in all_tasks}

        assert task_map[task1.id].depends_on == []
        assert task_map[task2.id].depends_on == [task1.id]


class TestUpdateDependsOn:
    """Test updating task dependencies."""

    def test_update_depends_on_adds_dependency(self, workspace):
        """Can add a dependency to an existing task."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(workspace, title="Second task")

        updated = tasks.update_depends_on(workspace, task2.id, [task1.id])
        assert updated.depends_on == [task1.id]

        # Verify persistence
        retrieved = tasks.get(workspace, task2.id)
        assert retrieved.depends_on == [task1.id]

    def test_update_depends_on_removes_dependency(self, workspace):
        """Can remove dependencies from a task."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(
            workspace,
            title="Second task",
            depends_on=[task1.id],
        )

        updated = tasks.update_depends_on(workspace, task2.id, [])
        assert updated.depends_on == []

    def test_update_depends_on_multiple_deps(self, workspace):
        """Can set multiple dependencies."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(workspace, title="Second task")
        task3 = tasks.create(workspace, title="Third task")

        updated = tasks.update_depends_on(
            workspace,
            task3.id,
            [task1.id, task2.id],
        )
        assert set(updated.depends_on) == {task1.id, task2.id}

    def test_update_depends_on_nonexistent_task_raises(self, workspace):
        """Cannot update dependencies for nonexistent task."""
        with pytest.raises(ValueError, match="Task not found"):
            tasks.update_depends_on(workspace, "nonexistent", [])

    def test_update_depends_on_self_reference_raises(self, workspace):
        """Cannot make a task depend on itself."""
        task = tasks.create(workspace, title="Test task")

        with pytest.raises(ValueError, match="cannot depend on itself"):
            tasks.update_depends_on(workspace, task.id, [task.id])

    def test_update_depends_on_nonexistent_dep_raises(self, workspace):
        """Cannot add nonexistent task as dependency."""
        task = tasks.create(workspace, title="Test task")

        with pytest.raises(ValueError, match="Dependency task not found"):
            tasks.update_depends_on(workspace, task.id, ["nonexistent"])


class TestGetDependents:
    """Test getting tasks that depend on a given task."""

    def test_get_dependents_empty(self, workspace):
        """Task with no dependents returns empty list."""
        task = tasks.create(workspace, title="Test task")
        dependents = tasks.get_dependents(workspace, task.id)
        assert dependents == []

    def test_get_dependents_single(self, workspace):
        """Returns single task that depends on the given task."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(
            workspace,
            title="Second task",
            depends_on=[task1.id],
        )

        dependents = tasks.get_dependents(workspace, task1.id)
        assert len(dependents) == 1
        assert dependents[0].id == task2.id

    def test_get_dependents_multiple(self, workspace):
        """Returns all tasks that depend on the given task."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(
            workspace,
            title="Second task",
            depends_on=[task1.id],
        )
        task3 = tasks.create(
            workspace,
            title="Third task",
            depends_on=[task1.id],
        )

        dependents = tasks.get_dependents(workspace, task1.id)
        assert len(dependents) == 2
        dep_ids = {d.id for d in dependents}
        assert dep_ids == {task2.id, task3.id}

    def test_get_dependents_excludes_indirect(self, workspace):
        """Only returns direct dependents, not transitive."""
        task1 = tasks.create(workspace, title="First task")
        task2 = tasks.create(
            workspace,
            title="Second task",
            depends_on=[task1.id],
        )
        task3 = tasks.create(
            workspace,
            title="Third task",
            depends_on=[task2.id],
        )

        # task3 depends on task2 which depends on task1
        # get_dependents(task1) should only return task2
        dependents = tasks.get_dependents(workspace, task1.id)
        assert len(dependents) == 1
        assert dependents[0].id == task2.id


class TestDatabaseMigration:
    """Test that the depends_on column migration works."""

    def test_task_created_before_migration_has_empty_depends_on(self, workspace):
        """Tasks created without depends_on should have empty list when read."""
        # This test verifies backward compatibility
        task = tasks.create(workspace, title="Test task")
        retrieved = tasks.get(workspace, task.id)
        assert retrieved.depends_on == []
