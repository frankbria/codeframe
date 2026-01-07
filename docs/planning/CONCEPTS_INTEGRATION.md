# General Concepts Integration Analysis

**Purpose**: Analysis of new concept ideas and their integration into CodeFRAME specification and implementation plan.

**Date**: 2025-01-16 (Original)
**Last Reviewed**: 2026-01-06
**Status**: Historical Planning Document

> **Note**: This document captures concept analysis from early 2025. Many features
> discussed here have since been implemented (context management, checklist system).
> See SPRINTS.md and specs/ for current implementation status.

---

## Concepts Analysis

### 1. Claude Code before_compact Hook for Status/Next Steps

**Concept**: "In Claude Code, use before_compact hook to write out status and next steps"

**Current Spec Coverage**:
- ✅ **ALREADY SPECIFIED**: Flash Save System (lines 561-608)
  - Triggers include "Pre-compactification (context >80% of limit)"
  - Checkpoint system captures project state, agent state, git commit, DB snapshot

**Gap Analysis**:
- ❌ **NOT SPECIFIED**: Specific Claude Code hook integration
- ❌ **NOT SPECIFIED**: Hook-based trigger mechanism vs polling
- ❌ **NOT SPECIFIED**: Status/next steps format for hook output

**Integration Recommendation**:
- **Where**: Section 7 "State Persistence & Recovery" → Add subsection "7.3 Claude Code Hook Integration"
- **When**: Sprint 6 (Context Management) or Sprint 8 (Polish)
- **Priority**: P1 (Nice to have - enhances UX but not blocking)

**Specification Addition**:
```markdown
### 7.3 Claude Code Hook Integration

**Hook Type**: `before_compact` (pre-compactification trigger)

**Implementation**:
```python
# .claude/hooks/before_compact.sh
#!/bin/bash
# Triggered by Claude Code before conversation compactification

# 1. Create flash save checkpoint
codeframe checkpoint create --trigger "pre_compact" --auto

# 2. Write status summary for next session
codeframe status --format compact > .codeframe/session_handoff.md

# 3. Log hook execution
echo "[$(date)] Flash save triggered by Claude Code compactification" >> .codeframe/logs/hooks.log
```

**Output Format** (.codeframe/session_handoff.md):
```markdown
# Session Handoff - [timestamp]
**Trigger**: Claude Code pre-compactification

## Current State
- Phase: [Discovery|Planning|Execution|Review|Release]
- Progress: X/Y tasks (Z%)
- Active Agents: [agent list with current tasks]

## Pending Blockers
- [SYNC] Blocker #X: [question]
- [ASYNC] Blocker #Y: [question]

## Next Steps
1. [Recommended next action]
2. [Alternative action if blocked]

## Context Preservation
- Checkpoint ID: ckpt_[timestamp]
- Git Commit: [hash]
- Token Usage: X/Y limit
```
```

**Sprint Integration**:
- **Sprint 6 (Context Management)**: Add hook framework
- **Task**: cf-36.5 - Claude Code hook integration (2-3 hours)

---

### 2. Local SQLite Issues List

**Concept**: "Use a local SQLite to track issues list"

**Current Spec Coverage**:
- ✅ **ALREADY IMPLEMENTED**: Tasks table (lines 871-886)
  - Tracks tasks with status, dependencies, priority, workflow_step
  - Full DAG dependency resolution

**Gap Analysis**:
- ❓ **CLARIFICATION NEEDED**: "Issues" vs "Tasks" distinction unclear
  - Are "issues" different from "tasks"?
  - GitHub Issues = external tracking, Tasks = internal work items?

**Integration Recommendation**:
- **Option A**: "Issues" = "Tasks" (already implemented)
  - No additional work needed
  - Use existing tasks table with enhanced metadata

- **Option B**: "Issues" = separate concept (bugs, enhancements, tech debt)
  - Add `issues` table for tracking defects/improvements
  - Link issues to tasks via `issue_id` foreign key
  - GitHub Issues sync capability (future)

