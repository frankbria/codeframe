# CodeFRAME: The Big Picture

> High-level vision; see [PRD.md](../PRD.md) for current product requirements and E2E workflows.

**Last Updated**: 2025-11-21
**Current State**: Sprints 0–9.5 Complete – MVP and Critical UX Fixes delivered; preparing E2E testing (Sprint 10).

---

## What CodeFRAME Is

CodeFRAME is an **autonomous AI development team** that turns your project ideas into working software through conversation. You describe what you want, and AI agents write the actual code, run tests, fix bugs, and deploy—all while you watch through a live dashboard.

Think of it as **hiring a team of AI developers** who never sleep, never forget context, and get smarter over time.

---

## The Vision: Your AI Development Team

```
YOU (Product Owner)
  ↓
  Describe your idea in plain English
  ↓
LEAD AGENT (Discovery)
  → Asks smart questions (Socratic method)
  → Generates Product Requirements Document (PRD)
  → Breaks PRD into 40+ executable tasks
  ↓
WORKER AGENTS (Execution)
  ├─ Backend Agent  → Writes Python/FastAPI code
  ├─ Frontend Agent → Writes React/TypeScript UI
  └─ Test Agent     → Writes and runs tests
  ↓
CONTINUOUS FEEDBACK LOOP
  ├─ Tests fail? → Agents fix automatically (3 attempts)
  ├─ Need help?  → Agents ask you questions (blockers)
  └─ Tasks done? → Auto-merge to main, deploy
  ↓
WORKING SOFTWARE IN YOUR GIT REPO
```

---

## How It Works: The Journey

### **Stage 1: Discovery** ✅ COMPLETE (Sprint 2)

**You**: "I want to build a SaaS for project management"

**Lead Agent**:
- Asks 5 intelligent questions (Socratic discovery)
- Captures your answers with structured metadata
- Learns about your users, features, constraints, tech stack

**Output**:
- Structured discovery data
- Clear understanding of requirements

---

### **Stage 2: Planning** ✅ COMPLETE (Sprint 2)

**Lead Agent**:
- Generates comprehensive PRD from discovery
- Breaks PRD into hierarchical issues (1.0, 1.1, 1.2...)
- Decomposes issues into granular tasks (1.1.1, 1.1.2, 1.1.3...)

**Example**:
```
Issue 1.5: User Authentication
  └─ Task 1.5.1: Create User model
  └─ Task 1.5.2: Implement password hashing
  └─ Task 1.5.3: Add login endpoint
  └─ Task 1.5.4: Write authentication tests
```

**Output**:
- PRD document
- 40+ executable tasks with dependencies
- Priority and workflow ordering

---

### **Stage 3: Execution** 🚧 IN PROGRESS (Sprint 3)

**This is where the magic happens.**

#### **3.1 Task Assignment**

**Lead Agent**:
- Picks highest priority task: "1.5.1: Create User model"
- Checks dependencies (are previous tasks done?)
- Assigns to Backend Worker Agent

#### **3.2 Autonomous Coding** ✅ CF-41 COMPLETE

**Backend Worker Agent**:
1. **Reads task** from database
2. **Queries codebase index** (cf-32): "What files/classes exist related to User?"
3. **Builds context**: Related files, symbols, dependencies
4. **Calls Claude API**: "Write the User model for this task"
5. **Receives code**: Complete Python file with tests
6. **Writes file**: `codeframe/models/user.py`
7. **Updates status**: Task → "in_progress" → "completed"

#### **3.3 Testing & Self-Correction** ✅ CF-42, CF-43 COMPLETE

**Test Runner** (cf-42):
- Runs `pytest tests/test_user.py`
- Parses results: 4/5 tests passing, 1 failure

**Self-Correction Loop** (cf-43):
- Backend Agent reads failure
- Analyzes error: "AssertionError: password not hashed"
- Regenerates fix
- Reruns tests
- Repeats up to 3 attempts
- ✅ All tests passing!

#### **3.4 Git Workflow** ✅ CF-33 COMPLETE

**Git Branching**:
- Task 1.5 starts → Creates `issue-1.5-user-authentication` branch
- Agents commit to this branch
- All tasks for 1.5 complete → Auto-merge to `main`
- Triggers deployment to staging

#### **3.5 Real-Time Updates** ✅ CF-45 COMPLETE

**Dashboard Shows**:
```
Backend Agent: Working on Task 1.5.2 ⚙️
├─ Created user.py
├─ Running tests... 3/5 passing
└─ Fixing test failure (attempt 1/3)

Frontend Agent: Idle (waiting on Task 1.7)
Test Agent: Completed Task 1.4 ✅
```

