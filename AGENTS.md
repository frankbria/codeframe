# CodeFRAME Documentation Guide for AI Agents

This guide helps AI agents efficiently navigate CodeFRAME's documentation structure.

---

## Quick Navigation

| I need to... | Read this file | Size | Details |
|--------------|----------------|------|---------|
| Know current sprint status | `SPRINTS.md` | ~400 lines | Sprint timeline index |
| Understand a specific sprint | `sprints/sprint-NN-name.md` | ~100 lines | Sprint summary |
| Implement a feature | `specs/{feature}/plan.md` | ~500 lines | Implementation guide |
| Understand feature design | `specs/{feature}/spec.md` | ~300 lines | Requirements & design |
| See granular tasks | `specs/{feature}/tasks.md` | ~600 lines | Task-by-task breakdown |
| Check project architecture | `CODEFRAME_SPEC.md` | ~800 lines | Overall system design |
| Learn coding standards | `CLAUDE.md` | ~200 lines | Project conventions |
| Understand testing | `TESTING.md` | ~300 lines | Test requirements |

---

## Directory Structure

### `/specs/` - Feature Implementation Specifications

**Purpose**: Detailed implementation guides for individual features

**Structure**: One directory per feature (`NNN-feature-name/`)

**Contents**:
```
specs/048-async-worker-agents/
├── spec.md          # Requirements, goals, design decisions
├── plan.md          # Implementation plan with phases
├── tasks.md         # Granular task breakdown (T001, T002...)
├── data-model.md    # Schema changes, data structures
├── research.md      # Technical research and trade-offs
├── quickstart.md    # Getting started guide
├── contracts/       # API contracts, interfaces
└── checklists/      # Feature-specific validation
```

**When to use**:
- ✅ Implementing a specific feature
- ✅ Understanding technical decisions
- ✅ Finding detailed task breakdown
- ❌ Getting project overview (too detailed)

**Example**: `specs/048-async-worker-agents/spec.md` explains the async migration design, research, and implementation plan in 400+ lines of detail.

---

### `/sprints/` - Sprint Execution Records

**Purpose**: Historical record of sprint deliverables

**Structure**: One file per sprint (`sprint-NN-name.md`)

**Contents** (~80-120 lines per file):
- Sprint goal and user story
- Task checklist with beads issue links
- Definition of Done with completion status
- Key git commit references
- Metrics (tests, coverage, performance)
- Retrospective notes

**When to use**:
- ✅ Understanding what was delivered when
- ✅ Finding git commits for a feature
- ✅ Seeing sprint timeline
- ❌ Implementation details (use specs/ instead)

**Example**: `sprints/sprint-05-async-workers.md` summarizes Sprint 5 deliverables, links to cf-48 (beads), specs/048-async-worker-agents/ (details), and PR #11 (implementation).

---

### Root Level - Project-Wide Documentation

**Purpose**: Cross-cutting project information

**Key files**:

#### Project Overview
- **`README.md`** - Project introduction, quick start, current status
- **`CODEFRAME_SPEC.md`** - Overall architecture and system design
- **`CHANGELOG.md`** - User-facing changes by version

#### Sprint Planning
- **`SPRINTS.md`** - Sprint timeline index and execution guidelines (NEW)
- **`AGILE_SPRINTS.md`** - Legacy sprint planning (→ archived)

#### Development Guides
- **`CLAUDE.md`** - Project-specific coding standards
- **`AGENTS.md`** - This file - documentation navigation guide
- **`TESTING.md`** - Testing standards and procedures
- **`CONTRIBUTING.md`** - Contribution guidelines

---

## Information Architecture

### Separation of Concerns