**Proposed Specification** (if Option B):
```sql
-- Issues table (distinct from tasks)
CREATE TABLE issues (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    issue_type TEXT CHECK(issue_type IN ('bug', 'enhancement', 'tech_debt', 'question')),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('open', 'in_progress', 'resolved', 'closed', 'wont_fix')),
    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
    created_by TEXT,  -- 'user' or agent_id
    assigned_to TEXT,  -- agent_id or 'user'
    linked_tasks TEXT,  -- JSON array of task IDs generated from this issue
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    github_issue_id INTEGER  -- For future GitHub sync
);
```

**Sprint Integration**:
- **Sprint 2 or Sprint 9**: Add issues table if needed
- **Task**: cf-XX - Issue tracking system (4-6 hours)
- **Priority**: P2 (Post-MVP unless user needs distinction)

**QUESTION FOR USER**: Do you want "issues" to be different from "tasks", or are they the same concept?

---

### 3. Issues List Tracking (Priorities, Predecessors, Status)

**Concept**: "Issues list should track priorities, predecessors, status"

**Current Spec Coverage**:
- ✅ **ALREADY IMPLEMENTED**: Tasks table has all these features
  - `priority` field (0-4, 0 = highest)
  - `depends_on` field (JSON array of task IDs = predecessors/dependencies)
  - `status` field (pending, assigned, in_progress, blocked, completed, failed)

**Integration Recommendation**:
- ✅ **NO ACTION NEEDED** - Already fully implemented in tasks table
- If "issues" are separate from "tasks", apply same schema as tasks table

---

### 4. Command to "Re-engineer" Issue List

**Concept**: "Should include a command to 're-engineer' the issue list"

**Current Spec Coverage**:
- ❌ **NOT SPECIFIED**: Re-engineering/replanning command
- ⚠️ **PARTIALLY COVERED**: Lead Agent can replan, but no explicit CLI command

**Gap Analysis**:
- Missing: CLI command for user-triggered replanning
- Missing: Criteria for when to trigger replanning
- Missing: Process for re-evaluating task decomposition

**Integration Recommendation**:
- **Where**: Section 13 "API Specifications" → Add CLI command
- **When**: Sprint 2 (Socratic Discovery + Task Decomposition)
- **Priority**: P1 (Important for adaptive planning)

**Specification Addition**:
```markdown
### Re-planning Command

**CLI**:
```bash
# Trigger Lead Agent to re-analyze and regenerate task list
codeframe replan [--from-prd] [--keep-completed]

# Options:
#   --from-prd: Re-read PRD and regenerate all tasks
#   --keep-completed: Preserve completed tasks, replan only pending
#   --interactive: Ask user for guidance during replanning
```

**Use Cases**:
1. **PRD Changed**: User updates requirements
2. **Blocked Path**: Current approach not working
3. **Scope Adjustment**: Need to add/remove features
4. **Dependency Issues**: Task order needs restructuring

**Lead Agent Behavior**:
1. Analyze current progress and completed work
2. Re-read PRD (if --from-prd) or use current understanding
3. Identify completed tasks to preserve (if --keep-completed)
4. Generate new task decomposition
5. Merge with existing tasks (preserve history)
6. Update dependencies based on new plan
7. Notify agents of task changes via WebSocket
```

**Sprint Integration**:
- **Sprint 2**: cf-14.5 - Re-planning command (3-4 hours)
- **Dependencies**: Requires Task Decomposition (cf-14) to be complete

---

### 5. Issue List vs Todo List Connection

**Concept**: "What's the connection between issue list and to do list? Is there a to do list for each issue? Is the GitHub Issue and PR model the right one to use?"

