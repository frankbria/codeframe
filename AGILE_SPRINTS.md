# CodeFRAME Agile Sprint Plan

**Philosophy**: Every sprint delivers a functional, working demo you can interact with and review - even if features are incomplete or use mock data.

---

## Sprint 0: Foundation ✅ COMPLETE

**Goal**: Project structure, specifications, web UI shell

**Deliverables**:
- ✅ Technical specification (CODEFRAME_SPEC.md)
- ✅ Python package structure
- ✅ FastAPI Status Server with mock data
- ✅ Next.js web dashboard with live UI

**Demo**: Static dashboard showing mock project/agents - looks real, but data is hardcoded

**Status**: ✅ Complete - Committed to GitHub

---

## Sprint 1: Hello CodeFRAME (Week 1)

**Goal**: End-to-end working system with simplest possible implementation

**User Story**: As a developer, I want to initialize a CodeFRAME project, see it in the dashboard, and have a basic chat with the Lead Agent.

**Functional Demo**:
```bash
# Terminal 1: Start Status Server
python -m codeframe.ui.server

# Terminal 2: Start Web UI
cd web-ui && npm run dev

# Terminal 3: Initialize and start a project
codeframe init hello-world
codeframe start

# Browser: http://localhost:3000
# See: Project appears in dashboard
# See: Lead Agent status shows "Initializing"
# Click: "Chat with Lead" → Type "Hello!" → Get response
```

**Implementation Tasks**:

### 🗄️ cf-8: Connect Status Server to Database (P0)
**Owner**: Backend/Infrastructure
**Dependencies**: None
**Estimated Effort**: 4-6 hours

**Detailed Subtasks**:
- [x] **cf-8.1**: Implement database CRUD methods ✅
  - ✅ `list_projects() -> List[Dict[str, Any]]`
  - ✅ `update_project(id, updates: Dict[str, Any]) -> int`
  - ✅ `create_agent(agent_id, agent_type, provider, maturity_level) -> str`
  - ✅ `get_agent(agent_id) -> Optional[Dict[str, Any]]`
  - ✅ `list_agents() -> List[Dict[str, Any]]`
  - ✅ `update_agent(agent_id, updates: Dict[str, Any]) -> int`
  - ✅ `create_memory(project_id, category, key, value) -> int`
  - ✅ `get_memory(memory_id) -> Optional[Dict[str, Any]]`
  - ✅ `get_project_memories(project_id) -> List[Dict[str, Any]]`
  - ✅ `get_conversation(project_id) -> List[Dict[str, Any]]`
  - ✅ Context manager support (`__enter__`, `__exit__`)
  - ✅ Enhanced `close()` with connection cleanup
  - **Implementation**: TDD approach (RED-GREEN-REFACTOR)
  - **Tests**: 26 comprehensive test cases (100% pass rate)
  - **Coverage**: 92.06% (exceeds 90% target)
  - **Commit**: e6f5e15 - "feat(cf-8.1): Implement database CRUD methods using TDD"

- [x] **cf-8.2**: Database initialization on server startup ✅
  - ✅ Initialize SQLite connection using FastAPI lifespan event
  - ✅ Create all database tables on startup
  - ✅ Handle connection lifecycle (startup/shutdown)
  - ✅ Support DATABASE_PATH environment variable configuration
  - ✅ Default to `.codeframe/state.db` if not configured
  - ✅ Thread-safe SQLite connection (`check_same_thread=False`)
  - **Implementation**: TDD approach (RED-GREEN-REFACTOR)
  - **Tests**: 10 comprehensive test cases (100% pass rate)
  - **Coverage**: 4 test classes - initialization, access, error handling, integration
  - **Commit**: c4a92b6 - "feat(cf-8.2): Initialize database on server startup using TDD"

- [x] **cf-8.3**: Wire Status Server endpoints to database ✅
  - ✅ `GET /api/projects` → `database.list_projects()`
  - ✅ `GET /api/projects/{id}/status` → `database.get_project(id)` with 404 handling
  - ✅ `GET /api/projects/{id}/agents` → `database.list_agents()`
  - ✅ Removed all mock data from endpoints (~100 lines removed)
  - **Implementation**: TDD approach (RED-GREEN-REFACTOR)
  - **Tests**: 11 comprehensive test cases (100% pass rate)
  - **Coverage**: 4 test classes - projects, status, agents, integration
  - **Code Quality**: 85% code reduction (mock data → database calls)
  - **Commit**: aaec07a - "feat(cf-8.3): Wire endpoints to database using TDD"

- [ ] **cf-8.4**: Basic unit tests
  - Test: Create project and retrieve it
  - Test: Update project status
  - Test: Create and retrieve conversation messages
  - Test: Error handling for missing projects

**Definition of Done**:
- ✅ Database CRUD methods implemented and tested
- ✅ Status Server loads real data from SQLite
- ✅ Dashboard shows actual projects (not mocks)
- ✅ Unit tests pass with >80% coverage

