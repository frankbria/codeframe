# Quickstart Guide: Review & Polish (Sprint 10)

**Feature**: 015-review-polish
**Target Audience**: Developers implementing Sprint 10 features
**Estimated Time**: 15 minutes to set up development environment

---

## Prerequisites

Before starting Sprint 10 implementation, ensure:

✅ **Sprints 1-9 Complete**:
- Sprint 6 (Human-in-the-Loop) - Blocker system
- Sprint 7 (Context Management) - Context snapshotting
- Sprint 8/9 (Agent Maturity, MVP Completion) - Worker Agent architecture

✅ **Development Environment**:
- Python 3.11+ installed
- Node.js 18+ and npm installed
- Git configured
- Claude API key set (`ANTHROPIC_API_KEY`)

✅ **Dependencies Installed**:
```bash
# Backend
cd /path/to/codeframe
uv venv && source .venv/bin/activate
uv sync

# Frontend
cd web-ui
npm install

# TestSprite MCP (for E2E testing)
# Already configured in MCP settings
```

✅ **Database Initialized**:
```bash
# Check database exists
ls .codeframe/state.db

# Run migrations (if needed)
python -c "from codeframe.persistence.database import Database; db = Database('.codeframe/state.db'); db.initialize()"
```

---

## Quick Start: 5-Minute Demo

### 1. Review Agent Analysis

Trigger a code review for a task:

```bash
# Using CLI
codeframe review task 42

# Using Python API
python3 << 'EOF'
import asyncio
from codeframe.agents.review_agent import ReviewAgent
from codeframe.persistence.database import Database

async def demo():
    db = Database(".codeframe/state.db")
    db.initialize(run_migrations=False)

    agent = ReviewAgent(agent_id="review-001", db=db)
    task = db.get_task(42)

    result = await agent.execute_task(task)
    print(f"Review complete: {len(result.findings)} findings")
    for finding in result.findings[:5]:  # Show first 5
        print(f"  [{finding.severity}] {finding.message}")

asyncio.run(demo())
EOF
```

**Expected Output**:
```
Review complete: 3 findings
  [high] Potential SQL injection in database query
  [medium] Function complexity exceeds threshold (cyclomatic complexity: 15)
  [low] Missing type hints for function parameters
```

---

### 2. Create and Restore Checkpoint

Save and restore project state:

```bash
# Create checkpoint
codeframe checkpoint create "Before async refactor"

# Make some changes...
# (simulate work by modifying a file)
echo "# TODO: refactor" >> codeframe/agents/worker_agent.py
git add . && git commit -m "WIP: async refactor"

# List checkpoints
codeframe checkpoint list

# Restore to checkpoint
codeframe checkpoint restore 1
```

**Expected Output**:
```
✓ Checkpoint created: ID 1, commit a1b2c3d4
  - Database backup: .codeframe/checkpoints/checkpoint-001-db.sqlite
  - Context snapshot: .codeframe/checkpoints/checkpoint-001-context.json

Checkpoints for project 1:
  1. "Before async refactor" (2025-11-21 10:30:00) [commit: a1b2c3d4]

⚠ Restore will revert 1 commit, 12 files changed (+42 -18 lines)
Confirm restore? (y/N): y
✓ Project restored to checkpoint 1
```

---

### 3. View Token Usage and Costs

Check project costs:

```bash
# Using CLI
codeframe metrics costs --project 1

# Using Python API
python3 << 'EOF'
from codeframe.lib.metrics_tracker import MetricsTracker
from codeframe.persistence.database import Database

db = Database(".codeframe/state.db")
db.initialize(run_migrations=False)

tracker = MetricsTracker(db)
costs = tracker.get_project_costs(project_id=1)

print(f"Total cost: ${costs['total_cost_usd']:.2f}")
print("\nCost by agent:")
for agent in costs['by_agent']:
    print(f"  {agent['agent_id']}: ${agent['cost_usd']:.2f}")
EOF
```

**Expected Output**:
```
Total cost: $42.50

Cost by agent:
  backend-001: $25.30
  frontend-001: $12.45
  test-001: $4.75
```

---

### 4. Run E2E Tests (TestSprite)

Execute end-to-end workflow test:

```bash
# Generate E2E tests with TestSprite
cd tests/e2e
testsprite plan --scenario "Full workflow test" --output test_full_workflow.py

# Run E2E tests
pytest test_full_workflow.py -v

# Or use Playwright directly
playwright test
```

**Expected Output**:
```
tests/e2e/test_full_workflow.py::test_discovery_to_completion PASSED
tests/e2e/test_full_workflow.py::test_quality_gates_block_bad_code PASSED
tests/e2e/test_full_workflow.py::test_checkpoint_restore PASSED

3 passed in 45.2s
```

---

## Development Workflow