**Current Spec Coverage**:
- ✅ **TASKS = PRIMARY WORK ITEMS**: Tasks table is the canonical work breakdown
- ❌ **NOT SPECIFIED**: Subtask/checklist concept within tasks
- ❌ **NOT SPECIFIED**: GitHub model integration

**Gap Analysis**:
- Missing: Subtask/checklist support for complex tasks
- Missing: GitHub Issues/PR integration model
- Unclear: Hierarchical task breakdown (epic → task → subtask)

**Integration Recommendation**:
- **Hierarchy Model**: Epic → Task → Subtask (optional)
  - **Epic** (not in spec): High-level feature (maps to PRD sections)
  - **Task** (current): Atomic unit of work (current tasks table)
  - **Subtask/Checklist** (new): Steps within a task

**Proposed Specification**:
```sql
-- Enhanced tasks table with hierarchy
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    parent_task_id INTEGER REFERENCES tasks(id),  -- NEW: For subtasks
    title TEXT NOT NULL,
    description TEXT,
    checklist JSON,  -- NEW: ["Step 1", "Step 2", ...] with completion tracking
    status TEXT,
    ...
);

-- Task checklist format
{
  "items": [
    {"id": 1, "description": "Write unit tests", "completed": true},
    {"id": 2, "description": "Implement feature", "completed": false},
    {"id": 3, "description": "Update docs", "completed": false}
  ],
  "completion": "1/3"
}
```

**GitHub Model Integration** (Future - Post-MVP):
```markdown
### GitHub Sync (Optional)

**Mapping**:
- CodeFRAME Task → GitHub Issue (bidirectional sync)
- Task completion → GitHub Issue close
- GitHub PR → Linked to task via commit message
- GitHub Comments → Stored in memory table

**Commands**:
```bash
codeframe github sync --enable
codeframe github push <task_id>  # Create GitHub issue
codeframe github pull              # Import GitHub issues as tasks
```
```

**Sprint Integration**:
- **Sprint 2**: Add checklist support to tasks (cf-14.6 - 2-3 hours)
- **Sprint 9+**: GitHub integration (Post-MVP)
- **Priority**: P2 (Checklist useful, GitHub integration future)

---

### 6. Agent Skills Library & Coordination

**Concept**: "Leverage skills from something like Superpowers, agents from a big list of agents"

**Current Spec Coverage**:
- ✅ **AGENT TYPES DEFINED**: Backend, Frontend, Test, Review (lines 129-134)
- ❌ **NOT SPECIFIED**: Skills/capabilities abstraction
- ❌ **NOT SPECIFIED**: Extensible agent library
- ❌ **NOT SPECIFIED**: Agent marketplace or registry

**Gap Analysis**:
- Missing: Skills taxonomy (what agents can do)
- Missing: Agent capability matching to tasks
- Missing: Extensible agent system (plugin architecture)

**Integration Recommendation**:
- **Where**: New section "Agent Capabilities & Registry"
- **When**: Sprint 4 (Multi-Agent Coordination) or Post-MVP
- **Priority**: P2 (Extensibility - not critical for MVP)

**Proposed Specification**:
```markdown
## Agent Capabilities & Registry

### Skills Taxonomy

**Core Skills** (All agents):
- File I/O (read, write, edit)
- Git operations (commit, branch, checkout)
- CLI execution
- Test running

**Specialized Skills** (By agent type):
```python
AGENT_SKILLS = {
    'backend': [
        'api_development',
        'database_design',
        'orm_usage',
        'auth_implementation',
        'api_documentation'
    ],
    'frontend': [
        'component_development',
        'state_management',
        'ui_styling',
        'responsive_design',
        'accessibility'
    ],
    'test': [
        'unit_testing',
        'integration_testing',
        'e2e_testing',
        'test_data_generation',
        'coverage_analysis'
    ],
    'review': [
        'code_review',
        'security_scanning',
        'performance_profiling',
        'linting',
        'documentation_review'
    ]
}
```

### Agent Registry (Future)

**Local Registry** (.codeframe/agents/):
```json
{
  "custom_agents": [
    {
      "id": "data-engineer-agent",
      "type": "custom",
      "provider": "claude",
      "skills": ["etl_pipeline", "data_modeling", "sql_optimization"],
      "system_prompt_path": ".codeframe/agents/data-engineer-prompt.md"
    }
  ]
}
```

**Task-Skill Matching**:
```python
def assign_task_to_agent(task: Task) -> Agent:
    required_skills = extract_skills_from_task(task)
    available_agents = get_idle_agents()

    # Match agents with required skills
    scored_agents = []
    for agent in available_agents:
        skill_match = len(set(required_skills) & set(agent.skills))
        maturity_bonus = agent.maturity_level.value
        score = skill_match * 10 + maturity_bonus
        scored_agents.append((agent, score))

    return max(scored_agents, key=lambda x: x[1])[0]
