"""Tests for Issue Generation from PRD.

Following TDD: These tests are written FIRST, before implementation.
Target: >85% coverage for issue_generator.py module.

Test Coverage:
1. PRD parsing and feature extraction
2. Issue creation with sequential numbering
3. Priority assignment based on keywords
4. Handling empty/malformed PRDs
5. Issue validation
6. Integration with database
"""

import pytest
from codeframe.planning.issue_generator import (
    IssueGenerator,
    parse_prd_features,
    assign_priority,
)
from codeframe.core.models import Issue, TaskStatus


# Sample PRD content for testing
SAMPLE_PRD = """# Product Requirements Document (PRD)

## Executive Summary
A comprehensive task management system for agile teams.

## Problem Statement
Teams struggle with coordinating work across multiple developers.

## User Personas
- Development teams
- Project managers
- QA engineers

## Features & Requirements

### Critical: User Authentication System
Implement secure authentication with OAuth2, JWT tokens, and role-based access control.
Users must be able to login, logout, and manage sessions securely.

### High: Task Management Dashboard
Create a real-time dashboard showing all tasks, their status, and assigned developers.
Must support filtering, sorting, and search functionality.

### Medium: Real-time Notifications
Add WebSocket-based notifications for task updates, comments, and assignments.
Should support email and in-app notifications.

### Low: Reporting System
Generate weekly reports showing team velocity, completed tasks, and blockers.
Export reports in PDF and Excel formats.

## Technical Architecture
- Backend: Python FastAPI
- Frontend: React with TypeScript
- Database: PostgreSQL
- Real-time: WebSocket

## Success Metrics
- 80% test coverage
- <200ms API response time
- 99.9% uptime

## Timeline & Milestones
- Sprint 1: Authentication (2 weeks)
- Sprint 2: Dashboard (3 weeks)
- Sprint 3: Notifications (2 weeks)
"""


MALFORMED_PRD = """# Product Requirements Document

This is a malformed PRD without proper features section.

## Some Random Section
Random content here.
"""


EMPTY_PRD = ""


PRD_WITHOUT_PRIORITIES = """# Product Requirements Document

## Features & Requirements

### User Authentication
Basic login and logout functionality.

### Task Dashboard
Show all tasks in a list view.
"""


@pytest.mark.unit
class TestPRDParsing:
    """Test PRD parsing and feature extraction."""

    def test_parse_prd_extracts_features_section(self):
        """Test that parser correctly extracts Features & Requirements section."""
        # ACT
        features = parse_prd_features(SAMPLE_PRD)

        # ASSERT
        assert len(features) > 0
        assert "Features & Requirements" in SAMPLE_PRD

    def test_parse_prd_identifies_feature_titles(self):
        """Test that parser extracts feature titles from headers."""
        # ACT
        features = parse_prd_features(SAMPLE_PRD)

        # ASSERT
        assert len(features) == 4
        feature_titles = [f["title"] for f in features]
        assert "User Authentication System" in feature_titles
        assert "Task Management Dashboard" in feature_titles
        assert "Real-time Notifications" in feature_titles
        assert "Reporting System" in feature_titles

    def test_parse_prd_extracts_feature_descriptions(self):
        """Test that parser extracts full feature descriptions."""
        # ACT
        features = parse_prd_features(SAMPLE_PRD)

        # ASSERT
        auth_feature = next(f for f in features if "Authentication" in f["title"])
        assert "OAuth2" in auth_feature["description"]
        assert "JWT tokens" in auth_feature["description"]
        assert "role-based access" in auth_feature["description"]

    def test_parse_prd_handles_empty_prd(self):
        """Test that parser handles empty PRD gracefully."""
        # ACT
        features = parse_prd_features(EMPTY_PRD)

        # ASSERT
        assert features == []

    def test_parse_prd_handles_malformed_prd(self):
        """Test that parser handles malformed PRD without features section."""
        # ACT
        features = parse_prd_features(MALFORMED_PRD)

        # ASSERT
        # Should return empty list if no features section found
        assert features == []

    def test_parse_prd_strips_priority_keywords_from_titles(self):
        """Test that parser removes priority keywords from feature titles."""
        # ACT
        features = parse_prd_features(SAMPLE_PRD)

        # ASSERT
        # Titles should not have "Critical:", "High:", etc.
        titles = [f["title"] for f in features]
        for title in titles:
            assert not title.startswith("Critical:")
            assert not title.startswith("High:")
            assert not title.startswith("Medium:")
            assert not title.startswith("Low:")

    def test_parse_prd_preserves_feature_order(self):
        """Test that parser maintains feature order from PRD."""
        # ACT
        features = parse_prd_features(SAMPLE_PRD)

        # ASSERT
        assert features[0]["title"] == "User Authentication System"
        assert features[1]["title"] == "Task Management Dashboard"
        assert features[2]["title"] == "Real-time Notifications"
        assert features[3]["title"] == "Reporting System"


