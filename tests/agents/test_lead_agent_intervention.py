"""
Tests for LeadAgent supervisor intervention logic.

Test coverage for tactical pattern-based intervention:
- Pattern matching on file conflict errors
- Intervention context applied to task
- Intervention instructions generated correctly
- Error handling when patterns don't match

Following strict TDD methodology.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from codeframe.agents.lead_agent import LeadAgent
from codeframe.agents.tactical_patterns import InterventionStrategy, TacticalPattern
from codeframe.persistence.database import Database
from codeframe.core.models import Task, TaskStatus


class TestLeadAgentIntervention:
    """Test supervisor intervention logic."""

    @pytest.fixture
    def lead_agent(self, temp_db_path):
        """Create a LeadAgent with real database."""
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project")

        agent = LeadAgent(
            project_id=project_id,
            db=db,
            api_key="sk-ant-test-key",
        )
        return agent

    @pytest.fixture
    def sample_task(self, lead_agent):
        """Create a sample task for testing."""
        db = lead_agent.db
        project_id = lead_agent.project_id

        # Create issue first
        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": "1.0",
            "title": "Test Issue",
            "status": "pending",
            "priority": 0,
            "workflow_step": 1,
        })

        # Create task
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Test task description",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        # Return as Task object
        return Task(
            id=task_id,
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Test task description",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
        )


class TestFileConflictIntervention(TestLeadAgentIntervention):
    """Test file conflict intervention handling."""

    def test_handle_file_conflict_creates_intervention_context(
        self, lead_agent, sample_task
    ):
        """Test that file conflict intervention creates proper context."""
        error = FileExistsError("File already exists: src/component.tsx")
        pattern = TacticalPattern(
            pattern_id="file_already_exists",
            error_pattern=r"file.*exists",
            category="file_conflict",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
        )

        lead_agent._handle_file_conflict_intervention(sample_task, error, pattern)

        # Verify context was saved
        context = lead_agent.db.get_task_intervention_context(sample_task.id)

        assert context is not None
        assert context["intervention_applied"] is True
        assert context["pattern_matched"] == "file_already_exists"
        assert context["strategy"] == "convert_create_to_edit"

    def test_handle_file_conflict_extracts_file_path(
        self, lead_agent, sample_task
    ):
        """Test that file path is extracted from error message."""
        error = FileExistsError("File already exists: src/Button.tsx")
        pattern = TacticalPattern(
            pattern_id="file_already_exists",
            error_pattern=r"file.*exists",
            category="file_conflict",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
        )

        lead_agent._handle_file_conflict_intervention(sample_task, error, pattern)

        context = lead_agent.db.get_task_intervention_context(sample_task.id)

        assert "src/Button.tsx" in context["existing_files"]

    def test_handle_file_conflict_includes_workspace_files(
        self, lead_agent, sample_task
    ):
        """Test that workspace state files are included in context."""
        # Add files to workspace state
        lead_agent.update_workspace_state(
            task_id=sample_task.id,
            files_created=["existing_file.py"],
        )

        error = FileExistsError("File already exists: new_file.py")
        pattern = TacticalPattern(
            pattern_id="file_already_exists",
            error_pattern=r"file.*exists",
            category="file_conflict",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
        )

        lead_agent._handle_file_conflict_intervention(sample_task, error, pattern)

        context = lead_agent.db.get_task_intervention_context(sample_task.id)

        # Both files should be in existing_files
        assert "existing_file.py" in context["existing_files"]
        assert "new_file.py" in context["existing_files"]

    def test_handle_file_conflict_includes_instruction(
        self, lead_agent, sample_task
    ):
        """Test that intervention includes clear instruction."""
        error = FileExistsError("File already exists: src/file.py")
        pattern = TacticalPattern(
            pattern_id="file_already_exists",
            error_pattern=r"file.*exists",
            category="file_conflict",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
        )

        lead_agent._handle_file_conflict_intervention(sample_task, error, pattern)

        context = lead_agent.db.get_task_intervention_context(sample_task.id)

        assert "instruction" in context
        assert "modify" in context["instruction"].lower()
        assert "create" in context["instruction"].lower()


class TestInterventionInstruction(TestLeadAgentIntervention):
    """Test intervention instruction generation."""

    def test_convert_create_to_edit_instruction(self, lead_agent):
        """Test CONVERT_CREATE_TO_EDIT instruction."""
        instruction = lead_agent._get_intervention_instruction(
            InterventionStrategy.CONVERT_CREATE_TO_EDIT
        )

        assert "modify" in instruction.lower()
        assert "create" in instruction.lower()
        assert "existing_files" in instruction

    def test_skip_file_creation_instruction(self, lead_agent):
        """Test SKIP_FILE_CREATION instruction."""
        instruction = lead_agent._get_intervention_instruction(
            InterventionStrategy.SKIP_FILE_CREATION
        )

        assert "skip" in instruction.lower()
        assert "existing_files" in instruction

    def test_create_backup_instruction(self, lead_agent):
        """Test CREATE_BACKUP instruction."""
        instruction = lead_agent._get_intervention_instruction(
            InterventionStrategy.CREATE_BACKUP
        )

        assert "backup" in instruction.lower()

    def test_retry_with_context_instruction(self, lead_agent):
        """Test RETRY_WITH_CONTEXT instruction."""
        instruction = lead_agent._get_intervention_instruction(
            InterventionStrategy.RETRY_WITH_CONTEXT
        )

        assert "existing_files" in instruction


class TestPatternMatcherIntegration(TestLeadAgentIntervention):
    """Test integration with TacticalPatternMatcher."""

    def test_pattern_matcher_initialized(self, lead_agent):
        """Test that pattern matcher is initialized."""
        assert lead_agent._tactical_pattern_matcher is not None

    def test_pattern_matcher_has_file_exists_pattern(self, lead_agent):
        """Test that matcher has file_already_exists pattern."""
        matcher = lead_agent._tactical_pattern_matcher

        # Test that it matches
        result = matcher.match_error("FileExistsError: File already exists")

        assert result is not None
        assert result.pattern_id == "file_already_exists"

    def test_pattern_matcher_returns_diagnostics(self, lead_agent):
        """Test that match_error_with_diagnostics returns diagnostics."""
        matcher = lead_agent._tactical_pattern_matcher

        result, diagnostics = matcher.match_error_with_diagnostics(
            "FileExistsError: File exists"
        )

        assert diagnostics["patterns_checked"] > 0
        assert diagnostics["matched_pattern"] == "file_already_exists"