```
```

**Sprint Integration**:
- **Sprint 4**: Basic skill matching (cf-24.5 - 3-4 hours)
- **Sprint 9+**: Custom agent registry (Post-MVP)
- **Priority**: P2 (Extensibility feature)

---

### 7. Subagent Coordination & Compactification Survival

**Concept**: "Send each issue to a subagent. How are things coordinated centrally? Single coordinator agent? How do they all 'survive' compactification?"

**Current Spec Coverage**:
- ✅ **COORDINATION SPECIFIED**: Lead Agent = central coordinator (lines 103-125)
- ✅ **FLASH SAVE SPECIFIED**: Pre-compactification checkpoints (lines 561-608)
- ✅ **AGENT STATE PERSISTENCE**: Agents survive via checkpoint/restore (lines 593-608)

**Gap Analysis**:
- ✅ **ALREADY SOLVED**: Architecture uses hybrid coordination (centralized Lead Agent)
- ✅ **ALREADY SOLVED**: Flash save system handles compactification survival
- ⚠️ **NEEDS CLARIFICATION**: "Subagent" terminology (are these Worker Agents?)

**Integration Recommendation**:
- ✅ **NO CHANGES NEEDED** - Current spec already addresses this
- 📝 **DOCUMENTATION**: Add diagram showing compactification survival flow

**Enhanced Documentation**:
```markdown
### Compactification Survival Flow

```
┌──────────────────────────────────────────────────┐
│  Claude Code Conversation Context (200K tokens)  │
│                                                  │
│  Lead Agent: 180K tokens used ⚠️ Approaching limit│
└──────────────┬───────────────────────────────────┘
               │
               │ Context >80% → Trigger flash save
               ▼
┌──────────────────────────────────────────────────┐
│           Flash Save Process                      │
│  1. Create checkpoint in SQLite                  │
│  2. Serialize agent state to DB                  │
│  3. Save context tiers (hot/warm/cold)           │
│  4. Git commit current work                      │
│  5. Write session handoff summary                │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│    Claude Code Compactification Occurs           │
│    (Conversation context cleared)                │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│           New Conversation Session                │
│  1. Load checkpoint from SQLite                  │
│  2. Restore agent state                          │
│  3. Reconstitute HOT tier context                │
│  4. Resume from where flash save occurred        │
│  5. Continue execution seamlessly                │
└──────────────────────────────────────────────────┘

**Worker Agents**: Independent of Lead Agent context
- Run in separate processes
- Persist state in SQLite independently
- Not affected by Lead Agent compactification
- Resume work from task queue after Lead restarts
```
```

**Sprint Integration**:
- ✅ **ALREADY IN SPRINT 6**: Context Management
- 📝 **ENHANCEMENT**: Add compactification survival diagram to spec

---

### 8. Claude Code Context Management

**Concept**: "Is there a way to manage Claude Code context so it's not a dump of every blasted conversation?"