---

## The Full Picture: 8-Week Journey

### **Sprint 0: Foundation** ✅ COMPLETE
- Project structure, specs
- FastAPI backend
- Next.js frontend dashboard
- Basic mocks

### **Sprint 1: Hello CodeFRAME** ✅ COMPLETE
- Database (SQLite)
- Lead Agent (basic chat)
- Project initialization
- Live dashboard

### **Sprint 2: Socratic Discovery** ✅ COMPLETE
- Discovery question framework
- Answer capture & structuring
- PRD generation from discovery
- Task decomposition (40+ tasks)
- Dashboard displays PRD & tasks
- Project phase tracking

### **Sprint 3: Autonomous Agent** ✅ COMPLETE
**Foundation** ✅ COMPLETE:
- cf-32: Codebase Indexing (tree-sitter, symbol extraction)
- cf-33: Git Branching & Deployment (feature branches, auto-merge)

**Execution** ✅ COMPLETE:
- cf-41: Backend Worker Agent (fetch tasks, generate code, write files)
- cf-42: Test Runner (pytest integration, result parsing)
- cf-43: Self-Correction Loop (read failures, fix code, retry)
- cf-44: Git Auto-Commit (create commits with descriptive messages)
- cf-45: Real-Time Dashboard Updates (WebSocket, live status)

**Demo Goal**: ✅ Watch Backend Agent write code and fix its own bugs!

### **Sprint 4: Multi-Agent Coordination** ✅ COMPLETE
- 3 agents working in parallel (Backend, Frontend, Test)
- Task dependency resolution (DAG)
- Bottleneck detection
- Subagent spawning (code reviewers, accessibility checkers)

**Demo Goal**: 3 agents working simultaneously on independent tasks!

### **Sprint 5: Human in the Loop** ✅ COMPLETE (implemented as Sprint 6 in [SPRINTS.md](../SPRINTS.md))
- Blockers (SYNC vs ASYNC)
- Dashboard blocker UI
- Agent resume after answer
- Notification system (email/webhook)

**Demo Goal**: Agent asks you a question, you answer, it continues!

### **Sprint 6: Context Management** ✅ COMPLETE (see Sprint 7 in [SPRINTS.md](../SPRINTS.md))
- Flash save before context limit
- HOT/WARM/COLD tiering
- Context diffing
- Dashboard shows what agents "remember"

**Demo Goal**: Agents work on long tasks without forgetting!

### **Sprint 7: Agent Maturity** 🔮 FUTURE (deferred; see "Agent Maturity" future sprint in [SPRINTS.md](../SPRINTS.md))
- Metrics tracking (success rate, blockers, test pass rate)
- Maturity levels (D1-D4)
- Adaptive instructions (detailed → autonomous)
- Promotion/demotion based on performance

**Demo Goal**: Watch agents learn and improve over time!

### **Sprint 8: Review & Polish** ✅ COMPLETE (mapped across AI Quality Enforcement, MVP Completion, and Critical UX Fixes in [SPRINTS.md](../SPRINTS.md))
- Review Agent (code quality gates)
- End-to-end workflows
- Production deployment
- MVP complete

**Demo Goal**: Complete autonomous development from idea → deployed app!

---

## Current State: Where We Are

As of Sprint 9.5 (Critical UX Fixes), Sprints 0–9.5 in [SPRINTS.md](../SPRINTS.md) are complete: single-agent execution, multi-agent coordination, async workers, human-in-the-loop blockers, context management, AI quality enforcement, MVP completion, and critical UX fixes (server command, project creation UI, discovery answers, context panel, and session lifecycle).

### ✅ **What's Working Right Now** (original Sprint 3 snapshot)

**Discovery Flow**:
```bash
codeframe start
# Lead Agent asks 5 questions
# You answer
# PRD generated with 40+ tasks
```

**Planning Flow**:
```
# PRD displayed in dashboard
# Issues/tasks shown with hierarchy
# Progress indicators working
```

**Infrastructure**:
```
# Database: All tables created, CRUD working
# Indexing: Can parse Python/TypeScript, extract symbols
# Git: Can create branches, merge, deploy
# Dashboard: Live UI showing projects, PRD, tasks
```

### ✅ **Sprint 3 Complete** - What We Built

**Backend Worker Agent** (cf-41):
- Fetch task from database ✅
- Query codebase for context ✅
- Generate code via Claude API ✅
- Write files to disk ✅
- Update task status ✅

**Test Runner** (cf-42):
- Run pytest and parse results ✅
- Extract test counts and failures ✅
- Return structured test data ✅

