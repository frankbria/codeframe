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
- [ ] **cf-8**: Connect Status Server to actual Database (P0)
  - Load real project from SQLite
  - Return actual project status (not mock)
  - Demo: Dashboard shows real project from DB

- [ ] **cf-9**: Implement basic Lead Agent with Anthropic SDK (P0)
  - Initialize Claude conversation
  - Basic chat functionality (no Socratic yet)
  - Store conversation state in DB
  - Demo: Chat interface works with real Claude responses

- [ ] **cf-10**: Connect Project.start() to Lead Agent (P0)
  - `codeframe start` launches Lead Agent
  - Agent sends initial greeting
  - Status updates reflect agent state
  - Demo: CLI start → Dashboard shows "Active" → Chat works

- [ ] **cf-11**: Add project creation to Status Server API (P1)
  - POST /api/projects endpoint
  - Create project from web UI (bonus)
  - Demo: Can create project via API or CLI

**Definition of Done**:
- ✅ Can run `codeframe init` and see it in dashboard
- ✅ Can run `codeframe start` and chat with Lead Agent
- ✅ Responses come from real Claude API
- ✅ Dashboard updates when project state changes
- ✅ All data persists in SQLite

**Sprint Review**: Working system - you can start a project and talk to an AI agent!

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
