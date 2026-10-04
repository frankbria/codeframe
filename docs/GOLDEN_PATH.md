# CodeFRAME v2 — Golden Path Contract (CLI-first)

This document is the contract for CodeFRAME v2 development.

**Rule 0 (the only rule that matters):**
> If a change does not directly support the Golden Path flow below, do not implement it.

This applies to both humans and agentic coding assistants.

---

## Goals

### What "done" looks like (Enhanced MVP definition)
CodeFRAME can run a complete end-to-end AI-driven development workflow **from the CLI** on a target repo:

1) **Initialize workspace with project discovery**
   - Analyze codebase and detect tech stack
   - Configure environment and tooling automatically
   - Create durable state storage

2) **AI-driven PRD generation and refinement**
   - Interactive AI session gathers project requirements
   - AI asks follow-up questions about scope, users, constraints
   - Generates comprehensive PRD + technical specs + user stories
   - Iterative refinement based on user feedback

3) **Intelligent task generation with dependency analysis**
   - Decompose PRD into actionable tasks with dependencies
   - Prioritize tasks and group by functionality
   - Generate implementation strategies per task

4) **Batch task execution with orchestration**
   - Execute multiple tasks in sequence or parallel
   - Handle inter-task dependencies automatically
   - Main agent coordinates entire batch workflow
   - Real-time progress monitoring and event streaming

5) **Human-in-the-loop blocker resolution**
   - Interactive blocker handling with contextual AI suggestions
   - Resume execution after blocker resolution
   - Learning from blocker patterns

6) **Integrated Git workflow and PR management**
   - Automatic branch creation per task/batch
   - AI-generated commit messages and PR descriptions
   - Automated verification gate execution
   - PR creation, review, and merging workflows

7) **Comprehensive checkpointing and state management**
   - Snapshots of workspace state with git refs
   - Resume interrupted workflows from checkpoints
   - Multi-environment state isolation

**No UI is required.**
**A FastAPI server is not required for the Golden Path to work.**
**All Git operations are integrated into the CLI workflow.**

---

## Non-Goals (explicitly forbidden until Golden Path works)

Do not build or refactor:
- Web UI / dashboard features
- Settings pages, preferences, themes
- Multi-provider/model switching UI or complex provider management
- Advanced metrics dashboards or timeseries endpoints
- Auth / sessions for remote users
- Electron desktop app
- Plugin marketplace / extensibility frameworks
- “Perfect” project structure, monorepo tooling, or build system redesign
- Large migrations or renames that aren’t required by Golden Path

These may be revisited **only after** Golden Path is working and stable.

---

## Golden Path CLI Flow (the only flow that matters)

### 0) Preconditions
- A target repo exists (any small test repo is fine).
- CodeFRAME runs locally and can store durable state (SQLite or filesystem).
- The CLI can be run from anywhere.

### 1) Initialize a workspace
Command:
- `codeframe init <path-to-repo>`

Required behavior:
- Registers the repo as a workspace.
- Creates/updates durable state storage.
- Prints a short workspace summary (repo path, workspace id, state location).

Artifacts:
- Local state created (DB/file), e.g. `.codeframe/` and/or `codeframe.db`.

### 2) AI-driven PRD generation and refinement
Commands:
- `codeframe prd generate` (primary - interactive AI session)
- `codeframe prd add <file.md>` (secondary - existing file support)
- `codeframe prd refine` (iterative improvement) — **NOT IMPLEMENTED**; use `codeframe prd update` / `codeframe prd stress-test`

Required behavior for `prd generate`:
- AI conducts interactive discovery session asking:
  - Project scope, objectives, and success criteria
  - Target users, use cases, and user stories
  - Technical constraints, preferences, and requirements
  - Timeline, priorities, and MVP boundaries
- Generates comprehensive PRD with:
  - Executive summary and problem statement
  - Functional requirements with acceptance criteria
  - Technical specifications and architecture guidance
  - User stories with priority ranking
  - Success metrics and validation criteria
- Provides iterative refinement based on user feedback
- Stores PRD in durable state with versioning
- Supports multiple PRD versions with change tracking