**Demo Script**:
```bash
# Create project via CLI
codeframe init test-project

# Check database directly
sqlite3 .codeframe/state.db "SELECT * FROM projects;"

# Check API returns real data
curl http://localhost:8080/api/projects

# Browser: Dashboard shows "test-project"
```

---

### 🤖 cf-9: Lead Agent with Anthropic SDK (P0)
**Owner**: AI/Agent Logic
**Dependencies**: cf-8 (needs database for conversation storage)
**Estimated Effort**: 6-8 hours

**Detailed Subtasks**:
- [ ] **cf-9.1**: Environment configuration
  - Add `ANTHROPIC_API_KEY` to `.env` file support
  - Load environment variables in `config.py`
  - Validation: Fail fast if API key missing with helpful error
  - Document setup in README

- [ ] **cf-9.2**: Anthropic SDK integration
  - Install `anthropic` package (already in pyproject.toml)
  - Create `AnthropicProvider` class in `codeframe/providers/anthropic.py`
  - Implement `send_message(conversation_history) -> response`
  - Handle API errors (rate limits, timeouts, invalid keys)

- [ ] **cf-9.3**: Lead Agent message handling
  - Implement `LeadAgent.chat(user_message) -> ai_response`
  - Load conversation history from database
  - Append user message to history
  - Send to Claude via AnthropicProvider
  - Save AI response to database
  - Return response

- [ ] **cf-9.4**: Conversation state persistence
  - Store messages in `memory` table with role (user/assistant)
  - Implement conversation retrieval by project_id
  - Handle long conversations (truncation strategy TBD in Sprint 6)

- [ ] **cf-9.5**: Basic observability
  - Log token usage per request
  - Log API latency
  - Log errors with context
  - (Defer cost tracking to Sprint 7)

**Definition of Done**:
- ✅ Can initialize Lead Agent with API key
- ✅ Can send message and get Claude response
- ✅ Conversation persists across restarts
- ✅ Error handling works (shows helpful messages)
- ✅ Basic logging in place

**Demo Script**:
```python
# Python REPL test
from codeframe.core.project import Project
from codeframe.agents.lead_agent import LeadAgent

project = Project.load("hello-world")
agent = LeadAgent(project.id)
response = agent.chat("Hello! What can you help me with?")
print(response)  # Should get actual Claude response

# Check database
# Conversation should be saved in memory table
```

---

### 🔌 cf-10: Project Start & Agent Lifecycle (P0)
**Owner**: Integration
**Dependencies**: cf-9 (needs Lead Agent), cf-8 (needs database)
**Estimated Effort**: 6-8 hours

**Detailed Subtasks**:
- [ ] **cf-10.1**: Status Server agent management
  - Add `running_agents: Dict[int, LeadAgent]` in server.py
  - Implement `start_agent(project_id)` async function
  - Store agent reference in dictionary
  - Update project status to "running"

- [ ] **cf-10.2**: POST /api/projects/{id}/start endpoint
  - Accept project ID
  - Call `start_agent(project_id)` in background task
  - Return 202 Accepted immediately (non-blocking)
  - Broadcast status change via WebSocket

- [ ] **cf-10.3**: Lead Agent greeting on start
  - When agent starts, send initial greeting message
  - Greeting: "Hi! I'm your Lead Agent. I'm here to help build your project. What would you like to create?"
  - Save greeting to conversation history
  - Broadcast greeting via WebSocket to dashboard

- [ ] **cf-10.4**: WebSocket message protocol
  - Define message types: `status_update`, `chat_message`, `agent_started`
  - Implement broadcast helper: `broadcast_message(type, data)`
  - Dashboard subscribes to messages and updates UI

- [ ] **cf-10.5**: CLI integration
  - Implement `codeframe start` command
  - Send POST request to Status Server
  - Handle case where server isn't running (helpful error)
  - Show success message with dashboard link

**Definition of Done**:
- ✅ `codeframe start` successfully starts Lead Agent
- ✅ Dashboard shows project status changes to "Running"
- ✅ Greeting message appears in dashboard chat
- ✅ WebSocket updates work in real-time
- ✅ Agent runs in background (CLI returns immediately)

**Demo Script**:
```bash
# Start everything
python -m codeframe.ui.server  # Terminal 1
cd web-ui && npm run dev       # Terminal 2

# Create and start project
codeframe init my-app          # Terminal 3
codeframe start

# Browser: http://localhost:3000
# See: Status changes "pending" → "running"
# See: Chat shows greeting message
# Type: "Hello!" → Get Claude response
```

---

### 📝 cf-11: Project Creation API (P1)
**Owner**: Backend/API
**Dependencies**: cf-8 (needs database)
**Estimated Effort**: 3-4 hours

**Detailed Subtasks**:
- [ ] **cf-11.1**: Request/Response models
  - Create `ProjectCreateRequest` Pydantic model
  - Fields: `project_name: str`, `project_type: str = "python"`
  - Validation: name required, type from enum
  - Create `ProjectResponse` model

