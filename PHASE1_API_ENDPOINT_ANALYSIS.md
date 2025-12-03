# Phase 1: API Endpoint Analysis - E2E Test Data Seeding

**Date**: 2025-12-03
**Status**: ✅ Complete

## Executive Summary

Analysis of CodeFRAME API endpoints reveals that **direct database seeding via Python script is the optimal approach** rather than API-based seeding. Many required "create" endpoints don't exist, as data is typically created internally by agents during normal operation.

## API Endpoint Findings

### ✅ Endpoints That Exist

1. **Projects** - `POST /api/projects` (Line 310)
   - Creates new project
   - Already used by global-setup.ts ✅

2. **Checkpoints** - `POST /api/projects/{project_id}/checkpoints` (Line 2908)
   - Creates checkpoint
   - Already used by global-setup.ts ✅

3. **Project Agents** - `POST /api/projects/{project_id}/agents` (Line 476)
   - Assigns agent to project
   - Requires agent to exist first

4. **Context** - `POST /api/agents/{agent_id}/context` (Line 1601)
   - Saves context items
   - Not needed for basic test data

5. **Reviews** - `POST /api/agents/{agent_id}/review` (Line 1939)
   - Triggers code review
   - May not support direct review creation

6. **Quality Gates** - `POST /api/tasks/{task_id}/quality-gates` (Line 2571)
   - Triggers quality gate checks
   - May not support direct gate result creation

### ❌ Endpoints That DON'T Exist

1. **Agents** - `POST /api/agents`
   - **Missing**: No endpoint to create agents directly
   - **Why**: Agents are created internally by Lead Agent
   - **Impact**: Cannot seed agents via API

2. **Tasks** - `POST /api/tasks`
   - **Missing**: No endpoint to create tasks directly
   - **Why**: Tasks are created internally during discovery/planning
   - **Impact**: Cannot seed tasks via API

3. **Token Usage** - `POST /api/token-usage` or `/api/projects/{id}/metrics/tokens`
   - **Missing**: No endpoint to record token usage directly
   - **Why**: Token usage is recorded automatically after LLM calls
   - **Impact**: Cannot seed metrics data via API

4. **Review Reports** - `POST /api/reviews` or `/api/projects/{id}/reviews`
   - **Uncertain**: May exist but not confirmed
   - **Impact**: Cannot reliably seed review data via API

5. **Quality Gate Results** - `POST /api/quality-gates`
   - **Missing**: No endpoint to create gate results directly
   - **Why**: Results are created by quality gate checks
   - **Impact**: Cannot seed gate results via API

6. **Activity Feed** - `POST /api/activity` or `/api/projects/{id}/activity`
   - **Missing**: No endpoint to add activity events
   - **Why**: Activity is derived from database triggers/events
   - **Impact**: Cannot seed activity via API

## Database Methods Available

From `codeframe/persistence/database.py`:

### ✅ Methods That Support Direct Data Creation

1. **`create_agent(agent_id, agent_type, ...)`** (Line 1169)
   - Directly inserts agent into `agents` table
   - ✅ Can use for seeding

2. **`create_task(task: Task)`** (Line 653)
   - Directly inserts task into `tasks` table
   - ✅ Can use for seeding

3. **`save_token_usage(token_usage: TokenUsage)`** (Line 3424)
   - Directly inserts token usage into `token_usage` table
   - ✅ Can use for seeding

4. **`save_code_review(review: CodeReview)`** (Line 2993)
   - Directly inserts review into `code_reviews` table
   - ✅ Can use for seeding

5. **`update_quality_gate_status(...)`** (Line 3120)
   - Updates quality gate results in database
   - ✅ Can use for seeding

6. **`assign_agent_to_project(project_id, agent_id, role)`** (from multi-agent PR)
   - Creates project-agent assignment in `project_agents` table
   - ✅ Can use for seeding