**Self-Correction Loop** (cf-43):
- Read test failures ✅
- Analyze errors and fix code ✅
- Retry up to 3 attempts ✅

**Git Auto-Commit** (cf-44):
- Generate conventional commit messages ✅
- Infer commit type from task ✅
- Record commits in changelog ✅

**Real-Time Dashboard** (cf-45):
- WebSocket broadcasts for all events ✅
- Live task status updates ✅
- Activity feed updates without refresh ✅

**Next Sprint**: Sprint 4 - Multi-Agent Coordination

---

## The Technology Stack

### **Backend**
- **Python 3.11+** with uv package manager
- **FastAPI** for REST APIs
- **SQLite** database (simple, embedded)
- **Tree-sitter** for code parsing
- **Anthropic Claude** for LLM
- **GitPython** for git operations

### **Frontend**
- **React + TypeScript** (`web-ui` app)
- **Tailwind CSS** for styling
- **SWR** for data fetching
- **React Testing Library** for tests

### **Infrastructure**
- **Git** for version control
- **GitHub** for remote repository
- **pytest** for testing (Python)
- **Jest** for testing (TypeScript)
- **PM2** for process management (staging)

---

## The Database Schema (Simplified)

```sql
projects
  ├─ id, name, status, phase, created_at
  └─ Tracks project lifecycle

issues (e.g., "1.5: User Authentication")
  ├─ id, project_id, issue_number, title, description
  ├─ status, priority, workflow_step
  └─ Hierarchical grouping of tasks

tasks (e.g., "1.5.2: Implement password hashing")
  ├─ id, project_id, issue_id, task_number
  ├─ title, description, status, priority
  ├─ assigned_to, depends_on, can_parallelize
  └─ Granular executable units

agents
  ├─ id, type (lead, backend, frontend, test)
  ├─ provider (claude), maturity_level (D1-D4)
  ├─ status (idle, working, blocked)
  └─ current_task_id, metrics

git_branches (cf-33)
  ├─ id, issue_id, branch_name
  ├─ created_at, merged_at, merge_commit
  └─ Tracks feature branches

memory
  ├─ id, project_id, category, key, value
  └─ Stores discovery data, PRD, conversation history
```

---

## Key Design Decisions

### **Why SQLite?**
- Simple, embedded (no separate server)
- Perfect for MVP and local dev
- Can migrate to PostgreSQL later if needed

### **Why Tree-sitter?**
- Fast, incremental parsing
- Multi-language support (Python, TypeScript, Go, Rust...)
- Industry standard (used by GitHub, Neovim, etc.)

### **Why Claude (Anthropic)?**
- 200K context window (huge!)
- Strong at code generation
- Tool use capabilities
- Strict TDD methodology

### **Why Git Branching?**
- Safe isolation (feature branches)
- Easy rollback if agents break things
- Standard development workflow
- Enables code review (future)

### **Why Hierarchical Issues/Tasks?**
- Mirrors real development (epics → stories → tasks)
- Clear dependency management
- Progress tracking at multiple levels
- Enables parallel execution

---

## The Development Philosophy

### **Test-Driven Development (TDD)**
Every feature follows RED-GREEN-REFACTOR:
1. **RED**: Write failing test
2. **GREEN**: Make test pass (minimal code)
3. **REFACTOR**: Improve code quality

**Why?**
- Ensures tests actually verify behavior
- Prevents regressions
- Documents expected behavior
- High confidence in changes

### **Strict Documentation**
Every major feature has:
- Design specification (before coding)
- Implementation details (during coding)
- Test coverage report (after coding)
- AGILE_SPRINTS.md updates (on completion)

**Why?**
- Clear requirements prevent scope creep
- Future developers understand decisions
- Easy onboarding
- Institutional knowledge preserved

### **Agent-First Thinking**
Ask: "Could an agent do this autonomously?"
- If yes → Design for agent execution
- If no → Maybe needs human-in-the-loop

**Why?**
- Forces clarity in requirements
- Reduces manual work
- Scales infinitely
- Enables 24/7 development

---

## The User Experience

### **For Developers**

**Day 1**: Project Initialization
```bash
git clone https://github.com/frankbria/codeframe.git
cd codeframe
uv sync  # Install dependencies
./scripts/start-dev.sh  # Start backend + frontend
```

**Day 2**: Start a Project
```bash
# Open http://localhost:14100
# Click "Create New Project"
# Name: "TaskFlow SaaS"
# Click "Start Discovery"
# Answer 5 questions
# PRD generated automatically
```

