# FastAPI Router Refactoring - Phase 1 Analysis Report

**Date:** 2025-12-11
**Analyzer:** Claude Code
**File Analyzed:** `/home/frankbria/projects/codeframe/codeframe/ui/server.py`
**Total Lines:** 4,161 lines

---

## Executive Summary

The `server.py` file contains **60+ endpoints** organized into 8 logical groups, with significant shared state and helper functions. The file has grown to 4,161 lines, making it a prime candidate for modular extraction into separate router files.

**Key Findings:**
- 8 distinct endpoint groups identified
- 3 shared state objects (ConnectionManager, running_agents, review_cache)
- 20+ inline imports indicating circular dependency avoidance patterns
- Largest endpoints exceed 150 lines of code
- Multiple utility functions shared across endpoint groups

---

## 1. Endpoint Groups

### 1.1 Projects Group (26 endpoints)
**Purpose:** Core project lifecycle management, CRUD operations, and project-level queries

**Endpoints:**
```
GET    /api/projects                                    # List all projects
POST   /api/projects                                    # Create project (130 LOC)
POST   /api/projects/{project_id}/start                 # Start lead agent
GET    /api/projects/{project_id}/status                # Get project status
POST   /api/projects/{project_id}/pause                 # Pause project
POST   /api/projects/{project_id}/resume                # Resume project
GET    /api/projects/{project_id}/tasks                 # List tasks
GET    /api/projects/{project_id}/activity              # Activity log
GET    /api/projects/{project_id}/issues                # List issues
GET    /api/projects/{project_id}/blockers              # List blockers
GET    /api/projects/{project_id}/blockers/metrics      # Blocker metrics
GET    /api/projects/{project_id}/prd                   # Get PRD document
GET    /api/projects/{project_id}/session               # Session state (014-session-lifecycle)

# Project-Agent Assignment (Phase 3 Multi-Agent)
GET    /api/projects/{project_id}/agents                # List agents on project
POST   /api/projects/{project_id}/agents                # Assign agent to project
DELETE /api/projects/{project_id}/agents/{agent_id}     # Remove agent from project
PUT    /api/projects/{project_id}/agents/{agent_id}/role # Update agent role
PATCH  /api/projects/{project_id}/agents/{agent_id}     # Update agent role (alt)

# Discovery (Feature 012-discovery-answer-ui)
POST   /api/projects/{project_id}/discovery/answer      # Submit discovery answer (129 LOC)
GET    /api/projects/{project_id}/discovery/progress    # Discovery progress (80 LOC)

# Chat Interface
POST   /api/projects/{project_id}/chat                  # Chat with lead agent (71 LOC)
GET    /api/projects/{project_id}/chat/history          # Chat history

# Checkpoints (Sprint 10, User Story 3)
GET    /api/projects/{project_id}/checkpoints           # List checkpoints (76 LOC)
POST   /api/projects/{project_id}/checkpoints           # Create checkpoint (103 LOC)
GET    /api/projects/{project_id}/checkpoints/{id}      # Get checkpoint (74 LOC)
DELETE /api/projects/{project_id}/checkpoints/{id}      # Delete checkpoint (69 LOC)
POST   /api/projects/{project_id}/checkpoints/{id}/restore # Restore checkpoint (112 LOC)
GET    /api/projects/{project_id}/checkpoints/{id}/diff # Checkpoint diff (164 LOC)

# Metrics & Costs (Sprint 10, User Story 5)
GET    /api/projects/{project_id}/metrics/tokens        # Token usage (108 LOC)
GET    /api/projects/{project_id}/metrics/costs         # Cost metrics (81 LOC)

# Review (Sprint 9)
GET    /api/projects/{project_id}/code-reviews          # List code reviews (145 LOC)
GET    /api/projects/{project_id}/review-stats          # Review statistics (66 LOC)
```