- [ ] **cf-11.2**: POST /api/projects endpoint
  - Accept `ProjectCreateRequest`
  - Validate input (name not empty, valid type)
  - Call `Project.create(name, type)` (already exists)
  - Return created project as `ProjectResponse`
  - Handle duplicate project names gracefully

- [ ] **cf-11.3**: Error handling
  - 400 Bad Request for invalid input
  - 409 Conflict for duplicate names
  - 500 Internal Server Error with details

- [ ] **cf-11.4**: (Bonus) Web UI project creation form
  - Add "New Project" button in dashboard
  - Modal with form: project name, type selector
  - Call POST /api/projects on submit
  - Refresh project list on success

**Definition of Done**:
- ✅ POST /api/projects works via curl/Postman
- ✅ Request validation rejects invalid input
- ✅ Created projects appear in dashboard
- ✅ (Bonus) Can create project from web UI

**Demo Script**:
```bash
# Via API
curl -X POST http://localhost:8080/api/projects \
  -H "Content-Type: application/json" \
  -d '{"project_name": "api-test", "project_type": "python"}'

# Via Web UI (bonus)
# Click "New Project" → Enter "ui-test" → Click Create
# Project appears in dashboard list
```

---

### 🧪 cf-12: Environment & Configuration (P0) - NEW
**Owner**: Infrastructure
**Dependencies**: None
**Estimated Effort**: 2-3 hours

**Detailed Subtasks**:
- [ ] **cf-12.1**: Environment file template
  - Create `.env.example` with required variables
  - Document: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_PATH`
  - Add to README setup instructions

- [ ] **cf-12.2**: Configuration validation
  - Check API key exists on server startup
  - Print helpful error if missing: "Missing ANTHROPIC_API_KEY. See .env.example"
  - Validate database path is writable

- [ ] **cf-12.3**: Configuration loading
  - Use `python-dotenv` to load `.env` file
  - Make config accessible via `codeframe.core.config`
  - Support environment variable override

**Definition of Done**:
- ✅ `.env.example` exists with documentation
- ✅ Server fails fast with helpful error if API key missing
- ✅ Configuration loads correctly

---

### ✅ cf-13: Manual Testing Checklist (P1) - NEW
**Owner**: QA
**Dependencies**: All other tasks
**Estimated Effort**: 1-2 hours

**Detailed Subtasks**:
- [ ] **cf-13.1**: Create testing checklist
  - Document in `TESTING.md`
  - Cover all Definition of Done items
  - Include setup steps

- [ ] **cf-13.2**: Execute manual tests
  - Follow checklist step by step
  - Document any failures
  - Fix critical issues before sprint review

**Checklist**:
```markdown
## Sprint 1 Manual Test Checklist

### Setup
- [ ] Clone repository
- [ ] Install Python dependencies: `pip install -e .`
- [ ] Install Node dependencies: `cd web-ui && npm install`
- [ ] Create `.env` file with ANTHROPIC_API_KEY
- [ ] Start Status Server: `python -m codeframe.ui.server`
- [ ] Start Web UI: `cd web-ui && npm run dev`

### Test: Project Creation (cf-8, cf-11)
- [ ] Run `codeframe init test-project`
- [ ] Verify: Project directory created at `./test-project`
- [ ] Verify: `.codeframe/` directory exists
- [ ] Verify: Database file exists at `.codeframe/state.db`
- [ ] Check API: `curl http://localhost:8080/api/projects`
- [ ] Verify: Dashboard shows "test-project"

### Test: Lead Agent Chat (cf-9, cf-10)
- [ ] Run `codeframe start` in project directory
- [ ] Verify: CLI shows "Project started. View at http://localhost:3000"
- [ ] Browser: Open http://localhost:3000
- [ ] Verify: Project status shows "Running"
- [ ] Verify: Chat interface shows greeting message
- [ ] Type message: "Hello! What can you build?"
- [ ] Verify: Get response from Claude within 5 seconds
- [ ] Type message: "What's 2+2?"
- [ ] Verify: Response shows "4" or similar
- [ ] Refresh browser
- [ ] Verify: Conversation history persists

### Test: Real-time Updates (cf-10)
- [ ] Open dashboard in two browser windows
- [ ] In terminal: `codeframe start`
- [ ] Verify: Both windows show status change simultaneously
- [ ] In one window: Send chat message
- [ ] Verify: Message appears in both windows

