"""Tests for database TODOs: issue dependencies and audit logging (cf-207).

Following TDD: These tests are written FIRST, before implementation.
Tests the P0 items from the database TODOs implementation plan.

Tests cover:
- Issue depends_on field parsing and storage
- Audit logging for PROJECT_UPDATED event
- Audit logging for PROJECT_DELETED event
"""

import json
import pytest
from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus, Issue


@pytest.fixture
def db(temp_db_path):
    """Create and initialize database with proper async cleanup."""
    database = Database(temp_db_path)
    database.initialize()

    yield database

    # Close async connection if it was opened (prevents hanging)
    if database._async_conn:
        import asyncio

        try:
            asyncio.get_event_loop().run_until_complete(database.close_async())
        except RuntimeError:
            asyncio.run(database.close_async())
    database.close()


@pytest.mark.unit
class TestIssueDependsOnColumn:
    """Test that issues table has depends_on column for dependency tracking."""

    def test_issues_table_has_depends_on_column(self, db):
        """Test that issues table has depends_on column after migration."""
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(issues)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert "depends_on" in columns, "issues table should have depends_on column"
        assert columns["depends_on"] == "TEXT", "depends_on column should be TEXT type"


@pytest.mark.unit
class TestIssueDependencyCRUD:
    """Test Issue dependency CRUD operations."""

    def test_create_issue_with_depends_on(self, db):
        """Test creating an issue with dependencies."""
        project_id = db.create_project("test-project", "Test Project")

        # Create first issue (no dependencies)
        issue1_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1",
                title="Issue 1",
                description="First issue",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # Create second issue that depends on first
        issue2 = Issue(
            project_id=project_id,
            issue_number="2",
            title="Issue 2",
            description="Depends on Issue 1",
            status=TaskStatus.PENDING,
            priority=1,
        )
        # Pass depends_on as dict field
        issue2_dict = {
            "project_id": project_id,
            "issue_number": "2",
            "title": "Issue 2",
            "description": "Depends on Issue 1",
            "status": "pending",
            "priority": 1,
            "depends_on": json.dumps([str(issue1_id)]),  # JSON string format
        }
        issue2_id = db.create_issue(issue2_dict)

        assert issue2_id is not None
        assert issue2_id > 0

    def test_get_issues_with_tasks_parses_depends_on(self, db):
        """Test that get_issues_with_tasks correctly parses depends_on field."""
        project_id = db.create_project("test-project", "Test Project")

        # Create issues with dependencies
        issue1_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1",
                title="Issue 1",
                description="First issue",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # Create issue 2 with dependency on issue 1 via raw SQL
        cursor = db.conn.cursor()
        cursor.execute(
            """INSERT INTO issues (project_id, issue_number, title, description, status, priority, depends_on)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, "2", "Issue 2", "Depends on Issue 1", "pending", 1, json.dumps([str(issue1_id)])),
        )
        db.conn.commit()

        # Get issues with tasks
        result = db.get_issues_with_tasks(project_id, include_tasks=False)

        assert len(result["issues"]) == 2

        # Find issue 2 and check depends_on
        issue2 = next(i for i in result["issues"] if i["issue_number"] == "2")
        assert issue2["depends_on"] == [str(issue1_id)], "depends_on should be parsed from JSON"

    def test_get_issues_with_tasks_handles_null_depends_on(self, db):
        """Test that get_issues_with_tasks handles NULL depends_on gracefully."""
        project_id = db.create_project("test-project", "Test Project")

        # Create issue without dependencies
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1",
                title="Issue 1",
                description="No dependencies",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # Get issues with tasks
        result = db.get_issues_with_tasks(project_id, include_tasks=False)

        assert len(result["issues"]) == 1
        assert result["issues"][0]["depends_on"] == [], "NULL depends_on should return empty list"

    def test_get_issues_with_tasks_handles_invalid_json(self, db):
        """Test that get_issues_with_tasks handles invalid JSON in depends_on."""
        project_id = db.create_project("test-project", "Test Project")

        # Create issue with invalid JSON in depends_on via raw SQL
        cursor = db.conn.cursor()
        cursor.execute(
            """INSERT INTO issues (project_id, issue_number, title, description, status, priority, depends_on)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, "1", "Issue 1", "Invalid JSON", "pending", 1, "not valid json"),
        )
        db.conn.commit()

        # Get issues with tasks - should not raise, should return empty list
        result = db.get_issues_with_tasks(project_id, include_tasks=False)

        assert len(result["issues"]) == 1
        assert result["issues"][0]["depends_on"] == [], "Invalid JSON should return empty list"

    def test_get_issues_with_tasks_handles_non_list_json(self, db):
        """Test that get_issues_with_tasks handles non-list JSON in depends_on."""
        project_id = db.create_project("test-project", "Test Project")

        # Create issue with non-list JSON via raw SQL
        cursor = db.conn.cursor()
        cursor.execute(
            """INSERT INTO issues (project_id, issue_number, title, description, status, priority, depends_on)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, "1", "Issue 1", "Non-list JSON", "pending", 1, json.dumps({"not": "a list"})),
        )
        db.conn.commit()

        # Get issues with tasks - should return empty list for non-list JSON
        result = db.get_issues_with_tasks(project_id, include_tasks=False)

        assert len(result["issues"]) == 1
        assert result["issues"][0]["depends_on"] == [], "Non-list JSON should return empty list"

    def test_update_issue_depends_on(self, db):
        """Test updating issue depends_on field."""
        project_id = db.create_project("test-project", "Test Project")

        # Create two issues
        issue1_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1",
                title="Issue 1",
                description="First",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        issue2_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="2",
                title="Issue 2",
                description="Second",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # Update issue2 to depend on issue1
        result = db.update_issue(issue2_id, {"depends_on": json.dumps([str(issue1_id)])})
        assert result == 1, "One row should be updated"

        # Verify via get_issues_with_tasks
        issues_result = db.get_issues_with_tasks(project_id, include_tasks=False)
        issue2 = next(i for i in issues_result["issues"] if i["issue_number"] == "2")
        assert issue2["depends_on"] == [str(issue1_id)]


@pytest.mark.unit
class TestProjectAuditLogging:
    """Test audit logging for project lifecycle events."""

    def test_update_project_logs_audit_event(self, db):
        """Test that update_project creates audit log with PROJECT_UPDATED event."""
        # Create project with user
        user_id = 1  # Assume user exists
        project_id = db.create_project("test-project", "Test Project", user_id=user_id)

        # Update project with user_id for audit logging
        db.update_project(project_id, {"name": "updated-name"}, user_id=user_id)

        # Verify audit log was created
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT * FROM audit_logs
               WHERE event_type = 'project.updated'
               AND resource_type = 'project'
               AND resource_id = ?""",
            (project_id,),
        )
        audit_log = cursor.fetchone()

        assert audit_log is not None, "Audit log should be created for project update"
        assert dict(audit_log)["user_id"] == user_id

    def test_update_project_audit_includes_updated_fields(self, db):
        """Test that PROJECT_UPDATED audit log includes metadata about updated fields."""
        user_id = 1
        project_id = db.create_project("test-project", "Test Project", user_id=user_id)

        # Update multiple fields
        db.update_project(
            project_id,
            {"name": "updated-name", "description": "updated description"},
            user_id=user_id,
        )

        # Verify audit log metadata contains updated fields
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT metadata FROM audit_logs
               WHERE event_type = 'project.updated' AND resource_id = ?""",
            (project_id,),
        )
        row = cursor.fetchone()
        assert row is not None

        metadata = json.loads(row[0]) if row[0] else {}
        assert "updated_fields" in metadata
        assert "name" in metadata["updated_fields"]
        assert "description" in metadata["updated_fields"]

    def test_update_project_without_user_id_skips_audit(self, db):
        """Test that update_project without user_id skips audit logging."""
        project_id = db.create_project("test-project", "Test Project")

        # Update without user_id (e.g., system operation)
        db.update_project(project_id, {"name": "updated-name"})

        # Verify no audit log was created
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) FROM audit_logs
               WHERE event_type = 'project.updated' AND resource_id = ?""",
            (project_id,),
        )
        count = cursor.fetchone()[0]
        assert count == 0, "No audit log should be created without user_id"

    def test_delete_project_logs_audit_event(self, db):
        """Test that delete_project creates audit log with PROJECT_DELETED event."""
        user_id = 1
        project_id = db.create_project("test-project", "Test Project", user_id=user_id)
        project_name = "test-project"

        # Delete project with user_id for audit logging
        db.delete_project(project_id, user_id=user_id)

        # Verify audit log was created (note: project is deleted but audit log persists)
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT * FROM audit_logs
               WHERE event_type = 'project.deleted'
               AND resource_type = 'project'
               AND resource_id = ?""",
            (project_id,),
        )
        audit_log = cursor.fetchone()

        assert audit_log is not None, "Audit log should be created for project deletion"
        assert dict(audit_log)["user_id"] == user_id

        # Verify metadata includes project name
        metadata = json.loads(dict(audit_log)["metadata"]) if dict(audit_log)["metadata"] else {}
        assert metadata.get("name") == project_name

    def test_delete_project_without_user_id_skips_audit(self, db):
        """Test that delete_project without user_id skips audit logging."""
        project_id = db.create_project("test-project", "Test Project")

        # Delete without user_id (e.g., cleanup operation)
        db.delete_project(project_id)

        # Verify no audit log was created
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) FROM audit_logs
               WHERE event_type = 'project.deleted' AND resource_id = ?""",
            (project_id,),
        )
        count = cursor.fetchone()[0]
        assert count == 0

    def test_update_project_audit_with_ip_address(self, db):
        """Test that PROJECT_UPDATED audit log can include IP address."""
        user_id = 1
        project_id = db.create_project("test-project", "Test Project", user_id=user_id)

        # Update with IP address
        db.update_project(
            project_id,
            {"name": "updated-name"},
            user_id=user_id,
            ip_address="192.168.1.100",
        )

        # Verify audit log includes IP address
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT ip_address FROM audit_logs
               WHERE event_type = 'project.updated' AND resource_id = ?""",
            (project_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "192.168.1.100"

    def test_delete_project_audit_with_ip_address(self, db):
        """Test that PROJECT_DELETED audit log can include IP address."""
        user_id = 1
        project_id = db.create_project("test-project", "Test Project", user_id=user_id)

        # Delete with IP address
        db.delete_project(project_id, user_id=user_id, ip_address="10.0.0.1")

        # Verify audit log includes IP address
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT ip_address FROM audit_logs
               WHERE event_type = 'project.deleted' AND resource_id = ?""",
            (project_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "10.0.0.1"


@pytest.mark.unit
class TestAuditLogIntegrity:
    """Test audit log data integrity and consistency."""

    def test_project_lifecycle_audit_trail(self, db):
        """Test complete audit trail for project lifecycle: create → update → delete."""
        user_id = 1

        # Create
        project_id = db.create_project("lifecycle-test", "Test lifecycle", user_id=user_id)

        # Update
        db.update_project(project_id, {"description": "Updated desc"}, user_id=user_id)

        # Delete
        db.delete_project(project_id, user_id=user_id)

        # Verify complete audit trail
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT event_type FROM audit_logs
               WHERE resource_type = 'project' AND resource_id = ?
               ORDER BY timestamp""",
            (project_id,),
        )
        events = [row[0] for row in cursor.fetchall()]

        assert "project.created" in events
        assert "project.updated" in events
        assert "project.deleted" in events

    def test_audit_log_timestamps_are_sequential(self, db):
        """Test that audit log timestamps are in chronological order."""
        user_id = 1
        project_id = db.create_project("timestamp-test", "Test", user_id=user_id)

        # Perform multiple operations
        import time
        db.update_project(project_id, {"name": "update1"}, user_id=user_id)
        time.sleep(0.01)  # Small delay to ensure different timestamps
        db.update_project(project_id, {"name": "update2"}, user_id=user_id)

        # Verify timestamps are sequential
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT timestamp FROM audit_logs
               WHERE resource_type = 'project' AND resource_id = ?
               ORDER BY id""",
            (project_id,),
        )
        timestamps = [row[0] for row in cursor.fetchall()]

        assert len(timestamps) >= 2, "Should have at least 2 audit logs"
        # Timestamps should be chronologically ordered
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], "Timestamps should be sequential"