**Shared State Dependencies:**
- `running_agents` (read/write) - agent lifecycle
- `app.state.db` (read/write) - all operations
- `app.state.workspace_manager` (read) - workspace creation
- `manager` (ConnectionManager) - WebSocket broadcasts

**Key Characteristics:**
- Heaviest endpoint group (26 endpoints)
- Multiple inline imports (LeadAgent, SessionManager, CheckpointManager, MetricsTracker)
- Significant business logic (discovery, checkpoints, metrics)

---

### 1.2 Agents Group (12 endpoints)
**Purpose:** Agent-specific operations (context, reviews, metrics)

**Endpoints:**
```
GET    /api/agents/{agent_id}/projects                  # List projects for agent

# Context Management (007-context-management)
GET    /api/agents/{agent_id}/context                   # List context items
POST   /api/agents/{agent_id}/context                   # Create context item (not shown, assumed)
DELETE /api/agents/{agent_id}/context/{item_id}         # Delete context item
GET    /api/agents/{agent_id}/context/stats             # Context statistics (75 LOC)
GET    /api/agents/{agent_id}/context/items             # Context items (paginated)
POST   /api/agents/{agent_id}/context/update-scores     # Update importance scores
POST   /api/agents/{agent_id}/context/update-tiers      # Update tiers (HOT/WARM/COLD)

# Flash Save (007-context-management)
POST   /api/agents/{agent_id}/flash-save                # Trigger flash save (60 LOC)
GET    /api/agents/{agent_id}/flash-save/checkpoints    # List flash save checkpoints

# Review (Sprint 9)
POST   /api/agents/{agent_id}/review                    # Trigger review (127 LOC)
POST   /api/agents/review/analyze                       # Analyze code review (58 LOC)

# Metrics (Sprint 10, User Story 5)
GET    /api/agents/{agent_id}/metrics                   # Agent-specific metrics (127 LOC)
```

**Shared State Dependencies:**
- `app.state.db` (read/write) - all operations
- `review_cache` (read/write) - review reports

**Key Characteristics:**
- Heavy use of ContextManager (inline import)
- Review operations cache results in `review_cache`
- Token counting and metrics tracking

---

### 1.3 Tasks Group (4 endpoints)
**Purpose:** Task-specific operations (quality gates, reviews)

**Endpoints:**
```
# Quality Gates (Sprint 10, User Story 2)
GET    /api/tasks/{task_id}/quality-gates               # Get quality gate status
POST   /api/tasks/{task_id}/quality-gates               # Trigger quality gates (104 LOC)

# Review (Sprint 9)
GET    /api/tasks/{task_id}/review-status               # Review status
GET    /api/tasks/{task_id}/reviews                     # List task reviews (138 LOC)
```

**Shared State Dependencies:**
- `app.state.db` (read/write) - all operations
- `review_cache` (read) - review status lookup

**Key Characteristics:**
- Quality gates run tests, type checks, coverage checks, code review
- Inline imports: QualityGates, Task, ReviewAgent

---

### 1.4 Blockers Group (2 endpoints)
**Purpose:** Blocker management (human-in-the-loop)

**Endpoints:**
```
GET    /api/blockers/{blocker_id}                       # Get blocker details
POST   /api/blockers/{blocker_id}/resolve               # Resolve blocker (79 LOC)
```

**Shared State Dependencies:**
- `app.state.db` (read/write) - all operations
- `manager` (ConnectionManager) - WebSocket broadcasts on resolve

**Key Characteristics:**
- Simple CRUD operations
- WebSocket integration for real-time updates

---

### 1.5 Lint Group (4 endpoints)
**Purpose:** Linting operations (code quality checks)

**Endpoints:**
```
GET    /api/lint/results                                # Get lint results
GET    /api/lint/trend                                  # Lint trend (historical)
GET    /api/lint/config                                 # Lint configuration
POST   /api/lint/run                                    # Run lint manually (138 LOC)
```