### Test: Error Handling
- [ ] Remove ANTHROPIC_API_KEY from .env
- [ ] Restart Status Server
- [ ] Verify: Server shows error "Missing ANTHROPIC_API_KEY"
- [ ] Try to start project
- [ ] Verify: Helpful error message shown
```

**Definition of Done**:
- ✅ All checklist items pass
- ✅ Documentation exists for manual testing

---

### 📊 Sprint 1 Implementation Roadmap

**Recommended Execution Order**:

**Day 1-2: Foundation**
1. cf-12 (Environment & Config) - *Must do first*
2. cf-8.1, cf-8.2 (Database CRUD + initialization)
3. cf-8.4 (Unit tests for database)

**Day 3-4: Agent Integration**
4. cf-9.1, cf-9.2 (Environment + Anthropic SDK)
5. cf-9.3, cf-9.4 (Message handling + persistence)
6. cf-8.3 (Wire endpoints to database)

**Day 5-6: End-to-End Integration**
7. cf-10.1, cf-10.2 (Agent lifecycle + start endpoint)
8. cf-10.3, cf-10.4 (Greeting + WebSocket)
9. cf-10.5 (CLI integration)
10. cf-11 (Project creation API)

**Day 7: Testing & Polish**
11. cf-9.5 (Observability/logging)
12. cf-13 (Manual testing checklist)
13. Sprint demo rehearsal
14. Bug fixes and polish

**Total Effort Estimate**: 25-35 hours (1 week with buffer)

**Critical Path**: cf-12 → cf-8 → cf-9 → cf-10
**Parallel Work**: cf-11 can be done anytime after cf-8

---

### 🎯 Sprint 1 Success Metrics

**Technical**:
- ✅ Zero mock data in production code
- ✅ Database operations tested at >80% coverage
- ✅ API response time <500ms (p95)
- ✅ WebSocket reconnect works automatically

**Functional**:
- ✅ Can run `codeframe init` and see it in dashboard
- ✅ Can run `codeframe start` and chat with Lead Agent
- ✅ Responses come from real Claude API
- ✅ Dashboard updates when project state changes
- ✅ All data persists in SQLite
- ✅ Conversation history persists across restarts

**User Experience**:
- ✅ Setup takes <5 minutes (README to working demo)
- ✅ Error messages are helpful (no cryptic stack traces)
- ✅ Demo is impressive ("Wow, this actually works!")

**Sprint Review**: Working system - you can start a project and talk to an AI agent!

---

### 🔍 Sprint 1 Scope Boundaries

**IN SCOPE** (Must have for demo):
- Basic chat with Lead Agent
- Real Claude API integration
- Data persistence in SQLite
- Real-time dashboard updates
- Project creation and startup

**OUT OF SCOPE** (Defer to later sprints):
- ❌ Socratic questioning (Sprint 2)
- ❌ Task generation (Sprint 2)
- ❌ Multi-agent coordination (Sprint 4)
- ❌ Blocker system (Sprint 5)
- ❌ Context tiering (Sprint 6)
- ❌ Agent maturity (Sprint 7)
- ❌ Pause/resume (Sprint 8)
- ❌ Cost budgeting (Future)
- ❌ Rollback functionality (Future)

**NICE TO HAVE** (If time permits):
- Web UI project creation form (cf-11.4)
- Streaming responses from Claude
- Token usage display in dashboard
- Dark mode for dashboard 😎

---

## Sprint 1 Progress Tracker

### Completed Tasks ✅
- **cf-12**: Environment & Configuration Management
  - Status: ✅ Complete
  - Commit: 1b20ab3
  - Coverage: Configuration validation, environment loading, Sprint-specific checks

- **cf-8.1**: Database CRUD Methods (TDD)
  - Status: ✅ Complete
  - Commit: e6f5e15
  - Tests: 26 test cases (100% pass rate)
  - Coverage: 92.06%
  - Methods: 12 new CRUD methods with comprehensive docstrings

- **cf-8.2**: Database Initialization on Server Startup (TDD)
  - Status: ✅ Complete
  - Commit: c4a92b6
  - Tests: 10 test cases (100% pass rate)
  - Coverage: 4 test classes (initialization, access, error handling, integration)
  - Implementation: FastAPI lifespan event, thread-safe SQLite, environment config

- **cf-8.3**: Wire Endpoints to Database (TDD)
  - Status: ✅ Complete
  - Commit: aaec07a
  - Tests: 11 test cases (100% pass rate)
  - Coverage: 4 test classes (projects, status, agents, integration)
  - Code Quality: 85% reduction (removed mock data)

### In Progress 🔄
- **cf-8.4**: Unit tests with coverage verification

### Pending ⏳
- **cf-9**: Lead Agent with Anthropic SDK
- **cf-10**: Project Start & Agent Lifecycle
- **cf-11**: Project Creation API
- **cf-13**: Manual Testing Checklist

### Sprint 1 Metrics
- **Tasks Completed**: 4/7 (57%)
- **Test Coverage**: 92.06% (database.py), 100% (server init & endpoints)
- **Pass Rate**: 100% (47 total tests passing: 26 + 10 + 11)
- **TDD Compliance**: 100% (cf-8.1, cf-8.2, cf-8.3 all followed strict TDD)
- **Code Quality**: 85% reduction in endpoint code (mock → database)

---

## Sprint 2: Socratic Discovery (Week 2)

**Goal**: Lead Agent conducts requirements gathering

**User Story**: As a developer, I want the Lead Agent to ask me questions about my project, generate a PRD, and show it in the dashboard.

**Functional Demo**:
```bash
codeframe start my-auth-app

