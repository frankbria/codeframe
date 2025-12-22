"""Tests for MetricsTracker (Sprint 10 Phase 5: Metrics and Cost Tracking).

Following TDD approach - these tests are written FIRST and will initially fail.
"""

import pytest
from datetime import datetime, timedelta, timezone
from codeframe.lib.metrics_tracker import MetricsTracker
from codeframe.core.models import CallType
from codeframe.persistence.database import Database


@pytest.fixture
def db():
    """Create in-memory database for testing."""
    database = Database(":memory:")
    database.initialize()

    # Create test project
    cursor = database.conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, description, workspace_path, status) VALUES (?, ?, ?, ?)",
        ("test-project", "Test project", "/tmp/test", "active"),
    )
    database.conn.commit()

    return database


@pytest.fixture
def tracker(db):
    """Create MetricsTracker instance."""
    return MetricsTracker(db=db)


# ============================================================================
# T108: test_record_token_usage - Records tokens after LLM call
# ============================================================================


@pytest.mark.asyncio
async def test_record_token_usage(tracker, db):
    """Test recording token usage after an LLM call."""
    # Given: A task exists
    cursor = db.conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (project_id, title, description, status) VALUES (?, ?, ?, ?)",
        (1, "Test task", "Test description", "in_progress"),
    )
    db.conn.commit()
    task_id = cursor.lastrowid

    # When: We record token usage
    usage_id = await tracker.record_token_usage(
        task_id=task_id,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=1000,
        output_tokens=500,
        call_type=CallType.TASK_EXECUTION,
    )

    # Then: Token usage is saved to database
    assert usage_id > 0

    # And: We can retrieve it
    cursor.execute("SELECT * FROM token_usage WHERE id = ?", (usage_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row["task_id"] == task_id
    assert row["agent_id"] == "backend-001"
    assert row["project_id"] == 1
    assert row["model_name"] == "claude-sonnet-4-5"
    assert row["input_tokens"] == 1000
    assert row["output_tokens"] == 500
    assert row["call_type"] == "task_execution"
    assert row["estimated_cost_usd"] > 0


@pytest.mark.asyncio
async def test_record_token_usage_without_task(tracker, db):
    """Test recording token usage for non-task LLM calls (e.g., coordination)."""
    # When: We record token usage without a task
    usage_id = await tracker.record_token_usage(
        task_id=None,
        agent_id="orchestrator-001",
        project_id=1,
        model_name="claude-haiku-4",
        input_tokens=500,
        output_tokens=200,
        call_type=CallType.COORDINATION,
    )

    # Then: Token usage is saved
    assert usage_id > 0

    # And: task_id is NULL
    cursor = db.conn.cursor()
    cursor.execute("SELECT task_id FROM token_usage WHERE id = ?", (usage_id,))
    row = cursor.fetchone()
    assert row["task_id"] is None


# ============================================================================
# T109: test_calculate_cost_sonnet - Cost calculation for Sonnet 4.5
# ============================================================================


def test_calculate_cost_sonnet():
    """Test cost calculation for Claude Sonnet 4.5 ($3/$15 per MTok)."""
    # Given: Sonnet pricing ($3 input, $15 output per million tokens)
    model_name = "claude-sonnet-4-5"
    input_tokens = 1_000_000  # 1M tokens
    output_tokens = 500_000  # 0.5M tokens

    # When: We calculate cost
    cost = MetricsTracker.calculate_cost(model_name, input_tokens, output_tokens)

    # Then: Cost is correct (1M * $3 + 0.5M * $15 = $3 + $7.50 = $10.50)
    assert cost == 10.50


def test_calculate_cost_sonnet_small():
    """Test cost calculation for small Sonnet usage."""
    # Given: Small token counts
    model_name = "claude-sonnet-4-5"
    input_tokens = 1000  # 0.001M tokens
    output_tokens = 500  # 0.0005M tokens

    # When: We calculate cost
    cost = MetricsTracker.calculate_cost(model_name, input_tokens, output_tokens)

    # Then: Cost is correct (1000 * $3 / 1M + 500 * $15 / 1M = $0.003 + $0.0075 = $0.0105)
    expected = (1000 * 3.00 / 1_000_000) + (500 * 15.00 / 1_000_000)
    assert cost == pytest.approx(expected, abs=1e-6)


# ============================================================================
# T110: test_calculate_cost_opus - Cost calculation for Opus 4
# ============================================================================


def test_calculate_cost_opus():
    """Test cost calculation for Claude Opus 4 ($15/$75 per MTok)."""
    # Given: Opus pricing ($15 input, $75 output per million tokens)
    model_name = "claude-opus-4"
    input_tokens = 1_000_000  # 1M tokens
    output_tokens = 500_000  # 0.5M tokens

    # When: We calculate cost
    cost = MetricsTracker.calculate_cost(model_name, input_tokens, output_tokens)

    # Then: Cost is correct (1M * $15 + 0.5M * $75 = $15 + $37.50 = $52.50)
    assert cost == 52.50


# ============================================================================
# T111: test_calculate_cost_haiku - Cost calculation for Haiku 4
# ============================================================================


def test_calculate_cost_haiku():
    """Test cost calculation for Claude Haiku 4 ($0.80/$4 per MTok)."""
    # Given: Haiku pricing ($0.80 input, $4 output per million tokens)
    model_name = "claude-haiku-4"
    input_tokens = 1_000_000  # 1M tokens
    output_tokens = 500_000  # 0.5M tokens

    # When: We calculate cost
    cost = MetricsTracker.calculate_cost(model_name, input_tokens, output_tokens)

    # Then: Cost is correct (1M * $0.80 + 0.5M * $4 = $0.80 + $2.00 = $2.80)
    assert cost == 2.80


def test_calculate_cost_unknown_model():
    """Test that unknown model raises ValueError."""
    # When/Then: Unknown model raises ValueError
    with pytest.raises(ValueError, match="Unknown model"):
        MetricsTracker.calculate_cost("claude-unknown-99", 1000, 500)


# ============================================================================
# T112: test_get_project_total_cost - Aggregate project costs
# ============================================================================


@pytest.mark.asyncio
async def test_get_project_total_cost(tracker, db):
    """Test aggregating total costs for a project."""
    # Given: Multiple token usages for different agents
    await tracker.record_token_usage(
        task_id=None,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
        call_type=CallType.TASK_EXECUTION,
    )

    await tracker.record_token_usage(
        task_id=None,
        agent_id="frontend-001",
        project_id=1,
        model_name="claude-haiku-4",
        input_tokens=500_000,
        output_tokens=250_000,
        call_type=CallType.TASK_EXECUTION,
    )

    # When: We get project costs
    result = await tracker.get_project_costs(project_id=1)

    # Then: Total cost is sum of both usages
    # Sonnet: (1M * $3 + 0.5M * $15) = $10.50
    # Haiku: (0.5M * $0.80 + 0.25M * $4) = $1.40
    # Total: $11.90
    assert result["total_cost_usd"] == pytest.approx(11.90, abs=0.01)
    assert result["total_tokens"] == 2_250_000
    assert result["project_id"] == 1

    # And: Breakdown by agent is provided
    assert len(result["by_agent"]) == 2
    agent_costs = {a["agent_id"]: a["cost_usd"] for a in result["by_agent"]}
    assert agent_costs["backend-001"] == pytest.approx(10.50, abs=0.01)
    assert agent_costs["frontend-001"] == pytest.approx(1.40, abs=0.01)

    # And: Breakdown by model is provided
    assert len(result["by_model"]) == 2
    model_costs = {m["model_name"]: m["cost_usd"] for m in result["by_model"]}
    assert model_costs["claude-sonnet-4-5"] == pytest.approx(10.50, abs=0.01)
    assert model_costs["claude-haiku-4"] == pytest.approx(1.40, abs=0.01)


@pytest.mark.asyncio
async def test_get_project_total_cost_empty(tracker, db):
    """Test getting costs for project with no usage."""
    # When: We get costs for empty project
    result = await tracker.get_project_costs(project_id=1)

    # Then: All values are zero
    assert result["total_cost_usd"] == 0.0
    assert result["total_tokens"] == 0
    assert len(result["by_agent"]) == 0
    assert len(result["by_model"]) == 0


# ============================================================================
# T113: test_get_cost_by_agent - Cost breakdown per agent
# ============================================================================


@pytest.mark.asyncio
async def test_get_cost_by_agent(tracker, db):
    """Test getting cost breakdown for a specific agent."""
    # Given: Multiple usages for an agent across different projects
    await tracker.record_token_usage(
        task_id=None,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
        call_type=CallType.TASK_EXECUTION,
    )

    await tracker.record_token_usage(
        task_id=None,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-haiku-4",
        input_tokens=200_000,
        output_tokens=100_000,
        call_type=CallType.CODE_REVIEW,
    )

    # When: We get costs for this agent
    result = await tracker.get_agent_costs(agent_id="backend-001")

    # Then: Total cost is sum of all usages
    # Sonnet: $10.50, Haiku: $0.56
    assert result["total_cost_usd"] == pytest.approx(11.06, abs=0.01)
    assert result["agent_id"] == "backend-001"

    # And: Breakdown by call type is provided
    assert len(result["by_call_type"]) == 2
    call_costs = {c["call_type"]: c["cost_usd"] for c in result["by_call_type"]}
    assert "task_execution" in call_costs
    assert "code_review" in call_costs


# ============================================================================
# T114: test_get_cost_by_model - Cost breakdown per model
# ============================================================================


@pytest.mark.asyncio
async def test_get_cost_by_model(tracker, db):
    """Test getting cost breakdown by model for a project."""
    # Given: Multiple usages with different models
    await tracker.record_token_usage(
        task_id=None,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
        call_type=CallType.TASK_EXECUTION,
    )

    await tracker.record_token_usage(
        task_id=None,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=500_000,
        output_tokens=250_000,
        call_type=CallType.TASK_EXECUTION,
    )

    await tracker.record_token_usage(
        task_id=None,
        agent_id="frontend-001",
        project_id=1,
        model_name="claude-haiku-4",
        input_tokens=500_000,
        output_tokens=250_000,
        call_type=CallType.TASK_EXECUTION,
    )

    # When: We get costs
    result = await tracker.get_project_costs(project_id=1)

    # Then: Model breakdown is correct
    model_costs = {m["model_name"]: m for m in result["by_model"]}

    # Sonnet: 2 calls totaling (1.5M * $3 + 0.75M * $15) = $15.75
    assert model_costs["claude-sonnet-4-5"]["cost_usd"] == pytest.approx(15.75, abs=0.01)
    assert model_costs["claude-sonnet-4-5"]["call_count"] == 2
    assert model_costs["claude-sonnet-4-5"]["total_tokens"] == 2_250_000

    # Haiku: 1 call totaling (0.5M * $0.80 + 0.25M * $4) = $1.40
    assert model_costs["claude-haiku-4"]["cost_usd"] == pytest.approx(1.40, abs=0.01)
    assert model_costs["claude-haiku-4"]["call_count"] == 1


# ============================================================================
# T115: test_get_token_usage_timeline - Token usage over time
# ============================================================================


@pytest.mark.asyncio
async def test_get_token_usage_timeline(tracker, db):
    """Test getting token usage timeline with date filtering."""
    # Given: Usages at different times
    now = datetime.now(timezone.utc)

    # Recent usage (today)
    await tracker.record_token_usage(
        task_id=None,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
        call_type=CallType.TASK_EXECUTION,
    )

    # Older usage (manually insert with backdated timestamp)
    old_timestamp = now - timedelta(days=10)
    cursor = db.conn.cursor()
    cursor.execute(
        """
        INSERT INTO token_usage
        (agent_id, project_id, model_name, input_tokens, output_tokens,
         estimated_cost_usd, call_type, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "backend-001",
            1,
            "claude-haiku-4",
            500_000,
            250_000,
            MetricsTracker.calculate_cost("claude-haiku-4", 500_000, 250_000),
            "task_execution",
            old_timestamp.isoformat(),  # Convert to ISO string
        ),
    )
    db.conn.commit()

    # When: We get timeline for last 7 days
    start_date = now - timedelta(days=7)
    result = await tracker.get_token_usage_stats(project_id=1, start_date=start_date, end_date=None)

    # Then: Only recent usage is included
    assert result["total_cost_usd"] == pytest.approx(10.50, abs=0.01)
    assert result["total_calls"] == 1
    assert result["date_range"]["start"] == start_date.isoformat()

    # When: We get all usage (no date filter)
    result_all = await tracker.get_token_usage_stats(project_id=1, start_date=None, end_date=None)

    # Then: Both usages are included
    assert result_all["total_cost_usd"] == pytest.approx(11.90, abs=0.01)
    assert result_all["total_calls"] == 2


@pytest.mark.asyncio
async def test_get_token_usage_stats_with_end_date(tracker, db):
    """Test filtering usage by end date."""
    # Given: Usage exists
    now = datetime.now(timezone.utc)
    await tracker.record_token_usage(
        task_id=None,
        agent_id="backend-001",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
        call_type=CallType.TASK_EXECUTION,
    )

    # When: We filter with end_date in the past
    past_date = now - timedelta(days=1)
    result = await tracker.get_token_usage_stats(project_id=1, start_date=None, end_date=past_date)

    # Then: No usages match
    assert result["total_cost_usd"] == 0.0
    assert result["total_calls"] == 0