**Shared State Dependencies:**
- `app.state.db` (read/write) - all operations

**Key Characteristics:**
- Inline import: LintRunner
- WebSocket broadcasts on lint completion
- Could be moved to a separate linting service

---

### 1.6 Root Group (3 endpoints)
**Purpose:** Health checks, WebSocket, entry points

**Endpoints:**
```
GET       /                                             # Health check (simple)
GET       /health                                       # Detailed health check
WEBSOCKET /ws                                          # WebSocket connection
```

**Shared State Dependencies:**
- `manager` (ConnectionManager) - WebSocket management
- `app.state.db` (read) - health check

**Key Characteristics:**
- Entry points and infrastructure
- WebSocket endpoint handles ping/pong and subscriptions
- Background task `broadcast_updates()` (line 4119)

---

### 1.7 Session Group (1 endpoint)
**Purpose:** Session lifecycle management (Feature 014-session-lifecycle)

**Endpoints:**
```
GET    /api/projects/{project_id}/session               # Get session state (77 LOC)
```

**Note:** This is already covered under Projects Group but logically separate.

**Shared State Dependencies:**
- `app.state.db` (read) - session state retrieval

**Key Characteristics:**
- Inline import: SessionManager
- Could be merged into Projects router

---

### 1.8 Context Group (Embedded in Agents)
**Purpose:** Context management API (Feature 007-context-management)

**Note:** Context endpoints are already listed under Agents Group (section 1.2).

---

## 2. Shared State

### 2.1 ConnectionManager Instance
**Location:** Line 169
**Type:** `ConnectionManager` class instance
**Purpose:** Manages WebSocket connections for real-time updates

```python
manager = ConnectionManager()
```

**Used By:**
- WebSocket endpoint (`/ws`)
- `start_agent()` utility function
- Project start/chat/discovery endpoints (broadcasts)
- Blocker resolution (broadcasts)
- Lint completion (broadcasts)

**Access Pattern:**
- Read: `manager.active_connections` (implicit)
- Write: `manager.connect()`, `manager.disconnect()`, `manager.broadcast()`

**Refactoring Strategy:**
- **Option A:** Pass as dependency injection (FastAPI Depends)
- **Option B:** Store in `app.state.manager` (similar to `app.state.db`)
- **Recommendation:** Option B (consistency with existing patterns)

---

### 2.2 running_agents Dictionary
**Location:** Line 172
**Type:** `Dict[int, LeadAgent]`
**Purpose:** Tracks active Lead Agents by project_id

```python
running_agents: Dict[int, LeadAgent] = {}
```

**Used By:**
- `start_agent()` utility function (write)
- `start_project_agent()` endpoint (read - via `start_agent()`)
- `chat_with_lead()` endpoint (read)

**Access Pattern:**
- Write: `running_agents[project_id] = agent` (in `start_agent()`)
- Read: `agent = running_agents.get(project_id)` (in `chat_with_lead()`)

**Refactoring Strategy:**
- **Option A:** Move to `app.state.running_agents`
- **Option B:** Create AgentRegistry service class
- **Recommendation:** Option A (simple, matches existing patterns)

---

### 2.3 review_cache Dictionary
**Location:** Line 175
**Type:** `Dict[int, dict]`
**Purpose:** Cache review reports by task_id (Sprint 9)

```python
review_cache: Dict[int, dict] = {}
```

**Used By:**
- `trigger_review()` endpoint (write)
- `get_review_status()` endpoint (read)
- `get_task_reviews()` endpoint (read, fallback)

**Access Pattern:**
- Write: `review_cache[task_id] = review_report` (in `trigger_review()`)
- Read: `review_cache.get(task_id)` (in `get_review_status()`)

**Refactoring Strategy:**
- **Option A:** Move to `app.state.review_cache`
- **Option B:** Replace with database-backed cache (redis, or database queries)
- **Recommendation:** Option A (short-term), Option B (long-term for multi-instance scaling)