# Browser: Chat shows
Lead: "Hi! Let's figure out what we're building..."
Lead: "1. What problem does this solve?"
Lead: "2. Who are the primary users?"

# You answer in chat
User: "User authentication for a SaaS app. Users are developers."

# Lead asks follow-ups
Lead: "Got it! What are the core features?"

# You finish discovery
User: "Login, signup, password reset"

# Lead generates PRD
Lead: "✅ I've created your PRD. Generating tasks now..."

# Dashboard shows:
# - PRD link (view generated document)
# - Task count: "Generating 40 tasks..."
# - Phase: "Planning"
```

**Implementation Tasks**:
- [ ] **cf-12**: Implement Socratic questioning system (P0)
  - Predefined question flow
  - Context-aware follow-ups
  - Store Q&A in memory table
  - Demo: Lead asks questions, remembers answers

- [ ] **cf-13**: Generate PRD from discovery (P0)
  - Claude generates PRD from Q&A
  - Save to .codeframe/memory/prd.md
  - Display in dashboard
  - Demo: PRD appears after discovery

- [ ] **cf-14**: Task decomposition (basic) (P0)
  - Claude breaks PRD into tasks
  - Create task records in DB
  - Show in dashboard task list
  - Demo: Tasks appear with dependencies

- [ ] **cf-15**: Dashboard memory/PRD viewer (P1)
  - View PRD in UI
  - View task list with dependencies
  - Visualize task DAG (simple)
  - Demo: Click "View PRD" shows document

**Definition of Done**:
- ✅ Lead Agent asks discovery questions
- ✅ Agent generates PRD document
- ✅ PRD saved and viewable in dashboard
- ✅ Tasks created in database
- ✅ Dashboard shows task list

**Sprint Review**: Working discovery workflow - AI generates a real project plan!

---

## Sprint 3: Single Agent Execution (Week 3)

**Goal**: One worker agent executes one task with self-correction

**User Story**: As a developer, I want to watch a Backend Agent write code, run tests, fix failures, and complete a task.

**Functional Demo**:
```bash
# After Sprint 2 discovery completes

# Dashboard shows:
# - Backend Agent: "Assigned to Task #1: Setup project structure"
# - Status: "Working" (green dot, animated)

# Watch activity feed update:
# 10:15 - Backend Agent started Task #1
# 10:16 - Backend Agent created 3 files
# 10:17 - Running tests... 2/3 passing
# 10:18 - Test failure detected, analyzing...
# 10:19 - Applied fix, re-running tests...
# 10:20 - ✅ All tests passed
# 10:20 - ✅ Task #1 completed

# Dashboard updates:
# - Progress: 1/40 tasks (2.5%)
# - Backend Agent: "Idle" (waiting for next task)
# - Git: 1 new commit
```

**Implementation Tasks**:
- [ ] **cf-16**: Create Backend Worker Agent (P0)
  - Initialize with provider (Claude)
  - Execute task with LLM
  - Write code to files
  - Demo: Agent creates real files

- [ ] **cf-17**: Implement test runner (Python only) (P0)
  - Run pytest on task files
  - Parse test output
  - Return results to agent
  - Demo: Tests run automatically

- [ ] **cf-18**: Self-correction loop (max 3 attempts) (P0)
  - Agent reads test failures
  - Attempts fix
  - Retry tests
  - Demo: Watch agent fix failing tests

- [ ] **cf-19**: Git auto-commit after task completion (P1)
  - Commit files with descriptive message
  - Update changelog
  - Show commit in activity feed
  - Demo: Git history shows agent commits

- [ ] **cf-20**: Real-time dashboard updates (P1)
  - WebSocket broadcasts on task status change
  - Activity feed updates live
  - Agent status card updates
  - Demo: No refresh needed, see updates live

**Definition of Done**:
- ✅ Backend Agent executes a real task
- ✅ Agent writes actual code files
- ✅ Tests run and results appear in dashboard
- ✅ Agent fixes test failures automatically
- ✅ Task marked complete when tests pass
- ✅ Git commit created
- ✅ Dashboard updates in real-time

**Sprint Review**: Working autonomous agent - it writes code and fixes its own bugs!

---

## Sprint 4: Multi-Agent Coordination (Week 4)

**Goal**: Multiple agents work in parallel with dependency resolution

**User Story**: As a developer, I want to watch Backend, Frontend, and Test agents work simultaneously on independent tasks while respecting dependencies.

**Functional Demo**:
```bash
# Dashboard shows 3 agents working:

# Backend Agent (green): Task #5 "API endpoints"
# Frontend Agent (yellow): Task #7 "Login UI" (waiting on #5)
# Test Agent (green): Task #6 "Unit tests for utils"