### Step 1: Choose a User Story

From spec.md, select a user story to implement:

**P0 Stories** (Critical):
- US-1: Review Agent Code Quality Analysis
- US-2: Quality Gates Block Bad Code
- US-3: Checkpoint and Recovery System
- US-4: End-to-End Integration Testing

**P1 Stories** (Enhancement):
- US-5: Metrics and Cost Tracking

---

### Step 2: Write Tests First (TDD)

Following constitution requirement, write tests before implementation:

```bash
# Example: Testing Review Agent
cd tests/agents
touch test_review_agent.py
```

**Example Test** (`tests/agents/test_review_agent.py`):
```python
import pytest
from codeframe.agents.review_agent import ReviewAgent
from codeframe.core.models import Task, TaskStatus

@pytest.mark.asyncio
async def test_review_agent_finds_security_issue(db):
    """Review agent detects SQL injection vulnerability."""
    # Arrange
    agent = ReviewAgent(agent_id="review-001", db=db)
    task = Task(
        id=1,
        project_id=1,
        title="Implement user search",
        description="Search users by name",
        status=TaskStatus.IN_PROGRESS,
        # ... (task contains code with SQL injection)
    )

    # Act
    result = await agent.execute_task(task)

    # Assert
    assert result.status == "blocked"  # Critical issue found
    assert len(result.findings) > 0
    security_findings = [f for f in result.findings if f.category == "security"]
    assert len(security_findings) > 0
    assert "SQL injection" in security_findings[0].message
```

Run test (should FAIL):
```bash
pytest tests/agents/test_review_agent.py -v
# Expected: FAILED (Review Agent not implemented yet)
```

---

### Step 3: Implement Feature

Implement the minimum code to make tests pass:

```bash
# Example: Review Agent implementation
cd codeframe/agents
touch review_agent.py
```

**Example Implementation** (`codeframe/agents/review_agent.py`):
```python
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import Task, TaskResult
from typing import List

class ReviewAgent(WorkerAgent):
    """Worker agent that performs code review using Claude Code skill."""

    async def execute_task(self, task: Task) -> TaskResult:
        # 1. Get changed files from task
        files = await self._get_changed_files(task)

        # 2. Analyze each file using reviewing-code skill
        all_findings = []
        for file in files:
            findings = await self._review_file(file)
            all_findings.extend(findings)

        # 3. Determine if critical issues found
        has_critical = any(f.severity in ["critical", "high"] for f in all_findings)

        # 4. Return result
        return TaskResult(
            status="blocked" if has_critical else "completed",
            findings=all_findings
        )

    async def _review_file(self, file) -> List[CodeReview]:
        # TODO: Invoke reviewing-code skill
        # TODO: Parse findings
        # TODO: Save to database
        pass
```

Run test (should PASS):
```bash
pytest tests/agents/test_review_agent.py -v
# Expected: PASSED
```

---

### Step 4: Add Database Migrations

Add new tables/columns:

```bash
# Create migration file
cd codeframe/persistence
touch migration_010_sprint10.py
```

**Example Migration** (`migration_010_sprint10.py`):
```python
def upgrade(conn):
    """Add Sprint 10 tables and columns."""
    cursor = conn.cursor()

    # Add code_reviews table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS code_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            agent_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add quality_gate_status to tasks
    cursor.execute("""
        ALTER TABLE tasks ADD COLUMN quality_gate_status TEXT
        CHECK(quality_gate_status IN ('pending', 'running', 'passed', 'failed'))
        DEFAULT 'pending'
    """)

    conn.commit()

def downgrade(conn):
    """Rollback Sprint 10 changes."""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS code_reviews")
    # Note: SQLite doesn't support DROP COLUMN, would need full table rebuild
    conn.commit()
```

Run migration:
```python
from codeframe.persistence.database import Database
db = Database(".codeframe/state.db")
db.initialize(run_migrations=True)
```

---

### Step 5: Add API Endpoints

Expose functionality via FastAPI:

```bash
cd codeframe/ui
# Edit server.py or create new endpoint file
```

**Example Endpoint** (`codeframe/ui/server.py`):
```python
@app.post("/api/agents/review/analyze")
async def trigger_code_review(request: CodeReviewRequest):
    """Trigger code review for a task."""
    review_agent = ReviewAgent(agent_id="review-001", db=db)
    task = db.get_task(request.task_id)

    # Start review in background
    asyncio.create_task(review_agent.execute_task(task))

    return {
        "message": f"Code review started for task {request.task_id}",
        "review_job_id": f"review-{request.task_id}-{int(time.time())}"
    }

@app.get("/api/tasks/{task_id}/reviews")
async def get_task_reviews(task_id: int, severity: Optional[str] = None):
    """Get code review findings for a task."""
    reviews = db.get_code_reviews(task_id=task_id, severity=severity)
    return {
        "task_id": task_id,
        "total_findings": len(reviews),
        "findings": [r.dict() for r in reviews]
    }
```