| Directory | Purpose | Granularity | Lifecycle | Size per file |
|-----------|---------|-------------|-----------|---------------|
| **specs/** | HOW to implement | Task-level detail | During feature | 400-800 lines |
| **sprints/** | WHAT was delivered | Sprint summary | After sprint | 80-120 lines |
| **Root** | Project overview | Cross-cutting | Living docs | 100-800 lines |

### Single Source of Truth

- **Beads issues** (`bd list`) - Task status (open/closed)
- **Git commits** - Implementation evidence
- **specs/** - Feature implementation details
- **sprints/** - Sprint timeline narrative
- **Root docs** - Project-wide standards

**Key principle**: Sprint and spec files REFERENCE beads/git; they don't duplicate content.

---

## Common Navigation Patterns

### 1. "What are we working on now?"

```
SPRINTS.md (~400 lines)
  └─> "Current Sprint: Sprint 6"
      └─> sprints/sprint-06-human-loop.md (~100 lines)
          └─> "Beads: cf-NEW-26 to cf-NEW-30"
          └─> "Spec: specs/006-human-in-loop/"
              └─> specs/006-human-in-loop/plan.md (~500 lines)
```

**Total reading**: ~400 lines (overview) + ~100 lines (sprint) = 500 lines to understand current work

---

### 2. "How was async migration implemented?"

```
sprints/sprint-05-async-workers.md (~100 lines)
  └─> Summary: "Converted to async/await, 30-50% performance boost"
  └─> Link: specs/048-async-worker-agents/spec.md (~400 lines)
      └─> Detailed design, research, migration strategy
  └─> Link: PR #11 (git commits 9ff2540, 324e555, etc.)
      └─> Actual code changes
```

**Progressive disclosure**: Summary (100 lines) → Details (400 lines) → Code (git diff)

---

### 3. "What's the overall project architecture?"

```
CODEFRAME_SPEC.md (~800 lines)
  └─> System architecture, agent types, communication patterns
  └─> References to specific feature specs:
      └─> specs/004-multi-agent-coordination/spec.md
      └─> specs/048-async-worker-agents/spec.md
```

---

### 4. "What tasks need to be done for feature X?"

```
specs/{feature}/tasks.md (~600 lines)
  └─> Phase-by-phase task breakdown
  └─> Acceptance criteria per task
  └─> Beads issue references
  └─> Estimated effort
```

---

## Best Practices for AI Agents

### ✅ DO

1. **Start with SPRINTS.md** for project overview (400 lines vs 2549 in old AGILE_SPRINTS.md)
2. **Read only what you need** - Each file is designed to be self-contained and < 800 lines
3. **Follow links for details** - Sprint files → specs → beads → git
4. **Trust the source of truth**:
   - Task status → beads issues (`bd show cf-XXX`)
   - Implementation → git commits
   - Details → spec files
5. **Check file dates** - Older specs may be outdated; verify against recent git commits

### ❌ DON'T

1. **Don't read AGILE_SPRINTS.md** - It's archived; use SPRINTS.md + individual sprint files
2. **Don't duplicate information** - Reference beads/git instead of copying details
3. **Don't guess file locations** - Use this guide to navigate
4. **Don't update archived sprint files** - They're historical records
5. **Don't read entire specs/ directory** - Find the specific feature you need

---

## File Size Guarantees

Every documentation file is designed to fit in a single agent context window:

- **`SPRINTS.md`**: ~400 lines (index + guidelines)
- **Individual sprint**: ~80-120 lines (summary)
- **Feature spec.md**: ~200-400 lines (requirements)
- **Feature plan.md**: ~300-600 lines (implementation plan)
- **Feature tasks.md**: ~400-800 lines (task breakdown)
- **`CODEFRAME_SPEC.md`**: ~800 lines (architecture)

**Old way**: AGILE_SPRINTS.md = 2549 lines (too large to read in one pass)
**New way**: SPRINTS.md (400) + specific sprint file (100) = 500 lines max

---

## Relationship Between Documentation Types

```
┌─────────────────────────────────────────────────────────┐
│ README.md (Project Overview)                            │
│   "CodeFRAME builds software with AI agents"            │
│   → Link to SPRINTS.md for timeline                     │
│   → Link to CODEFRAME_SPEC.md for architecture          │
└─────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
┌───────▼──────────┐          ┌─────────▼────────────┐
│ SPRINTS.md       │          │ CODEFRAME_SPEC.md    │
│ (Timeline Index) │          │ (Architecture)       │
│                  │          │                      │
│ Sprint 0-9 table │          │ Agent types          │
│ Current: Sprint 6│          │ Communication        │
│ Execution guide  │          │ Database schema      │
└───────┬──────────┘          └──────────────────────┘
        │
        ├─> sprints/sprint-05-async-workers.md (Summary)
        │     │
        │     └─> specs/048-async-worker-agents/ (Details)
        │           ├─> spec.md (Design)
        │           ├─> plan.md (Implementation)
        │           ├─> tasks.md (T001, T002...)
        │           └─> research.md (Decisions)
        │
        ├─> sprints/sprint-06-human-loop.md (Current)
        │     │
        │     └─> specs/006-human-in-loop/ (Details)
        │
        └─> sprints/sprint-07-context-mgmt.md (Planned)
```

---

## Migration Notes

**Transition period**: During documentation restructure:
- ✅ Use `SPRINTS.md` for current state
- ⚠️ `AGILE_SPRINTS.md` is being migrated (may be outdated)
- ✅ Individual sprint files are authoritative
- ✅ Specs are unchanged

**After migration complete**:
- ✅ `SPRINTS.md` is the sprint index
- 📁 `AGILE_SPRINTS.md` moved to `docs/archive/`
- ✅ All sprint files in `sprints/` directory
- ✅ This guide (`AGENTS.md`) is the navigation reference

---

## Quick Reference Examples

### Finding Current Sprint Tasks
```bash
# 1. Check sprint index
cat SPRINTS.md  # Find current sprint

# 2. Read sprint summary
cat sprints/sprint-06-human-loop.md  # Get task list

# 3. Check beads for status
bd list | grep cf-NEW-26  # See task status

# 4. Read spec for details
cat specs/006-human-in-loop/plan.md  # Implementation guide
```

### Understanding Past Decisions
```bash
# 1. Find the sprint
cat SPRINTS.md  # Sprint 5 = async migration

# 2. Read sprint summary
cat sprints/sprint-05-async-workers.md  # What was delivered

# 3. Read detailed spec
cat specs/048-async-worker-agents/research.md  # Why async?

# 4. Check git commits
git show 9ff2540  # See actual changes
```

### Implementing a New Feature
```bash
# 1. Find feature spec
ls specs/  # Find your feature number

# 2. Read requirements
cat specs/{feature}/spec.md  # Understand goals

# 3. Follow implementation plan
cat specs/{feature}/plan.md  # Step-by-step guide

# 4. Execute tasks
cat specs/{feature}/tasks.md  # Task breakdown
```

---

## Questions?

If this documentation structure is unclear:
1. Check the README.md for project overview
2. Read SPRINTS.md for sprint context
3. Ask the user for clarification

**Remember**: This structure is designed for efficient agent navigation. Each file is sized to fit in a single read, and cross-references provide progressive disclosure.