**Current Spec Coverage**:
- ✅ **FULLY SPECIFIED**: Virtual Project Context System (lines 181-335)
  - Three-tier architecture (HOT/WARM/COLD)
  - Importance scoring algorithm
  - Context diffing and hot-swap
  - Intelligent archival

**Gap Analysis**:
- ✅ **ALREADY SOLVED**: Virtual Project system is the solution to this exact problem
- 📝 **NEEDS**: Better documentation/examples of how it prevents context pollution

**Integration Recommendation**:
- ✅ **NO CHANGES NEEDED** - This is already the core innovation of CodeFRAME!
- 📝 **DOCUMENTATION**: Add examples showing before/after context management

**Enhanced Documentation Example**:
```markdown
### Context Management Example

**WITHOUT Virtual Project** (Traditional approach):
```
Lead Agent Context (180K tokens):
- Every single task specification (1-40)
- All test results (including old failures)
- Entire PRD
- Complete file contents
- All conversation history
- Every decision ever made
→ Result: Context window exhausted, compactification loses everything
```

**WITH Virtual Project** (CodeFRAME approach):
```
Lead Agent Context (60K tokens):

🔥 HOT TIER (18K):
- Current task: #27 specification
- Active files: auth.py, user_model.py (current edits only)
- Latest test result: 3/5 passing
- Active blocker: "Which OAuth provider?"
- Last 3 important decisions

♨️ WARM TIER (42K):
- Related files (imports, not full content)
- Project structure overview
- PRD section for current phase only
- Code patterns (not all code)
- Last 10 medium decisions

❄️ COLD TIER (archived in SQLite, queryable):
- Completed tasks 1-26
- Resolved test failures
- Full PRD (retrievable)
- Old decisions
- Full git history

→ Result: 60K tokens, 30-50% reduction, nothing lost, everything queryable
```
```

**Sprint Integration**:
- ✅ **ALREADY IN SPRINT 6**: Virtual Project context management fully specified

---

### 9. Codebase Index Storage Location

**Concept**: "Where is an index of the codebase stored?"

**Current Spec Coverage**:
- ⚠️ **PARTIALLY SPECIFIED**: Context items table (lines 923-935)
- ❌ **NOT SPECIFIED**: Codebase indexing strategy
- ❌ **NOT SPECIFIED**: File dependency graph
- ❌ **NOT SPECIFIED**: Symbol/class/function registry

**Gap Analysis**:
- Missing: Explicit codebase indexing system
- Missing: AST parsing for structure awareness
- Missing: Dependency graph between files

**Integration Recommendation**:
- **Where**: New subsection "3.4 Codebase Indexing"
- **When**: Sprint 3 or Sprint 6 (when agents need structural awareness)
- **Priority**: P1 (Important for agent efficiency)

**Proposed Specification**:
```markdown
### 3.4 Codebase Indexing

**Purpose**: Enable agents to understand codebase structure without reading every file

**Index Storage**: SQLite table + in-memory cache

```sql
CREATE TABLE codebase_index (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    file_path TEXT NOT NULL,
    file_type TEXT,  -- 'source', 'test', 'config', 'doc'
    language TEXT,    -- 'python', 'typescript', 'rust', etc.
    symbols JSON,     -- Classes, functions, exports
    imports JSON,     -- Dependencies on other files
    loc INTEGER,      -- Lines of code
    last_modified TIMESTAMP,
    content_hash TEXT,
    INDEX(project_id, file_path)
);
```

**Symbol Structure**:
```json
{
  "classes": [
    {"name": "UserModel", "line": 15, "methods": ["save", "delete"]}
  ],
  "functions": [
    {"name": "authenticate", "line": 45, "args": ["username", "password"]}
  ],
  "exports": ["UserModel", "authenticate"]
}
```

**Indexing Process**:
```python
def index_codebase(project_id: int) -> None:
    """Parse and index all source files."""
    for file in get_source_files(project_id):
        if file.language == 'python':
            symbols = parse_python_ast(file.content)
        elif file.language == 'typescript':
            symbols = parse_typescript_ast(file.content)

        imports = extract_imports(file.content, file.language)

        db.upsert_index(
            project_id=project_id,
            file_path=file.path,
            symbols=symbols,
            imports=imports,
            content_hash=hash(file.content)
        )