Test endpoint:
```bash
# Start server
uvicorn codeframe.ui.server:app --reload

# Test API
curl -X POST http://localhost:8000/api/agents/review/analyze \
  -H "Content-Type: application/json" \
  -d '{"task_id": 42, "project_id": 1}'
```

---

### Step 6: Add Frontend Components

Create React components for dashboard:

```bash
cd web-ui/src/components
mkdir reviews
cd reviews
touch ReviewFindings.tsx ReviewSummary.tsx
```

**Example Component** (`ReviewFindings.tsx`):
```tsx
import React, { useEffect, useState } from 'react';
import { getTaskReviews } from '../../api/reviews';
import type { CodeReview } from '../../types/reviews';

export function ReviewFindings({ taskId }: { taskId: number }) {
  const [findings, setFindings] = useState<CodeReview[]>([]);

  useEffect(() => {
    getTaskReviews(taskId).then(data => setFindings(data.findings));
  }, [taskId]);

  return (
    <div className="review-findings">
      <h3>Code Review Findings ({findings.length})</h3>
      {findings.map(finding => (
        <div key={finding.id} className={`finding severity-${finding.severity}`}>
          <span className="severity">{finding.severity}</span>
          <span className="message">{finding.message}</span>
          {finding.recommendation && (
            <p className="recommendation">{finding.recommendation}</p>
          )}
        </div>
      ))}
    </div>
  );
}
```

Test component:
```bash
cd web-ui
npm test -- ReviewFindings.test.tsx
```

---

### Step 7: Integration Testing

Test full workflow:

```bash
# Run integration tests
pytest tests/integration/test_sprint10_integration.py -v

# Run E2E tests with TestSprite
cd tests/e2e
testsprite update --test test_full_workflow.py
playwright test
```

---

## Common Tasks

### Add New Code Review Category

1. Update `ReviewCategory` enum in `core/models.py`
2. Update database CHECK constraint for `category` column
3. Update API spec in `contracts/api-spec.yaml`
4. Update frontend TypeScript types in `web-ui/src/types/reviews.ts`

### Add New Quality Gate

1. Implement gate check in `lib/quality_gates.py`
2. Add to `QualityGateType` enum in `core/models.py`
3. Call from `WorkerAgent.complete_task()` pre-completion hook
4. Add tests in `tests/lib/test_quality_gates.py`

### Customize Token Pricing

Edit model pricing in `lib/metrics_tracker.py`:
```python
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "custom-model": {"input": 5.00, "output": 20.00},  # Add new model
}
```

---

## Debugging Tips

### Review Agent Not Finding Issues

Check:
1. Task has code files attached: `db.get_task_files(task_id)`
2. Reviewing-code skill is available: Check Claude Code skills
3. Review agent has correct permissions: Check agent config

### Checkpoint Restore Fails

Check:
1. Checkpoint files exist: `ls .codeframe/checkpoints/`
2. Git commit exists: `git log --oneline | grep <commit-sha>`
3. Database backup is valid: `sqlite3 checkpoint-XXX-db.sqlite ".tables"`

### Metrics Show $0.00 Costs

Check:
1. Token usage records exist: `db.get_token_usage(project_id=1)`
2. Model name matches pricing table: Check `model_name` in records
3. Tokens are non-zero: Check `input_tokens`, `output_tokens`

---

## Next Steps

After completing Sprint 10:

1. **Run Full Test Suite**: `pytest && npm test`
2. **Update Documentation**: Update README.md, CLAUDE.md
3. **Create Demo Video**: Record 8-hour autonomous session
4. **Prepare Sprint Review**: Document MVP completion metrics
5. **Plan Sprint 11**: Production deployment, monitoring, scaling

---

## Resources

- **Spec**: [spec.md](./spec.md) - Full feature specification
- **Data Model**: [data-model.md](./data-model.md) - Database schema and Pydantic models
- **API Contracts**: [contracts/api-spec.yaml](./contracts/api-spec.yaml) - OpenAPI spec
- **Research**: [research.md](./research.md) - Architecture decisions
- **Constitution**: `.specify/memory/constitution.md` - Development principles
- **TestSprite Docs**: https://testsprite.dev/docs (E2E testing)
- **Claude Code Skills**: https://docs.claude.com/skills/reviewing-code

---

## Getting Help

- **Issues**: Check beads issue tracker (`bd list`)
- **Questions**: Create ASYNC blocker for human input
- **Bugs**: Run `pytest tests/ -v --tb=short` for details
- **Documentation**: See `AGENTS.md` for navigation guide

**Good luck building Sprint 10! 🚀**
