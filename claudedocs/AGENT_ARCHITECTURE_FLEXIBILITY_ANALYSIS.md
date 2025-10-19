# Agent Architecture Flexibility Analysis
**Date**: 2025-10-19
**Context**: Pre-Sprint 4 architectural review
**Concern**: Ensuring agent types aren't hard-coded and system supports future extensibility

---

## Executive Summary

**CRITICAL FINDING**: The current architecture has **3 hard-coded constraints** that will block Claude Code skills integration and future agent type flexibility:

1. ✅ **Database schema CHECK constraint** (Line 103 of database.py) - Enum restricts agent types to 5 values
2. ✅ **CODEFRAME_SPEC.md documentation** (Lines 129-133) - Explicitly lists 4 agent types as "MVP"
3. ⚠️ **No plugin/skill discovery system** - cf-24.6 is planned but not implemented

**Risk Level**: 🔴 **HIGH** - Proceeding with Sprint 4 as currently specified will create technical debt

**Recommendation**: Refactor agent type system BEFORE implementing cf-21 (Frontend Agent) and cf-22 (Test Agent)

---

## Detailed Findings

### 1. Database Schema Constraint (CRITICAL)

**Location**: `codeframe/persistence/database.py:103`

```sql
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
    provider TEXT,
    maturity_level TEXT CHECK(...),
    status TEXT CHECK(...),
    ...
)
```

**Problem**:
- Hard-coded enum: `'lead', 'backend', 'frontend', 'test', 'review'`
- Adding new agent types (e.g., "security", "accessibility", "docs") requires **schema migration**
- Claude Code skills cannot dynamically define new agent types
- Subagent spawning (cf-24.5) limited to these 5 types

**Impact**:
- ❌ **Blocks** Claude Code skills integration (cf-24.6)
- ❌ **Blocks** dynamic agent type creation
- ❌ **Forces** migration for every new agent capability
- ✅ **Allows** current 5 agent types to work

**Compatibility with Claude Code Skills**: 🔴 **INCOMPATIBLE**

---

### 2. Specification Documentation (MEDIUM)

**Location**: `CODEFRAME_SPEC.md:129-133`

```markdown
**Types** (MVP):
- **Backend Agent**: API development, database, business logic
- **Frontend Agent**: UI components, state management
- **Test Agent**: Unit tests, integration tests, E2E tests
- **Review Agent**: Code review, quality checks, security scans
```

**Problem**:
- Spec documents 4 agent types as canonical/primary
- No mention of extensibility or plugin system
- Creates expectation that these are the ONLY types
- Sprint 4 tasks (cf-21, cf-22) assume these exact types

**Impact**:
- ⚠️ **Guides** implementation toward rigid 4-type system
- ⚠️ **Limits** architectural thinking about flexibility
- ⚠️ **Creates** documentation debt when types expand
- ✅ **Provides** clear MVP scope

**Compatibility with Claude Code Skills**: 🟡 **PARTIALLY COMPATIBLE** (documentation only, not code)

---

### 3. Agent Implementation (LOW RISK, but revealing)

**Location**: `codeframe/agents/`

**Current Structure**:
```
codeframe/agents/
├── __init__.py
├── lead_agent.py
├── worker_agent.py          # Generic base class
└── backend_worker_agent.py  # Specialized implementation
```

**Findings**:
- ✅ **Good**: `WorkerAgent` base class exists (worker_agent.py:5)
- ✅ **Good**: Takes `agent_type: str` as constructor parameter (not enum)
- ✅ **Good**: `BackendWorkerAgent` is a **specialization**, not the only option
- ⚠️ **Missing**: No agent registry/factory pattern
- ⚠️ **Missing**: No skills discovery system

**Code Analysis**:

```python
# worker_agent.py - Generic base (GOOD!)
class WorkerAgent:
    def __init__(self, agent_id: str, agent_type: str, provider: str, ...):
        self.agent_type = agent_type  # String, not enum - flexible!
```

