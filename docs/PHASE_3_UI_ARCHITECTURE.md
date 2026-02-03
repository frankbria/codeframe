# CodeFRAME Phase 3: UI Information Architecture

**Created**: 2026-02-03
**Status**: Approved design for golden path UI

## Overview

This document defines the information architecture for the CodeFRAME web UI. The UI follows the "golden path" philosophy - we build only what's necessary for the core workflow, nothing more.

**Key Constraints:**
- CLI is fully functional and production-ready (Phase 1 complete)
- REST API with SSE streaming is complete (Phase 2 complete)
- UI should consume existing API, not drive new features
- Tech stack: Next.js App Router, Shadcn/UI + Tailwind (Nova template), Hugeicons

---

## 1. View Inventory

### 1.1 Workspace View (Home)
**Purpose:** Initialize and overview the current workspace state.

**Key Actions:**
- Initialize workspace (one-time setup per repo)
- View workspace metadata (tech stack, git status)
- Quick access to PRD, tasks, and active runs

**Data Displayed:**
- Workspace path and initialization status
- Detected tech stack configuration
- Quick stats: PRD count, task counts by status, active runs
- Recent activity timeline (last 5 events)

---

### 1.2 PRD View
**Purpose:** Create, view, and iterate on Product Requirements Documents.

**Key Actions:**
- Upload/paste PRD markdown
- Start discovery session (Socratic AI conversation)
- Edit PRD content
- Generate tasks from PRD

**Data Displayed:**
- PRD content (markdown rendered)
- PRD metadata (version, created date, file path)
- Discovery session transcript (if applicable)
- Associated tasks count and status breakdown

---

### 1.3 Task Board View
**Purpose:** Visualize and manage task lifecycle from backlog to completion.

**Key Actions:**
- View tasks grouped by status (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED, FAILED)
- Filter/search tasks
- Execute single task
- Start batch execution
- View task details
- Mark tasks as READY manually

**Data Displayed:**
- Kanban-style columns (or simple list grouped by status)
- Per-task cards showing: title, description snippet, status, dependencies, effort estimate
- Batch execution controls (strategy selector, retry config)
- Task dependency indicators (visual cues for blocked/blocking relationships)

---

### 1.4 Execution Monitor View
**Purpose:** Real-time observation of AI agent task execution.

**Key Actions:**
- View streaming output (planning, file changes, shell commands, verification)
- Pause/stop execution
- Answer blockers inline
- Review generated changes (file diffs)

**Data Displayed:**
- Task being executed (title, description)
- Agent state (PLANNING, EXECUTING, BLOCKED, COMPLETED, FAILED)
- Live event stream with timestamps
- File changes preview (collapsible sections)
- Verification gate results (ruff, pytest)
- Blocker questions (if raised)

---

### 1.5 Blocker Resolution View
**Purpose:** Respond to agent questions and unblock stuck tasks.

**Key Actions:**
- View open blockers
- Provide text answer to blocker
- Mark blocker as resolved
- Resume blocked task

