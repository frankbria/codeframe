# Resolved Concepts - Implementation Decisions

**Date**: 2025-01-17
**Status**: FINALIZED - Ready for Specification Integration
**Source**: CONCEPTS_INTEGRATION.md User Review

---

## Executive Summary

All open concepts from `CONCEPTS_INTEGRATION.md` have been clarified and prioritized. This document captures the final decisions and their integration plan into CodeFRAME specifications and sprint planning.

---

## Decision Summary

### 1. ✅ Hierarchical Issue/Task Model - ADOPTED

**Decision**: Implement hierarchical work breakdown with `1.5.12` notation.

**Definition**:
- **Issue**: High-level work item requiring multiple tasks (e.g., `1.5`)
- **Task**: Lowest-level atomic unit (e.g., `1.5.12`)
- **Parallelization Rule**: Last number group = sequential tasks within issue
  - Within `1.5.x`: Tasks are sequential (cannot parallelize)
  - Between `1.4` and `1.5`: Issues can parallelize

**Example**:
```
Issue 1.5: "User Authentication System" (can run parallel to Issue 1.6)
  ├─ Task 1.5.1: Create User model (must happen first)
  ├─ Task 1.5.2: Implement password hashing (depends on 1.5.1)
  ├─ Task 1.5.3: Add login endpoint (depends on 1.5.2)
  └─ Task 1.5.4: Write tests (depends on 1.5.3)

Issue 1.6: "User Profile UI" (parallel to 1.5)
  ├─ Task 1.6.1: Create profile component
  └─ Task 1.6.2: Add edit functionality
```

**Database Schema Changes**:
```sql
-- New Issues table
CREATE TABLE issues (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    issue_number TEXT NOT NULL,  -- e.g., "1.5"
    title TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed')),
    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
    workflow_step INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Enhanced Tasks table
ALTER TABLE tasks ADD COLUMN issue_id INTEGER REFERENCES issues(id);
ALTER TABLE tasks ADD COLUMN task_number TEXT NOT NULL;  -- e.g., "1.5.3"
ALTER TABLE tasks ADD COLUMN parent_issue_number TEXT;   -- e.g., "1.5"
ALTER TABLE tasks ADD COLUMN can_parallelize BOOLEAN DEFAULT FALSE;  -- Always FALSE within issue

-- Index for fast lookups
CREATE INDEX idx_tasks_issue_number ON tasks(parent_issue_number);
CREATE INDEX idx_issues_number ON issues(issue_number);
```

**Sprint Integration**: Sprint 2 (PRD Generation & Task Decomposition)
- Modify `cf-16.2` to generate issues first, then tasks within issues
- Adjust UI (cf-16.3) to show hierarchical view

---

### 2. ✅ Subagent Architecture - CLARIFIED

**Decision**: Subagent = any agent reporting to a superior (not just Worker Agents).

**Architecture**:
```
Lead Agent (Top-level Coordinator)
 │
 ├─► Backend Worker Agent (executes backend tasks)
 │    ├─► Code Reviewer Subagent (reviews backend code)
 │    └─► Test Runner Subagent (runs backend-specific tests)
 │
 ├─► Frontend Worker Agent (executes UI tasks)
 │    ├─► Accessibility Checker Subagent (a11y validation)
 │    └─► Visual Regression Subagent (screenshot comparison)
 │
 ├─► Test Worker Agent (writes tests)
 │    └─► Coverage Analyzer Subagent (coverage reports)
 │
 ├─► QA Specialist Agent (validates requirements)
 └─► User Communication Agent (handles blocker questions)
```

**Key Insight**: Agents can spawn their own subagents for specialized tasks!

**Terminology Update**:
- **Worker Agent**: Specific type of subagent (Backend, Frontend, Test, Review)
- **Subagent**: Any agent communicating back to a superior agent
- **Specialist Agent**: Non-worker subagents (QA, Communication, Research)