@pytest.mark.unit
class TestPriorityAssignment:
    """Test priority assignment based on keywords."""

    def test_assign_priority_critical_keyword(self):
        """Test that 'critical' keyword assigns priority 0."""
        # ARRANGE
        text = "Critical: This is a critical feature"

        # ACT
        priority = assign_priority(text)

        # ASSERT
        assert priority == 0

    def test_assign_priority_high_keyword(self):
        """Test that 'high' keyword assigns priority 1."""
        # ARRANGE
        text = "High: This is a high priority feature"

        # ACT
        priority = assign_priority(text)

        # ASSERT
        assert priority == 1

    def test_assign_priority_medium_keyword(self):
        """Test that 'medium' keyword assigns priority 2."""
        # ARRANGE
        text = "Medium: This is a medium priority feature"

        # ACT
        priority = assign_priority(text)

        # ASSERT
        assert priority == 2

    def test_assign_priority_low_keyword(self):
        """Test that 'low' keyword assigns priority 3."""
        # ARRANGE
        text = "Low: This is a low priority feature"

        # ACT
        priority = assign_priority(text)

        # ASSERT
        assert priority == 3

    def test_assign_priority_default_no_keyword(self):
        """Test that features without priority keywords get default priority 2."""
        # ARRANGE
        text = "This feature has no priority keyword"

        # ACT
        priority = assign_priority(text)

        # ASSERT
        assert priority == 2  # Default medium priority

    def test_assign_priority_case_insensitive(self):
        """Test that priority keywords are case-insensitive."""
        # ARRANGE
        texts = [
            "CRITICAL: All caps",
            "critical: Lowercase",
            "CrItIcAl: Mixed case",
        ]

        # ACT & ASSERT
        for text in texts:
            priority = assign_priority(text)
            assert priority == 0

    def test_assign_priority_with_multiple_keywords(self):
        """Test that first keyword takes precedence."""
        # ARRANGE
        text = "Critical: This is critical but also mentions high priority"

        # ACT
        priority = assign_priority(text)

        # ASSERT
        assert priority == 0  # Should use "critical", not "high"


@pytest.mark.unit
class TestIssueGeneration:
    """Test issue generation from parsed features."""

    def test_generate_issues_creates_correct_count(self):
        """Test that generator creates correct number of issues."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        assert len(issues) == 4

    def test_generate_issues_assigns_sequential_numbers(self):
        """Test that issues get sequential numbers like 2.1, 2.2, 2.3."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        assert issues[0].issue_number == "2.1"
        assert issues[1].issue_number == "2.2"
        assert issues[2].issue_number == "2.3"
        assert issues[3].issue_number == "2.4"

    def test_generate_issues_with_different_sprint_numbers(self):
        """Test that sprint number is reflected in issue numbers."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues_sprint_1 = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=1)
        issues_sprint_3 = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=3)

        # ASSERT
        assert issues_sprint_1[0].issue_number == "1.1"
        assert issues_sprint_3[0].issue_number == "3.1"

    def test_generate_issues_sets_correct_titles(self):
        """Test that issues have correct titles from PRD."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        assert issues[0].title == "User Authentication System"
        assert issues[1].title == "Task Management Dashboard"
        assert issues[2].title == "Real-time Notifications"
        assert issues[3].title == "Reporting System"

    def test_generate_issues_sets_descriptions(self):
        """Test that issues have descriptions from PRD."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        auth_issue = issues[0]
        assert "OAuth2" in auth_issue.description
        assert "JWT tokens" in auth_issue.description

    def test_generate_issues_assigns_priorities_correctly(self):
        """Test that issues get correct priorities based on keywords."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        assert issues[0].priority == 0  # Critical
        assert issues[1].priority == 1  # High
        assert issues[2].priority == 2  # Medium
        assert issues[3].priority == 3  # Low

    def test_generate_issues_sets_status_to_pending(self):
        """Test that all new issues have status='pending'."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        for issue in issues:
            assert issue.status == TaskStatus.PENDING

    def test_generate_issues_sets_workflow_step_to_zero(self):
        """Test that all new issues have workflow_step=0."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        for issue in issues:
            assert issue.workflow_step == 0

    def test_generate_issues_from_empty_prd_returns_empty_list(self):
        """Test that empty PRD returns empty list."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(EMPTY_PRD, sprint_number=2)

        # ASSERT
        assert issues == []

    def test_generate_issues_handles_prd_without_priorities(self):
        """Test that features without priority keywords get default priority."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(PRD_WITHOUT_PRIORITIES, sprint_number=2)

        # ASSERT
        assert len(issues) == 2
        for issue in issues:
            assert issue.priority == 2  # Default medium priority


