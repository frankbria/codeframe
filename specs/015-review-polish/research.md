# Research: Review & Polish (Sprint 10)

**Feature**: 015-review-polish
**Date**: 2025-11-21
**Researchers**: AI Planning Agent

## Research Questions

Based on Technical Context and spec.md, the following architecture decisions require research:

1. **Review Agent Type**: Specialized worker vs. subprocess reviewer vs. Claude Code skill wrapper
2. **Quality Gate Triggers**: Pre-commit, pre-merge, pre-completion, or combination
3. **Checkpoint Format**: Full state dump vs. incremental snapshots
4. **Cost Tracking**: Real-time per-request vs. batch aggregation
5. **TestSprite Integration**: Best practices for E2E test generation and maintenance

## Research Findings

### R1: Review Agent Implementation Strategy

**Decision**: **Hybrid Approach - Use Claude Code `reviewing-code` skill wrapped in custom Worker Agent**

**Rationale**:
- Claude Code already has a production-quality `reviewing-code` skill (per CLAUDE.md and available skills)
- No need to reinvent code review logic (security patterns, complexity analysis, best practices)
- Custom Worker Agent wrapper provides:
  - Integration with CodeFRAME's multi-agent architecture
  - Database persistence for review findings
  - WebSocket broadcasting for dashboard updates
  - Quality gate integration

**Alternatives Considered**:
1. **Full custom implementation**: Rejected - duplicates work, lower quality than Claude's built-in skill
2. **Direct skill invocation**: Rejected - doesn't integrate with worker architecture, no persistence
3. **Third-party tools (SonarQube, Semgrep)**: Rejected for MVP - adds external dependencies, out of scope

**Implementation Approach**:
```python
class ReviewAgent(WorkerAgent):
    """Worker agent that wraps Claude Code reviewing-code skill."""

    async def execute_task(self, task: Task) -> TaskResult:
        # 1. Get code files from task
        files = self._get_changed_files(task)

        # 2. Invoke reviewing-code skill for each file
        for file in files:
            review_result = await self._invoke_skill(
                skill="reviewing-code",
                context=file.content,
                focus_areas=["security", "performance", "quality"]
            )

            # 3. Parse and persist findings
            findings = self._parse_review_findings(review_result)
            await self.db.save_code_reviews(task.id, findings)

        # 4. Determine if critical issues found
        has_critical = any(f.severity == "critical" for f in findings)

        return TaskResult(
            status="blocked" if has_critical else "completed",
            findings=findings
        )
```

**References**:
- CLAUDE.md mentions `reviewing-code` skill available
- Constitution Section V requires observability (database persistence)
- Worker Agent pattern established in Sprint 5 (cf-048)

---

### R2: Quality Gate Enforcement Points

**Decision**: **Pre-completion hooks with multi-stage gates**

**Rationale**:
- Quality gates must run **before marking task complete** to prevent bad code from being "done"
- Multi-stage approach catches issues at different levels:
  1. **Unit tests**: Fast feedback (<10s), catches regressions
  2. **Type checking**: Fast (<30s), catches type errors
  3. **Code review**: Slower (<2min), catches quality/security issues
  4. **Coverage check**: Fast (<10s), ensures adequate testing
- Pre-commit hooks are too early (blocks developer iteration)
- Pre-merge hooks are too late (bad code already marked complete)

**Implementation Approach**:
```python
# In WorkerAgent.complete_task()
async def complete_task(self, task: Task) -> TaskResult:
    # Stage 1: Run tests
    test_result = await self._run_tests(task)
    if not test_result.passed:
        return self._create_blocker(task, "Tests failed", test_result)

    # Stage 2: Type checking
    type_result = await self._run_type_check(task)
    if not type_result.passed:
        return self._create_blocker(task, "Type errors", type_result)

    # Stage 3: Coverage check
    coverage = await self._check_coverage(task)
    if coverage < 0.85:
        return self._create_blocker(task, f"Coverage {coverage}% < 85%")

    # Stage 4: Code review (Review Agent)
    review_result = await self._trigger_review_agent(task)
    if review_result.has_critical_issues:
        return self._create_blocker(task, "Critical review findings", review_result)

    # All gates passed
    return TaskResult(status="completed")
```