**Communication Pattern**:
- Subagents communicate only with their direct superior
- All coordination flows through hierarchy (no peer-to-peer)
- State persisted in SQLite for cross-session continuity

**Sprint Integration**: Sprint 4 (Multi-Agent Coordination)
- Add subagent spawning capability to Worker Agents
- Implement hierarchical reporting in Lead Agent

---

### 3. ✅ Claude Code Skills Integration - P1 for MVP

**Decision**: Leverage Claude Code's built-in skills system (Superpowers framework).

**Integration Approach**:
```python
class WorkerAgent:
    def __init__(self, agent_id: str, provider: AgentProvider):
        self.agent_id = agent_id
        self.provider = provider
        self.available_skills = self._discover_skills()

    def _discover_skills(self) -> List[str]:
        """Discover available Claude Code skills."""
        # Read from ~/.claude/skills directory
        return list_available_skills()

    def execute_task(self, task: Task):
        """Execute task with skill support."""
        # Determine which skills are needed
        if task.requires_tdd:
            self.invoke_skill("superpowers:test-driven-development")

        if task.needs_debugging:
            self.invoke_skill("superpowers:systematic-debugging")

        if task.needs_refactoring:
            self.invoke_skill("superpowers:refactoring-expert")

        # Agent proceeds with work using skill guidance
        result = self._do_work(task)
        return result

    def invoke_skill(self, skill_name: str):
        """Invoke a Claude Code skill."""
        # Use Skill tool to load skill prompt
        skill_context = load_skill(skill_name)
        self.provider.add_system_context(skill_context)
```

**Available Skills** (Superpowers):
- `test-driven-development`: RED-GREEN-REFACTOR cycle
- `systematic-debugging`: Root cause analysis
- `refactoring-expert`: Code quality improvement
- `code-reviewer`: Code review workflows
- `verification-before-completion`: Evidence-based validation
- (Many more available in Superpowers framework)

**Sprint Integration**: Sprint 4 (Multi-Agent Coordination) or Sprint 6 (Context Management)
- Priority: **P1** (Important but not blocking MVP)
- Task: `cf-XX.skills` - Claude Code Skills Integration (3-4 hours)

---

### 4. ✅ P0 Item Sprint Assignment - FINALIZED

**Codebase Indexing** → **Sprint 3** (Single Agent Execution)
- **Rationale**: Agents need structural awareness when writing code
- **Dependencies**: None (standalone)
- **Task**: `cf-18.5` - Codebase Indexing (4-6 hours)

**Git Branching Strategy** → **Sprint 3** (Single Agent Execution)
- **Rationale**: Natural pairing with git auto-commits (cf-19)
- **Dependencies**: Git integration (cf-19)
- **Task**: `cf-19.5` - Git Branching & Deployment Workflow (4-6 hours)

**Both P0 items deferred from Sprint 2 to Sprint 3** based on architectural dependencies.

---

## Priority Classification

### ✅ Already Implemented - No Action
1. Flash Save / Pre-compactification (Section 7)
2. SQLite state tracking (tasks table)
3. Task priorities/dependencies
4. Lead Agent coordination (Section 2)
5. Context management (Virtual Project - Section 3)
6. Compactification survival (Flash Save System)

### 🔴 P0 - Sprint 3 (MVP Must-Have)
1. **Hierarchical Issue/Task Model** (Sprint 2 - cf-16 modifications)
2. **Codebase Indexing** (Sprint 3 - cf-18.5) - 4-6 hours
3. **Git Branching Strategy** (Sprint 3 - cf-19.5) - 4-6 hours

### 🟡 P1 - Important (Add to MVP)
4. **Replan Command** (Sprint 2 - cf-16.4) - 3-4 hours
5. **Task Checklists** (Sprint 2 - cf-16.5) - 2-3 hours
6. **Claude Code Skills Integration** (Sprint 4 or 6 - cf-XX.skills) - 3-4 hours
7. **Claude Code Hooks** (Sprint 6 or 8 - cf-36.5) - 2-3 hours