```python
# backend_worker_agent.py - Specialized implementation
class BackendWorkerAgent:
    """Autonomous agent that executes backend development tasks."""
    # Hardcoded prompts for "Backend Worker Agent" role
    # LLM instructions specific to backend work
```

**Impact**:
- ✅ **Allows** new agent types via WorkerAgent base class
- ⚠️ **Requires** manual class creation for each type (no markdown instructions)
- ❌ **Cannot** define agent via simple markdown file

**Compatibility with Claude Code Skills**: 🟡 **PARTIALLY COMPATIBLE** (extensible but manual)

---

### 4. Claude Code Skills Integration Gap (cf-24.6)

**Location**: `AGILE_SPRINTS.md:1940-1945`

```markdown
- [ ] **cf-24.6**: Claude Code Skills Integration (P1)
  - Integrate with Superpowers framework
  - Skills discovery and invocation
  - TDD, debugging, refactoring skills support
  - Demo: Agent uses test-driven-development skill
  - **Estimated Effort**: 3-4 hours
```

**Problem**:
- Task is **P1 (lower priority)** but is **foundational** for flexibility
- No implementation yet - just a plan
- Described as "3-4 hours" but requires architectural changes
- Should be **P0** and **prerequisite** for cf-21, cf-22

**Impact**:
- ❌ **Delays** skills integration to after agent types are hard-coded
- ❌ **Creates** technical debt if cf-21/cf-22 implemented first
- ❌ **Requires** refactoring if done out of order

**Compatibility with Claude Code Skills**: 🔴 **NOT IMPLEMENTED**

---

## User's Specific Questions Answered

### Q1: "Will they be compatible with Claude Code skills?"

**Answer**: 🔴 **NO**, not without refactoring.

**Reason**:
- Database CHECK constraint prevents dynamic agent types
- cf-24.6 (skills integration) is P1, not implemented
- Current architecture assumes manually-coded agent classes

**Required Changes**:
1. Remove/loosen database CHECK constraint on agent type
2. Implement cf-24.6 BEFORE cf-21/cf-22
3. Create agent capability/skill registry system

---

### Q2: "Can they be enhanced by simple markdown instructions?"

**Answer**: 🔴 **NO**, not currently.

**Current Limitation**:
- `BackendWorkerAgent` has hardcoded system prompts (lines 198-311)
- No mechanism to load agent instructions from markdown files
- Agent behavior is Python code, not configuration

**What Would Be Needed**:
```
codeframe/agents/definitions/
├── backend.md        # Backend agent instructions
├── frontend.md       # Frontend agent instructions
├── security.md       # NEW: Security agent (user-defined)
└── accessibility.md  # NEW: a11y agent (user-defined)
```

**Implementation Gap**:
- No markdown → agent instruction loader
- No agent factory that reads definitions/
- No cf-24.6 implementation (skills framework)

---

### Q3: "Are we accidentally hard-coding agent types?"

**Answer**: ✅ **YES**, in 2 places:

1. **Database schema** (database.py:103): CHECK constraint = hard enum
2. **Specification** (CODEFRAME_SPEC.md:129-133): Documents 4 types as canonical

**Good News**:
- Python code uses strings (`agent_type: str`), not enums
- `WorkerAgent` base class is generic and reusable

**Bad News**:
- Database will reject any type not in ['lead', 'backend', 'frontend', 'test', 'review']
- Documentation guides toward rigid 4-type thinking

---

### Q4: "Are we boxing ourselves in?"

**Answer**: ✅ **YES**, if we proceed with Sprint 4 as currently planned.

**Danger Scenario**:
```
1. Implement cf-21: Frontend Worker Agent (hardcoded class)
2. Implement cf-22: Test Worker Agent (hardcoded class)
3. Deploy to production with 3 agent types working
4. Attempt cf-24.6: Claude Code Skills Integration
5. Realize database schema + hardcoded classes block flexibility
6. Require breaking changes to add dynamic agent types
7. Technical debt + migration pain
```