**Gate Bypass for Human Approval**:
- Risky changes (schema migrations, API contract changes) require manual approval
- Add `requires_human_approval` flag to task
- Quality gates still run, but create ASYNC blocker instead of auto-blocking

**Alternatives Considered**:
1. **Pre-commit hooks**: Rejected - too early, blocks iteration
2. **Pre-merge only**: Rejected - too late, bad code already "done"
3. **Continuous background checks**: Rejected - too complex for MVP, resource intensive

**References**:
- Constitution Section I (Test-First Development) requires tests before completion
- Blocker system from cf-049 (Human-in-the-Loop)
- Task status model supports "blocked" state (database.py:114)

---

### R3: Checkpoint Storage Format

**Decision**: **Hybrid format - JSON snapshot + SQLite backup + git commit**

**Rationale**:
- **JSON for metadata**: Lightweight, human-readable, easy to version
- **SQLite backup for data**: Full database snapshot, ensures data integrity
- **Git commit for code**: Built-in versioning, diff support, proven reliability
- Incremental snapshots add complexity without significant benefit for MVP

**Checkpoint Structure**:
```json
{
  "checkpoint_id": 42,
  "name": "Before refactoring agent coordination",
  "created_at": "2025-11-21T10:30:00Z",
  "git_commit": "a1b2c3d4e5f6",
  "database_backup": ".codeframe/checkpoints/checkpoint-042-db.sqlite",
  "context_snapshot": ".codeframe/checkpoints/checkpoint-042-context.json",
  "metadata": {
    "project_id": 1,
    "phase": "active",
    "tasks_completed": 27,
    "tasks_total": 40,
    "agents_active": ["backend-001", "frontend-001"],
    "last_task_completed": "Implement JWT refresh tokens"
  }
}
```

**Storage Layout**:
```
.codeframe/checkpoints/
├── checkpoint-001.json           # Metadata
├── checkpoint-001-db.sqlite      # Full DB snapshot
├── checkpoint-001-context.json   # Context items snapshot
├── checkpoint-002.json
├── checkpoint-002-db.sqlite
├── checkpoint-002-context.json
└── ...
```

**Restore Process**:
1. Validate checkpoint exists and is complete (all 3 files present)
2. Show diff: `git diff <current> <checkpoint-commit>`
3. Confirm with user
4. Checkout git commit: `git checkout <commit-sha>`
5. Restore database: Copy `checkpoint-XXX-db.sqlite` → `state.db`
6. Restore context: Load context items into `context_items` table
7. Verify integrity: Check task counts, agent states match metadata

**Alternatives Considered**:
1. **Git-only**: Rejected - doesn't capture database state, context items
2. **Incremental snapshots**: Rejected - complex to implement, reconstruct overhead
3. **Full tar.gz archives**: Rejected - opaque, hard to inspect, slow

**References**:
- Database schema has `checkpoints` table (database.py:236-248)
- Context items from cf-007 (context_items table:219-234)
- Session lifecycle from cf-014 (session state restoration patterns)

---

### R4: Token and Cost Tracking Strategy

**Decision**: **Hybrid tracking - Real-time recording + batch aggregation for queries**

**Rationale**:
- **Real-time recording**: Capture tokens immediately after each LLM call for accuracy
- **Batch aggregation**: Pre-calculate aggregates (per-agent, per-day) for dashboard performance
- Best of both worlds: Accurate data + fast queries

**Data Model**:
```python
# Real-time recording (inserted on every LLM call)
class TokenUsage(BaseModel):
    id: int
    task_id: int
    agent_id: str
    model_name: str          # e.g., "claude-sonnet-4-5"
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    timestamp: datetime

# Batch aggregation (calculated hourly via background job)
class TokenUsageAggregate(BaseModel):
    id: int
    project_id: int
    agent_id: str
    date: date
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
```

**Token Counting Strategy**:
- Use **tiktoken** library (already used in cf-007 for context management)
- Count tokens **before API call** for estimates
- Record **actual tokens from API response headers** (more accurate)
- Formula: `cost = (input_tokens * input_price + output_tokens * output_price) / 1_000_000`