# Activity feed:
# 11:00 - Lead Agent assigned Task #5 to Backend
# 11:00 - Lead Agent assigned Task #6 to Test Agent
# 11:01 - Frontend Agent waiting on Task #5 (dependency)
# 11:05 - Test Agent completed Task #6 ✅
# 11:10 - Backend Agent completed Task #5 ✅
# 11:10 - Frontend Agent started Task #7 (dependency resolved)
# 11:15 - Frontend Agent completed Task #7 ✅

# Progress: 7/40 tasks (17.5%)
```

**Implementation Tasks**:
- [ ] **cf-21**: Create Frontend Worker Agent (P0)
  - React/TypeScript code generation
  - File operations
  - Demo: Frontend agent creates UI components

- [ ] **cf-22**: Create Test Worker Agent (P0)
  - Write unit tests
  - Run tests for other agents' code
  - Demo: Test agent validates backend/frontend

- [ ] **cf-23**: Implement task dependency resolution (P0)
  - DAG traversal
  - Block tasks until dependencies complete
  - Unblock when ready
  - Demo: Agent waits, then auto-starts when unblocked

- [ ] **cf-24**: Parallel agent execution (P0)
  - Multiple agents run concurrently
  - Lead Agent coordinates assignment
  - No task conflicts
  - Demo: 3 agents working simultaneously

- [ ] **cf-25**: Bottleneck detection (P1)
  - Detect when multiple tasks wait on one
  - Highlight in dashboard
  - Alert in activity feed
  - Demo: Dashboard shows "Bottleneck: Task #8"

**Definition of Done**:
- ✅ 3 agent types working (Backend, Frontend, Test)
- ✅ Agents execute tasks in parallel
- ✅ Dependencies respected (tasks wait when needed)
- ✅ Dashboard shows all agents and their tasks
- ✅ Progress bar updates as tasks complete

**Sprint Review**: Working multi-agent system - autonomous parallel development!

---

## Sprint 5: Human in the Loop (Week 5)

**Goal**: Agents can ask for help when blocked

**User Story**: As a developer, I want agents to ask me questions when stuck, answer via the dashboard, and watch them continue working.

**Functional Demo**:
```bash
# Dashboard shows:

# ⚠️ Pending Questions (1)
# 🔴 SYNC - Task #15 (Backend Agent)
# "Should password reset tokens expire after 1hr or 24hrs?"
# Blocking: Backend Agent, Test Agent (2 agents)
# [Answer Now]

# You click "Answer Now" → Modal appears
# "Security vs UX trade-off. Recommendation: 1hr for security, 24hr for UX."
# Input: "1 hour"
# [Submit]

# Activity feed updates:
# 14:05 - Blocker #1 resolved: "1 hour"
# 14:05 - Backend Agent resumed Task #15
# 14:05 - Test Agent unblocked

# Agents continue working
# 14:10 - Backend Agent completed Task #15 ✅
```

**Implementation Tasks**:
- [ ] **cf-26**: Blocker creation and storage (P0)
  - Agent creates blocker when stuck
  - Store in blockers table
  - Classify as SYNC or ASYNC
  - Demo: Blocker appears in dashboard

- [ ] **cf-27**: Blocker resolution UI (P0)
  - Modal for answering questions
  - Submit answer via API
  - Update blocker status
  - Demo: Answer question in UI

- [ ] **cf-28**: Agent resume after blocker resolved (P0)
  - Agent receives answer
  - Continues task execution
  - Updates dashboard
  - Demo: Agent unblocks and continues

- [ ] **cf-29**: SYNC vs ASYNC blocker handling (P1)
  - SYNC: Pause dependent work
  - ASYNC: Continue other tasks
  - Visual distinction in UI
  - Demo: SYNC blocks, ASYNC doesn't

- [ ] **cf-30**: Notification system (email/webhook) (P1)
  - Send notification on SYNC blocker
  - Zapier webhook integration
  - Demo: Email sent when agent needs help

**Definition of Done**:
- ✅ Agents create blockers when stuck
- ✅ Blockers appear in dashboard with severity
- ✅ Can answer questions via UI
- ✅ Agents resume after answer received
- ✅ SYNC blockers pause work, ASYNC don't
- ✅ Notifications sent for SYNC blockers

**Sprint Review**: Working human-AI collaboration - agents ask for help when needed!

---

## Sprint 6: Context Management (Week 6)

**Goal**: Virtual Project system prevents context pollution

**User Story**: As a developer, I want to see agents intelligently manage their memory, keeping relevant context hot and archiving old information.

**Functional Demo**:
```bash
# Dashboard shows new "Context" section for each agent:

# Backend Agent
# Context: 85K tokens (HOT: 18K, WARM: 67K)
# [View Context Details]

# Click to expand:
# 🔥 HOT TIER (18K tokens)
# - Current task: Task #27 spec
# - Active files: auth.py, user_model.py
# - Recent test: 3/5 passing
# - High-importance decision: "Using JWT not sessions"

# ♨️ WARM TIER (67K tokens)
# - Related files: db_migration.py
# - Project structure overview
# - Code patterns

# ❄️ COLD TIER (archived)
# - Completed Task #20
# - Old test failure (resolved)