### 3) Intelligent task generation with dependency analysis
Commands:
- `codeframe tasks generate` (enhanced with dependencies)
- `codeframe tasks analyze` (dependency graph analysis) — **NOT IMPLEMENTED**; use `codeframe tasks tree` / `codeframe schedule bottlenecks`

Required behavior:
- Decomposes PRD into granular, actionable tasks
- Automatically detects and assigns task dependencies
- Estimates effort and complexity for each task
- Groups related tasks into logical workstreams
- Prioritizes tasks based on dependencies and value delivery
- Supports task templates for common patterns (setup, implementation, testing, deployment)
- Generates implementation strategy per task (files to modify, approaches to consider)
- Creates task dependency graph with critical path identification

### 4) Batch task execution with orchestration
Commands:
- `codeframe work batch run` (primary - main execution pathway)
- `codeframe work start <task-id>` (secondary - single task fallback)
- `codeframe work batch status <batch-id>` (monitoring)
- `codeframe work batch follow <batch-id>` (real-time streaming)

Required behavior for batch execution:
- Executes multiple tasks with intelligent scheduling:
  - Serial execution for dependent tasks
  - Parallel execution for independent tasks
  - Auto-strategy using dependency graph analysis
- Main orchestrator agent coordinates entire batch:
  - Resource allocation and task scheduling
  - Inter-task communication and data sharing
  - Failure handling and retry logic
  - Progress tracking and milestone reporting
- Real-time event streaming with:
  - Task start/completion events
  - Progress indicators and ETAs
  - Blocker detection and notification
  - Dependency resolution updates
- Supports execution strategies:
  - `--strategy serial`: Linear execution
  - `--strategy parallel`: Max parallelization
  - `--strategy auto`: AI-optimized based on dependencies

### 5) Enhanced human-in-loop blocker resolution
Commands:
- `codeframe blocker list` (enhanced with context) — note the singular `blocker`
- `codeframe blocker answer <blocker-id> "<text>"` (with AI suggestions)
- `codeframe blocker resolve <blocker-id>` (automated resolution options)

Required behavior:
- AI provides contextual blocker resolution suggestions:
  - Similar past blockers and their solutions
  - Multiple solution approaches with trade-offs
  - Impact analysis of resolution choices
- Interactive blocker handling with:
  - Rich context display (related code, PRD sections, task dependencies)
  - Suggested responses ranked by confidence
  - Impact on task timeline and dependencies
- Learning system that:
  - Records blocker patterns and resolutions
  - Improves future blocker handling suggestions
  - Reduces human intervention over time

### 6) Integrated Git workflow and PR management
Commands:
- `codeframe work start <task-id> --create-branch` (branch management) — **`--create-branch` NOT IMPLEMENTED**
- `codeframe pr create` (PR creation with AI descriptions)
- `codeframe pr list` (PR status monitoring)
- `codeframe pr merge <pr-id>` (PR merging with verification)

Required behavior:
- **Branch Management**:
  - Automatic feature branch creation per task/batch
  - Branch naming conventions with task/batch IDs
  - Branch cleanup and organization utilities
  - Conflict detection and resolution assistance
- **PR Creation**:
  - AI generates comprehensive PR descriptions:
    - Summary of changes and business impact
    - Technical implementation details
    - Testing performed and results
    - Breaking changes and migration notes
  - Automated PR labeling and categorization
  - Reviewer assignment based on code expertise
- **PR Workflow**:
  - Automated gate execution before merge (tests, lint, security scans)
  - Integration with CI/CD pipelines
  - Merge strategies (squash, merge, rebase) based on team preferences
  - Post-merge cleanup and notification

### 7) Enhanced verification and quality gates
Commands:
- `codeframe review` (comprehensive code review)
- `codeframe gates run` (automated quality checks)
- `codeframe quality report` (quality metrics and trends) — **NOT IMPLEMENTED**; `codeframe stats` covers token/cost only

Required behavior:
- **Comprehensive Gate Suite**:
  - Unit tests with coverage reporting
  - Integration and end-to-end tests
  - Static code analysis (lint, security, complexity)
  - Performance regression tests
  - Documentation and API specification validation