```

**Agent Usage**:
```python
# Find where UserModel is defined
file = index.find_symbol("UserModel")

# Find all files that import auth module
dependents = index.find_importers("auth.py")

# Get project structure
structure = index.get_tree_view(project_id)
```

**Update Strategy**:
- Incremental: Re-index only changed files (hash comparison)
- Triggered: After git commits, file writes
- Background: Scheduled re-index every 5 minutes during active work
```

**Sprint Integration**:
- **Sprint 3**: Basic indexing (cf-18.5 - 4-6 hours)
- **Sprint 6**: Advanced symbol tracking (enhancement)
- **Priority**: P1 (Needed for efficient agent navigation)

---

### 10. Special Branches (Deployment, Migration)

**Concept**: "What about special branches for things like deployment or migration?"

**Current Spec Coverage**:
- ✅ **GIT INTEGRATION SPECIFIED**: Auto-commits (lines 673-675, Sprint 3)
- ❌ **NOT SPECIFIED**: Branch management strategy
- ❌ **NOT SPECIFIED**: Deployment branches
- ❌ **NOT SPECIFIED**: Migration workflow

**Gap Analysis**:
- Missing: Git branching strategy
- Missing: Deployment workflow
- Missing: Database migration management

**Integration Recommendation**:
- **Where**: New section "9.5 Git Workflow & Branching Strategy"
- **When**: Sprint 3 (Git Integration) or Sprint 8 (Review & Polish)
- **Priority**: P1 (Important for production deployments)

**Proposed Specification**:
```markdown
### 9.5 Git Workflow & Branching Strategy

**Default Branch Strategy**:
```
main (protected)
 ├── dev (integration branch, agents work here)
 │   ├── feature/task-12-user-auth (auto-created per task)
 │   ├── feature/task-15-api-endpoints
 │   └── feature/task-18-frontend-ui
 ├── staging (deployment testing)
 └── production (final deployment)
```

**Branch Management**:
```python
class GitWorkflow:
    def start_task(self, task: Task) -> str:
        """Create feature branch for task."""
        branch_name = f"feature/task-{task.id}-{slugify(task.title)}"
        git.checkout('dev')
        git.pull()
        git.checkout(branch_name, create=True)
        return branch_name

    def complete_task(self, task: Task) -> None:
        """Merge feature branch back to dev."""
        git.checkout('dev')
        git.merge(task.branch_name, squash=True)
        git.branch(task.branch_name, delete=True)
```

**Special Branches**:

**1. Migration Branch** (`migration/vX.Y`):
- Used for database schema changes
- Automated migration scripts
- Testing before merge to dev

```python
def handle_migration_task(task: Task) -> None:
    """Special handling for migration tasks."""
    # 1. Create migration branch
    branch = f"migration/v{get_next_version()}"
    git.checkout(branch, create=True)

    # 2. Generate migration script
    migration = generate_migration(task.changes)
    write_file(f"migrations/{timestamp}_{task.title}.sql", migration)

    # 3. Test migration
    test_db = create_test_database()
    run_migration(test_db, migration)

    # 4. Commit and merge if tests pass
    if all_tests_pass():
        git.commit("migration: " + task.title)
        git.checkout('dev')
        git.merge(branch)
```

**2. Deployment Branch** (`deploy/env`):
- Environment-specific branches (deploy/staging, deploy/production)
- Automated deployment pipelines
- Rollback support

```python
def deploy_to_environment(env: str, commit_hash: str) -> None:
    """Deploy specific commit to environment."""
    deploy_branch = f"deploy/{env}"

    # 1. Update deployment branch
    git.checkout(deploy_branch)
    git.reset(commit_hash, hard=True)

    # 2. Tag deployment
    tag = f"{env}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    git.tag(tag)

    # 3. Trigger deployment (external CI/CD)
    trigger_deployment(env, tag)