**Safe Scenario**:
```
1. Refactor agent type system (remove CHECK constraint)
2. Implement cf-24.6: Skills integration + markdown definitions
3. Define frontend/test agents via markdown (not hardcoded classes)
4. Proceed with cf-21/cf-22 using flexible architecture
5. Future agent types = just add markdown file
6. No breaking changes needed
```

---

## Architectural Recommendations

### Recommendation 1: Remove Database CHECK Constraint

**Change**: `codeframe/persistence/database.py:103`

**Before**:
```sql
type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
```

**After**:
```sql
type TEXT NOT NULL,  -- Allow any agent type
```

**Rationale**:
- Enables dynamic agent type registration
- Allows Claude Code skills to define new types
- No functional loss (validation can be done at application layer)

**Migration**:
```sql
-- Add migration to remove CHECK constraint
ALTER TABLE agents DROP CONSTRAINT agents_type_check;  -- SQLite doesn't support this
-- Alternative: Create new table without constraint, copy data, rename
```

**Effort**: 1 hour

---

### Recommendation 2: Implement Agent Definition System (cf-24.6 FIRST)

**Priority**: 🔴 **P0** (must do before cf-21, cf-22)

**Design**:
```
codeframe/agents/definitions/
├── backend.yaml         # YAML or Markdown
├── frontend.yaml
├── test.yaml
└── custom/              # User-extensible
    ├── security.yaml
    └── docs.yaml
```

**Example Definition** (backend.yaml):
```yaml
name: Backend Worker
type: backend
description: Executes backend development tasks (API, database, business logic)
capabilities:
  - python_development
  - api_design
  - database_modeling
  - test_driven_development
system_prompt: |
  You are a Backend Worker Agent in the CodeFRAME autonomous development system.

  Your role:
  - Read task descriptions carefully
  - Analyze existing codebase structure
  - Write clean, tested Python code
  - Follow project conventions and patterns
tools:
  - codebase_index
  - test_runner
  - anthropic_api
maturity_model: situational_leadership_ii
```

**Loader Implementation**:
```python
class AgentDefinitionLoader:
    def load_definitions(self, path: Path) -> Dict[str, AgentDefinition]:
        """Load all agent definitions from YAML/Markdown."""
        definitions = {}
        for file in path.glob("*.yaml"):
            definition = yaml.safe_load(file.read_text())
            definitions[definition["type"]] = AgentDefinition(**definition)
        return definitions

    def create_agent(self, agent_type: str, **kwargs) -> WorkerAgent:
        """Factory method using definition."""
        definition = self.definitions[agent_type]
        return WorkerAgent(
            agent_type=agent_type,
            system_prompt=definition.system_prompt,
            capabilities=definition.capabilities,
            **kwargs
        )
```

**Benefits**:
- ✅ Agents defined via configuration, not hardcoded classes
- ✅ Users can add new agent types without touching Python code
- ✅ Claude Code skills can provide agent definitions
- ✅ Markdown instructions become agent behavior

**Effort**: 3-4 hours (as estimated in cf-24.6)

---

### Recommendation 3: Capability-Based Agent System

**Concept**: Instead of rigid "backend" vs "frontend" types, use **capabilities**

**Example**:
```yaml
# Instead of type: backend
capabilities:
  - python_development
  - api_design
  - sql_database
  - async_programming

# Instead of type: frontend
capabilities:
  - react_development
  - typescript
  - ui_design
  - accessibility

# Hybrid agent (flexible!)
capabilities:
  - python_development
  - react_development
  - full_stack_expertise
```

**Task Routing**:
```python
def assign_task_to_agent(task: Task, agents: List[Agent]) -> Agent:
    """Match task requirements to agent capabilities."""
    required_capabilities = task.extract_required_capabilities()

    # Find agent with best capability match
    best_agent = max(
        agents,
        key=lambda a: len(set(a.capabilities) & set(required_capabilities))
    )
    return best_agent
```

**Benefits**:
- ✅ More flexible than rigid types
- ✅ Agents can have multiple specializations
- ✅ Tasks matched to capabilities, not arbitrary labels
- ✅ Easier to extend (just add capabilities to definition)