### 🟢 P2 - Post-MVP (Future)
8. GitHub Issues integration
9. Agent skills marketplace/registry
10. Deployment automation beyond basic git

---

## Specification Updates Required

### 1. CODEFRAME_SPEC.md

**Section 5: Task Coordination** - Add subsection "5.1 Hierarchical Issue/Task Model":
```markdown
### 5.1 Hierarchical Issue/Task Model

CodeFRAME uses a hierarchical work breakdown structure with dot notation:

**Hierarchy**:
- **Issue** (`1.5`): High-level work item, may span multiple tasks
- **Task** (`1.5.3`): Atomic unit of work within an issue

**Parallelization Rules**:
- Issues at same level can execute in parallel (e.g., `1.4` and `1.5`)
- Tasks within an issue are sequential (e.g., `1.5.1` → `1.5.2` → `1.5.3`)
- Use numbering to control parallelism: go up a level to parallelize

**Example**:
```
1.0 Sprint 2: Socratic Discovery
  ├─ 1.1 Chat Interface (parallel to 1.2)
  │   ├─ 1.1.1 Backend API (sequential)
  │   ├─ 1.1.2 Frontend Component (depends on 1.1.1)
  │   └─ 1.1.3 WebSocket Integration (depends on 1.1.2)
  │
  └─ 1.2 Discovery Framework (parallel to 1.1)
      ├─ 1.2.1 Question Engine (sequential)
      ├─ 1.2.2 Answer Parser (depends on 1.2.1)
      └─ 1.2.3 Lead Agent Integration (depends on 1.2.2)
```
```

**Section 2: Core Components** - Add subsection "2.4 Subagent Architecture":
```markdown
### 2.4 Subagent Architecture

**Definition**: A subagent is any agent that communicates back to a superior agent.

**Types**:
1. **Worker Agents**: Execute tasks (Backend, Frontend, Test, Review)
2. **Specialist Subagents**: Spawned by Worker Agents for specific work
   - Code Reviewer Subagent (reviews code quality)
   - Test Runner Subagent (executes tests)
   - Accessibility Checker Subagent (validates a11y)
   - Coverage Analyzer Subagent (generates reports)

**Spawning Pattern**:
```python
class WorkerAgent:
    def spawn_subagent(self, subagent_type: str, task_context: dict) -> Subagent:
        """Create a specialized subagent for focused work."""
        subagent = Subagent.create(
            type=subagent_type,
            parent=self.agent_id,
            context=task_context,
            provider=self.provider
        )

        # Register with Lead Agent
        lead_agent.register_subagent(subagent, parent=self.agent_id)

        return subagent

    def execute_task(self, task: Task):
        # Spawn code reviewer after implementation
        if task.requires_review:
            reviewer = self.spawn_subagent('code_reviewer', {
                'files': task.modified_files,
                'standards': self.coding_standards
            })
            review_result = reviewer.review()
            # Process review feedback

        return result
```

**Communication Hierarchy**:
- Subagents report only to direct superior
- No peer-to-peer communication
- Lead Agent maintains registry of all agents/subagents
- State persists in SQLite across sessions
```

**Section 12: Database Schema** - Update to add issues table and modify tasks table.

---

### 2. AGILE_SPRINTS.md

**Sprint 2 Updates**:
- Modify **cf-16.2** description to include hierarchical issue generation
- Add **cf-16.4**: Replan Command (P1) - 3-4 hours
- Add **cf-16.5**: Task Checklists (P1) - 2-3 hours

**Sprint 3 Additions**:
- Add **cf-18.5**: Codebase Indexing (P0) - 4-6 hours
- Add **cf-19.5**: Git Branching & Deployment (P0) - 4-6 hours

**Sprint 4 Additions**:
- Add **cf-24.5**: Subagent Spawning (subagents can create subagents) - 3-4 hours
- Add **cf-24.6**: Claude Code Skills Integration (P1) - 3-4 hours