7. **`get_recent_activity(project_id, limit)`** (Line 2510)
   - Reads activity from database
   - ❓ Activity generation method unknown

## Recommended Seeding Strategy

### ✅ Option A: Direct Database Seeding (RECOMMENDED)

**Approach**: Create Python script `tests/e2e/seed-test-data.py` that:
1. Opens SQLite database directly
2. Uses database methods (`create_agent`, `create_task`, etc.)
3. Inserts all required test data
4. Called from `global-setup.ts` via `execSync`

**Pros**:
- ✅ Works with existing codebase (no new endpoints needed)
- ✅ Fast execution (<5 seconds)
- ✅ Direct control over data
- ✅ Already structured in global-setup.ts (line 37)

**Cons**:
- ⚠️ Bypasses API layer (but acceptable for tests)
- ⚠️ Requires Python script maintenance

**Implementation**:
```python
# tests/e2e/seed-test-data.py
import sys
import sqlite3
from codeframe.persistence.database import Database
from codeframe.core.models import Task, Agent, etc.

def seed_data(db_path: str, project_id: int):
    db = Database(db_path)

    # Seed agents
    db.create_agent(...)

    # Seed tasks
    task = Task(...)
    db.create_task(task)

    # Seed token usage
    usage = TokenUsage(...)
    db.save_token_usage(usage)

    # etc.
```

### ❌ Option B: API-Based Seeding (NOT VIABLE)

**Approach**: Use API endpoints to create data

**Blockers**:
- ❌ Most required endpoints don't exist
- ❌ Would require creating 6-8 new API endpoints
- ❌ Significant development effort (8-12 hours)
- ❌ Not justified for test-only functionality

## Current State of global-setup.ts

The existing `tests/e2e/global-setup.ts` file:

✅ **Already Implemented**:
- Creates/reuses test project via API (lines 782-815)
- Has seeding functions written (lines 65-768):
  - `seedAgents()` - Ready but not called
  - `seedTasks()` - Ready but not called
  - `seedTokenUsage()` - Ready but not called
  - `seedCheckpoints()` - Ready and CALLED (line 828)
  - `seedReviews()` - Ready but not called
- Calls `seedDatabaseDirectly()` function (line 822)
- Expects Python script at `tests/e2e/seed-test-data.py` (line 44)

⚠️ **Missing**:
- The Python script `tests/e2e/seed-test-data.py` doesn't exist yet

## Next Steps (Phase 2)

1. **Create `tests/e2e/seed-test-data.py`** that:
   - Accepts `db_path` and `project_id` as arguments
   - Opens SQLite database
   - Seeds all required data:
     - 5 agents (lead, backend, frontend, test, review)
     - 10 tasks (3 completed, 2 in-progress, 2 blocked, 3 pending)
     - 15 token usage records (Sonnet, Opus, Haiku)
     - 2 review reports (1 approved, 1 changes_requested)
     - 2 quality gate results
     - Project-agent assignments
   - Prints progress to stdout

2. **Test locally** with Chromium:
   ```bash
   cd tests/e2e
   npx playwright test --project=chromium
   ```

3. **Expected outcome**: 40-50% test pass rate (4-5 more tests passing)

## Validation Checklist

- ✅ Reviewed GitHub Actions failure logs (last 5 runs all failed)
- ✅ Confirmed test infrastructure works (navigation, project creation)
- ✅ Analyzed API endpoints (checkpoints exist, others don't)
- ✅ Verified database methods support direct seeding
- ✅ Confirmed global-setup.ts structure is correct
- ✅ Identified missing Python script as blocker

## Summary

**Finding**: Direct database seeding via Python script is the correct approach.

**Rationale**:
1. Most create endpoints don't exist (agents, tasks, token usage, etc.)
2. Database methods exist and support direct data creation
3. global-setup.ts already expects this approach (line 37)
4. Fastest path to 90-100% test pass rate

**Action**: Proceed to Phase 2 - Create `seed-test-data.py` script