**Effort**: 4-5 hours (refactor task assignment logic)

---

### Recommendation 4: Refactor cf-21 and cf-22 Task Definitions

**Current Plan** (AGILE_SPRINTS.md:1954):
```markdown
- [ ] **cf-21**: Implement Frontend Worker Agent (P0)
- [ ] **cf-22**: Implement Test Worker Agent (P0)
```

**Revised Plan**:
```markdown
- [ ] **cf-24.6**: Agent Definition System (P0) - MOVED UP FROM P1
  - Create agent definition loader (YAML/Markdown)
  - Remove database CHECK constraint on agent type
  - Implement agent factory pattern
  - Define backend agent via YAML (refactor existing BackendWorkerAgent)
  - Demo: Load agent from definition file

- [ ] **cf-21**: Define Frontend Agent via Markdown/YAML (P0)
  - Create frontend.yaml agent definition
  - System prompts for UI development
  - Capabilities: react, typescript, tailwind, accessibility
  - Demo: Frontend agent loaded from definition, executes task

- [ ] **cf-22**: Define Test Agent via Markdown/YAML (P0)
  - Create test.yaml agent definition
  - System prompts for test writing (pytest, jest)
  - Capabilities: unit_testing, integration_testing, tdd
  - Demo: Test agent loaded from definition, writes tests
```

**Key Changes**:
- cf-24.6 becomes **prerequisite** for cf-21, cf-22
- Agents defined via files, not hardcoded classes
- Future agent types = add YAML file (no code changes)

---

## Migration Plan

### Phase 1: Database Schema Fix (1 hour)

**Tasks**:
1. Create migration script to drop agent type CHECK constraint
2. Update database.py:103 to remove constraint from schema creation
3. Test that arbitrary agent types can be stored
4. Commit: "refactor(cf-24.6): Remove hardcoded agent type constraint"

**Risk**: Low - backward compatible change

---

### Phase 2: Agent Definition System (4 hours)

**Tasks**:
1. Create `codeframe/agents/definitions/` directory
2. Implement `AgentDefinitionLoader` class
3. Create YAML schema for agent definitions
4. Refactor `BackendWorkerAgent` to use definition file
5. Create `backend.yaml` from existing backend agent code
6. Update agent factory to load from definitions
7. Add tests for definition loading
8. Commit: "feat(cf-24.6): Implement agent definition system"

**Risk**: Medium - requires refactoring existing backend agent

---

### Phase 3: Define Frontend and Test Agents (2 hours)

**Tasks**:
1. Create `frontend.yaml` agent definition
2. Create `test.yaml` agent definition
3. Test that agents load from definitions
4. Verify agents can execute tasks
5. Commit: "feat(cf-21,cf-22): Add frontend and test agent definitions"

**Risk**: Low - using new flexible system

---

### Phase 4: Claude Code Skills Integration (3 hours)

**Tasks**:
1. Add `codeframe/agents/definitions/custom/` for user definitions
2. Document how users can add custom agent types
3. Create example custom agent (e.g., `security.yaml`)
4. Add skills discovery to load custom definitions
5. Commit: "feat(cf-24.6): Enable custom agent type definitions"

**Risk**: Low - additive feature

---

**Total Effort**: ~10 hours (vs. 3-4 hours if done naively)

**Payoff**:
- ✅ Future-proof architecture
- ✅ No technical debt
- ✅ Claude Code skills compatible
- ✅ Markdown-defined agents
- ✅ Extensible without code changes

---

## Comparison: Current vs. Proposed Architecture

### Current (Hard-coded) Architecture

```
Database:
  agents.type CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review'))
  ❌ Fixed enum, requires migration to extend

Code:
  codeframe/agents/backend_worker_agent.py (811 lines of hardcoded logic)
  ❌ Need new Python class for each agent type

To Add New Agent Type:
  1. Write 800+ lines of Python code
  2. Run database migration to add type to CHECK constraint
  3. Deploy code + schema changes
  ❌ High effort, high risk

Claude Code Skills:
  ❌ Cannot define agent types
  ❌ Skills can't provide agent instructions
```