```

**Configuration**:
```json
{
  "git_workflow": {
    "default_branch": "dev",
    "feature_branch_prefix": "feature/task-",
    "auto_merge_to_dev": true,
    "require_review": true,
    "protected_branches": ["main", "production"],
    "deployment": {
      "staging": {
        "branch": "deploy/staging",
        "auto_deploy": true,
        "pipeline_url": "https://ci.example.com/deploy/staging"
      },
      "production": {
        "branch": "deploy/production",
        "auto_deploy": false,
        "require_approval": true,
        "pipeline_url": "https://ci.example.com/deploy/production"
      }
    },
    "migrations": {
      "branch_prefix": "migration/",
      "auto_test": true,
      "require_review": true
    }
  }
}
```

**CLI Commands**:
```bash
# Deploy to environment
codeframe deploy staging
codeframe deploy production --commit abc123

# Rollback deployment
codeframe deploy rollback staging --to-tag staging-20250115-120000

# Migration management
codeframe migrate create "Add user roles column"
codeframe migrate test
codeframe migrate apply
```
```

**Sprint Integration**:
- **Sprint 3**: Basic git integration (auto-commits)
- **Sprint 8**: Branch strategy and deployment (cf-44.5 - 4-6 hours)
- **Priority**: P1 (Critical for production use)

---

## Summary of Integration Actions

### ✅ Already Implemented (No Action)
1. **Flash Save / Pre-compactification** - Already in spec (Section 7)
2. **SQLite for state** - Already implemented (tasks table = issue tracking)
3. **Priorities, predecessors, status** - Already in tasks table
4. **Hybrid coordination** - Lead Agent already specified
5. **Compactification survival** - Flash save system handles this
6. **Context management** - Virtual Project system (core innovation!)

### 📝 Specification Enhancements Needed
1. **Claude Code Hook Integration** - Section 7.3 (Sprint 6 or 8)
2. **Replan Command** - Add to CLI spec (Sprint 2)
3. **Task Checklists** - Enhance tasks table (Sprint 2)
4. **Agent Skills/Registry** - New section (Sprint 4 or Post-MVP)
5. **Codebase Indexing** - Section 3.4 (Sprint 3 or 6)
6. **Git Branching Strategy** - Section 9.5 (Sprint 3 or 8)

### ❓ Clarifications Needed from User
1. **Issues vs Tasks**: Are these the same concept, or do you need separate issue tracking?
2. **Subagent terminology**: Does "subagent" mean "Worker Agent" in your mind?
3. **Agent library priority**: How important is extensible agent system for MVP?

### 🎯 Priority Recommendations

**P0 (MVP Must-Have)**:
- Codebase indexing (Sprint 3)
- Git branching strategy (Sprint 3 or 8)

**P1 (Highly Recommended)**:
- Replan command (Sprint 2)
- Claude Code hooks (Sprint 6 or 8)
- Task checklists (Sprint 2)

**P2 (Nice to Have / Post-MVP)**:
- Issues as separate concept (if needed)
- Agent skills registry
- GitHub integration

---

## Next Steps

1. **User Review**: Review this analysis and provide feedback
2. **Clarify Questions**: Answer the 3 clarification questions above
3. **Prioritize**: Confirm priority assignments (P0/P1/P2)
4. **Update Specs**: Integrate approved concepts into CODEFRAME_SPEC.md
5. **Update Sprints**: Add new tasks to AGILE_SPRINTS.md with effort estimates

---

**Document Status**: Draft for User Review
**Last Updated**: 2025-01-16
**Next Action**: Await user feedback and clarifications