**Sprint 6 Additions**:
- Add **cf-36.5**: Claude Code Hooks (before_compact) (P1) - 2-3 hours

---

## Beads Issues to Create

### Sprint 2 (Immediate)
1. `cf-16.4` [P1] - Replan Command
2. `cf-16.5` [P1] - Task Checklists

### Sprint 3 (Week 3)
3. `cf-18.5` [P0] - Codebase Indexing
4. `cf-19.5` [P0] - Git Branching Strategy

### Sprint 4 (Week 4)
5. `cf-24.5` [P1] - Subagent Spawning
6. `cf-24.6` [P1] - Claude Code Skills Integration

### Sprint 6 (Week 6)
7. `cf-36.5` [P1] - Claude Code Hooks Integration

---

## Implementation Notes

### Hierarchical Issue/Task Model

**Lead Agent Behavior** (PRD → Issues → Tasks):
```python
def generate_work_breakdown(prd: PRD) -> List[Issue]:
    """Generate hierarchical work breakdown from PRD."""
    # 1. Extract high-level features → Issues
    issues = []
    for idx, feature in enumerate(prd.features, start=1):
        issue = Issue(
            issue_number=f"{sprint_number}.{idx}",
            title=feature.title,
            description=feature.description
        )

        # 2. Break feature into atomic tasks
        tasks = decompose_feature_to_tasks(feature)
        for task_idx, task in enumerate(tasks, start=1):
            task.task_number = f"{issue.issue_number}.{task_idx}"
            task.parent_issue_number = issue.issue_number
            task.can_parallelize = False  # Sequential within issue
            task.depends_on = [f"{issue.issue_number}.{task_idx-1}"] if task_idx > 1 else []
            issue.tasks.append(task)

        issues.append(issue)

    return issues
```

**Agent Assignment**:
- Lead Agent assigns entire Issue to Worker Agent
- Worker Agent executes tasks sequentially within issue
- Multiple Worker Agents can work on different issues in parallel

### Subagent Spawning

**When to Spawn Subagents**:
1. **Code Review**: After implementation, before marking complete
2. **Test Execution**: Parallel test runs for large test suites
3. **Coverage Analysis**: Post-test coverage report generation
4. **Accessibility Checks**: Frontend validation
5. **Security Scans**: Vulnerability detection

**Subagent Lifecycle**:
```python
# 1. Spawn
subagent = worker.spawn_subagent('code_reviewer', context)

# 2. Execute
result = subagent.execute()

# 3. Report back to parent
worker.receive_subagent_report(subagent.id, result)

# 4. Terminate (or persist for reuse)
subagent.terminate()
```

---

## Next Actions

1. ✅ Update `CODEFRAME_SPEC.md` with new sections - **COMPLETE** (2025-10-16)
2. ✅ Update `AGILE_SPRINTS.md` with new tasks - **COMPLETE** (2025-10-16)
3. ✅ Create beads issues for P0/P1 items - **COMPLETE** (2025-10-16)
   - cf-30: cf-16.4 [P1] Replan Command
   - cf-31: cf-16.5 [P1] Task Checklists
   - cf-32: cf-18.5 [P0] Codebase Indexing
   - cf-33: cf-19.5 [P0] Git Branching Strategy
   - cf-34: cf-24.5 [P1] Subagent Spawning
   - cf-35: cf-24.6 [P1] Claude Code Skills Integration
   - cf-36: cf-36.5 [P1] Claude Code Hooks Integration
4. ⏳ Archive `CONCEPTS_INTEGRATION.md` (mark as resolved) - **PENDING**
5. ⏳ Update `docs/SPRINT2_PLAN.md` with cf-16 modifications - **PENDING**

---

**Document Status**: IMPLEMENTED
**Last Updated**: 2025-10-16
**Implementation Status**: All P0/P1 tasks integrated into specifications and created in beads issue tracker
