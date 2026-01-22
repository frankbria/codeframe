# CodeFRAME Feature Roadmap

Last updated: 2026-01-16

This document outlines the feature roadmap for CodeFRAME v2, planned outward from existing functionality toward a fully autonomous agentic coding system.

---

## Design Principles

1. **CLI-first** — All features work from the command line without a server
2. **Incremental expansion** — Each phase builds on the previous
3. **User control** — Configuration over convention, explicit over implicit
4. **Deep git integration** — Work with git, don't replace it
5. **Server when required** — FastAPI only when external access is needed

---

## Current State (Phase 2+ Complete)

### What Works Now
- Single task execution with planning → execution → verification
- Batch execution with serial/parallel/auto strategies
- Self-correction loop for verification failures (up to 3 attempts)
- Blocker detection for human-in-the-loop decisions
- Verification gates (ruff, pytest)
- State persistence across sessions (SQLite)
- Project preferences via AGENTS.md/CLAUDE.md
- Verbose mode for observability (`--verbose`)

### Known Gaps
- Environment detection failures (agent guesses wrong package manager)
- Limited error visibility (can't easily see why tasks failed)
- No live output streaming during execution
- Agent context limits (truncates large files)
- No git workflow integration
- No front-of-funnel (idea → PRD) tooling

---

## Phase 3: Agent Reliability

**Goal:** Agent completes tasks successfully more often

### 3.1 Environment Configuration
- Project config file: `.codeframe/config.yaml`
- User explicitly sets:
  - Package manager (uv, pip, poetry, npm, etc.)
  - Python/Node version requirements
  - Test framework (pytest, jest, etc.)
  - Lint tools (ruff, eslint, etc.)
- Agent respects config — never guesses
- Eventually: agent collects these during PRD creation (Phase 5)

**Commands:**
```bash
cf config init                    # Interactive config setup
cf config set package_manager uv  # Set specific value
cf config show                    # Display current config
```

### 3.2 Error Surfacing
- Full execution history with errors
- Store stderr/stdout from failed shell commands
- Searchable error events

**Commands:**
```bash
cf work show <task-id>           # Full execution history
cf events list --task <id>       # Events for a task
cf events search --error         # Find error events
cf events search --type GATE_FAILED
```

### 3.3 Smarter Context Loading
- Configurable context window per task complexity
- PRD hints for relevant files (e.g., `<!-- files: src/auth/*.py -->`)
- Improved file relevance scoring
- Option to explicitly include/exclude files

### 3.4 Enhanced Self-Correction ✅
- Pattern-based quick fixes:
  - Import errors → add import
  - Missing dependency → install it
  - Type errors → add type hints
- Learn from previous fix attempts in same run
- Escalate to blocker after N similar failures
- Better error message parsing
- **Shell command execution** during self-correction (uv pip install, etc.)
- **FixScope classification** (LOCAL vs GLOBAL) for parallel coordination

### 3.5 Agent Tool System (Future - see codeframe-p77g)
Current: Agents can create/edit files and run shell commands during self-correction.
Future: Formalized tool interface with:
- Tool protocol (name, description, parameters, execute)
- MCP server integration for external tools
- Permission system for dangerous operations
- Full rollback support

---

## Phase 4: Continuous Execution

**Goal:** Agent runs autonomously until human input is needed

### 4.1 Watch Mode
- Agent runs continuously through task queue
- Automatically pauses when blocker created
- Resumes immediately when blocker answered
- Respects task priorities and dependencies
- Configurable: stop on first failure vs continue

**Commands:**
```bash
cf work watch                    # Run until queue empty or blocked
cf work watch --stop-on-failure  # Stop on first failure
cf work watch --priority high    # Only high priority tasks
```

### 4.2 Live Streaming
- Real-time output during execution
- Stream to terminal or log file
- Batch-level streaming for parallel execution

**Commands:**
```bash
cf work follow <task-id>         # Tail single task output
cf work batch follow [batch-id]  # Stream batch progress
cf work follow --log task.log    # Write to file while streaming
```

### 4.3 Graceful Interruption
- Ctrl+C triggers clean shutdown
- State saved at current step
- Resume picks up exactly where stopped

**Commands:**
```bash
cf work pause                    # Pause current execution
cf work resume                   # Resume paused work
cf work status                   # Show pause/resume state
```

---

## Phase 5: Idea → PRD Generation

**Goal:** Agent helps define what to build

### 5.1 Interactive PRD Creation
- Guided conversation to capture requirements
- Agent asks clarifying questions
- Generates structured PRD from answers
- Templates for common project types

**Commands:**
```bash
cf prd create                    # Start interactive PRD creation
cf prd create --template api     # Use API project template
cf prd create --from idea.txt    # Start from rough notes
```

### 5.2 Project Configuration Collection
- During PRD creation, collect environment config
- Package manager, frameworks, conventions
- Store in `.codeframe/config.yaml`
- Agent uses for all future tasks

### 5.3 Documentation Generation
- Generate project documentation scaffolds
- Infer from codebase structure + PRD
- Human reviews and edits

**Commands:**
```bash
cf docs generate                 # Generate all docs
cf docs generate --type readme   # Just README
cf docs generate --type agents   # Just AGENTS.md
```

### 5.4 PRD Refinement
- Agent analyzes PRD for gaps
- Asks targeted follow-up questions
- Suggests missing requirements
- Validates against codebase reality

**Commands:**
```bash
cf prd refine                    # Improve existing PRD
cf prd validate                  # Check PRD against codebase
cf prd gaps                      # List identified gaps
```

---

## Phase 6: Git Integration

**Goal:** Agent manages git contextually without reimplementing git

### 6.1 Git Passthrough
- Run git commands in workspace context
- Sanitize dangerous operations (force push, hard reset require confirmation)
- Log all git operations for audit
- Context-aware suggestions

**Commands:**
```bash
cf git -- status                 # Passthrough to git status
cf git -- log --oneline -5       # Any git command
cf git -- push origin main       # Dangerous ops prompt for confirmation
```

### 6.2 Smart Defaults
- Auto-generate commit messages from completed tasks
- Branch naming from task/batch IDs
- Enhanced status with task context

**Commands:**
```bash
cf git commit                    # Auto-message from recent tasks
cf git commit -m "custom"        # Override message
cf git branch                    # Create branch from current batch
cf git branch --name feature/x   # Explicit name
cf git status                    # Git status + task context
```

### 6.3 Workflow Commands
- Create feature branches automatically
- Branch-per-batch default (configurable to branch-per-task)
- PR creation with task summaries

**Commands:**
```bash
cf work start <id> --branch           # Auto-create feature branch
cf work batch run --branch            # Branch for entire batch
cf pr create                          # Create PR from current branch
cf pr create --draft                  # Create as draft
cf pr create --title "Feature X"      # Custom title
```

### 6.4 Diff Review
- Review changes before committing
- Approve workflow for verification

**Commands:**
```bash
cf review diff                   # Show uncommitted changes
cf review diff --task <id>       # Changes from specific task
cf review approve                # Approve and commit
cf review reject                 # Rollback task changes
```

---

## Phase 7: Multi-Agent Coordination

**Goal:** Specialized agents working together on complex tasks

### 7.1 Agent Roles
- **Backend Agent** — API design, database, business logic
- **Frontend Agent** — UI components, state management
- **Test Agent** — Test generation, coverage analysis
- **Review Agent** — Code review, security scanning

Role-specific:
- System prompts optimized for role
- Tool access restrictions (e.g., Review agent is read-only)
- Quality gates per role

**Commands:**
```bash
cf tasks set role <id> backend   # Assign role to task
cf tasks generate --auto-roles   # Auto-detect roles from task content
cf agents list                   # Show available agent roles
```

### 7.2 Agent Handoff
- Shared context passing between agents
- Handoff protocols:
  - Implementation → Test (passes interface contracts)
  - Test → Review (passes test results)
  - Review → Implementation (passes feedback)
- Dependency tracking across agent work

**Commands:**
```bash
cf work pipeline <task-id>       # Run through impl→test→review
cf work handoff <from> <to>      # Manual handoff with context
```

### 7.3 Parallel Agent Execution
- Multiple agents on independent tasks simultaneously
- Conflict detection (same file modified by multiple agents)
- Resolution strategies:
  - Serialize conflicting tasks
  - Merge changes (if safe)
  - Create blocker for human decision

**Commands:**
```bash
cf work batch run --multi-agent       # Enable parallel agents
cf work batch run --max-agents 3      # Limit concurrent agents
cf conflicts list                      # Show detected conflicts
cf conflicts resolve <id> --merge     # Attempt merge
cf conflicts resolve <id> --serialize # Run sequentially
```

---

## Phase 8: Observability & History

**Goal:** Understand what happened and why

### 8.1 Execution Timeline
- Full event timeline for any task
- Event types:
  - TASK_STARTED, TASK_COMPLETED, TASK_FAILED
  - PLAN_CREATED, STEP_STARTED, STEP_COMPLETED
  - GATE_PASSED, GATE_FAILED
  - BLOCKER_CREATED, BLOCKER_ANSWERED
  - SELF_CORRECTION_ATTEMPTED
- Duration tracking per step
- Filterable and searchable

**Commands:**
```bash
cf history <task-id>             # Full timeline
cf history <task-id> --steps     # Just execution steps
cf history <task-id> --gates     # Just verification events
cf history --since "2h ago"      # Recent history
```

### 8.2 Replay & Debug
- Re-run task with same context (for debugging)
- Step-by-step execution with confirmation
- Export traces for external analysis

**Commands:**
```bash
cf replay <task-id>              # Dry-run with same context
cf replay <task-id> --step       # Step-by-step with prompts
cf debug <task-id>               # Interactive debug session
cf export trace <task-id>        # Export for analysis
```

---

## Phase 9: TUI Dashboard

**Goal:** Rich terminal interface for power users

Built with Rich/Textual for cross-platform terminal UI.

### 9.1 Status View
- Real-time task status updates
- Streaming execution log
- Blocker notifications with sound/flash
- Progress indicators

### 9.2 Interactive Control
- Answer blockers inline (no separate command needed)
- Pause/resume with hotkeys
- Priority adjustment via UI
- Task selection and drill-down

### 9.3 Split Layout
```
┌─────────────────────┬────────────────────────────────┐
│ Tasks               │ Execution Output               │
│ ─────────────────── │ ────────────────────────────── │
│ ● Task 1 [DONE]     │ [12:34:56] Planning task...    │
│ ◐ Task 2 [RUNNING]  │ [12:34:58] Step 1: Create file │
│ ○ Task 3 [READY]    │ [12:35:01] Step 2: Edit main   │
│ ⚠ Task 4 [BLOCKED]  │ [12:35:05] Running ruff...     │
│ ○ Task 5 [READY]    │                                │
├─────────────────────┴────────────────────────────────┤
│ > cf work start task-3 --execute                     │
└──────────────────────────────────────────────────────┘
```

- Left panel: Task list with status indicators
- Right panel: Live execution output
- Bottom: Command input
- Reserve space for future cost/token display

**Commands:**
```bash
cf tui                           # Launch TUI
cf tui --watch                   # Launch in watch mode
```

---

## Phase 10: Remote Access & Metrics

**Goal:** External system integration and usage tracking

*This phase requires FastAPI server.*

### 10.1 Webhooks
- Configurable webhook endpoints
- Events: task_completed, task_failed, blocker_created, batch_completed
- Payload includes task details, duration, errors
- Integration targets: Slack, Discord, custom endpoints

**Configuration:**
```yaml
# .codeframe/config.yaml
webhooks:
  - url: https://hooks.slack.com/...
    events: [blocker_created]
  - url: https://my-server.com/codeframe
    events: [task_completed, task_failed]
```

**Commands:**
```bash
cf webhooks list                 # Show configured webhooks
cf webhooks test <url>           # Send test payload
cf webhooks add <url> --events task_completed,task_failed
```

### 10.2 Git Platform Integration
- GitHub/GitLab PR integration
- Post task summaries as PR comments
- Update PR status checks
- Triggered by PR events (webhook receiver)

**Commands:**
```bash
cf github connect                # OAuth setup
cf github pr comment <pr-num>    # Post task summary
cf github status <pr-num>        # Update status check
```

### 10.3 REST API
- Full CRUD for tasks, blockers, batches
- Start/stop/pause execution
- Real-time status via SSE

**Endpoints:**
```
GET    /api/tasks                # List tasks
POST   /api/tasks                # Create task
GET    /api/tasks/{id}           # Get task details
POST   /api/tasks/{id}/start     # Start execution
POST   /api/tasks/{id}/stop      # Stop execution

GET    /api/blockers             # List blockers
POST   /api/blockers/{id}/answer # Answer blocker

GET    /api/batches              # List batches
POST   /api/batches              # Create batch
GET    /api/batches/{id}/stream  # SSE event stream
```

**Commands:**
```bash
cf serve                         # Start API server
cf serve --port 8080             # Custom port
```

### 10.4 Token & Cost Tracking
- Track tokens per LLM call
- Aggregate by task, batch, time period
- Breakdown by purpose (planning, execution, generation)
- Expose via API for external dashboards
- Include in webhook payloads

**Commands:**
```bash
cf summary --costs               # Show token/cost summary
cf summary --costs --since "7d"  # Last 7 days
cf costs export --format csv     # Export for analysis
```

---

## Execution Order

```
Phase 3: Agent Reliability       ← Fix known pain points
    │
    ↓
Phase 4: Continuous Execution    ← True autonomy
    │
    ↓
Phase 5: Idea → PRD              ← Complete front of funnel
    │
    ↓
Phase 6: Git Integration         ← Passthrough first, then workflows
    │
    ↓
Phase 7: Multi-Agent             ← Scale capabilities
    │
    ↓
Phase 8: Observability           ← Understand and debug
    │
    ↓
Phase 9: TUI                     ← Power user experience
    │
    ↓
Phase 10: Remote & Metrics       ← Webhooks, API, cost tracking
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Environment config | User-set, agent-collected | Avoid guessing, explicit is better |
| Execution priority | Continuous before git | Autonomy is core value proposition |
| Branch strategy | Per-batch default | Most common use case, configurable |
| Git commands | Passthrough with `cf git --` | Avoid reimplementing git |
| Multi-agent timing | Before TUI | Capability before UX polish |
| FastAPI trigger | Webhooks (Phase 10) | Deep git integration, not CI/CD replacement |
| Token tracking | End of roadmap | Nice-to-have, not blocking |
| TUI framework | Rich/Textual | Cross-platform, Python-native |

---

## Dependencies & Prerequisites

### Phase 3
- No external dependencies
- Builds on existing agent infrastructure

### Phase 4
- Requires Phase 3 (reliable agent before continuous mode)
- May need async refactoring for streaming

### Phase 5
- Requires Phase 3 (config collection uses same infrastructure)
- Requires Phase 4 (PRD creation is interactive, needs good UX)

### Phase 6
- Independent of Phases 4-5 (could be done earlier if prioritized)
- Git passthrough is low-risk, high-value

### Phase 7
- Requires Phases 3-4 (agents must be reliable before coordination)
- Significant architecture work for handoff protocols

### Phase 8
- Requires event infrastructure from earlier phases
- Mostly additive, low-risk

### Phase 9
- Requires all CLI features complete (TUI wraps CLI)
- New dependency: Rich or Textual

### Phase 10
- Requires FastAPI (new server component)
- Webhooks could be done standalone
- API requires stable CLI interface

---

## Non-Goals

These are explicitly out of scope for the v2 roadmap:

1. **GUI/Web Dashboard** — TUI only, no React/browser UI
2. **CI/CD Replacement** — Integrate with git, don't replace CI/CD
3. **Multi-User/Teams** — Single-user focus for now
4. **Cloud Hosting** — Local-first, self-hosted only
5. **Model Training** — Use existing LLMs, don't train custom models
6. **IDE Plugins** — CLI/TUI only, no VS Code extension

---

## Success Metrics

### Phase 3
- Task completion rate > 80% (currently ~0% on new projects)
- Error messages visible for 100% of failures

### Phase 4
- Agent runs for 30+ minutes without human intervention
- Clean resume after Ctrl+C in 100% of cases

### Phase 5
- PRD generation from idea in < 10 minutes
- Generated PRDs pass validation 90%+ of time

### Phase 6
- Zero accidental force pushes or data loss
- PR creation works on first try 95%+ of time

### Phase 7
- Multi-agent batch completes 80%+ of tasks
- Conflict resolution handles 90%+ automatically

### Phase 8
- Any failure can be diagnosed from history
- Replay reproduces issue 100% of time

### Phase 9
- TUI responsive with 100+ tasks
- Blocker answered without leaving TUI

### Phase 10
- Webhook delivery > 99.9% reliability
- API latency < 100ms for status queries