**Model Pricing (as of 2025-11)**:
```python
MODEL_PRICING = {
    "claude-sonnet-4-5": {
        "input_usd_per_mtok": 3.00,
        "output_usd_per_mtok": 15.00
    },
    "claude-opus-4": {
        "input_usd_per_mtok": 15.00,
        "output_usd_per_mtok": 75.00
    },
    "claude-haiku-4": {
        "input_usd_per_mtok": 0.80,
        "output_usd_per_mtok": 4.00
    }
}
```

**Dashboard Query Optimization**:
- Use aggregates for overview charts (total cost, cost over time)
- Use raw records for detailed drill-down (per-task breakdown)
- Cache dashboard data for 30 seconds (WebSocket updates trigger refresh)

**Alternatives Considered**:
1. **Batch-only recording**: Rejected - loses per-task granularity
2. **Real-time aggregation**: Rejected - slow queries, doesn't scale
3. **External analytics service**: Rejected - adds dependency, privacy concerns

**References**:
- Tasks table already has `estimated_tokens`, `actual_tokens` columns (database.py:122-123)
- Token counting from cf-007 uses tiktoken (lib/token_counter.py)
- Dashboard WebSocket pattern established in cf-009

---

### R5: TestSprite E2E Testing Integration

**Decision**: **Use TestSprite MCP for test generation, Playwright for execution**

**Rationale**:
- **TestSprite** excels at generating E2E test plans and code from natural language
- **Playwright** is industry-standard for browser automation, already used in codebase (per CLAUDE.md)
- Combination provides: AI-generated tests + reliable execution framework
- TestSprite MCP already available (per skill list: `testsprite-skill`)

**E2E Test Scenarios** (TestSprite inputs):
1. **Full workflow**: Discovery → Planning → Execution → Completion
   - User creates project
   - Answers Socratic questions
   - Agents execute tasks
   - Dashboard shows progress
   - Project completes successfully

2. **Quality gates**: Task completion with test failures
   - Backend agent completes task
   - Tests fail
   - Quality gate blocks completion
   - Blocker created
   - Dashboard shows blocked task

3. **Checkpoint/restore**: Create checkpoint and restore
   - Project at 50% completion
   - Create checkpoint
   - Continue work to 75%
   - Restore checkpoint
   - Verify restored to 50% state

4. **Review agent**: Code review finds critical issue
   - Backend agent completes code change
   - Review agent analyzes code
   - Critical security issue found
   - Task blocked
   - Dashboard shows review findings

**TestSprite Workflow**:
```bash
# 1. Initialize TestSprite
testsprite init --project codeframe --type backend

# 2. Generate test plan from scenario
testsprite plan --scenario "Full workflow E2E test" --output tests/e2e/test_full_workflow.py

# 3. Execute tests
playwright test tests/e2e/

# 4. Maintain tests (on code changes)
testsprite update --test tests/e2e/test_full_workflow.py --changes "Added checkpoint UI"
```

**Test Data Strategy**:
- **Fixtures**: Small realistic project (REST API with 3-4 endpoints)
- **Mock LLM calls**: Use recorded responses for fast, deterministic tests
- **Database seeding**: Pre-populate tasks, agents for specific test scenarios
- **Cleanup**: Reset database, git repo after each test

**Alternatives Considered**:
1. **Manual E2E tests**: Rejected - time-consuming, hard to maintain
2. **Selenium**: Rejected - Playwright is modern standard, better async support
3. **Cypress**: Rejected - Playwright has better Python integration

**References**:
- TestSprite MCP available (see CLAUDE.md)
- Playwright already used for frontend testing (CLAUDE.md mentions Playwright)
- E2E test requirements in spec.md US-4

---

## Research Summary

All architecture decisions resolved. No NEEDS CLARIFICATION remaining.

**Key Decisions**:
1. **Review Agent**: Wrap Claude Code `reviewing-code` skill in Worker Agent
2. **Quality Gates**: Pre-completion multi-stage hooks (tests → types → coverage → review)
3. **Checkpoints**: Hybrid JSON + SQLite + git format
4. **Cost Tracking**: Real-time recording + batch aggregation
5. **E2E Testing**: TestSprite for generation + Playwright for execution

**Ready for Phase 1**: Design & Contracts (data models, API contracts, quickstart)