@pytest.mark.unit
class TestIssueValidation:
    """Test issue validation logic."""

    def test_issue_requires_title(self):
        """Test that issue validation requires a title."""
        # ARRANGE
        generator = IssueGenerator()

        # Create issue with empty title
        issue = Issue(
            issue_number="2.1",
            title="",
            description="Description",
            priority=2,
            status=TaskStatus.PENDING,
            workflow_step=0,
        )

        # ACT & ASSERT
        with pytest.raises(ValueError):
            generator._validate_issue(issue)

    def test_issue_number_format_validation(self):
        """Test that issue number must match format X.Y."""
        # ARRANGE
        generator = IssueGenerator()

        # Valid format should not raise
        valid_issue = Issue(
            issue_number="2.1",
            title="Test",
            description="Test",
            priority=2,
            status=TaskStatus.PENDING,
            workflow_step=0,
        )
        generator._validate_issue(valid_issue)  # Should not raise

        # Invalid format should raise
        invalid_issue = Issue(
            issue_number="invalid",
            title="Test",
            description="Test",
            priority=2,
            status=TaskStatus.PENDING,
            workflow_step=0,
        )

        with pytest.raises(ValueError):
            generator._validate_issue(invalid_issue)

    def test_issue_priority_range_validation(self):
        """Test that priority must be 0-4."""
        # ARRANGE
        generator = IssueGenerator()

        # Valid priority should not raise
        valid_issue = Issue(
            issue_number="2.1",
            title="Test",
            description="Test",
            priority=3,
            status=TaskStatus.PENDING,
            workflow_step=0,
        )
        generator._validate_issue(valid_issue)  # Should not raise

        # Invalid priority should raise
        invalid_issue = Issue(
            issue_number="2.1",
            title="Test",
            description="Test",
            priority=5,  # Out of range
            status=TaskStatus.PENDING,
            workflow_step=0,
        )

        with pytest.raises(ValueError):
            generator._validate_issue(invalid_issue)


@pytest.mark.unit
class TestIssueGeneratorEdgeCases:
    """Test edge cases and error handling."""

    def test_generate_issues_with_very_long_features(self):
        """Test handling of features with very long descriptions."""
        # ARRANGE
        long_description = "x" * 10000
        prd = f"""# PRD

## Features & Requirements

### Feature Title
{long_description}
"""
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(prd, sprint_number=2)

        # ASSERT
        assert len(issues) == 1
        assert len(issues[0].description) <= 10000

    def test_generate_issues_with_special_characters_in_titles(self):
        """Test handling of special characters in feature titles."""
        # ARRANGE
        prd = """# PRD

## Features & Requirements

### Feature with Special Ch@rs & Symbols!
Description here.
"""
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(prd, sprint_number=2)

        # ASSERT
        assert len(issues) == 1
        assert "Special Ch@rs" in issues[0].title

    def test_generate_issues_with_nested_headers(self):
        """Test that nested headers within features don't create separate issues."""
        # ARRANGE
        prd = """# PRD

## Features & Requirements

### Main Feature
Description here.

#### Sub-section
This should not be a separate issue.

### Another Feature
Second feature description.
"""
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(prd, sprint_number=2)

        # ASSERT
        # Should only have 2 issues (level 3 headers), not 3
        assert len(issues) == 2
        assert issues[0].title == "Main Feature"
        assert issues[1].title == "Another Feature"

    def test_generate_issues_with_large_sprint_number(self):
        """Test handling of large sprint numbers."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=99)

        # ASSERT
        assert issues[0].issue_number == "99.1"
        assert issues[1].issue_number == "99.2"


@pytest.mark.unit
class TestIssueGeneratorIntegration:
    """Test integration with other components."""

    def test_issue_generator_creates_valid_issue_objects(self):
        """Test that generator creates valid Issue model instances."""
        # ARRANGE
        generator = IssueGenerator()

        # ACT
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ASSERT
        for issue in issues:
            assert isinstance(issue, Issue)
            assert hasattr(issue, "issue_number")
            assert hasattr(issue, "title")
            assert hasattr(issue, "description")
            assert hasattr(issue, "priority")
            assert hasattr(issue, "status")
            assert hasattr(issue, "workflow_step")

    def test_issue_generator_output_serializable(self):
        """Test that generated issues can be serialized (for database)."""
        # ARRANGE
        generator = IssueGenerator()
        issues = generator.generate_issues_from_prd(SAMPLE_PRD, sprint_number=2)

        # ACT & ASSERT
        for issue in issues:
            # Should be able to convert to dict for database insertion
            issue_dict = {
                "issue_number": issue.issue_number,
                "title": issue.title,
                "description": issue.description,
                "priority": issue.priority,
                "status": issue.status,
                "workflow_step": issue.workflow_step,
            }
            assert isinstance(issue_dict, dict)
            assert all(isinstance(k, str) for k in issue_dict.keys())