# Activity feed:
# 15:30 - Backend Agent: Flash save triggered (85K → 45K tokens)
# 15:30 - Archived 15 items to COLD tier
# 15:30 - Context optimized, continuing work
```

**Implementation Tasks**:
- [ ] **cf-31**: Implement ContextItem storage (P0)
  - Save context items to DB
  - Track importance scores
  - Access count tracking
  - Demo: Context items stored and queryable

- [ ] **cf-32**: Importance scoring algorithm (P0)
  - Calculate scores based on type, age, access
  - Automatic tier assignment
  - Score decay over time
  - Demo: Items auto-tier based on importance

- [ ] **cf-33**: Context diffing and hot-swap (P0)
  - Calculate context changes
  - Load only new/updated items
  - Remove stale items
  - Demo: Agent context updates efficiently

- [ ] **cf-34**: Flash save before compactification (P0)
  - Detect context >80% of limit
  - Create checkpoint
  - Archive COLD items
  - Resume with fresh context
  - Demo: Agent continues after flash save

- [ ] **cf-35**: Context visualization in dashboard (P1)
  - Show tier breakdown
  - Token usage per tier
  - Item list with importance scores
  - Demo: Inspect what agent "remembers"

**Definition of Done**:
- ✅ Context items stored with importance scores
- ✅ Items automatically tiered (HOT/WARM/COLD)
- ✅ Flash saves trigger before context limit
- ✅ Agents continue working after flash save
- ✅ Dashboard shows context breakdown
- ✅ 30-50% token reduction achieved

**Sprint Review**: Working context management - agents stay efficient for long-running tasks!

---

## Sprint 7: Agent Maturity (Week 7)

**Goal**: Agents learn and improve over time

**User Story**: As a developer, I want to watch agents graduate from needing detailed instructions to working autonomously as they gain experience.

**Functional Demo**:
```bash
# Dashboard shows agent maturity progression:

# Backend Agent
# Maturity: Coaching (D2) → Supporting (D3)
# Tasks: 25 completed, 95% success rate
# [View Metrics]

# Metrics modal:
# Success rate: 95% (↑ from 75%)
# Blocker frequency: 8% (↓ from 25%)
# Test pass rate: 97%
# Rework rate: 3%

# Activity feed:
# 16:00 - Backend Agent promoted to D3 (Supporting)
# 16:00 - Task instructions simplified (full autonomy granted)
# 16:05 - Backend Agent completed Task #30 independently

# Compare task assignments:
# D1 (Directive): "Step 1: Create auth.py. Step 2: Import jwt..."
# D3 (Supporting): "Implement JWT refresh token flow"
```

**Implementation Tasks**:
- [ ] **cf-36**: Agent metrics tracking (P0)
  - Track success rate, blockers, tests, rework
  - Store in agents.metrics JSON
  - Update after each task
  - Demo: Metrics visible in dashboard

- [ ] **cf-37**: Maturity assessment logic (P0)
  - Calculate maturity based on metrics
  - Promote/demote based on performance
  - Store maturity level in DB
  - Demo: Agent auto-promotes after good performance

- [ ] **cf-38**: Adaptive task instructions (P0)
  - D1: Detailed step-by-step
  - D2: Guidance + examples
  - D3: Minimal instructions
  - D4: Goal only
  - Demo: Instructions change based on maturity

- [ ] **cf-39**: Maturity visualization (P1)
  - Show current maturity level
  - Display metrics chart
  - Show progression history
  - Demo: See agent growth over time

**Definition of Done**:
- ✅ Metrics tracked for all agents
- ✅ Maturity levels auto-adjust based on performance
- ✅ Task instructions adapt to maturity
- ✅ Dashboard shows maturity and metrics
- ✅ Agents become more autonomous over time

**Sprint Review**: Working agent learning - watch AI agents get better at their jobs!

---

## Sprint 8: Review & Polish (Week 8)

**Goal**: Complete MVP with Review Agent and quality gates

**User Story**: As a developer, I want a Review Agent to check code quality before tasks are marked complete, and see the full system working end-to-end.

**Functional Demo**:
```bash
# Complete workflow demo:

1. codeframe init my-saas-app
2. codeframe start
   - Socratic discovery (Sprint 2)
   - PRD generation
   - 40 tasks created

3. Agents work in parallel (Sprints 3-4)
   - Backend, Frontend, Test agents
   - Dependencies respected
   - Real-time dashboard updates

4. Human blockers (Sprint 5)
   - Agent asks: "Which OAuth provider?"
   - You answer: "Auth0"
   - Agent continues

5. Context management (Sprint 6)
   - Flash saves every 2 hours
   - Agents stay efficient

6. Agent improvement (Sprint 7)
   - Agents promote to D3/D4
   - Less hand-holding needed

7. Review Agent (NEW - Sprint 8)
   - Reviews completed tasks
   - Suggests improvements
   - Blocks merge if critical issues

8. Completion
   - 40/40 tasks complete
   - All tests passing
   - Code reviewed
   - Ready to deploy!