### Proposed (Flexible) Architecture

```
Database:
  agents.type TEXT NOT NULL
  ✅ Any string allowed, no constraints

Code:
  codeframe/agents/worker_agent.py (base class)
  codeframe/agents/definitions/backend.yaml (50 lines)
  ✅ Generic base class + configuration

To Add New Agent Type:
  1. Create YAML file in definitions/custom/
  2. No code changes
  3. No database migration
  ✅ Low effort, low risk

Claude Code Skills:
  ✅ Skills can provide agent definitions
  ✅ Markdown instructions = agent behavior
  ✅ User can add custom types without coding
```

---

## Recommended Next Steps

### Option A: Refactor Before Sprint 4 (Recommended)

**Timeline**: ~10 hours upfront investment

**Sequence**:
1. Remove database CHECK constraint (1 hour)
2. Implement cf-24.6: Agent definition system (4 hours)
3. Define frontend agent via YAML (1 hour)
4. Define test agent via YAML (1 hour)
5. Test multi-agent execution with definitions (2 hours)
6. Document custom agent creation for users (1 hour)

**Result**:
- ✅ Sprint 4 proceeds with flexible architecture
- ✅ No technical debt
- ✅ Claude Code skills ready to integrate
- ✅ Future agent types = add YAML file

**Risk**: Delays Sprint 4 by ~1.5 days

---

### Option B: Proceed As-Is, Refactor Later (Not Recommended)

**Timeline**: Sprint 4 proceeds immediately, refactor later

**Sequence**:
1. Implement cf-21: Hard-code FrontendWorkerAgent class
2. Implement cf-22: Hard-code TestWorkerAgent class
3. Deploy Sprint 4 demo
4. **Later**: Realize flexibility needed for skills integration
5. **Later**: Painful refactor to remove hardcoded types
6. **Later**: Database migration + backward compatibility issues

**Result**:
- ⚠️ Technical debt accumulated
- ❌ Refactor effort 2-3x higher (backward compatibility)
- ❌ Breaking changes for deployed systems
- ❌ Delayed Claude Code skills integration

**Risk**: High future maintenance burden

---

## Conclusion

**Bottom Line**: The current architecture **will box us in** if we proceed with Sprint 4 as specified.

**Critical Issues**:
1. Database CHECK constraint blocks dynamic agent types
2. No agent definition system (cf-24.6 not implemented)
3. cf-21 and cf-22 will create hardcoded agent classes

**Required Changes**:
1. ✅ Remove database type constraint
2. ✅ Implement agent definition system (YAML/Markdown)
3. ✅ Make cf-24.6 a **P0 prerequisite** for cf-21, cf-22

**Investment**: 10 hours upfront to avoid 20-30 hours of refactoring later

**Recommendation**: **Refactor before Sprint 4** (Option A)

**User's Goal**: "Future-proof AI agent skills and no 'hard-coded' agent assignments or definitions"

**Answer**: This goal is **achievable** but requires architectural changes BEFORE cf-21/cf-22 implementation.

---

## Appendix: Compatibility Matrix

| Feature | Current Architecture | Proposed Architecture |
|---------|---------------------|----------------------|
| **Add new agent type** | ❌ Code + migration | ✅ Add YAML file |
| **Claude Code skills** | ❌ Incompatible | ✅ Compatible |
| **Markdown instructions** | ❌ Not supported | ✅ Supported |
| **Dynamic capabilities** | ❌ Fixed types | ✅ Capability-based |
| **User extensibility** | ❌ Requires coding | ✅ Configuration only |
| **Backward compatible** | ❌ Breaks on extend | ✅ Additive changes |
| **Database migrations** | ❌ Required for types | ✅ Not needed |
| **cf-24.6 integration** | ❌ Blocked | ✅ Enabled |

---

**Analysis Date**: 2025-10-19
**Analyst**: Claude Code (Sonnet 4.5)
**Next Action**: User decision on Option A (refactor first) vs Option B (technical debt)