---

### 2.4 app.state Objects
**Lifecycle:** Managed by `lifespan()` context manager (lines 81-108)

#### app.state.db
**Type:** `Database`
**Initialization:** Line 92-93
**Purpose:** SQLite database connection

```python
app.state.db = Database(db_path)
app.state.db.initialize()
```

**Used By:** All endpoints (universal dependency)

#### app.state.workspace_manager
**Type:** `WorkspaceManager`
**Initialization:** Line 101
**Purpose:** Manages project workspaces (git clones, directory structure)

```python
app.state.workspace_manager = WorkspaceManager(workspace_root)
```

**Used By:**
- `create_project()` endpoint (workspace creation)

---

## 3. Dependencies

### 3.1 External Dependencies
**FastAPI Ecosystem:**
```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
```

**Python Standard Library:**
```python
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime, UTC, timezone
import asyncio
import json
import logging
import os
import shutil
import sqlite3
```

---

### 3.2 Internal Dependencies (Top-Level Imports)

#### From codeframe.core.models
```python
from codeframe.core.models import (
    ProjectStatus,
    TaskStatus,
    BlockerResolve,
    ContextItemCreateModel,
    ContextItemResponse,
    DiscoveryAnswer,
    DiscoveryAnswerResponse,
)
```

#### From codeframe.persistence.database
```python
from codeframe.persistence.database import Database
```

#### From codeframe.ui.models
```python
from codeframe.ui.models import (
    ProjectCreateRequest,
    ProjectResponse,
    SourceType,
    ReviewRequest,
    QualityGatesRequest,
    CheckpointCreateRequest,
    CheckpointResponse,
    CheckpointDiffResponse,
    RestoreCheckpointRequest,
    AgentAssignmentRequest,
    AgentRoleUpdateRequest,
    AgentAssignmentResponse,
    ProjectAssignmentResponse,
)
```

#### From codeframe.agents
```python
from codeframe.agents.lead_agent import LeadAgent
```

#### From codeframe.workspace
```python
from codeframe.workspace import WorkspaceManager
```

---

### 3.3 Inline Dependencies (Lazy Loading)
**Purpose:** Avoid circular imports or reduce startup time

**20+ inline imports identified:**

1. **codeframe.ui.websocket_broadcasts** (line 960)
   - `broadcast_discovery_answer_submitted`
   - `broadcast_discovery_question_presented`
   - `broadcast_discovery_completed`
   - `broadcast_to_project`

2. **codeframe.agents.lead_agent.LeadAgent** (line 1160)
   - Used in `get_discovery_progress()`

3. **codeframe.testing.lint_runner.LintRunner** (lines 1481, 1524)
   - Used in `get_lint_config()`, `run_lint_manual()`

4. **codeframe.core.session_manager.SessionManager** (line 1659)
   - Used in `get_session_state()`

5. **codeframe.lib.context_manager.ContextManager** (lines 1902, 1938, 1978)
   - Used in `update_context_scores()`, `update_context_tiers()`, `flash_save_context()`

6. **codeframe.agents.review_worker_agent.ReviewWorkerAgent** (line 2093)
   - Used in `trigger_review()`

7. **codeframe.agents.review_agent.ReviewAgent** (line 2319)
   - Used in `analyze_code_review()`

8. **codeframe.lib.token_counter.TokenCounter** (line 2765)
   - Used in `get_context_stats()`

9. **codeframe.lib.quality_gates.QualityGates** (line 2941)
   - Used in `trigger_quality_gates()`

10. **codeframe.lib.checkpoint_manager.CheckpointManager** (lines 3291, 3537, 3622)
    - Used in `create_checkpoint()`, `restore_checkpoint()`, `get_checkpoint_diff()`

11. **codeframe.lib.metrics_tracker.MetricsTracker** (lines 3814, 3927, 4006)
    - Used in `get_project_token_metrics()`, `get_project_cost_metrics()`, `get_agent_metrics()`