# Duration: ~8 hours of autonomous work
# Your involvement: ~30 minutes (discovery + blockers)
```

**Implementation Tasks**:
- [ ] **cf-40**: Create Review Agent (P0)
  - Code quality analysis
  - Security scanning
  - Performance checks
  - Demo: Review agent analyzes code

- [ ] **cf-41**: Quality gates (P0)
  - Block completion if tests fail
  - Block if review finds critical issues
  - Require human approval for risky changes
  - Demo: Bad code gets rejected

- [ ] **cf-42**: Checkpoint and recovery system (P0)
  - Manual checkpoint creation
  - Restore from checkpoint
  - List checkpoints
  - Demo: Pause, resume days later

- [ ] **cf-43**: Metrics and cost tracking (P1)
  - Track token usage per agent
  - Calculate costs
  - Display in dashboard
  - Demo: See how much the project cost

- [ ] **cf-44**: End-to-end integration testing (P0)
  - Full workflow test
  - All features working together
  - No regressions
  - Demo: Complete project start to finish

**Definition of Done**:
- ✅ Review Agent operational
- ✅ Quality gates prevent bad code
- ✅ Checkpoint/resume works
- ✅ Cost tracking accurate
- ✅ Full system works end-to-end
- ✅ All Sprint 1-7 features integrated
- ✅ MVP complete and usable

**Sprint Review**: **MVP COMPLETE** - Fully functional autonomous coding system!

---

## Sprint Execution Guidelines

### Sprint Ceremony Schedule

**Sprint Planning** (Monday morning):
- Review sprint goals and user story
- Break down tasks into beads issues
- Assign priorities
- Estimate effort

**Daily Standups** (Not required for solo, but useful):
- What did I complete yesterday?
- What am I working on today?
- Any blockers?

**Mid-Sprint Check** (Wednesday):
- Is demo still achievable?
- Do we need to descope?
- Any risks?

**Sprint Review** (Friday afternoon):
- **DEMO TIME** - Run the working demo
- Record demo (optional but recommended)
- What worked?
- What needs improvement?

**Sprint Retrospective** (Friday):
- What went well?
- What could be better?
- Action items for next sprint

### Demo-Driven Development Rules

1. **Demo Must Work**: If a feature can't demo, it didn't happen
2. **Mock Data is OK**: Early sprints can use mock data if real data isn't ready
3. **User Perspective**: Demo as if you're showing a customer
4. **Record Demos**: Consider recording demos for progress tracking
5. **No Excuses**: "Almost working" doesn't count - adjust scope if needed

### Scope Management

**During Sprint**:
- ✅ **Add**: Small improvements to demo quality
- ⚠️ **Change**: Only if demo still achievable
- ❌ **Remove**: Better to descope than miss demo

**Descoping Strategy**:
1. Identify P0 (must have for demo) vs P1 (nice to have)
2. Move P1 to next sprint if needed
3. Focus on making demo impressive

### Definition of "Done" for Sprint

- ✅ Demo runs successfully
- ✅ Code committed to main branch
- ✅ Beads issues closed
- ✅ Documentation updated
- ✅ No known critical bugs in demo path

---

## MVP Success Criteria

After Sprint 8, CodeFRAME should demonstrate:

**End-to-End Workflow**:
1. Initialize project → See in dashboard
2. Socratic discovery → PRD generated
3. Task decomposition → 40 tasks created
4. Multi-agent execution → Parallel work
5. Dependency resolution → Tasks wait when needed
6. Self-correction → Agents fix test failures
7. Human blockers → Ask questions, get answers
8. Context management → Long-running efficiency
9. Agent maturity → Improvement over time
10. Code review → Quality gates enforced
11. Completion → Deployable code produced

**Dashboard Features**:
- Real-time updates (WebSocket)
- All agent statuses visible
- Task progress tracking
- Blocker management
- Activity feed
- Context visualization
- Metrics and cost tracking

**Non-Functional**:
- Response time <2s for dashboard
- Handles 40+ task projects
- Recovers from crashes
- Works 24/7 autonomously
- Costs <$50 for typical project

---

## Post-MVP Sprints (Optional)

### Sprint 9: Multi-Provider Support
- Add GPT-4 provider
- Provider selection per agent
- Cost comparison

### Sprint 10: Project Templates
- FastAPI + Next.js template
- Django + React template
- CLI tool template

### Sprint 11: Global Memory
- Learn patterns across projects
- User preferences
- Best practices library

### Sprint 12: Multi-User Collaboration
- Multiple developers per project
- Role-based access
- Notification routing

---

## Notes

- Each sprint is **1 week** (5 working days)
- **MVP completion**: 8 weeks
- **Total effort**: ~40-60 hours per sprint (solo developer)
- **Adjust scope** as needed to maintain demo quality
- **Focus on demos** - this keeps development tangible and motivating

**Remember**: At the end of every sprint, you should be able to show someone the system working and have them impressed!