**Data Displayed:**
- List of open blockers (task context, blocker question, timestamp)
- Blocker detail (full context, attempted fixes, agent's question)
- Answer input form
- History of resolved blockers (optional, low priority)

---

### 1.6 Review & Commit View
**Purpose:** Inspect changes and commit to git with confidence.

**Key Actions:**
- View unified diff of all changes
- Run quality checks (lint, tests)
- Export patch file
- Commit with generated message
- Create GitHub PR

**Data Displayed:**
- File tree with changed files highlighted
- Unified diff viewer (syntax highlighted)
- Quality gate results (pass/fail badges)
- Commit message suggestion (from AI)
- PR creation form (title, description)

---

## 2. Navigation Structure

### Primary Navigation (Sidebar)
Persistent left sidebar with icon + label navigation:
1. **Workspace** (home icon)
2. **PRD** (document icon)
3. **Tasks** (checklist icon)
4. **Execution** (play/monitor icon) - only visible when runs are active
5. **Blockers** (alert icon) - badge count for open blockers
6. **Review** (git branch icon)

### Secondary Navigation
- **Workspace breadcrumb** at top: shows current repo path, links to workspace root
- **Task detail modal** opens from Task Board (overlay, not new view)
- **Blocker answer modal** opens from Execution Monitor or Blocker view (inline expansion preferred)

### Navigation Flow (Golden Path)
```
Workspace → PRD → Tasks → Execution Monitor → Blockers (if needed) → Review & Commit
            ↓                                                           ↓
         (Generate Tasks)                                         (Create PR)
```

### URL Structure
```
/                          → Workspace View
/prd                       → PRD View
/prd/discovery             → PRD Discovery Session (sub-view)
/tasks                     → Task Board View
/tasks/:id                 → Task Detail (modal overlay)
/execution                 → Execution Monitor (auto-navigates when run starts)
/execution/:run_id         → Specific run monitoring
/blockers                  → Blocker Resolution View
/review                    → Review & Commit View
```

---

## 3. Component Hierarchy per View

### 3.1 Workspace View
```
WorkspaceView
├── WorkspaceHeader
│   ├── RepoPathDisplay
│   └── InitializeWorkspaceButton (if not initialized)
├── WorkspaceStatsCards
│   ├── TechStackCard
│   ├── TaskStatsCard (READY, IN_PROGRESS, DONE counts)
│   └── ActiveRunsCard
└── RecentActivityFeed
    └── ActivityItem[] (event type, timestamp, description)
```

**Modals:** None
**Panels:** None (single-column layout)

---

### 3.2 PRD View
```
PRDView
├── PRDHeader
│   ├── PRDTitle (editable inline)
│   ├── PRDActions
│   │   ├── UploadPRDButton
│   │   ├── StartDiscoveryButton
│   │   └── GenerateTasksButton
│   └── PRDMetadata (version, file path)
├── PRDContent (two-column when discovery active)
│   ├── MarkdownEditor (left, or full-width when no discovery)
│   └── DiscoveryPanel (right, collapsible)
│       ├── DiscoveryTranscript (chat-style messages)
│       └── DiscoveryInput (text input + send button)
└── AssociatedTasksSummary
    └── TaskCountByStatus (compact badges)
```

**Modals:**
- `UploadPRDModal` (file picker or paste markdown)

**Panels:**
- `DiscoveryPanel` (slides in from right when session starts)

---

### 3.3 Task Board View
```
TaskBoardView
├── TaskBoardHeader
│   ├── TaskFilters (status, search bar)
│   └── BatchActions
│       ├── SelectTasksMode (checkbox selection)
│       ├── BatchStrategySelector (serial/parallel/auto)
│       └── ExecuteBatchButton
├── TaskBoardContent (Kanban columns or grouped list)
│   ├── TaskColumn (status: BACKLOG)
│   │   └── TaskCard[]
│   ├── TaskColumn (status: READY)
│   ├── TaskColumn (status: IN_PROGRESS)
│   ├── TaskColumn (status: BLOCKED)
│   ├── TaskColumn (status: FAILED)
│   └── TaskColumn (status: DONE)
└── TaskQuickActions (floating action button)
    └── CreateTaskManuallyButton (low priority)
```

**TaskCard Component:**
```
TaskCard
├── TaskTitle
├── TaskDescriptionSnippet (truncated)
├── TaskMetadata (effort, dependencies badge)
├── TaskStatusBadge
└── TaskActions
    ├── ViewDetailsButton
    ├── ExecuteButton (if READY)
    └── MarkReadyButton (if BACKLOG)
```

**Modals:**
- `TaskDetailModal` (full description, dependencies, execution history, edit controls)

**Panels:** None

---

### 3.4 Execution Monitor View
```
ExecutionMonitorView
├── ExecutionHeader
│   ├── CurrentTaskTitle
│   ├── AgentStateBadge (PLANNING, EXECUTING, BLOCKED, etc.)
│   └── ExecutionControls
│       ├── PauseButton
│       └── StopButton
├── EventStream (main content, scrollable)
│   ├── EventItem[] (timestamp, event type, content)
│   │   ├── PlanningEvent (displays plan steps)
│   │   ├── FileChangeEvent (collapsible diff preview)
│   │   ├── ShellCommandEvent (command + output)
│   │   ├── VerificationEvent (gate results, pass/fail)
│   │   └── BlockerEvent (blocker question, inline answer form)
│   └── AutoScrollToggle (stick to bottom or allow manual scroll)
├── ProgressIndicator (top or sidebar)
│   ├── CurrentStepDisplay (e.g., "Step 3 of 7: Running pytest")
│   └── ProgressBar
└── ChangesSidebar (collapsible right panel)
    ├── ChangedFilesList (tree view)
    └── FileDiffPreview (click to expand in sidebar)
```

**Modals:**
- `BlockerAnswerModal` (or inline expansion in EventStream - prefer inline)

**Panels:**
- `ChangesSidebar` (right-side collapsible, shows file diffs)

---

### 3.5 Blocker Resolution View
```
BlockerResolutionView
├── BlockerList
│   └── BlockerCard[]
│       ├── TaskContext (task title, description)
│       ├── BlockerQuestion (agent's question, highlighted)
│       ├── BlockerMetadata (timestamp, attempts count)
│       ├── AnswerForm (text area + submit button)
│       └── ResolveButton (marks resolved, resumes task)
└── ResolvedBlockersAccordion (collapsed by default)
    └── ResolvedBlockerItem[]
```

**Modals:** None (inline answer forms)
**Panels:** None

---

### 3.6 Review & Commit View
```
ReviewCommitView
├── ReviewHeader
│   ├── ChangeSummary (X files changed, Y insertions, Z deletions)
│   └── QualityGateResults
│       ├── GateBadge (ruff: passed)
│       └── GateBadge (pytest: 12/12 passed)
├── FileTreePanel (left sidebar, 25% width)
│   └── FileTree (changed files, click to view diff)
├── DiffViewer (main content, 75% width)
│   ├── UnifiedDiff (syntax highlighted)
│   └── DiffNavigation (prev/next file buttons)
└── CommitPanel (bottom or right panel)
    ├── CommitMessageSuggestion (AI-generated, editable)
    ├── CommitButton
    └── PRCreationToggle
        └── PRForm (title, description, auto-populated)
```

**Modals:**
- `ExportPatchModal` (displays patch content, copy button)
- `PRCreatedModal` (success message + PR URL)

**Panels:**
- `FileTreePanel` (left, persistent)
- `CommitPanel` (bottom or right, collapsible)

---

## 4. Real-time Patterns

### SSE Event Handling Strategy

**Connection Management:**
- Open SSE connection when navigating to Execution Monitor View
- Subscribe to `/api/v2/tasks/{task_id}/stream` endpoint
- Maintain connection until run completes or user navigates away
- Automatic reconnection with exponential backoff on disconnect

**Event Stream Display:**
```
┌─────────────────────────────────────────────────────┐
│ 10:23:45 [PLANNING]                                 │
│ • Analyzing task requirements...                    │
│ • Generated 5-step plan                            │
│                                                     │
│ 10:23:47 [EXECUTING] Step 1/5                      │
│ Creating file: src/auth/middleware.py              │
│   [View Diff ▼]                                    │
│                                                     │
│ 10:23:48 [VERIFICATION]                            │
│ ✓ ruff check: passed                              │
│                                                     │
│ 10:23:50 [EXECUTING] Step 2/5                      │
│ Running: pytest tests/auth/                        │
│   stdout: ===== test session starts =====          │
│   stdout: collected 3 items                        │
│   ✗ FAILED tests/auth/test_middleware.py::test_1  │
│                                                     │
│ 10:23:52 [SELF_CORRECTING]                         │
│ Attempting fix (1/3)...                            │
│ • Detected ImportError for Optional                │
│ • Applying quick fix: add missing import           │
│                                                     │
│ 10:23:54 [VERIFICATION]                            │
│ ✓ pytest: 3/3 passed                              │
│ ✓ All gates passed                                │
│                                                     │
│ 10:23:55 [COMPLETED]                               │
│ Task completed successfully                         │
└─────────────────────────────────────────────────────┘
```

**Event Type Styling:**
| Event | Badge Color | Details |
|-------|-------------|---------|
| PLANNING | Blue | Indented bullet list |
| EXECUTING | Green | Step counter (X/Y), collapsible details |
| VERIFICATION | Orange → Green/Red | Checkmark when passed, X when failed |
| SELF_CORRECTING | Yellow | Shows attempt count |
| BLOCKED | Red | Interrupt pattern with inline form |
| COMPLETED | Green | Success icon |
| FAILED | Red | Error icon |

**Interrupt Pattern for Blockers:**
```
┌─────────────────────────────────────────────────────┐
│ 10:24:10 [BLOCKED] 🚨                               │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Agent needs your help:                          │ │
│ │                                                 │ │
│ │ "Should I use JWT or session-based auth for    │ │
│ │  the API? The PRD mentions 'secure auth' but   │ │
│ │  doesn't specify implementation."              │ │
│ │                                                 │ │
│ │ [Text input area]                              │ │
│ │                                                 │ │
│ │ [Answer Blocker]  [View Full Context]          │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ Execution paused - waiting for response...          │
└─────────────────────────────────────────────────────┘
```

**Auto-scroll Behavior:**
- Default: stick to bottom (new events auto-scroll into view)
- User scrolls up: pause auto-scroll, show "New events ↓" button at bottom
- Click button or scroll to bottom: re-enable auto-scroll

---

## 5. Interaction Patterns

### 5.1 PRD Discovery Flow (Socratic AI Conversation)

**Pattern:** Chat-style interface with AI leading questions.

**Flow:**
1. User clicks "Start Discovery Session" button
2. Discovery panel slides in from right (or expands below PRD editor)
3. AI sends first message: "What problem does this project solve?"
4. User types answer in chat input
5. AI acknowledges, asks follow-up: "Who are the primary users?"
6. Conversation continues (multi-turn, 5-10 questions typical)
7. AI signals completion: "I have enough information to generate a PRD. Review below."
8. AI-generated PRD appears in markdown editor (left pane)
9. User can edit, then click "Generate Tasks"

**Key UX Details:**
- Clear AI branding: Avatar or badge for AI messages
- Thinking indicator: Animated dots while AI generates next question
- Conversation persistence: Session saved, can resume later
- Skip option: "I'll write the PRD manually" button to close discovery
- Edit-as-you-go: User can edit generated PRD before finalizing

---

### 5.2 Task Execution Monitoring

**Pattern:** Real-time streaming with progressive disclosure.

**Flow:**
1. User clicks "Execute" on a READY task
2. Auto-navigate to Execution Monitor View
3. SSE connection opens, events stream in
4. Collapsible sections for verbose output (file diffs, shell output)
5. Critical events (blockers, failures) interrupt with highlighted banner
6. On completion, show success summary + "View Changes" button (navigates to Review)

**Key UX Details:**
- Visual hierarchy: Critical events (BLOCKED, FAILED) use color + size to grab attention
- Diff previews: Inline, collapsible, syntax-highlighted
- Command output: Monospace font, collapsible, scrollable
- Pause/stop controls: Always visible at top, confirm before stopping

---

### 5.3 Blocker Resolution

**Pattern:** Inline expansion with context visibility.

**Flow:**
1. Agent raises blocker during execution
2. Interrupt pattern in Execution Monitor (highlighted blocker event)
3. User types answer in inline form
4. Click "Answer Blocker" → sends answer to API
5. Execution auto-resumes after answer submitted

**Key UX Details:**
- Context visibility: Show task title, description, and agent's attempted fixes
- Guidance questions: AI can suggest what information it needs
- No dead ends: Option to skip/cancel blocker (marks task as BLOCKED)
- Notification badge: Blocker count on sidebar icon

---

### 5.4 Batch Execution with Parallel Tasks

**Pattern:** Multi-task progress dashboard with strategy selector.

**Batch Execution Monitor Layout:**
```
┌─────────────────────────────────────────────────────┐
│ Batch Execution (5 tasks)                           │
│ Strategy: Parallel (max 3)                         │
│                                                     │
│ ✓ Task 1: Add authentication [COMPLETED] 45s      │
│ ⟳ Task 2: Write tests [IN_PROGRESS] 12s           │
│   └─ [View Live Output ▼]                         │
│ ⏸ Task 3: Update docs [WAITING] (depends on 2)    │
│ ✗ Task 4: Deploy API [FAILED] 8s                  │
│   └─ [View Error ▼]                               │
│ ● Task 5: Lint code [READY]                       │
│                                                     │
│ [Pause All] [Cancel Batch]                         │
└─────────────────────────────────────────────────────┘
```

**Key UX Details:**
- Parallel execution indicator: Highlight tasks running simultaneously
- Click to expand: Each task row expands to show live event stream
- Retry failed tasks: Button to retry only failed tasks in batch

---

## 6. Anti-patterns to Avoid

### 6.1 Feature Creep
**DON'T BUILD:**
- ❌ Task templates UI (CLI has `cf templates`)
- ❌ Custom agent configuration (tech stack is auto-detected)
- ❌ Multi-workspace switcher (one workspace per session)
- ❌ Task editing UI (tasks are generated from PRD)
- ❌ Historical analytics (no dashboards or charts)
- ❌ User management (single-user tool)
- ❌ Notification center (SSE events in context are enough)

### 6.2 Complex State Management
**DON'T BUILD:**
- ❌ Optimistic updates (wait for API confirmation)
- ❌ Offline mode (assume network connectivity)
- ❌ Undo/redo (git handles rollback)
- ❌ Draft states (PRD discovery is the only "draft")

### 6.3 Over-engineered Real-time
**DON'T BUILD:**
- ❌ Live collaboration (no multiplayer)
- ❌ Cursor positions (no "typing" indicators)
- ❌ Live file preview (diffs on completion are enough)
- ❌ WebSocket fallbacks (SSE is sufficient)

### 6.4 Premature Abstraction
**DON'T BUILD:**
- ❌ Custom design system (use Shadcn/UI as-is)
- ❌ Theming engine (stick to Tailwind CSS)
- ❌ Plugin architecture (no extension points)
- ❌ Internationalization (English-only for v1)

### 6.5 Desktop-only Patterns
**DON'T BUILD:**
- ❌ Drag-and-drop task reordering (tasks ordered by dependencies)
- ❌ Resizable panels (fixed layouts are fine)
- ❌ Keyboard shortcuts (mouse-first is acceptable)
- ❌ Multi-window support (single-tab experience)

### 6.6 Trying to Replicate CLI in UI
**DON'T BUILD:**
- ❌ Terminal emulator (translate to visual components)
- ❌ Command palette (normal navigation is fine)
- ❌ Log viewer (design for readability, not raw text)

---

## 7. Summary

### The 6 Core Views

| View | Purpose | Key Component | Real-time? |
|------|---------|---------------|------------|
| **Workspace** | Overview & initialization | WorkspaceStatsCards | Static |
| **PRD** | Document creation & discovery | DiscoveryPanel | SSE (discovery chat) |
| **Tasks** | Kanban board & batch controls | TaskCard grid | Poll on nav |
| **Execution** | Monitor AI agent work | EventStream | SSE (execution events) |
| **Blockers** | Answer agent questions | BlockerCard with inline form | Poll on nav |
| **Review** | Inspect & commit changes | DiffViewer + CommitPanel | Static |

### Design Philosophy
- **Navigation:** Left sidebar (persistent), URL-driven, auto-navigate on execution start
- **Real-time:** SSE for execution and discovery only, simple polling elsewhere
- **Minimal:** Every screen serves the golden path, every component is essential
- **Elegant:** Clean, crisp UI focused on the task at hand