**Day 3**: Watch Agents Work
```bash
# Dashboard shows:
# - 40 tasks decomposed
# - Backend Agent: Working on Task 1.1 ⚙️
# - Progress: 5% complete
# - Activity feed updates live
```

**Day 7**: Review & Deploy
```bash
# All tasks complete ✅
# Code in git repo
# Tests passing
# App deployed to staging
```

### **For Product Owners**

**What You Do**:
- Describe your product idea (conversational)
- Answer discovery questions
- Review PRD (approve/request changes)
- Answer blocker questions when agents stuck
- Review final product

**What You DON'T Do**:
- Write any code
- Set up infrastructure
- Debug test failures
- Manage dependencies
- Write documentation

---

## The Competitive Edge

### **vs Traditional Development**
- **Speed**: Agents work 24/7, no breaks
- **Cost**: $1-5 per task (API costs) vs $50-200/hour (developers)
- **Consistency**: No "bad days", always follows best practices
- **Scalability**: Spin up 10 agents instantly vs hiring 10 developers

### **vs Other AI Coding Tools** (Cursor, GitHub Copilot, etc.)
- **Autonomous**: Full task execution, not just suggestions
- **Context Aware**: Understands entire codebase, not just current file
- **Multi-Agent**: Parallel execution with coordination
- **Self-Correcting**: Fixes its own bugs automatically
- **Observable**: Dashboard shows exactly what agents are doing

### **vs No-Code Platforms** (Bubble, Webflow, etc.)
- **Full Code**: Real Python/TypeScript in git repo
- **Customizable**: Not locked into platform constraints
- **Portable**: Take code anywhere, no vendor lock-in
- **Scalable**: Can handle complex enterprise requirements

---

## Success Metrics (When Complete)

### **Phase 1: MVP Validation**
- ✅ Generate PRD from conversational discovery
- ✅ Decompose into 40+ executable tasks
- ⏳ Agent completes 10+ tasks autonomously
- ⏳ Tests pass for agent-generated code
- ⏳ Code quality matches human developer standards

### **Phase 2: Production Readiness**
- Agent self-correction rate >80%
- Human intervention rate <20%
- Task completion time <30 min average
- API cost per task <$2
- Zero security vulnerabilities in generated code

### **Phase 3: Market Validation**
- 10+ external users onboarded
- 5+ complete projects built end-to-end
- User satisfaction >4/5 stars
- Agent maturity progression demonstrated
- Multi-agent coordination proven

---

## The Path Forward

### **Immediate Next Steps** (This Week)
1. ✅ Create design for cf-41 (Backend Worker Agent)
2. ✅ Implement cf-41 using strict TDD
3. ✅ Implement cf-42 (Test Runner)
4. ✅ Implement cf-43 (Self-Correction Loop)
5. ✅ Demo: Agent writes code, runs tests, fixes bugs

### **This Month** (Sprint 3 ✅ COMPLETE)
- ✅ cf-44: Git auto-commit (commit ef0105e)
- ✅ cf-45: Real-time dashboard updates (commit d9af52b)
- Ready for end-to-end demo: Discovery → Planning → Execution → Deployment

### **Next 2 Months** (Sprints 4-5)
- Multi-agent parallel execution
- Human-in-the-loop blockers
- Context management for long tasks
- Agent maturity system

### **Next 6 Months** (Production)
- Review Agent (code quality gates)
- External beta testing
- Security hardening
- Performance optimization
- Production deployment guides

---

## The Grand Vision

**Imagine a world where:**
- Anyone with an idea can build software
- Development teams never sleep
- Code quality is consistently high
- Bugs are fixed before humans notice
- New features ship daily, not quarterly

**CodeFRAME makes this real.**

Not by replacing developers—but by **augmenting them**.

Senior developers focus on architecture, design, and complex problems.
AI agents handle the repetitive, well-defined, testable work.

**The result?**
- 10x faster development
- 90% lower costs
- 100% test coverage
- Zero burnout

---

## Your Role Right Now

**You're seeing the foundation being built.**

- Sprints 0-2: ✅ Planning infrastructure complete
- Sprint 3 Foundation: ✅ Execution infrastructure ready
- **Sprint 3 Execution**: ✅ First autonomous agent complete!

**cf-41 through cf-45 represent the breakthrough moment.**

We've gone from "AI can plan" to **"AI can code, test, fix, and commit."**

Everything after this is scaling: more agents, better coordination, smarter learning.

The foundation is complete. Sprint 4 begins multi-agent coordination.

---

**Welcome to the future of software development. Welcome to CodeFRAME.** 🚀
