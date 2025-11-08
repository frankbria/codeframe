# Sprint Standards and Process

**Version**: 1.0.0
**Effective**: Sprint 6+
**Last Updated**: 2025-11-08
**Purpose**: Codify lessons learned from Sprints 0-5 and establish clear standards for all future sprints

---

## Table of Contents

1. [Pre-Sprint Planning](#pre-sprint-planning)
2. [Speckit Workflow (MANDATORY)](#speckit-workflow-mandatory)
3. [Sprint Execution Standards](#sprint-execution-standards)
4. [Testing Requirements](#testing-requirements)
5. [Documentation Standards](#documentation-standards)
6. [Git Workflow](#git-workflow)
7. [Quality Gates](#quality-gates)
8. [Sprint Retrospective](#sprint-retrospective)
9. [Sprint 6+ Checklist](#sprint-6-checklist)
10. [Templates and Examples](#templates-and-examples)

---

## Pre-Sprint Planning

### When to Create a New Sprint vs Extend Existing

**Create a new sprint when**:
- Previous sprint is complete and merged to main
- New feature requires distinct specification (different user stories)
- Sprint scope is substantially different from previous work
- Calendar week boundary crossed (sprints typically 1-2 weeks)

**Extend existing sprint when**:
- Adding P2/P3 features to partially-complete sprint
- Fixing bugs discovered in sprint testing
- Completing deferred tasks from sprint backlog
- Sprint duration is still within 2-week window

**Examples from Sprints 0-5**:
- ✅ Sprint 4.5 created: Schema refactoring was distinct from multi-agent work
- ✅ Sprint 5 created: Async migration was architectural change requiring new spec
- ❌ Should have extended Sprint 4: Adding AgentCard UI (actually done correctly as part of Sprint 4)

### Sprint Naming Convention

**Format**: `sprint-NN-short-name.md`

**Rules**:
- **NN**: Two-digit sprint number (00, 01, 02..., 10, 11...)
- **short-name**: 2-4 words, lowercase, hyphen-separated
- **short-name style**: Action-oriented or feature-focused
  - Good: `async-workers`, `human-loop`, `multi-agent`
  - Bad: `phase2`, `updates`, `improvements`

**Examples**:
- `sprint-00-foundation.md` - Project setup sprint
- `sprint-04.5-project-schema.md` - Interim schema refactoring (note: decimal for interim sprints)
- `sprint-06-human-loop.md` - Human-in-the-loop feature
- `sprint-09-polish.md` - Polish and review sprint

### Sprint Numbering

**Standard numbering** (Sprints 0-9):
- Sprint 0: Foundation (setup)
- Sprints 1-5: ✅ Complete
- Sprint 6: Next sprint (human-loop)
- Sprints 7-9: Planned sprints

**Interim sprints** (exceptional cases):
- Use decimal notation: `4.5`, `7.5`
- Only when urgent refactoring needed mid-sprint
- Document reason in sprint file
- Example: Sprint 4.5 was schema refactoring between Sprint 4 and 5

**Future sprints** (10+):
- Continue sequential numbering: 10, 11, 12...
- Reset numbering only at major version milestones
- Document in SPRINTS.md roadmap section

### Setting Realistic Goals and User Stories

**Sprint Goal**:
- Single sentence describing sprint outcome
- Focus on user value, not technical details
- Measurable success criteria
- Example: "Convert worker agents to async/await pattern for true concurrent execution"

**User Story Format**:
- "As a [user role], I want [capability] so that [business value]"
- Focus on observable behavior, not implementation
- Include acceptance criteria
- Example: "As a developer, I want worker agents to broadcast WebSocket updates reliably without threading deadlocks"

**P0 vs P1 vs P2 Features**:
- **P0** (Must-Have): Core functionality for sprint success, blocks Definition of Done
- **P1** (Should-Have): Important enhancements, defer if time-constrained
- **P2** (Nice-to-Have): Polish and optimizations, defer to future sprints
- **P3** (Future): Identified but not planned for current sprint

**Velocity Planning**:
- Sprint 1-3: 4-6 features typical
- Sprint 4-5: 6-8 features (team matured)
- Plan for 80% capacity (account for unknowns)
- Defer P1 features if P0 at risk

---

## Speckit Workflow (MANDATORY)

Starting Sprint 6, all features MUST follow the speckit workflow. This is a constitutional requirement.

### Overview: 5-Step Process

```
/speckit.specify → /speckit.plan → /speckit.tasks → /speckit.implement → /speckit.checklist
      ↓                 ↓                ↓                  ↓                    ↓
   spec.md        plan.md +        tasks.md          Execute tasks      Validate complete
                  research.md                        with agents
                  data-model.md
                  quickstart.md
                  contracts/
```

### Step 1: `/speckit.specify` - Create Feature Specification

**Purpose**: Define WHAT to build from user perspective (no implementation details)

**Command**:
```bash
/speckit.specify [natural language feature description]
```

**Example**:
```bash
/speckit.specify I want agents to ask for help when blocked and resume after user answers
```

**Workflow**:
1. Command analyzes feature description
2. Generates 2-4 word branch name (e.g., `006-human-loop`)
3. Creates `specs/###-feature-name/` directory
4. Generates `spec.md` from template
5. Fills in user stories, requirements, success criteria

**Output**: `specs/###-feature-name/spec.md` containing:

- **User Scenarios & Testing** (Mandatory)
  - User Story 1, 2, 3... with priorities (P1, P2, P3)
  - Each story independently testable
  - Acceptance scenarios in Given/When/Then format
  - Edge cases identified

- **Requirements** (Mandatory)
  - Functional Requirements (FR-001, FR-002...)
  - Key Entities (if data involved)
  - Non-functional requirements (performance, security)

- **Success Criteria** (Mandatory)
  - Measurable outcomes (SC-001, SC-002...)
  - Technology-agnostic metrics
  - User satisfaction indicators

**Template**: `.specify/templates/spec-template.md`

**Quality Validation**:
- No implementation details (no languages, frameworks, APIs)
- Focus on user value and business needs
- All mandatory sections completed
- Maximum 3 [NEEDS CLARIFICATION] markers

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 4: Well-defined user stories enabled parallel agent implementation
- ✅ Sprint 5: Clear success criteria (async migration, no deadlocks) drove implementation
- ❌ Sprint 1-2: Initial specs had too much implementation detail (avoid this)

### Step 2: `/speckit.plan` - Generate Implementation Plan

**Purpose**: Define HOW to build (technical approach, architecture, research)

**Command**:
```bash
/speckit.plan
```
(Assumes current feature from `/speckit.specify`)

**Workflow**:
1. Loads `spec.md` from current feature
2. Runs **Constitution Check** (validates against core principles)
3. Performs **Phase 0: Research** (patterns, alternatives, decisions)
4. Defines **Technical Context** (language, deps, platform)
5. Decides **Project Structure** (single/web/mobile)
6. Creates **Phase 1: Design** artifacts (data model, quickstart, contracts)

**Output**: Multiple files in `specs/###-feature-name/`:

1. **plan.md** - Implementation plan
   - Summary
   - Technical Context (language/version, deps, storage, testing, platform)
   - Constitution Check (GATE: must pass before Phase 0)
   - Project Structure (docs + source code)
   - Complexity Tracking (if constitution violations)

2. **research.md** - Phase 0 output
   - Pattern Analysis (existing patterns to follow)
   - Alternatives Considered (technical decisions)
   - Rationale (why chosen approach)
   - Constraints (technical/business limitations)

3. **data-model.md** - Phase 1 output
   - Entities (classes, tables, types)
   - Relationships (foreign keys, references)
   - Schema (database schema, type definitions)
   - Validation rules

4. **quickstart.md** - Phase 1 output
   - 5-minute tutorial
   - Code examples (extracted from actual code)
   - Common patterns (usage examples)
   - Troubleshooting (common errors)

5. **contracts/** directory - Phase 1 output
   - API contracts (endpoint signatures)
   - Interface definitions (TypeScript interfaces, Python protocols)
   - Event schemas (WebSocket events, message formats)
   - Test requirements (contract tests, integration tests)

**Templates**:
- `.specify/templates/plan-template.md`

**Constitution Check Gates**:

Per `.specify/memory/constitution.md`, all features must comply with:

I. **Test-First Development** (NON-NEGOTIABLE)
   - Tests written before implementation
   - Tests must fail initially
   - User approval of failing tests before proceeding

II. **Async-First Architecture**
   - All I/O-bound operations use async/await
   - No blocking synchronous calls in agent paths
   - AsyncAnthropic client for LLM calls

III. **Context Efficiency**
   - Virtual Project system (Hot/Warm/Cold tiers)
   - Importance scoring (0.0-1.0)
   - 30-50% token usage reduction

IV. **Multi-Agent Coordination**
   - Lead Agent coordinates via SQLite state
   - Worker agents execute independently
   - Dependency resolution via DAG

V. **Observability & Traceability**
   - WebSocket broadcasts for real-time updates
   - SQLite changelog for state mutations
   - Git auto-commits with conventional messages
   - Structured logging

VI. **Type Safety**
   - Python type hints (mypy enforcement)
   - TypeScript strict mode (no `any`)
   - Pydantic models for runtime validation

VII. **Incremental Delivery**
   - User stories prioritized (P1, P2, P3)
   - Each story independently testable
   - MVP-first approach

**Complexity Tracking**:
If constitution check fails, document in plan.md:
| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Example: 4th agent type | Specialized skill needed | Existing agents can't handle X |

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Async-first architecture reduced deadlocks and improved performance 30-50%
- ✅ Sprint 4: Multi-agent DAG coordination enabled parallel execution
- ❌ Sprint 3: Initial threading model violated async-first (fixed in Sprint 5)

### Step 3: `/speckit.tasks` - Generate Actionable Task List

**Purpose**: Break implementation into executable tasks organized by user story

**Command**:
```bash
/speckit.tasks
```

**Workflow**:
1. Loads spec.md (for user stories P1, P2, P3)
2. Loads plan.md (for tech stack, architecture)
3. Loads data-model.md, contracts/, research.md (if exist)
4. Generates task list organized by phase and user story
5. Marks parallelization opportunities [P]
6. Tracks dependencies

**Output**: `specs/###-feature-name/tasks.md`

**Task Format**: `[ID] [P?] [Story] Description`
- **ID**: T001, T002, T003...
- **[P]**: Parallel marker (different files, no dependencies)
- **[Story]**: User story reference (US1, US2, US3)
- **Description**: Specific action with exact file path

**Phase Organization**:

1. **Phase 1: Setup (Shared Infrastructure)**
   - Project initialization
   - Basic structure
   - Linting/formatting config
   - Example: `T001 Create project structure per implementation plan`

2. **Phase 2: Foundational (Blocking Prerequisites)**
   - Core infrastructure
   - MUST be complete before ANY user story
   - Database schema, auth framework, API routing
   - Example: `T004 Setup database schema and migrations framework`
   - **Checkpoint**: Foundation ready - user stories can begin in parallel

3. **Phase 3+: User Story Implementation**
   - One phase per user story (P1, P2, P3...)
   - Each story independently testable
   - Tests written FIRST (if requested)
   - Example:
     ```
     ## Phase 3: User Story 1 - Blocker Creation (Priority: P1) 🎯 MVP

     ### Tests for User Story 1 (OPTIONAL - only if tests requested) ⚠️
     - [ ] T010 [P] [US1] Contract test for blocker creation in tests/contract/test_blocker.py
     - [ ] T011 [P] [US1] Integration test for blocker workflow in tests/integration/test_blocker.py

     ### Implementation for User Story 1
     - [ ] T012 [P] [US1] Create Blocker model in codeframe/models/blocker.py
     - [ ] T013 [US1] Implement BlockerService in codeframe/services/blocker_service.py
     - [ ] T014 [US1] Add blocker creation endpoint in codeframe/api/blockers.py
     ```
   - **Checkpoint**: User Story 1 fully functional and testable independently

4. **Phase N: Polish & Cross-Cutting Concerns**
   - Documentation updates
   - Code cleanup
   - Performance optimization
   - Security hardening
   - Quickstart validation

**Dependencies & Execution Order**:

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Stories (Phase 3+)**: Depend on Foundational completion
  - Can proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories

**Parallel Opportunities**:
- All tasks marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members
- Example:
  ```bash
  # Launch all tests for User Story 1 together:
  Task: "Contract test for blocker creation in tests/contract/test_blocker.py"
  Task: "Integration test for blocker workflow in tests/integration/test_blocker.py"
  ```

**Template**: `.specify/templates/tasks-template.md`

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 4: User story organization enabled parallel agent work
- ✅ Sprint 5: Phase breakdown (1-5) tracked migration progress clearly
- ❌ Sprint 1-2: Tasks too granular initially (find right balance)

### Step 4: `/speckit.implement` - Execute Tasks with Agents

**Purpose**: Execute implementation tasks with AI agent coordination

**Command**:
```bash
/speckit.implement
```

**Prerequisites**:
- tasks.md exists (from `/speckit.tasks`)
- plan.md exists (for tech stack)
- Constitution checks passed

**Workflow**:

1. **Checklist Validation** (if checklists/ exists)
   - Scan all checklist files
   - Count total, completed, incomplete items
   - Display status table:
     ```
     | Checklist   | Total | Completed | Incomplete | Status |
     |-------------|-------|-----------|------------|--------|
     | ux.md       | 12    | 12        | 0          | ✓ PASS |
     | test.md     | 8     | 5         | 3          | ✗ FAIL |
     | security.md | 6     | 6         | 0          | ✓ PASS |
     ```
   - If incomplete: Ask user to proceed or stop
   - If complete: Automatically proceed

2. **Load Implementation Context**
   - REQUIRED: Read tasks.md, plan.md
   - IF EXISTS: Read data-model.md, contracts/, research.md, quickstart.md

3. **Project Setup Verification**
   - Detect project type (git, Docker, Node.js, Python, etc.)
   - Create/verify ignore files (.gitignore, .dockerignore, etc.)
   - Verify essential patterns exist

4. **Task Execution Loop**
   - For each phase (Setup → Foundational → User Stories → Polish):
     - Load tasks for phase
     - Detect parallel opportunities [P]
     - Execute tasks (TDD approach)
     - Update progress in SPRINT_TASK_MATRIX.md
     - Broadcast WebSocket updates
     - Git commit after logical groups

5. **TDD Approach** (Constitution Principle I):
   - Write test FIRST
   - Ensure test FAILS
   - Get user approval of failing test
   - Implement feature
   - Ensure test PASSES
   - Refactor if needed

6. **Continuous Integration**
   - Run tests after each implementation task
   - Verify coverage ≥85%
   - Fix failures immediately
   - No accumulation of technical debt

**Real-Time Progress Tracking**:
- Dashboard shows agent status
- SPRINT_TASK_MATRIX.md updated with checkboxes
- WebSocket events: task_assigned, task_started, task_completed
- Activity feed shows agent actions

**Agent Coordination** (Constitution Principle IV):
- Lead Agent coordinates via SQLite state
- Worker agents (Backend, Frontend, Test) execute independently
- Parallel tasks assigned to different agents
- Dependency resolution via DAG

**Error Handling**:
- Retry failed tasks (max 3 attempts per agent)
- Self-correction loop for test failures
- Blocker creation when stuck (Sprint 6+ feature)
- User intervention when needed

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Async agents eliminated deadlocks, 30-50% performance boost
- ✅ Sprint 4: Multi-agent parallel execution worked well with DAG
- ✅ Sprint 3: Self-correction loop (max 3 attempts) prevented infinite loops
- ❌ Sprint 4: Threading model caused deadlocks (fixed in Sprint 5)

### Step 5: `/speckit.checklist` - Validate Feature Completion

**Purpose**: Verify all requirements met before marking sprint complete

**Command**:
```bash
/speckit.checklist
```

**Prerequisites**:
- Implementation complete (all tasks in tasks.md checked)
- Tests passing (100%)

**Workflow**:
1. Load spec.md (for success criteria)
2. Load plan.md (for constitution compliance)
3. Generate validation checklist
4. Run automated checks (tests, coverage, linting)
5. Manual validation items
6. Report pass/fail

**Validation Items**:

### Functional Requirements
- [ ] All P0 features implemented and working
- [ ] User story demonstrated successfully
- [ ] No regressions in existing features
- [ ] All beads issues for sprint closed

### Testing Requirements
- [ ] Unit tests for all new code (≥ 85% coverage)
- [ ] Integration tests for cross-component features
- [ ] All tests passing (100%)
- [ ] Manual testing checklist completed

### Code Quality
- [ ] Code reviewed (manual or AI-assisted)
- [ ] No TODOs or FIXMEs in production code
- [ ] Linting clean (ruff, eslint)
- [ ] Type checking passes (mypy, tsc --noEmit)

### Constitution Compliance
- [ ] Test-first development followed (tests before code)
- [ ] Async-first architecture maintained
- [ ] Type safety enforced
- [ ] Observability maintained (WebSocket broadcasts, logging)
- [ ] Incremental delivery achieved (user stories independently testable)

### Documentation
- [ ] Sprint file created in `sprints/`
- [ ] Feature spec updated (if in `specs/`)
- [ ] CHANGELOG.md updated with user-facing changes
- [ ] Architecture docs updated if design changed
- [ ] Quickstart.md validated (examples work)

**Output**: Pass/fail report with specific failures

**Template**: `.specify/templates/checklist-template.md`

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: All tests passing (93/93) before merge
- ✅ Sprint 4.5: Zero data loss migration (validated before deploy)
- ❌ Sprint 2: Some edge cases found in manual testing (add to automated tests)

---

## Sprint Execution Standards

### Definition of Done

Every sprint must meet these criteria before marking complete:

#### Functional Requirements
- [ ] All P0 features implemented and working
- [ ] User story demonstrated successfully
- [ ] No regressions in existing features
- [ ] All beads issues for sprint closed

#### Testing Requirements
- [ ] Unit tests for all new code (≥ 85% coverage)
- [ ] Integration tests for cross-component features
- [ ] All tests passing (100%)
- [ ] Manual testing checklist completed

#### Code Quality
- [ ] Code reviewed (manual or AI-assisted)
- [ ] No TODOs or FIXMEs in production code
- [ ] Documentation updated (README, CLAUDE.md)
- [ ] Git commits follow conventional commit format

#### Integration
- [ ] Backend and frontend integrated (if applicable)
- [ ] WebSocket events working (if applicable)
- [ ] Database migrations applied successfully
- [ ] No breaking changes (or documented if unavoidable)

#### Documentation
- [ ] Sprint file created in `sprints/`
- [ ] Feature spec updated (if in `specs/`)
- [ ] CHANGELOG.md updated with user-facing changes
- [ ] Architecture docs updated if design changed

**Key Lessons from Sprints 0-5**:
- Sprint 5: Met all criteria, merged cleanly to main
- Sprint 4.5: Perfect schema migration, zero data loss
- Sprint 4: Deferred P1 features to avoid scope creep (good decision)

### Required Artifacts

For each sprint, you MUST create:

#### In `sprints/` directory:

**File**: `sprint-NN-name.md`

**Sections** (see Sprint 5 as example):
1. **Header**
   - Status: 🚧 In Progress | ✅ Complete | 📋 Planned
   - Duration: Week N (Month Year)
   - Epic/Issues: cf-XX, cf-YY

2. **Goal** (1 sentence)
   - What this sprint delivers
   - Focus on user value

3. **User Story** (1-2 sentences)
   - As a [role], I want [capability] so that [value]

4. **Implementation Tasks**
   - Core Features (P0) with checkboxes
   - Optional Features (P1) with checkboxes
   - Deferred Features (P2) with checkboxes
   - Each task linked to commit SHA

5. **Definition of Done**
   - All checklist items from sprint planning
   - Each item checked when complete

6. **Key Commits**
   - List of significant commits with SHA and description
   - Format: `SHA - type(scope): description`

7. **Metrics**
   - Tests: X passing (Y%)
   - Coverage: Z%
   - Performance: Specific metrics
   - Agents: Number and types

8. **Key Features Delivered**
   - Bullet list of major features
   - Focus on user-visible changes

9. **Sprint Retrospective** (see section below)

10. **References**
    - Beads issues
    - Feature specs
    - Documentation
    - Pull requests

**Examples**:
- Excellent: `sprints/sprint-05-async-workers.md` (complete retrospective, metrics)
- Excellent: `sprints/sprint-04.5-project-schema.md` (schema changes documented)

#### In `specs/` directory (if applicable):

**Directory**: `specs/###-feature-name/`

**Required Files** (complete speckit):
1. **spec.md** - User stories, requirements, success criteria
2. **plan.md** - Technical context, constitution check, structure
3. **tasks.md** - Actionable tasks organized by phase and user story
4. **research.md** - Patterns, alternatives, decisions
5. **data-model.md** - Schema, types, structures
6. **quickstart.md** - 5-minute tutorial, patterns, troubleshooting
7. **contracts/** - API contracts, interfaces, events

**Examples**:
- Complete: `specs/048-async-worker-agents/` (all 7 artifacts present)
- Complete: `specs/004-multi-agent-coordination/` (full speckit)

#### Global Documentation Updates

**SPRINTS.md**:
- Update "Current Sprint" link
- Add sprint to "Completed Sprints" section
- Update metrics (cumulative progress)
- Add sprint summary (3-5 bullet points)

**CLAUDE.md** (if architecture changed):
- Update "Active Technologies" section
- Update "Recent Changes" section
- Add manual additions if needed (see Phase 5.2 example)

**README.md** (if user-facing changes):
- Update feature list
- Update installation/setup if needed
- Update usage examples
- Add screenshots if UI changed

**CHANGELOG.md** (always):
- Document breaking changes
- Document new features
- Document bug fixes
- Follow Keep a Changelog format

---

## Testing Requirements

### Test-First Development (Constitution Principle I)

**MANDATORY**: Tests MUST be written before implementation code.

**Red-Green-Refactor Cycle**:

1. **RED**: Write failing test
   ```python
   # tests/test_blocker.py
   async def test_create_blocker():
       """Test blocker creation when agent gets stuck."""
       blocker = await create_blocker(agent_id="agent-1", question="How to proceed?")
       assert blocker.status == "pending"
   ```
   - Run test: `pytest tests/test_blocker.py::test_create_blocker`
   - Verify: Test FAILS (function doesn't exist yet)
   - Get user approval: "Test fails as expected, ready to implement?"

2. **GREEN**: Implement minimum code to pass
   ```python
   # codeframe/services/blocker_service.py
   async def create_blocker(agent_id: str, question: str) -> Blocker:
       """Create a new blocker for agent."""
       blocker = Blocker(agent_id=agent_id, question=question, status="pending")
       await db.save_blocker(blocker)
       return blocker
   ```
   - Run test: `pytest tests/test_blocker.py::test_create_blocker`
   - Verify: Test PASSES

3. **REFACTOR**: Improve code quality
   - Extract common logic
   - Improve naming
   - Add type hints
   - Re-run tests: All still passing

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Migrated 150+ tests to async, all passing before merge
- ✅ Sprint 4: 118/120 tests passing (98% pass rate), fixed 2 flaky tests
- ❌ Sprint 1-2: Some tests written after code (adopt TDD strictly going forward)

### Coverage Targets

**Minimum Coverage**: 85% line coverage (enforced by pytest-cov)

**Coverage by Category**:
- **Models**: 90%+ (simple data structures)
- **Services**: 85%+ (business logic)
- **API Endpoints**: 80%+ (integration tests cover)
- **Utilities**: 90%+ (pure functions)
- **UI Components**: 85%+ (Jest/Vitest)

**Measuring Coverage**:

Backend (Python):
```bash
pytest --cov=codeframe --cov-report=term-missing --cov-report=html
open htmlcov/index.html
```

Frontend (TypeScript):
```bash
cd web-ui
npm test -- --coverage
open coverage/index.html
```

**Coverage Enforcement**:
- Fail CI build if coverage drops below 85%
- Review coverage report before merge
- Identify untested code paths
- Add tests or justify exclusion

**Key Lessons from Sprints 0-5**:
- Sprint 5: 85%+ coverage maintained after async migration
- Sprint 4: 150+ multi-agent tests, 85%+ coverage
- Sprint 1: 92% coverage (set high bar early)

### Unit Testing

**Scope**: Individual functions, methods, classes in isolation

**Frameworks**:
- Backend: pytest (Python)
- Frontend: Jest/Vitest (TypeScript)

**Requirements**:
- Test happy path (expected behavior)
- Test edge cases (boundary conditions)
- Test error handling (exceptions, validation)
- Mock external dependencies (Anthropic API, database)
- Fast execution (< 5 seconds for all unit tests)

**Example** (Backend unit test):
```python
# tests/unit/test_agent_pool.py
import pytest
from codeframe.agents.pool import AgentPool

@pytest.fixture
def agent_pool():
    """Fixture providing fresh agent pool."""
    return AgentPool(max_agents=5)

def test_agent_pool_initialization(agent_pool):
    """Test agent pool initializes with correct capacity."""
    assert agent_pool.max_agents == 5
    assert agent_pool.active_agents == 0
    assert agent_pool.available_capacity == 5

def test_agent_pool_add_agent(agent_pool):
    """Test adding agent to pool."""
    agent = agent_pool.add_agent("agent-1", "backend")
    assert agent.id == "agent-1"
    assert agent.type == "backend"
    assert agent_pool.active_agents == 1

def test_agent_pool_max_capacity(agent_pool):
    """Test pool rejects agents when at capacity."""
    for i in range(5):
        agent_pool.add_agent(f"agent-{i}", "backend")

    with pytest.raises(PoolCapacityError):
        agent_pool.add_agent("agent-6", "backend")

@pytest.mark.asyncio
async def test_agent_pool_async_operations(agent_pool):
    """Test async agent operations."""
    agent = agent_pool.add_agent("agent-1", "backend")
    task = await agent.execute_task("task-1")
    assert task.status == "completed"
```

**Example** (Frontend unit test):
```typescript
// web-ui/__tests__/components/AgentCard.test.tsx
import { render, screen } from '@testing-library/react';
import { AgentCard } from '@/components/AgentCard';

describe('AgentCard', () => {
  const mockAgent = {
    id: 'agent-1',
    type: 'backend',
    status: 'working',
    currentTask: 'Implement API endpoint',
  };

  it('renders agent information', () => {
    render(<AgentCard agent={mockAgent} />);
    expect(screen.getByText('agent-1')).toBeInTheDocument();
    expect(screen.getByText('backend')).toBeInTheDocument();
    expect(screen.getByText('Implement API endpoint')).toBeInTheDocument();
  });

  it('displays correct status color', () => {
    const { container } = render(<AgentCard agent={mockAgent} />);
    const statusIndicator = container.querySelector('.status-working');
    expect(statusIndicator).toHaveClass('bg-green-500');
  });

  it('handles missing current task', () => {
    const agentNoTask = { ...mockAgent, currentTask: null };
    render(<AgentCard agent={agentNoTask} />);
    expect(screen.getByText('Idle')).toBeInTheDocument();
  });
});
```

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Async test migration systematic (pytest-asyncio)
- ✅ Sprint 4: Unit tests isolated (mocked database, Anthropic)
- ✅ Sprint 3: Self-correction loop tested with max 3 attempts

### Integration Testing

**Scope**: Cross-component interactions, system behavior

**Requirements**:
- Test WebSocket communication (backend ↔ frontend)
- Test database persistence (write → read → update → delete)
- Test agent coordination (Lead Agent → Worker Agents)
- Use test database (not production)
- Clean state between tests (fixtures, teardown)

**Example** (Integration test):
```python
# tests/integration/test_blocker_workflow.py
import pytest
from codeframe.database import Database
from codeframe.services.blocker_service import BlockerService
from codeframe.api.websocket import broadcast_blocker_created

@pytest.fixture
async def test_db():
    """Fixture providing test database."""
    db = Database(":memory:")  # In-memory SQLite
    await db.initialize()
    yield db
    await db.close()

@pytest.mark.asyncio
async def test_blocker_creation_workflow(test_db, websocket_client):
    """Test complete blocker creation and notification workflow."""
    # Setup
    blocker_service = BlockerService(test_db)

    # Step 1: Agent creates blocker
    blocker = await blocker_service.create_blocker(
        agent_id="agent-1",
        task_id="task-42",
        question="How to handle edge case X?",
    )
    assert blocker.id is not None
    assert blocker.status == "pending"

    # Step 2: Verify database persistence
    retrieved_blocker = await test_db.get_blocker(blocker.id)
    assert retrieved_blocker.question == "How to handle edge case X?"

    # Step 3: Verify WebSocket broadcast
    message = await websocket_client.receive_json()
    assert message["event"] == "blocker_created"
    assert message["data"]["blocker_id"] == blocker.id

    # Step 4: User resolves blocker
    resolved = await blocker_service.resolve_blocker(
        blocker_id=blocker.id,
        answer="Use pattern Y for edge case X",
    )
    assert resolved.status == "resolved"

    # Step 5: Verify agent can retrieve answer
    answer = await blocker_service.get_blocker_answer(blocker.id)
    assert answer == "Use pattern Y for edge case X"
```

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Integration tests validated async WebSocket broadcasts
- ✅ Sprint 4: Multi-agent coordination tested end-to-end
- ✅ Sprint 3: Self-correction integration test (create task → execute → fail → retry → succeed)

### Manual Testing

**When**: Before marking sprint complete (after all automated tests pass)

**Purpose**:
- Verify user experience (automated tests miss UX issues)
- Validate real-world workflows
- Catch visual/interaction bugs
- Smoke test critical paths

**Checklist Template**:

```markdown
# Sprint N Manual Test Checklist

## Setup
- [ ] Clean database (delete `.codeframe/state.db`)
- [ ] Fresh environment (new terminal, restart services)
- [ ] All services running (backend, frontend, MongoDB if needed)

## Feature Test: [Feature Name]

### Scenario 1: [Happy Path]
- [ ] Step 1: [Action] → Expected: [Result]
- [ ] Step 2: [Action] → Expected: [Result]
- [ ] Step 3: [Action] → Expected: [Result]

### Scenario 2: [Edge Case]
- [ ] Step 1: [Action] → Expected: [Result]
- [ ] Step 2: [Action] → Expected: [Result]

### Scenario 3: [Error Handling]
- [ ] Step 1: [Action] → Expected: [Error Message]
- [ ] Step 2: [Recovery Action] → Expected: [Result]

## Regression Tests

### Sprint 1 Features
- [ ] Project creation still works
- [ ] Dashboard displays projects
- [ ] WebSocket updates in real-time

### Sprint 2 Features
- [ ] Chat interface functional
- [ ] PRD generation works
- [ ] Task decomposition correct

[Continue for all previous sprints]

## Performance Checks
- [ ] Dashboard loads < 2 seconds
- [ ] WebSocket latency < 100ms
- [ ] Task assignment < 500ms

## Deliverable
- [ ] Screen recording of critical paths
- [ ] Test log with results
- [ ] Bug report (if issues found)
```

**Example**: See `TESTING.md` for Sprint 1 manual test checklist

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 4: Manual testing found dependency visualization bug (fixed before merge)
- ✅ Sprint 2: Chat interface UX improved based on manual testing
- ❌ Sprint 3: Missed WebSocket reliability issue (found in Sprint 4, fixed in Sprint 5)

---

## Documentation Standards

### Sprint Documentation

**File**: `sprints/sprint-NN-name.md`

**Length**: 80-120 lines (Sprint 5 example: 125 lines)

**Required Sections**:
1. Header (status, duration, issues)
2. Goal (1 sentence)
3. User Story (1-2 sentences)
4. Implementation Tasks (checkboxes)
5. Definition of Done (checkboxes)
6. Key Commits (SHA + description)
7. Metrics (tests, coverage, performance)
8. Key Features Delivered (bullet list)
9. Sprint Retrospective (see below)
10. References (beads, specs, docs, PRs)

**Format Example** (Sprint 5):
```markdown
# Sprint 5: Async Worker Agents

**Status**: ✅ Complete
**Duration**: Week 5 (November 2025)
**Epic/Issues**: cf-48

## Goal
Convert worker agents from synchronous to asynchronous execution to resolve event loop deadlocks.

## User Story
As a developer, I want worker agents to broadcast WebSocket updates reliably without threading deadlocks or race conditions.

## Implementation Tasks

### Core Features (P0)
- [x] **Phase 1**: Convert BackendWorkerAgent to async/await - 9ff2540
- [x] **Phase 2**: Convert FrontendWorkerAgent to async/await - 9ff2540
- [x] **Phase 3**: Convert TestWorkerAgent to async/await - 9ff2540

## Definition of Done
- [x] All worker agents use `async def execute_task()`
- [x] LeadAgent removes `run_in_executor()` wrapper
- [x] 100% test pass rate maintained

## Key Commits
- `9ff2540` - feat: convert worker agents to async/await (cf-48 Phase 1-3)

## Metrics
- **Tests**: 150+ async tests migrated
- **Coverage**: 85%+ maintained
- **Pass Rate**: 100%

[... continue with remaining sections]
```

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Excellent retrospective with challenges/solutions
- ✅ Sprint 4.5: Schema changes clearly documented
- ❌ Sprint 0-1: Initial sprint docs too brief (improved over time)

### Spec Documentation

**Directory**: `specs/###-feature-name/`

**Required Files** (complete speckit):
1. spec.md (user stories, requirements, success criteria)
2. plan.md (technical context, constitution check, structure)
3. tasks.md (actionable tasks organized by phase and user story)
4. research.md (patterns, alternatives, decisions)
5. data-model.md (schema, types, structures)
6. quickstart.md (5-minute tutorial, patterns, troubleshooting)
7. contracts/ (API contracts, interfaces, events)

**Quality Guidelines**:

- **Extract from actual code** (not speculation)
  - Bad: "We might use JWT for auth"
  - Good: "Authentication uses JWT with RS256 algorithm (see `auth_service.py:42`)"

- **Keep quickstart practical** (5-minute tutorial)
  - Include copy-paste code examples
  - Show real output
  - Document common errors
  - Example: `specs/048-async-worker-agents/quickstart.md`

- **API contracts must match implementation**
  - Document actual endpoint signatures
  - Include request/response examples
  - Show error responses
  - Test contracts with contract tests

**Example** (quickstart.md structure):
```markdown
# Quickstart: Async Worker Agents

**Time**: 5 minutes | **Prerequisites**: Python 3.11+, CodeFRAME installed

## 1. Basic Usage (2 min)

### Convert Sync Agent to Async
```python
# Before (sync)
class BackendWorkerAgent:
    def execute_task(self, task_id: str):
        result = anthropic.messages.create(...)
        return result

# After (async)
class BackendWorkerAgent:
    async def execute_task(self, task_id: str):
        result = await anthropic.messages.create(...)
        return result
```

## 2. Common Patterns (2 min)

### Async LLM Calls
[Example code...]

### Async WebSocket Broadcasts
[Example code...]

## 3. Troubleshooting (1 min)

### Error: "Event loop already running"
**Cause**: Mixing sync and async code
**Solution**: Use `asyncio.run()` or `await` consistently
[Example...]
```

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Excellent quickstart with before/after examples
- ✅ Sprint 4: Complete speckit (all 7 artifacts)
- ❌ Sprint 1-2: Specs incomplete initially (improved in Sprint 4+)

### Update Global Docs

**SPRINTS.md**:
- Update "Current Sprint" section
- Add sprint to "Completed Sprints" table
- Update metrics (cumulative progress)
- Add sprint summary (3-5 lines)

**CLAUDE.md** (if architecture changed):
- Update "Active Technologies" section
- Update "Recent Changes" section
- Add manual additions if needed

**README.md** (if user-facing changes):
- Update feature list
- Update installation if dependencies changed
- Update usage examples
- Add screenshots if UI changed

**CHANGELOG.md** (always):
- Document breaking changes (BREAKING CHANGE:)
- Document new features (feat:)
- Document bug fixes (fix:)
- Follow Keep a Changelog format

**Example** (CHANGELOG.md):
```markdown
# Changelog

## [Unreleased]

### Added
- Sprint 5: Async worker agents with AsyncAnthropic client
- WebSocket broadcasts now reliable without event loop deadlocks

### Changed
- BREAKING CHANGE: Python 3.11+ required for async/await support
- Worker agents now use `async def execute_task()` instead of sync

### Fixed
- Sprint 5: Event loop deadlocks in multi-agent WebSocket broadcasts
- Sprint 4: Dependency visualization edge case
```

---

## Git Workflow

### Branch Strategy

**Main Branch**:
- Always production-ready
- All tests passing
- Documentation up-to-date
- Protected (no direct commits)

**Feature Branches**:
- Format: `###-feature-name` (e.g., `048-async-worker-agents`)
- Created from main
- Merged via pull request
- Deleted after merge

**Sprint Branches** (optional):
- Format: `sprint-N` (e.g., `sprint-6`)
- Used for multi-feature sprints
- Merges multiple feature branches
- Merged to main when sprint complete

**Example Workflow**:
```bash
# Start new feature
git checkout main
git pull origin main
git checkout -b 048-async-worker-agents

# Work on feature
git add .
git commit -m "feat(cf-48): convert BackendWorkerAgent to async"

# Push to remote
git push -u origin 048-async-worker-agents

# Create pull request
gh pr create --title "Sprint 5: Async Worker Agents" --body "..."

# Merge after approval
gh pr merge --squash
```

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Clean feature branch, merged via PR #11
- ✅ Sprint 4: Multiple feature branches merged to sprint-4 branch
- ❌ Sprint 1-2: Some direct commits to main (use PRs going forward)

### Commit Conventions

**Format**: Conventional Commits

**Structure**: `type(scope): description`

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `test`: Add or update tests
- `docs`: Documentation only
- `refactor`: Code refactoring (no behavior change)
- `perf`: Performance improvement
- `chore`: Maintenance (dependencies, config)
- `ci`: CI/CD changes

**Scope**: Beads issue or feature ID (e.g., `cf-48`, `sprint-5`)

**Examples**:
```bash
# Good commits
feat(cf-48): convert BackendWorkerAgent to async/await
fix(cf-48): resolve event loop deadlock in WebSocket broadcasts
test(cf-48): migrate all worker agent tests to async patterns
docs(sprint-5): update README with async migration details
refactor(cf-48): extract async LLM call to shared utility

# Bad commits (avoid)
feat: updates  # Too vague, no scope
fix bug  # No scope, unclear what bug
WIP  # Not descriptive
asdf  # Meaningless
```

**Commit Message Body** (optional):
```bash
feat(cf-48): convert BackendWorkerAgent to async/await

- Replace sync Anthropic client with AsyncAnthropic
- Update execute_task() to async def
- Remove run_in_executor() wrapper in LeadAgent
- Update all call sites to await agent.execute_task()

Resolves: cf-48
Breaking Change: Python 3.11+ required
```

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Excellent commit messages (9ff2540, 324e555, etc.)
- ✅ Sprint 4: Commits linked to tasks (cc8b46e, ce2bfdb)
- ❌ Sprint 1: Some vague commits early on (improved over time)

### Pull Requests

**Title**: Match sprint or feature name
- Good: "Sprint 5: Async Worker Agents"
- Good: "Fix: Resolve WebSocket deadlock in multi-agent coordination"
- Bad: "Updates"

**Description Template**:
```markdown
## Summary
[Brief description of changes]

## Related Issues
- Beads: cf-48
- Spec: specs/048-async-worker-agents/

## Changes
- [ ] Convert BackendWorkerAgent to async
- [ ] Convert FrontendWorkerAgent to async
- [ ] Convert TestWorkerAgent to async
- [ ] Migrate tests to async patterns

## Testing
- [x] All tests passing (93/93)
- [x] Coverage ≥ 85%
- [x] Manual testing complete
- [x] No regressions

## Documentation
- [x] Sprint file created (sprints/sprint-05-async-workers.md)
- [x] README updated
- [x] CHANGELOG.md updated
- [x] Spec complete (7 artifacts)

## Constitution Compliance
- [x] Test-first development followed
- [x] Async-first architecture maintained
- [x] Type safety enforced
- [x] Observability maintained

## Screenshots/Demo
[Optional: screenshots, screen recording, demo link]

## Breaking Changes
- Python 3.11+ required for async/await support
```

**Review Process**:
1. Create PR from feature branch
2. Automated checks run (tests, linting, type checking)
3. Manual review (code quality, architecture)
4. Address feedback
5. Approve and merge (squash or merge commit)

**Merge Strategy**:
- **Squash merge**: For feature branches (clean history)
- **Merge commit**: For sprint branches (preserve feature history)
- **Rebase**: Rarely (only for small fixes)

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: PR #11 excellent (all tests passing, complete docs)
- ✅ Sprint 4: Multi-feature PR organized well
- ❌ Sprint 1-2: PRs lacked testing evidence (add screenshots/logs)

---

## Quality Gates

Before merging any feature branch, all quality gates must pass:

### Automated Checks

**Tests**:
```bash
# Backend tests
pytest --cov=codeframe --cov-report=term-missing
# Must pass: 100% tests, ≥85% coverage

# Frontend tests
cd web-ui && npm test -- --coverage
# Must pass: 100% tests, ≥85% coverage
```

**Linting**:
```bash
# Backend linting
ruff check .
# Must pass: No errors

# Frontend linting
cd web-ui && npm run lint
# Must pass: No errors
```

**Type Checking**:
```bash
# Backend type checking
mypy codeframe/
# Must pass: No type errors

# Frontend type checking
cd web-ui && npm run type-check
# Must pass: No type errors
```

**Pre-commit Hooks** (optional):
```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Runs automatically on git commit:
# - Linting (ruff, eslint)
# - Type checking (mypy, tsc)
# - Format checking (black, prettier)
```

### Manual Review

**Code Quality**:
- [ ] No code duplication (DRY principle)
- [ ] Clear naming (variables, functions, classes)
- [ ] Appropriate abstractions (not over-engineered)
- [ ] Error handling comprehensive
- [ ] Logging at appropriate levels

**Architecture**:
- [ ] Follows existing patterns
- [ ] Doesn't violate constitution principles
- [ ] Reasonable complexity (justify if needed)
- [ ] Scalable design (handles growth)

**Security**:
- [ ] No API keys in code
- [ ] Input validation on all endpoints
- [ ] SQL injection prevented (parameterized queries)
- [ ] XSS prevented (sanitized output)
- [ ] Authentication/authorization enforced

**Performance**:
- [ ] No N+1 queries
- [ ] Async operations where appropriate
- [ ] Reasonable memory usage
- [ ] No blocking operations in hot paths

### Constitution Compliance

**Verify each principle**:

I. **Test-First Development**
   - [ ] Tests written before code
   - [ ] Tests failed initially
   - [ ] User approved failing tests

II. **Async-First Architecture**
   - [ ] All I/O uses async/await
   - [ ] No blocking calls in agent paths
   - [ ] AsyncAnthropic client used

III. **Context Efficiency**
   - [ ] Virtual Project system used
   - [ ] Importance scoring applied
   - [ ] Context tiers managed

IV. **Multi-Agent Coordination**
   - [ ] Lead Agent coordinates via SQLite
   - [ ] Worker agents independent
   - [ ] Dependencies via DAG

V. **Observability & Traceability**
   - [ ] WebSocket broadcasts working
   - [ ] SQLite changelog updated
   - [ ] Git auto-commits enabled
   - [ ] Structured logging present

VI. **Type Safety**
   - [ ] Python type hints present
   - [ ] TypeScript strict mode enabled
   - [ ] Pydantic models for validation

VII. **Incremental Delivery**
   - [ ] User stories prioritized
   - [ ] Each story independently testable
   - [ ] MVP-first approach

### Documentation Checklist

**Sprint Documentation**:
- [ ] Sprint file created in `sprints/`
- [ ] All required sections present
- [ ] Retrospective honest and detailed
- [ ] Links to all artifacts

**Spec Documentation** (if new feature):
- [ ] Complete speckit (7 artifacts)
- [ ] Quickstart validated (examples work)
- [ ] API contracts match implementation
- [ ] Research documents actual decisions

**Global Documentation**:
- [ ] SPRINTS.md updated
- [ ] CLAUDE.md updated (if needed)
- [ ] README.md updated (if needed)
- [ ] CHANGELOG.md updated

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: All quality gates passed before merge
- ✅ Sprint 4.5: Manual review caught schema edge case
- ❌ Sprint 2: Type checking not enforced initially (added in Sprint 3)

---

## Sprint Retrospective

At sprint end, document in sprint file:

### Template

```markdown
## Sprint Retrospective

### What Went Well
- [Success 1]: [Description and impact]
- [Success 2]: [Description and impact]
- [Success 3]: [Description and impact]

### Challenges & Solutions
- **Challenge**: [Problem encountered]
  - **Solution**: [How it was solved]
- **Challenge**: [Problem encountered]
  - **Solution**: [How it was solved]

### Key Learnings
- [Technical insight gained]
- [Process improvement identified]
- [Pattern discovered]

### Technical Debt Created
- [Known issue or shortcut taken]
- [Planned follow-up work]

### Performance Improvements
- [Metric 1]: [Improvement percentage or measurement]
- [Metric 2]: [Improvement percentage or measurement]
```

### Example (Sprint 5)

```markdown
## Sprint Retrospective

### What Went Well
- Clean async migration without major breaking changes
- All Sprint 3 and Sprint 4 tests continue passing
- Broadcast reliability significantly improved
- Threading overhead eliminated

### Challenges & Solutions
- **Challenge**: AsyncAnthropic API differences from sync client
  - **Solution**: Updated all LLM call sites to use async methods
- **Challenge**: Test migration complexity (150+ tests)
  - **Solution**: Phased migration with validation at each step
- **Challenge**: Self-correction loop async conversion
  - **Solution**: Careful refactoring with comprehensive integration tests

### Key Learnings
- Threading and async don't mix well - use one or the other
- AsyncAnthropic client requires different initialization
- Test migration benefits from automated tools (pytest-asyncio)
- Proper async architecture simpler than sync + threading

### Performance Improvements
- Eliminated thread pool overhead
- 30-50% faster concurrent execution
- Better CPU utilization with cooperative multitasking
- Reduced memory footprint (no thread stacks)
```

### Retrospective Guidelines

**Be honest**:
- Document failures, not just successes
- Identify root causes, not symptoms
- Propose concrete improvements

**Be specific**:
- Use metrics (30-50% improvement, not "better")
- Name files/modules (blocker_service.py, not "blocker code")
- Quote error messages or commit SHAs

**Be actionable**:
- Each learning should inform future decisions
- Technical debt should have follow-up tasks
- Challenges should have documented solutions

**Key Lessons from Sprints 0-5**:
- ✅ Sprint 5: Excellent retrospective (honest, specific, actionable)
- ✅ Sprint 4: Technical debt documented (threading issues)
- ✅ Sprint 3: Learnings applied in Sprint 4 (self-correction max attempts)

---

## Sprint 6+ Checklist

Use this checklist for every future sprint:

### Planning Phase

- [ ] Sprint number and name decided
  - Format: `sprint-NN-short-name`
  - Example: `sprint-06-human-loop`

- [ ] Goal and user story defined
  - Goal: 1 sentence
  - User Story: As a [role], I want [capability] so that [value]

- [ ] Beads issues created
  - Run: `bd create "[feature description]"`
  - Link to sprint file

- [ ] `/speckit.specify` run
  - Output: `specs/###-feature-name/spec.md`
  - User stories prioritized (P1, P2, P3)
  - Requirements documented
  - Success criteria defined

- [ ] `/speckit.plan` run
  - Output: `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/`
  - Constitution check passed
  - Technical context documented
  - Project structure decided

- [ ] `/speckit.tasks` run
  - Output: `tasks.md`
  - Tasks organized by phase and user story
  - Dependencies tracked
  - Parallelization marked [P]

- [ ] Sprint file created in `sprints/`
  - File: `sprints/sprint-NN-name.md`
  - All required sections present
  - Tasks linked to commits (TBD initially)

### Execution Phase

- [ ] Tests written first (TDD)
  - Tests fail initially
  - User approves failing tests
  - Implementation makes tests pass

- [ ] `/speckit.implement` running
  - Tasks executed in order
  - Progress tracked in real-time

- [ ] Progress tracked in SPRINT_TASK_MATRIX.md
  - Checkboxes updated as tasks complete
  - Blockers documented

- [ ] Commits follow conventions
  - Format: `type(scope): description`
  - Meaningful messages
  - Linked to beads issues

- [ ] WebSocket updates working
  - Events broadcast in real-time
  - Dashboard reflects agent status

- [ ] Dashboard showing progress
  - Agents visible
  - Tasks updating
  - Progress bar accurate

### Completion Phase

- [ ] All P0 features working
  - User stories demonstrated
  - Acceptance criteria met

- [ ] All tests passing (100%)
  - Backend: pytest
  - Frontend: npm test
  - No flaky tests

- [ ] Coverage ≥85%
  - Backend: pytest --cov
  - Frontend: npm test -- --coverage
  - Review coverage report

- [ ] `/speckit.checklist` validated
  - All checklist items checked
  - Constitution compliance verified

- [ ] Constitution compliance verified
  - Test-first followed
  - Async-first maintained
  - Type safety enforced
  - Observability present
  - Incremental delivery achieved

- [ ] Documentation updated
  - SPRINTS.md: Sprint summary added
  - README.md: User-facing changes documented (if any)
  - CLAUDE.md: Architecture changes documented (if any)
  - CHANGELOG.md: Breaking changes, features, fixes

- [ ] Retrospective written
  - What went well
  - Challenges & solutions
  - Key learnings
  - Technical debt
  - Metrics

- [ ] SPRINT_TASK_MATRIX.md updated
  - All tasks checked
  - Final status: ✅ Complete

- [ ] Pull request created and merged
  - Title matches sprint name
  - Description complete (summary, testing, docs)
  - All quality gates passed
  - Merged to main

- [ ] Beads issues closed
  - Run: `bd close cf-XX`
  - Mark sprint complete

---

## Templates and Examples

### Best Examples to Follow

**Sprint Documentation**:
- **Sprint 5** (`sprints/sprint-05-async-workers.md`): Complete retrospective, excellent metrics, honest challenges/solutions
- **Sprint 4.5** (`sprints/sprint-04.5-project-schema.md`): Perfect schema migration, zero data loss, clear documentation
- **Sprint 4** (`sprints/sprint-04-multi-agent.md`): Multi-agent coordination, deferred features documented, good retrospective

**Spec Documentation**:
- **Sprint 5 Spec** (`specs/048-async-worker-agents/`): Complete speckit (all 7 artifacts), excellent quickstart
- **Sprint 4 Spec** (`specs/004-multi-agent-coordination/`): Full speckit, clear user stories, good contracts

**Testing**:
- **Sprint 5**: 150+ async tests migrated, 100% pass rate, 85%+ coverage
- **Sprint 4**: Integration tests for multi-agent coordination
- **Sprint 3**: Self-correction loop testing (max 3 attempts)

### Templates Location

**Speckit Templates**:
- `.specify/templates/spec-template.md` - Feature specification
- `.specify/templates/plan-template.md` - Implementation plan
- `.specify/templates/tasks-template.md` - Task list
- `.specify/templates/checklist-template.md` - Validation checklist

**Command Templates**:
- `.claude/commands/speckit.specify.md` - Specify workflow
- `.claude/commands/speckit.plan.md` - Plan workflow
- `.claude/commands/speckit.tasks.md` - Tasks workflow
- `.claude/commands/speckit.implement.md` - Implement workflow
- `.claude/commands/speckit.checklist.md` - Checklist workflow

**Sprint Template**:

Create `sprints/sprint-NN-name.md`:

```markdown
# Sprint N: [Name]

**Status**: 🚧 In Progress
**Duration**: Week N (Month Year)
**Epic/Issues**: cf-XX, cf-YY

## Goal
[One sentence describing sprint outcome]

## User Story
As a [role], I want [capability] so that [value].

## Implementation Tasks

### Core Features (P0)
- [ ] **Phase 1**: [Description] - [SHA when done]
- [ ] **Phase 2**: [Description] - [SHA when done]

### Optional Features (P1)
- [ ] **Task X**: [Description] - [SHA when done]

## Definition of Done
- [ ] All P0 features implemented and working
- [ ] All tests passing (100%)
- [ ] Coverage ≥85%
- [ ] Documentation updated
- [ ] Constitution compliance verified

## Key Commits
- `SHA` - type(scope): description

## Metrics
- **Tests**: X passing (Y%)
- **Coverage**: Z%
- **Performance**: [Metrics]

## Key Features Delivered
- [Feature 1]: [Description]
- [Feature 2]: [Description]

## Sprint Retrospective

### What Went Well
- [Success]

### Challenges & Solutions
- **Challenge**: [Problem]
  - **Solution**: [Fix]

### Key Learnings
- [Insight]

### Technical Debt Created
- [Known issue]

## References
- **Beads**: cf-XX
- **Specs**: specs/###-feature-name/
- **Docs**: [Links]
- **PR**: #X
```

### Constitution Template

For reference, the constitution is at:
- `.specify/memory/constitution.md` (canonical)
- `.claude/commands/speckit.constitution.md` (slash command)

**Core Principles**:
1. Test-First Development (NON-NEGOTIABLE)
2. Async-First Architecture
3. Context Efficiency
4. Multi-Agent Coordination
5. Observability & Traceability
6. Type Safety
7. Incremental Delivery

**Workflow**:
1. `/speckit.specify` → spec.md
2. `/speckit.plan` → plan.md + research.md + data-model.md + quickstart.md + contracts/
3. `/speckit.tasks` → tasks.md
4. `/speckit.implement` → Execute tasks
5. `/speckit.checklist` → Validate complete

### Common Mistakes to Avoid

**Planning**:
- ❌ Vague sprint goals ("Make improvements")
- ❌ Too many P0 features (overcommit)
- ❌ No user story (implementation-focused)
- ✅ Clear goal, realistic P0 scope, user-centric story

**Specification**:
- ❌ Implementation details in spec.md (languages, frameworks)
- ❌ Too many [NEEDS CLARIFICATION] markers (limit 3)
- ❌ No success criteria
- ✅ User-focused spec, informed guesses, measurable criteria

**Testing**:
- ❌ Tests written after code (violates constitution)
- ❌ Coverage < 85%
- ❌ Flaky tests not fixed
- ✅ TDD (tests first), ≥85% coverage, stable tests

**Documentation**:
- ❌ Incomplete sprint file (missing retrospective)
- ❌ Spec extracted from speculation (not actual code)
- ❌ Quickstart doesn't work (examples broken)
- ✅ Complete sprint file, spec from real code, validated quickstart

**Git Workflow**:
- ❌ Vague commit messages ("updates", "WIP")
- ❌ Direct commits to main (bypass PR)
- ❌ Merge with failing tests
- ✅ Conventional commits, PRs only, all tests passing

---

## Appendix: Sprint 0-5 Lessons Learned

### Sprint 0: Foundation
- ✅ Architecture documented early (CODEFRAME_SPEC.md)
- ✅ GitHub README with diagrams
- ❌ Initial specs too brief (improved over time)

### Sprint 1: Hello CodeFRAME
- ✅ 92% test coverage set high bar
- ✅ WebSocket real-time communication worked well
- ❌ Some tests written after code (adopt TDD in Sprint 6+)

### Sprint 2: Socratic Discovery
- ✅ 169 backend + 54 frontend tests (comprehensive)
- ✅ Chat interface UX validated with manual testing
- ❌ Some edge cases found late (add to automated tests)

### Sprint 3: Single Agent Execution
- ✅ Self-correction loop (max 3 attempts) prevented infinite loops
- ✅ Git auto-commit functionality worked well
- ❌ Threading model caused deadlocks (fixed in Sprint 5)

### Sprint 4: Multi-Agent Coordination
- ✅ Dependency DAG enabled parallel execution
- ✅ React Context + useReducer excellent state management
- ❌ WebSocket broadcast reliability issues (fixed in Sprint 5)
- Technical debt: Threading model, run_in_executor() overhead

### Sprint 4.5: Project Schema Refactoring
- ✅ Perfect schema migration, zero data loss
- ✅ Rollback mechanism prevented partial state corruption
- ✅ Clean separation of concerns (workspace manager)
- Lesson: Flexible schema design enables future SaaS deployment

### Sprint 5: Async Worker Agents
- ✅ Clean async migration, 30-50% performance improvement
- ✅ All tests migrated (150+), 100% pass rate
- ✅ Broadcast reliability significantly improved
- ✅ Excellent retrospective with honest challenges
- Lesson: Async-first architecture simpler than sync + threading

### Sprint 6+ Goals
- Apply all lessons learned
- Mandatory speckit workflow
- Strict TDD adherence
- Constitution compliance at every gate
- Complete documentation
- Honest retrospectives

---

**Version History**:
- 1.0.0 (2025-11-08): Initial version based on Sprints 0-5 learnings
