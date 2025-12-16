"""Tests for Review Agent (Sprint 10 - US-1).

Following TDD: These tests are written BEFORE implementation.
Expected result: ALL TESTS FAIL (RED phase) until ReviewAgent is implemented.
"""

import pytest
from codeframe.core.models import (
    Task,
    TaskStatus,
    CodeReview,
    Severity,
    ReviewCategory,
)
from codeframe.persistence.database import Database


@pytest.fixture
def db():
    """Create a test database in memory."""
    database = Database(":memory:")
    database.initialize()

    # Manually apply Sprint 10 migration for in-memory database
    from codeframe.persistence.migrations.migration_007_sprint10_review_polish import (
        migration as migration_007,
    )

    if migration_007.can_apply(database.conn):
        migration_007.apply(database.conn)

    # Create test project
    cursor = database.conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, description, workspace_path, status) VALUES (?, ?, ?, ?)",
        ("test-project", "Test project", "/tmp/test", "active"),
    )
    database.conn.commit()

    return database


@pytest.fixture
def sample_code_with_sql_injection():
    """Sample code with SQL injection vulnerability for testing."""
    return '''
def get_user(username):
    """Get user from database - VULNERABLE!"""
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    return cursor.fetchone()
'''


@pytest.fixture
def sample_code_with_performance_issue():
    """Sample code with O(n²) performance issue."""
    return '''
def find_duplicates(items):
    """Find duplicate items - SLOW O(n²) algorithm!"""
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] == items[j]:
                duplicates.append(items[i])
    return duplicates
'''


@pytest.fixture
def sample_task_with_code(db, sample_code_with_sql_injection):
    """Create a task with code files for review."""
    # Create an issue first (required by foreign key)
    from codeframe.core.models import Issue

    issue = Issue(
        project_id=1,
        issue_number="1.1",
        title="User Management",
        status=TaskStatus.IN_PROGRESS,
        priority=0,
        workflow_step=1,
    )
    issue_id = db.create_issue(issue)

    # Create the task in the database
    task_id = db.create_task_with_issue(
        project_id=1,
        issue_id=issue_id,
        task_number="1.1.1",
        parent_issue_number="1.1",
        title="Implement user search",
        description="Add database query for user search",
        status=TaskStatus.IN_PROGRESS,
        priority=0,
        workflow_step=1,
        can_parallelize=False,
    )

    # Create Task object with the created task_id
    task = Task(
        id=task_id,
        project_id=1,
        issue_id=issue_id,
        task_number="1.1.1",
        parent_issue_number="1.1",
        title="Implement user search",
        description="Add database query for user search",
        status=TaskStatus.IN_PROGRESS,
        assigned_to="backend-001",
        depends_on="",
        can_parallelize=False,
        priority=2,
        workflow_step=1,
        requires_mcp=False,
        estimated_tokens=0,
        actual_tokens=None,
        created_at=None,
        completed_at=None,
    )

    # Mock file content that would be extracted from task
    task._test_code_files = [
        {"path": "src/users/search.py", "content": sample_code_with_sql_injection}
    ]

    return task


@pytest.mark.asyncio
async def test_detect_sql_injection(db, sample_task_with_code):
    """T019: Review Agent detects SQL injection vulnerability.

    Expected: FAIL - ReviewAgent not implemented yet
    """
    from codeframe.agents.review_agent import ReviewAgent

    agent = ReviewAgent(agent_id="review-001", db=db)
    result = await agent.execute_task(sample_task_with_code)

    # Assert critical security finding detected
    assert result.status == "blocked", "Task should be blocked due to critical finding"
    assert len(result.findings) > 0, "Should find at least one issue"

    # Check for SQL injection finding
    security_findings = [f for f in result.findings if f.category == ReviewCategory.SECURITY]
    assert len(security_findings) > 0, "Should detect security issue"

    sql_injection_found = any(
        "sql injection" in finding.message.lower() or "sql" in finding.message.lower()
        for finding in security_findings
    )
    assert sql_injection_found, "Should specifically identify SQL injection"

    # Check severity
    critical_findings = [f for f in result.findings if f.severity == Severity.CRITICAL]
    assert len(critical_findings) > 0, "SQL injection should be marked as CRITICAL"