---

### 3.4 Circular Dependency Risks

**Identified Risks:**

1. **LeadAgent ↔ server.py**
   - `server.py` imports `LeadAgent` (top-level)
   - LeadAgent likely uses database models and may call API endpoints (indirect)
   - **Mitigation:** Inline import of LeadAgent in `get_discovery_progress()` (line 1160)

2. **websocket_broadcasts ↔ server.py**
   - `websocket_broadcasts` module may reference `manager` from `server.py`
   - `server.py` imports broadcast functions inline (line 960)
   - **Mitigation:** Inline import pattern

3. **Database ↔ models**
   - No circular dependency risk (Database uses models, models don't use Database)

**Recommendation:**
- Continue using inline imports for agents, broadcasts, and heavy libraries
- Extract shared state (manager, running_agents, review_cache) to `app.state` to reduce coupling

---

## 4. Utility Functions

### 4.1 start_agent()
**Location:** Lines 178-250 (73 lines)
**Purpose:** Initialize and start Lead Agent for a project

**Function Signature:**
```python
async def start_agent(
    project_id: int,
    db: Database,
    agents_dict: Dict[int, LeadAgent],
    api_key: str
) -> None
```

**Responsibilities:**
1. Create LeadAgent instance
2. Store agent in `agents_dict` (running_agents)
3. Update project status to RUNNING
4. Broadcast WebSocket events (agent_started, status_update)
5. Send greeting message
6. Save greeting to database

**Used By:**
- `start_project_agent()` endpoint (background task)

**Shared State Access:**
- Writes to `agents_dict` (parameter)
- Uses `manager.broadcast()` (WebSocket)
- Uses `db.update_project()`, `db.create_memory()`

**Refactoring Strategy:**
- Move to `codeframe.agents.agent_manager` module
- Keep inline to avoid circular imports if needed

---

### 4.2 get_deployment_mode()
**Location:** Lines 54-64
**Purpose:** Get deployment mode from environment (self_hosted vs hosted)

**Used By:**
- `create_project()` endpoint (security check)

**Refactoring Strategy:**
- Move to `codeframe.core.config` module

---

### 4.3 is_hosted_mode()
**Location:** Lines 67-73
**Purpose:** Check if running in hosted SaaS mode

**Used By:**
- `create_project()` endpoint (security check)

**Refactoring Strategy:**
- Move to `codeframe.core.config` module

---

### 4.4 Helper Functions (Inline)

#### _extract_enum_value_for_counting()
**Location:** Line 2395
**Purpose:** Extract enum value for counting (review statistics)

#### _extract_enum_value()
**Location:** Line 2423
**Purpose:** Extract enum value with default (review statistics)

**Refactoring Strategy:**
- Move to `codeframe.lib.enum_utils` or keep in review router

---

### 4.5 broadcast_updates()
**Location:** Lines 4119-4132
**Purpose:** Background task to periodically broadcast updates (not actively used)

**Note:** This function is defined but never started as a background task.

**Refactoring Strategy:**
- Remove if unused, or start as lifespan background task

---

## 5. Dependency Graph

### 5.1 Visual Dependency Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                          codeframe/ui/server.py                      │
│                            (4,161 lines)                             │
└─────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────────┐
        │                         │                             │
        ▼                         ▼                             ▼
┌──────────────┐         ┌────────────────┐          ┌──────────────────┐
│ Shared State │         │   App State    │          │ External Deps    │
├──────────────┤         ├────────────────┤          ├──────────────────┤
│ manager      │         │ app.state.db   │          │ FastAPI          │
│ running_     │         │ app.state.     │          │ asyncio          │
│   agents     │         │   workspace_   │          │ sqlite3          │
│ review_cache │         │   manager      │          │ pathlib          │
└──────────────┘         └────────────────┘          └──────────────────┘
        │                         │                             │
        └─────────────────────────┼─────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────────┐
        │                         │                             │
        ▼                         ▼                             ▼
┌──────────────┐         ┌────────────────┐          ┌──────────────────┐
│  Projects    │         │    Agents      │          │     Tasks        │
│  Router      │         │    Router      │          │     Router       │
├──────────────┤         ├────────────────┤          ├──────────────────┤
│ 26 endpoints │         │ 12 endpoints   │          │  4 endpoints     │
│              │         │                │          │                  │
│ Dependencies:│         │ Dependencies:  │          │ Dependencies:    │
│ • manager    │         │ • app.state.db │          │ • app.state.db   │
│ • running_   │         │ • review_cache │          │ • review_cache   │
│   agents     │         │                │          │                  │
│ • app.state  │         │ Inline Imports:│          │ Inline Imports:  │
│              │         │ • ContextMgr   │          │ • QualityGates   │
│ Inline       │         │ • ReviewAgent  │          │ • ReviewAgent    │
│ Imports:     │         │ • MetricsTrack │          │                  │
│ • LeadAgent  │         │                │          │                  │
│ • SessionMgr │         │                │          │                  │
│ • Checkpoint │         │                │          │                  │
│ • Metrics    │         │                │          │                  │
└──────────────┘         └────────────────┘          └──────────────────┘
        │                         │                             │
        └─────────────────────────┼─────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────────┐
        │                         │                             │
        ▼                         ▼                             ▼
┌──────────────┐         ┌────────────────┐          ┌──────────────────┐
│  Blockers    │         │     Lint       │          │      Root        │
│  Router      │         │    Router      │          │     Router       │
├──────────────┤         ├────────────────┤          ├──────────────────┤
│  2 endpoints │         │  4 endpoints   │          │  3 endpoints     │
│              │         │                │          │  + WebSocket     │
│ Dependencies:│         │ Dependencies:  │          │                  │
│ • app.state  │         │ • app.state.db │          │ Dependencies:    │
│ • manager    │         │                │          │ • manager        │
│              │         │ Inline Imports:│          │ • app.state.db   │
│              │         │ • LintRunner   │          │                  │
└──────────────┘         └────────────────┘          └──────────────────┘
```

---

### 5.2 Endpoint → Shared State Dependencies

| Endpoint Group | manager | running_agents | review_cache | app.state.db | workspace_mgr |
|----------------|---------|----------------|--------------|--------------|---------------|
| Projects       | ✓       | ✓              | -            | ✓            | ✓             |
| Agents         | -       | -              | ✓            | ✓            | -             |
| Tasks          | -       | -              | ✓            | ✓            | -             |
| Blockers       | ✓       | -              | -            | ✓            | -             |
| Lint           | ✓       | -              | -            | ✓            | -             |
| Root           | ✓       | -              | -            | ✓            | -             |

---

### 5.3 Inline Import Dependencies

| Endpoint Group | Inline Imports                                               |
|----------------|--------------------------------------------------------------|
| Projects       | LeadAgent, SessionManager, CheckpointManager, MetricsTracker |
| Agents         | ContextManager, ReviewWorkerAgent, ReviewAgent, MetricsTracker |
| Tasks          | QualityGates, ReviewAgent, Task                              |
| Blockers       | (none)                                                       |
| Lint           | LintRunner                                                   |
| Root           | subprocess, uvicorn                                          |

---

## 6. Refactoring Recommendations

### 6.1 Router Extraction Order (Phase 2-4)

**Phase 2: Extract Simple Routers (Low Risk)**
1. **Blockers Router** (2 endpoints, minimal dependencies)
2. **Lint Router** (4 endpoints, self-contained)
3. **Root Router** (3 endpoints + WebSocket, infrastructure)

**Phase 3: Extract Medium Routers (Medium Risk)**
4. **Tasks Router** (4 endpoints, uses review_cache)
5. **Agents Router** (12 endpoints, uses review_cache, inline imports)

**Phase 4: Extract Complex Routers (High Risk)**
6. **Projects Router** (26 endpoints, heaviest, uses all shared state)

---

### 6.2 Shared State Migration Strategy

**Step 1: Move to app.state**
```python
# In lifespan()
app.state.manager = ConnectionManager()
app.state.running_agents = {}
app.state.review_cache = {}
```

**Step 2: Update references**
- Replace `manager` → `request.app.state.manager` (or use Depends())
- Replace `running_agents` → `request.app.state.running_agents`
- Replace `review_cache` → `request.app.state.review_cache`

**Step 3: Create dependency injection helpers**
```python
# codeframe/ui/dependencies.py
from fastapi import Depends, Request

def get_manager(request: Request) -> ConnectionManager:
    return request.app.state.manager

def get_running_agents(request: Request) -> Dict[int, LeadAgent]:
    return request.app.state.running_agents

def get_review_cache(request: Request) -> Dict[int, dict]:
    return request.app.state.review_cache
```

---

### 6.3 Utility Function Extraction

**New Modules:**
1. **codeframe/ui/dependencies.py** - Dependency injection helpers
2. **codeframe/ui/agent_lifecycle.py** - `start_agent()` function
3. **codeframe/core/config.py** - `get_deployment_mode()`, `is_hosted_mode()`
4. **codeframe/lib/enum_utils.py** - `_extract_enum_value()` helpers (if reused)

---

### 6.4 File Structure (Target)

```
codeframe/ui/
├── server.py                    # FastAPI app, lifespan, CORS, includes routers (100-200 LOC)
├── dependencies.py              # Dependency injection helpers (NEW)
├── agent_lifecycle.py           # start_agent() utility (NEW)
├── models.py                    # Request/response models (existing)
├── websocket_broadcasts.py      # WebSocket broadcast functions (existing)
├── routers/                     # NEW DIRECTORY
│   ├── __init__.py
│   ├── root.py                  # Health checks, WebSocket (50-100 LOC)
│   ├── projects.py              # Projects endpoints (600-800 LOC)
│   ├── agents.py                # Agents endpoints (400-600 LOC)
│   ├── tasks.py                 # Tasks endpoints (300-400 LOC)
│   ├── blockers.py              # Blockers endpoints (100-150 LOC)
│   └── lint.py                  # Lint endpoints (200-300 LOC)
```

---

## 7. Risk Assessment

### 7.1 High-Risk Areas

1. **WebSocket Integration**
   - `manager` is accessed across multiple routers
   - **Mitigation:** Move to `app.state.manager`, use dependency injection

2. **running_agents Dictionary**
   - Shared mutable state accessed by Projects router (chat, start)
   - **Mitigation:** Move to `app.state.running_agents`, document threading/async safety

3. **review_cache Dictionary**
   - Shared cache accessed by Agents and Tasks routers
   - **Mitigation:** Move to `app.state.review_cache`, consider Redis for production scaling

4. **Inline Imports**
   - 20+ inline imports indicate circular dependency concerns
   - **Mitigation:** Keep inline imports pattern in extracted routers

5. **Projects Router Size**
   - 26 endpoints, 2000+ LOC
   - **Mitigation:** Extract in Phase 4, thorough testing

---

### 7.2 Testing Strategy

**Phase 2-4 Testing:**
1. **Before Extraction:** Run full E2E test suite (47 tests)
2. **After Each Router Extraction:**
   - Re-run E2E tests
   - Run router-specific integration tests
   - Manual smoke testing
3. **After All Extraction:** Full regression testing

**Test Coverage:**
- Backend: 550+ tests, 88%+ coverage
- E2E: 47 tests (Playwright + Pytest)

---

## 8. Next Steps (Phase 2-4)

### Phase 2: Extract Simple Routers (Blockers, Lint, Root)
1. Create `codeframe/ui/routers/` directory
2. Extract Blockers router (2 endpoints)
3. Extract Lint router (4 endpoints)
4. Extract Root router (3 endpoints + WebSocket)
5. Update `server.py` to include routers
6. Run E2E tests

### Phase 3: Extract Medium Routers (Tasks, Agents)
1. Move shared state to `app.state`
2. Create dependency injection helpers
3. Extract Tasks router (4 endpoints)
4. Extract Agents router (12 endpoints)
5. Run E2E tests

### Phase 4: Extract Complex Router (Projects)
1. Extract utility functions (start_agent, config helpers)
2. Extract Projects router (26 endpoints)
3. Reduce `server.py` to app setup only (100-200 LOC)
4. Run full regression tests

---

## Appendix A: Endpoint Size Distribution

**Top 30 Largest Endpoints:**

| Endpoint Function                | Lines | Start Line | Router Group |
|----------------------------------|-------|------------|--------------|
| get_checkpoint_diff              | 164   | 3599       | Projects     |
| run_quality_gates (internal)     | 157   | 3008       | Tasks        |
| get_project_code_reviews         | 145   | 2591       | Projects     |
| run_lint_manual                  | 138   | 1504       | Lint         |
| get_task_reviews                 | 138   | 2453       | Tasks        |
| create_project                   | 130   | 314        | Projects     |
| submit_discovery_answer          | 129   | 938        | Projects     |
| trigger_review                   | 127   | 2052       | Agents       |
| get_agent_metrics                | 127   | 3952       | Agents       |
| restore_checkpoint               | 112   | 3487       | Projects     |
| get_project_token_metrics        | 108   | 3763       | Projects     |
| run_review (internal)            | 107   | 2346       | Agents       |
| trigger_quality_gates            | 104   | 2904       | Tasks        |
| create_checkpoint                | 103   | 3241       | Projects     |
| get_project_cost_metrics         | 81    | 3871       | Projects     |
| get_discovery_progress           | 80    | 1119       | Projects     |
| start_agent (utility)            | 79    | 178        | Utility      |
| resolve_blocker_endpoint         | 79    | 1307       | Blockers     |
| get_session_state                | 77    | 1642       | Projects     |
| list_checkpoints                 | 76    | 3165       | Projects     |

**Key Insight:** 15 of top 20 largest endpoints belong to **Projects Router**, confirming it's the most complex group.

---

## Appendix B: Import Analysis

**Top-Level Imports (Always Loaded):**
- FastAPI ecosystem (FastAPI, WebSocket, HTTPException, etc.)
- Python stdlib (asyncio, json, logging, os, pathlib, sqlite3, etc.)
- codeframe.core.models (8 models)
- codeframe.persistence.database (Database)
- codeframe.ui.models (11 models)
- codeframe.agents.lead_agent (LeadAgent)
- codeframe.workspace (WorkspaceManager)

**Inline Imports (Lazy Loaded):**
- codeframe.ui.websocket_broadcasts (4 functions)
- codeframe.agents.* (LeadAgent, ReviewWorkerAgent, ReviewAgent)
- codeframe.lib.* (ContextManager, TokenCounter, QualityGates, CheckpointManager, MetricsTracker)
- codeframe.core.* (SessionManager)
- codeframe.testing.* (LintRunner)

**Total Unique Modules Imported:** 30+

---

## Appendix C: Glossary

- **LOC:** Lines of Code
- **Inline Import:** Import statement inside a function (lazy loading)
- **Shared State:** Module-level variables accessed by multiple endpoints
- **Circular Dependency:** Module A imports B, B imports A (causes import errors)
- **Dependency Injection:** FastAPI pattern for passing dependencies to endpoint functions
- **WebSocket:** Persistent bidirectional connection for real-time updates
- **Flash Save:** Context management feature to archive COLD tier context items

---

**End of Phase 1 Analysis Report**