- **AI-Assisted Code Review**:
  - Automated code quality assessment
  - Best practices compliance checking
  - Potential bug detection and suggestions
  - Code style and maintainability analysis
- **Quality Tracking**:
  - Trend analysis of code quality metrics
  - Technical debt accumulation tracking
  - Gate failure pattern identification

### 8) Integrated artifact and commit management
Commands:
- `codeframe commit create -m "<message>"` (AI-generated commits)
- `codeframe patch export` (safe patch generation)
- `codeframe artifacts list` (artifact tracking) — **NOT IMPLEMENTED**

Required behavior:
- **Smart Commits**:
  - AI generates meaningful commit messages:
    - Conventional commit format compliance
    - Contextual change descriptions
    - References to tasks/PRDs/issues
    - Breaking change highlights
  - Atomic commit boundaries and logical grouping
- **Artifact Management**:
  - Automatic patch generation for safety
  - Commit linking to tasks and batches
  - Rollback points and recovery procedures
  - Integration with external artifact repositories

### 9) Comprehensive checkpointing and state management
Commands:
- `codeframe checkpoint create "<name>"` (enhanced snapshots)
- `codeframe checkpoint restore <checkpoint-id>` (workflow resume)
- `codeframe summary` (comprehensive reporting)

Required behavior:
- **Rich Checkpoints**:
  - Complete workspace state capture:
    - Task statuses and progress
    - Git refs and working directory state
    - PRD versions and requirements
    - Configuration and environment settings
  - Incremental checkpoint optimization
  - Cross-environment checkpoint portability
- **Workflow Resume**:
  - Seamless resumption from any checkpoint
  - Context restoration for active agents
  - Branch and working directory restoration
  - Event log continuity and replay
- **Comprehensive Reporting**:
  - Executive summaries with progress metrics
  - Detailed task completion reports
  - Quality gate performance tracking
  - Resource utilization and timing analysis
  - Risk assessment and mitigation recommendations

---

## State Machine (authoritative)

Statuses (`codeframe/core/state_machine.py`):
- `BACKLOG` - Task identified but not ready for execution
- `READY` - Task prepared and ready to start
- `IN_PROGRESS` - Task actively being worked on
- `BLOCKED` - Task waiting for human input or external dependency
- `FAILED` - Task execution failed (can be retried)
- `DONE` - Task completed locally
- `MERGED` - Task changes integrated (terminal)

Allowed transitions (mirrors `ALLOWED_TRANSITIONS`; a test keeps them equal):
- BACKLOG -> READY
- READY -> IN_PROGRESS, BACKLOG
- IN_PROGRESS -> BLOCKED, DONE, READY, FAILED
- BLOCKED -> IN_PROGRESS, READY
- FAILED -> READY, IN_PROGRESS
- DONE -> READY, MERGED
- MERGED -> (none)

The CLI is the authority for transitions.
UIs (web/electron) are views over this state machine, not the source of truth.
There is no review state: `cf pr create` and `cf pr merge` do not change task
status. MERGED is set explicitly with `cf tasks set status <id> MERGED`.

---

## Implementation Principles

### Core-first (no FastAPI in the core)
- Domain logic must live in a reusable core module/package.
- Core must not import FastAPI, websockets, or HTTP request objects.
- FastAPI server (if used) must be a thin adapter over core.

### CLI-first (server optional)
- Golden Path commands must work without any running backend server.
- If a server exists, it may be started separately (`codeframe serve`) and must wrap core.

### Salvage safely
- Legacy code can be read and copied from.
- Core must not take dependencies on legacy UI-driven modules.
- Prefer copying useful functions into core and simplifying interfaces.

### Keep it runnable
- Every commit should keep `codeframe --help` working.
- The Golden Path commands should remain executable even if stubs at first.

---

## Status

What has shipped is tracked in one place: the **Summary** table at the end of
[`docs/PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md). This file is the workflow
contract, not a status report. The checklist that used to live here went stale
(it listed `prd generate`, the PR commands and `cf auth` as missing long after
they shipped) and was removed rather than kept in sync twice.