@pytest.mark.asyncio
async def test_detect_performance_issue(db, sample_code_with_performance_issue):
    """T020: Review Agent detects performance issue (O(n²) algorithm).

    Expected: FAIL - ReviewAgent not implemented yet
    """
    from codeframe.agents.review_agent import ReviewAgent
    from codeframe.core.models import Issue

    # Create issue and task in database
    issue = Issue(
        project_id=1,
        issue_number="1.2",
        title="Performance Optimization",
        status=TaskStatus.IN_PROGRESS,
        priority=0,
        workflow_step=1,
    )
    issue_id = db.create_issue(issue)

    task_id = db.create_task_with_issue(
        project_id=1,
        issue_id=issue_id,
        task_number="1.2.1",
        parent_issue_number="1.2",
        title="Implement duplicate finder",
        description="Find duplicates in list",
        status=TaskStatus.IN_PROGRESS,
        priority=0,
        workflow_step=1,
        can_parallelize=False,
    )

    task = Task(
        id=task_id,
        project_id=1,
        issue_id=issue_id,
        task_number="1.2.1",
        parent_issue_number="1.2",
        title="Implement duplicate finder",
        description="Find duplicates in list",
        status=TaskStatus.IN_PROGRESS,
        assigned_to="backend-001",
        depends_on="",
        can_parallelize=False,
        priority=2,
        workflow_step=1,
        requires_mcp=False,
        estimated_tokens=0,
        actual_tokens=None,
        created_at=None,
        completed_at=None,
    )
    task._test_code_files = [
        {"path": "src/utils/duplicates.py", "content": sample_code_with_performance_issue}
    ]

    agent = ReviewAgent(agent_id="review-001", db=db)
    result = await agent.execute_task(task)

    # Should find performance issue
    perf_findings = [f for f in result.findings if f.category == ReviewCategory.PERFORMANCE]
    assert len(perf_findings) > 0, "Should detect performance issue"

    # Check for O(n²) or algorithmic complexity mention
    complexity_mentioned = any(
        "o(n" in finding.message.lower() or "complexity" in finding.message.lower()
        for finding in perf_findings
    )
    assert complexity_mentioned, "Should mention algorithmic complexity"


@pytest.mark.asyncio
async def test_store_review_findings(db, sample_task_with_code):
    """T021: Review Agent stores findings in database.

    Expected: FAIL - ReviewAgent not implemented yet
    """
    from codeframe.agents.review_agent import ReviewAgent

    agent = ReviewAgent(agent_id="review-001", db=db)
    result = await agent.execute_task(sample_task_with_code)

    # Verify findings stored in database
    stored_reviews = db.get_code_reviews(task_id=sample_task_with_code.id)

    assert len(stored_reviews) > 0, "Findings should be stored in database"
    assert stored_reviews[0].task_id == sample_task_with_code.id
    assert stored_reviews[0].agent_id == "review-001"
    assert stored_reviews[0].project_id == 1


@pytest.mark.asyncio
async def test_block_on_critical_finding(db, sample_task_with_code):
    """T022: Review Agent blocks task on critical severity finding.

    Expected: FAIL - ReviewAgent not implemented yet
    """
    from codeframe.agents.review_agent import ReviewAgent

    agent = ReviewAgent(agent_id="review-001", db=db)
    result = await agent.execute_task(sample_task_with_code)

    # Should block task due to critical finding
    assert result.status == "blocked", "Task should be blocked"

    # Should create a blocker for human attention
    blocker = db.get_pending_blocker(agent_id="review-001")
    assert blocker is not None, "Should create blocker for critical issue"
    assert (
        "security" in blocker.get("question", "").lower()
        or "sql" in blocker.get("question", "").lower()
    )


@pytest.mark.asyncio
async def test_pass_on_low_severity(db):
    """T023: Review Agent passes task on low severity findings.

    Expected: FAIL - ReviewAgent not implemented yet
    """
    from codeframe.agents.review_agent import ReviewAgent

    # Clean code with only minor style issues
    clean_code = '''
def calculate_total(items):
    """Calculate total price of items."""
    return sum(item.price for item in items)
'''

    task = Task(
        id=3,
        project_id=1,
        title="Calculate total",
        description="Sum item prices",
        status=TaskStatus.IN_PROGRESS,
    )
    task._test_code_files = [{"path": "src/utils/calc.py", "content": clean_code}]

    agent = ReviewAgent(agent_id="review-001", db=db)
    result = await agent.execute_task(task)

    # Should NOT block for clean code or minor issues
    assert result.status in ["completed", "passed"], "Clean code should pass review"

    # If findings exist, they should be low severity
    if result.findings:
        for finding in result.findings:
            assert finding.severity in [Severity.LOW, Severity.INFO, Severity.MEDIUM]


@pytest.mark.asyncio
async def test_full_review_workflow(db, sample_task_with_code):
    """T024: Full review workflow integration test.

    Expected: FAIL - ReviewAgent not implemented yet
    """
    from codeframe.agents.review_agent import ReviewAgent

    agent = ReviewAgent(agent_id="review-001", db=db)

    # Execute review
    result = await agent.execute_task(sample_task_with_code)

    # Verify complete workflow
    assert result is not None
    assert hasattr(result, "status")
    assert hasattr(result, "findings")

    # Findings should be CodeReview objects
    if result.findings:
        finding = result.findings[0]
        assert isinstance(finding, CodeReview)
        assert finding.file_path is not None
        assert finding.message is not None
        assert finding.severity in [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]
        assert finding.category in [
            ReviewCategory.SECURITY,
            ReviewCategory.PERFORMANCE,
            ReviewCategory.QUALITY,
            ReviewCategory.MAINTAINABILITY,
            ReviewCategory.STYLE,
        ]

    # Database should have records
    stored_reviews = db.get_code_reviews(task_id=sample_task_with_code.id)
    assert len(stored_reviews) == len(result.findings), "All findings should be stored"
