# CodeFRAME Technical Specification v1.0

**Fully Remote Autonomous Multiagent Environment for Coding**

---

## Executive Summary

CodeFRAME is an autonomous AI coding system that manages software development through coordinated agent swarms. Built initially on Claude Code with support for multiple LLM providers, it enables developers to launch projects, define requirements through Socratic dialogue, and let AI agents work autonomously while maintaining human oversight through asynchronous interruption patterns.

**Key Innovation**: Virtual Project context management - React-like diffing for agent memory that hot-swaps context based on importance scoring, preventing context pollution and enabling long-running autonomous execution.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [Virtual Project Context System](#virtual-project-context-system)
4. [Agent Management & Maturity](#agent-management--maturity)
5. [Task Coordination](#task-coordination)
6. [Notification System](#notification-system)
7. [State Persistence & Recovery](#state-persistence--recovery)
8. [Multi-Provider Support](#multi-provider-support)
9. [Test Automation](#test-automation)
10. [Status Server & UI](#status-server--ui)
11. [15-Step Workflow Integration](#15-step-workflow-integration)
12. [Database Schema](#database-schema)
13. [API Specifications](#api-specifications)
14. [MVP Scope & Roadmap](#mvp-scope--roadmap)

---

## Architecture Overview

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────┐
│                    CodeFRAME CLI / API                       │
│  Commands: init, start, pause, resume, status, config        │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│           ORCHESTRATION ENGINE (Lead Agent)                  │
│  • Hybrid coordination (centralized planning + distributed)  │
│  • Project state management                                  │
│  • Task queue & dependency resolution (DAG)                  │
│  • Agent lifecycle management                                │
│  • Conflict detection & resolution                           │
│  • Flash save coordination before compactification           │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┬──────────────┐
        │           │           │              │
┌───────▼──┐  ┌────▼────┐  ┌──▼──────┐  ┌───▼──────┐
│ Backend  │  │Frontend │  │  Test   │  │ Review   │
│ Agent    │  │ Agent   │  │  Agent  │  │ Agent    │
│ (Claude) │  │ (GPT-4?)│  │ (Claude)│  │ (GPT-4?) │
└───────┬──┘  └────┬────┘  └──┬──────┘  └───┬──────┘
        │          │          │              │
        └──────────┴──────────┴──────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│              SHARED CONTEXT LAYER                            │
│                                                              │
│  📁 File System              🗄️ SQLite Database              │
│  ├── .codeframe/             ├── projects                   │
│  │   ├── config.json         ├── tasks                      │
│  │   ├── state.db            ├── agents                     │
│  │   ├── checkpoints/        ├── blockers                   │
│  │   ├── memory/             ├── memory                     │
│  │   │   ├── prd.md          ├── context_items              │
│  │   │   ├── decisions.md    ├── context_snapshots          │
│  │   │   └── patterns.md     ├── changelog                  │
│  │   └── logs/               └── checkpoints                │
│  └── src/ [actual codebase]                                 │
└──────────────────────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┬──────────────┐
        │           │           │              │
┌───────▼──────┐ ┌─▼─────────┐ ┌▼────────────┐ ┌▼──────────┐
│Notification  │ │  Status   │ │ Test        │ │ Git       │
│Service       │ │  Server   │ │ Runner      │ │ Integration│
│(Multi-chan)  │ │(Web+Chat) │ │(pytest/jest)│ │(Auto-     │
│              │ │           │ │             │ │commit)    │
└──────────────┘ └───────────┘ └─────────────┘ └───────────┘
```

### Design Principles

1. **Hybrid Coordination**: Central Lead Agent for planning, distributed workers for execution
2. **Shared Memory**: SQLite database + filesystem for state, no direct agent-to-agent communication
3. **Asynchronous Human Interaction**: 2-level interruption (sync/async) with user control
4. **Context Efficiency**: Virtual Project system for intelligent context management
5. **Provider Agnostic**: Abstract interface supporting multiple LLM providers
6. **Self-Correcting**: Automated test-driven development with retry logic

---

## Core Components

### 1. Lead Agent (Orchestrator)

**Role**: Project manager and coordinator with single-throat-to-choke responsibility

**Responsibilities**:
- Socratic requirements discovery (Steps 1-3 of 15-step workflow)
- PRD generation and task decomposition
- Task queue management with dependency resolution
- Worker agent assignment based on maturity level
- Bottleneck detection and work rebalancing
- Blocker escalation with severity classification
- Flash save coordination before context compactification
- Checkpoint creation and recovery management

**Implementation Model**:
- **Hybrid conversation**: Maintains conversation during active phase
- Serialize and restart fresh between major phases
- Example: Discovery phase = 1 conversation, Execution = new conversation

**Technology**:
- Python orchestrator process (runs continuously)
- Claude API (or configured provider) for decision-making
- SQLite for state persistence

### 2. Worker Agents

**Types** (MVP):
- **Backend Agent**: API development, database, business logic
- **Frontend Agent**: UI components, state management
- **Test Agent**: Unit tests, integration tests, E2E tests
- **Review Agent**: Code review, quality checks, security scans

**Execution Pattern**:
```python
while project.is_active():
    task = lead_agent.get_next_task(agent_id=self.id)
    if task is None:
        if lead_agent.has_blockers():
            # Try to work on unblocked tasks
            task = lead_agent.get_unblocked_task(agent_id=self.id)
        else:
            sleep(60)
            continue

    result = self.execute_task(task)

    if result.status == "blocked":
        blocker = create_blocker(task, result)
        lead_agent.register_blocker(blocker)
    else:
        lead_agent.mark_complete(task.id, result)
        self.flash_save()
```

**Communication**:
- No direct agent-to-agent communication
- All coordination through Lead Agent + SQLite
- Read current codebase state from filesystem
- Write changes atomically with rollback capability

### 3. Shared Context Layer

**Components**:
- **SQLite Database** (`state.db`): Structured data (tasks, agents, blockers, memory)
- **Filesystem**: Code, checkpoints, logs, documentation
- **Virtual Context System**: Hot/warm/cold tiering for agent memory

**Key Tables** (see Database Schema section for full details):
- `projects`: Project metadata and configuration
- `tasks`: Task queue with dependencies and status
- `agents`: Agent registry with maturity tracking
- `blockers`: Human input requirements with severity
- `memory`: Learned patterns, decisions, preferences
- `context_items`: Virtual Project context with importance scores
- `checkpoints`: State snapshots for recovery

---

## Virtual Project Context System

### Overview

Inspired by React's Virtual DOM, the Virtual Project system manages agent context windows through intelligent diffing and hot-swapping. This prevents context pollution, optimizes token usage, and enables long-running autonomous execution.

### Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────┐
│           AGENT'S ACTIVE CONTEXT WINDOW                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  🔥 HOT TIER (~20K tokens, always loaded)               │
│  ├─ Current task specification                          │
│  ├─ Files being actively edited (max 3-5)              │
│  ├─ Latest test results only                           │
│  ├─ Active blocker context                             │
│  └─ High-importance decisions (last 10)                 │
│                                                          │
│  ♨️  WARM TIER (~40K tokens, loaded on-demand)          │
│  ├─ Related files (imports, dependencies)               │
│  ├─ Project structure overview                          │
│  ├─ PRD sections relevant to current phase              │
│  ├─ Code patterns and conventions                       │
│  └─ Medium-importance decisions (last 50)               │
│                                                          │
│  ❄️  COLD TIER (archived, queryable)                    │
│  ├─ Completed tasks and old code versions               │
│  ├─ Resolved test failures                              │
│  ├─ Deprecated decisions                                │
│  ├─ Full git history                                    │
│  └─ Low-importance changelog entries                    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Importance Scoring Algorithm

Every context item receives a dynamic importance score (0.0-1.0) determining tier placement:

```python
def calculate_importance_score(item: ContextItem) -> float:
    """
    Score calculation:
    - 0.8-1.0: HOT tier (always loaded)
    - 0.4-0.8: WARM tier (on-demand)
    - 0.0-0.4: COLD tier (archived)
    """
    age_hours = (datetime.now() - item.recency).total_seconds() / 3600

    # Base importance by type
    type_weights = {
        'current_task': 1.0,
        'active_file': 0.9,
        'recent_test': 0.85,
        'blocker': 0.95,
        'high_decision': 0.8,
        'related_file': 0.6,
        'prd': 0.7,
        'pattern': 0.5,
        'old_test': 0.3,
        'completed_task': 0.2,
        'deprecated': 0.1
    }

    base_score = type_weights.get(item.item_type, 0.5)

    # Exponential time decay (half-life ~17 hours)
    time_decay = math.exp(-age_hours / 24)

    # Access frequency boost
    access_boost = min(item.access_count * 0.1, 0.3)

    # Manual importance override
    manual_boost = item.importance

    # Weighted combination
    final_score = (base_score * 0.4 +
                  time_decay * 0.3 +
                  access_boost * 0.1 +
                  manual_boost * 0.2)

    return min(final_score, 1.0)
```

### Context Diffing & Hot-Swap

Before each agent invocation, compute minimal context changes:

```python
def prepare_agent_context(agent_id: str, task_id: int) -> dict:
    """React-like reconciliation for context."""
    current_context = get_cached_context(agent_id)

    # Compute ideal context for this task
    hot_items = gather_hot_items(task_id)
    warm_items = gather_warm_items(task_id)

    # Calculate diff
    context_diff = {
        'added': [item for item in hot_items if item not in current_context],
        'removed': [item for item in current_context if item not in hot_items],
        'updated': [item for item in hot_items if item.version > current_context[item.id].version]
    }

    # Apply diff
    new_context = current_context.copy()
    new_context.update(context_diff['added'])
    new_context.update(context_diff['updated'])
    for item in context_diff['removed']:
        new_context.pop(item.id)

    cache_context(agent_id, new_context)

    return {
        'hot_tier': new_context,
        'warm_tier_keys': [item.id for item in warm_items],
        'context_diff': context_diff
    }
```

### Intelligent Archival: "Will This Matter Later?"

After significant events, agents self-assess importance:

```python
def archive_decision(event: Event) -> None:
    """AI-driven importance assessment."""
    assessment = agent.evaluate(
        prompt=f"""
        Event: {event.description}

        Rate long-term importance (0.0-1.0):
        - 1.0: Critical architectural decision, impacts all future work
        - 0.7: Important pattern, likely referenced again
        - 0.5: Useful context, might be relevant later
        - 0.3: Resolved issue, unlikely to matter again
        - 0.1: Noise, safe to archive immediately

        Score:
        Reasoning:
        """
    )

    event.importance_score = assessment.score

    if assessment.score >= 0.8:
        save_to_tier(event, 'hot')
    elif assessment.score >= 0.4:
        save_to_tier(event, 'warm')
    else:
        save_to_tier(event, 'cold')
```

---

## Agent Management & Maturity

### Situational Leadership II Integration

Agents progress through four maturity levels based on performance metrics:

```python
class AgentMaturity(Enum):
    D1 = "directive"     # Low skill, high commitment - needs step-by-step
    D2 = "coaching"      # Some skill - needs guidance + encouragement
    D3 = "supporting"    # High skill - needs autonomy + support
    D4 = "delegating"    # High skill + confidence - full ownership
```

### Maturity Progression

**Metrics Tracked**:
- Task success rate
- Blocker frequency
- Test pass rate
- Rework rate
- Context efficiency (tokens per task)

**Progression Rules**:
```python
def assess_maturity(agent: Agent) -> None:
    metrics = calculate_metrics(agent)

    # Promotion criteria
    if (metrics.success_rate > 0.9 and
        metrics.blocker_freq < 0.1 and
        metrics.test_pass > 0.95 and
        metrics.rework < 0.05):
        promote_maturity(agent)

    # Regression criteria
    elif (metrics.success_rate < 0.7 or
          metrics.blocker_freq > 0.3):
        demote_maturity(agent)
```

### Task Assignment Adaptation

Lead Agent adjusts instructions based on maturity:

| Maturity | Instructions | Autonomy | Check-ins | Validation |
|----------|-------------|----------|-----------|------------|
| D1 (Directive) | Detailed step-by-step | Low | After each step | Lead reviews before commit |
| D2 (Coaching) | Guidance + examples | Medium | After subtasks | Automated tests must pass |
| D3 (Supporting) | Task description only | High | On completion | Peer review |
| D4 (Delegating) | Goal statement | Full | Optional | Self-review |

### User Override

Users can manually adjust or constrain agent maturity:

```json
{
  "agent_management": {
    "backend_agent": {
      "maturity_override": "coaching",
      "auto_progression": true
    },
    "global_policy": {
      "require_review_below_maturity": "supporting",
      "allow_full_autonomy": false
    }
  }
}
```

---

## Task Coordination

### Task Structure

```python
@dataclass
class Task:
    id: int
    project_id: int
    title: str
    description: str
    status: TaskStatus  # pending, assigned, in_progress, blocked, completed, failed
    assigned_to: str | None  # agent_id
    depends_on: List[int]  # Task IDs that must complete first
    priority: int  # 0-4 (0 = highest)
    workflow_step: int  # Maps to 15-step workflow
    requires_mcp: bool  # Needs MCP server support
    estimated_tokens: int
    actual_tokens: int | None
```

### Dependency Resolution

Tasks organized as Directed Acyclic Graph (DAG):

```python
def get_ready_tasks(project_id: int) -> List[Task]:
    """
    Returns tasks ready to work on:
    - Status = 'pending'
    - All dependencies completed
    - No circular dependencies
    """
    tasks = db.get_pending_tasks(project_id)
    ready = []

    for task in tasks:
        deps = db.get_task_dependencies(task.id)
        if all(dep.status == 'completed' for dep in deps):
            ready.append(task)

    return sorted(ready, key=lambda t: t.priority)
```

### Bottleneck Detection

Lead Agent monitors for work imbalances:

```python
def detect_bottlenecks() -> List[Bottleneck]:
    """
    Identifies situations where agents are blocked waiting for one task.
    """
    bottlenecks = []

    for task in get_in_progress_tasks():
        waiting_count = count_tasks_waiting_on(task.id)
        if waiting_count >= 3:  # 3+ tasks blocked by one
            bottlenecks.append(Bottleneck(
                task_id=task.id,
                waiting_tasks=waiting_count,
                recommendation="Assign additional agent or escalate"
            ))

    return bottlenecks
```

---

## Notification System

### Multi-Channel Architecture

```
┌─────────────────────────────────────┐
│  Notification Router                │
└────────────┬────────────────────────┘
             │
    ┌────────┼────────┬─────────┐
    │        │        │         │
┌───▼───┐ ┌─▼──┐ ┌───▼────┐ ┌──▼─────┐
│Desktop│ │Email│ │SMS     │ │Webhook │
│       │ │SMTP │ │Twilio  │ │Zapier  │
└───────┘ └─────┘ └────────┘ └────┬───┘
                                   │
                         ┌─────────┼─────────┐
                         │         │         │
                    ┌────▼───┐ ┌───▼────┐ ┌─▼────┐
                    │Slack   │ │Discord │ │Custom│
                    └────────┘ └────────┘ └──────┘
```

### Notification Severity

**SYNC (Synchronous)**:
- Work pauses until user responds
- Immediate notification via all enabled channels
- Examples: Critical blockers, security decisions, ambiguous requirements

**ASYNC (Asynchronous)**:
- Work continues on other tasks
- Batched/digest notifications
- Examples: Clarifications, preferences, minor decisions

### Configuration

```json
{
  "notifications": {
    "sync_blockers": {
      "enabled": true,
      "channels": ["desktop", "sms", "webhook"],
      "webhook_url": "https://hooks.zapier.com/..."
    },
    "async_blockers": {
      "enabled": true,
      "channels": ["email", "webhook"],
      "batch_interval": 3600
    }
  }
}
```

### MVP Implementation: Zapier Integration

```python
def send_notification(notification: Notification) -> None:
    """Route notification to configured channels."""
    if 'webhook' in notification.channels:
        send_via_zapier(notification)
    if 'desktop' in notification.channels:
        send_desktop_notification(notification)
    # Email/SMS via Zapier for MVP

def send_via_zapier(notification: Notification) -> None:
    payload = {
        'project': notification.project_id,
        'severity': notification.severity,
        'title': notification.title,
        'message': notification.message,
        'action_url': f"http://localhost:8080/blockers/{notification.blocker_id}"
    }
    requests.post(config['zapier_webhook_url'], json=payload)
```

---

## State Persistence & Recovery

### Flash Save System

**Triggers**:
1. Pre-compactification (context >80% of limit)
2. Task completion
3. Manual checkpoint command
4. Scheduled (every 30 minutes during active work)
5. Before pause

**Checkpoint Contents**:
```json
{
  "checkpoint_id": "ckpt_20250115_120000",
  "trigger": "pre_compactification",
  "timestamp": "2025-01-15T12:00:00Z",
  "project_state": {
    "current_phase": "execution",
    "active_tasks": [12, 15, 18],
    "completed_tasks": [1, 2, 3, ...],
    "blocked_tasks": [13]
  },
  "agent_state": {
    "lead": {"status": "working", "context_tokens": 145000},
    "backend": {"status": "working", "current_task": 12}
  },
  "git_commit": "abc123def",
  "db_snapshot": "state_db_backup.db"
}
```

### Recovery Process

```python
def resume_project(project_id: int) -> None:
    checkpoint = load_latest_checkpoint(project_id)

    # 1. Restore database
    restore_db(checkpoint.db_snapshot)

    # 2. Git checkout to checkpoint
    git_checkout(checkpoint.git_commit)

    # 3. Reinitialize agents
    lead_agent = LeadAgent.from_checkpoint(checkpoint.agent_state['lead'])
    workers = [Agent.from_checkpoint(state) for state in checkpoint.agent_state.values()]

    # 4. Resume execution
    lead_agent.continue_execution()
```

### Rollback Capabilities (Post-MVP)

Git-style rollback without extensive implementation:

```bash
# List checkpoints
codeframe checkpoints list

# Rollback to checkpoint
codeframe rollback <checkpoint_id>
```

Simple implementation: Restore DB + git reset to checkpoint commit.

---

## Multi-Provider Support

### Provider Interface

```python
from abc import ABC, abstractmethod

class AgentProvider(ABC):
    @abstractmethod
    def initialize(self, config: dict) -> None:
        """Setup with API keys, etc."""
        pass

    @abstractmethod
    def start_conversation(self, system_prompt: str, context: dict) -> str:
        """Start conversation, return conversation_id."""
        pass

    @abstractmethod
    def send_message(self, conversation_id: str, message: str) -> str:
        """Send message, get response."""
        pass

    @abstractmethod
    def serialize_conversation(self, conversation_id: str) -> dict:
        """Export for checkpoint."""
        pass

    @abstractmethod
    def restore_conversation(self, state: dict) -> str:
        """Restore from checkpoint."""
        pass

    @abstractmethod
    def supports_mcp(self) -> bool:
        """MCP server support?"""
        pass

    @abstractmethod
    def get_token_usage(self, conversation_id: str) -> dict:
        """Return {input_tokens, output_tokens, cost}."""
        pass
```

### MVP Providers

**Claude Provider** (Primary):
- Full MCP server support
- Extended thinking capability
- Hooks support
- Model: claude-sonnet-4 (configurable)

**GPT-4 Provider** (Secondary):
- Function calling support
- No MCP (yet)
- Model: gpt-4-turbo (configurable)

### Provider Selection

```json
{
  "providers": {
    "lead_agent": "claude",
    "backend_agent": "claude",
    "frontend_agent": "gpt4",
    "test_agent": "claude",
    "review_agent": "gpt4"
  }
}
```

### Task Routing Based on Capabilities

```python
def assign_task(task: Task) -> Agent:
    available_agents = get_idle_agents()

    # Tasks requiring MCP → Claude agents only
    if task.requires_mcp:
        return next(a for a in available_agents if a.provider.supports_mcp())

    # Otherwise, assign by maturity + availability
    return max(available_agents, key=lambda a: a.maturity_score())
```

---

## Test Automation

### Supported Frameworks (MVP)

| Language | Framework | Command | Success Pattern |
|----------|-----------|---------|-----------------|
| Python | pytest | `pytest {path} -v --tb=short` | `passed` |
| TypeScript/JavaScript | jest | `npm test -- {path} --verbose` | `PASS` |
| TypeScript/JavaScript | vitest | `npx vitest run {path}` | `Test Files.*passed` |
| Rust | cargo | `cargo test {name}` | `test result: ok` |

### Test Runner Integration

```python
class TestRunner:
    def __init__(self, project_type: str):
        self.config = load_test_config(project_type)

    def run_tests(self, scope: str = "all") -> TestResult:
        cmd = self.config['command'].format(test_path=scope)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        output = result.stdout + result.stderr
        passed = re.search(self.config['success_pattern'], output)
        failed = re.search(self.config['failure_pattern'], output)

        return TestResult(
            success=bool(passed) and not bool(failed),
            output=output,
            failed_tests=extract_failed_tests(output) if failed else []
        )
```

### Self-Correction Loop

```python
def self_correct_cycle(agent: Agent, task: Task, max_attempts: int = 3):
    for attempt in range(max_attempts):
        # 1. Write code
        code_result = agent.execute_task(task)

        # 2. Run tests
        test_result = run_tests(scope=task.files)

        if test_result.success:
            # Archive test output to COLD tier (low importance)
            archive_context_item(test_result.output, importance=0.2)
            return TaskResult(status='completed')
        else:
            # Add failures to HOT context
            add_to_hot_context(f"Test failures: {test_result.failed_tests}", importance=0.9)

            if attempt == max_attempts - 1:
                # Escalate after max attempts
                return TaskResult(
                    status='blocked',
                    blocker=create_blocker(task, test_result)
                )
```

---

## Status Server & UI

### Technology Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React or HTMX (TBD based on complexity)
- **Real-time**: WebSocket for live updates
- **Access**: `localhost:8080` (local) + Tailscale (remote)

### Dashboard Views

**Main Dashboard**:
- Progress bar with task completion percentage
- Phase indicator (Discovery, Planning, Execution, Review, Release)
- Agent status cards (active/idle/blocked)
- Pending questions queue (sync/async)
- Recent activity feed
- Cost/token usage metrics

**Chat Interface**:
- Natural language queries to Lead Agent
- Examples: "How's it going?", "What's blocking?", "Show test results"
- Quick action buttons
- Response with context-aware answers

### API Endpoints

```python
# FastAPI routes
@app.get("/api/status")
async def get_project_status(project_id: int):
    """Return overall project state."""
    pass

@app.get("/api/agents")
async def get_agent_status(project_id: int):
    """Return all agents and their current activity."""
    pass

@app.get("/api/blockers")
async def get_pending_blockers(project_id: int):
    """Return blockers awaiting user input."""
    pass

@app.post("/api/blockers/{blocker_id}/resolve")
async def resolve_blocker(blocker_id: int, resolution: str):
    """User provides answer to blocker."""
    pass

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time updates for dashboard."""
    pass
```

---

## 15-Step Workflow Integration

CodeFRAME implements the full "Vibe Engineering" workflow:

| Step | Phase | Lead Agent Behavior | Worker Agents |
|------|-------|---------------------|---------------|
| 1. Socratic Questioning | Discovery | Runs Socratic dialog | Idle |
| 2. PRD Development | Planning | Drafts PRD, iterates | Idle |
| 3. Story Development | Planning | Breaks PRD into tasks | Idle |
| 4. Technical To-Dos | Planning | Finalizes task queue | Idle |
| 5. Architecture Design | Planning | Collaborates on arch | Idle |
| 6. Test Development | Execution | Assigns test tasks | Test Agent works |
| 7. Coding Deployment | Execution | Assigns code tasks | All agents work |
| 8. Documentation | Execution | Parallel doc tasks | Backend/Frontend |
| 9. Version Control | Continuous | Auto-commit after tasks | All agents |
| 10. CI/Linting | Continuous | Run after commits | Test Agent |
| 11. Code Review | Review | Assigns to Review Agent | Review Agent |
| 12. Manual QA | Review | Deploys preview | User tests |
| 13. Research/Iteration | Adaptive | Spawns research tasks | As needed |
| 14. Release Estimation | Planning | Provides estimates | Idle |
| 15. Deployment | Release | Coordinates deployment | All agents |

---

## Database Schema

### Core Tables

```sql
-- Projects
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT CHECK(status IN ('init', 'planning', 'active', 'paused', 'completed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config JSON
);

-- Tasks (with dependencies)
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed')),
    assigned_to TEXT,
    depends_on TEXT,  -- JSON array of task IDs
    priority INTEGER CHECK(priority BETWEEN 0 AND 4),
    workflow_step INTEGER,
    requires_mcp BOOLEAN DEFAULT FALSE,
    estimated_tokens INTEGER,
    actual_tokens INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Agents
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
    provider TEXT,
    maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
    status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
    current_task_id INTEGER REFERENCES tasks(id),
    last_heartbeat TIMESTAMP,
    metrics JSON  -- {success_rate, blocker_freq, test_pass, etc.}
);

-- Blockers
CREATE TABLE blockers (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    severity TEXT CHECK(severity IN ('sync', 'async')),
    reason TEXT,
    question TEXT,
    resolution TEXT,
    created_at TIMESTAMP,
    resolved_at TIMESTAMP
);

-- Memory
CREATE TABLE memory (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    category TEXT CHECK(category IN ('pattern', 'decision', 'gotcha', 'preference')),
    key TEXT,
    value TEXT,
    created_at TIMESTAMP
);

-- Context Items (Virtual Project)
CREATE TABLE context_items (
    id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    item_type TEXT,
    content TEXT,
    importance_score FLOAT,
    importance_reasoning TEXT,
    created_at TIMESTAMP,
    last_accessed TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    current_tier TEXT CHECK(current_tier IN ('hot', 'warm', 'cold')),
    manual_pin BOOLEAN DEFAULT FALSE
);

-- Context Snapshots
CREATE TABLE context_snapshots (
    id INTEGER PRIMARY KEY,
    agent_id TEXT,
    task_id INTEGER,
    timestamp TIMESTAMP,
    hot_items JSON,
    warm_items JSON,
    token_count INTEGER,
    context_hash TEXT
);

-- Changelog
CREATE TABLE changelog (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    agent_id TEXT,
    task_id INTEGER,
    action TEXT,
    details JSON,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Checkpoints
CREATE TABLE checkpoints (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    trigger TEXT,
    state_snapshot JSON,
    git_commit TEXT,
    db_backup_path TEXT,
    created_at TIMESTAMP
);
```

### Global Memory (Future)

```sql
-- Global patterns across all projects
CREATE TABLE global_memory (
    id INTEGER PRIMARY KEY,
    category TEXT,
    pattern_type TEXT,
    pattern_data JSON,
    usage_count INTEGER DEFAULT 1,
    projects TEXT,  -- JSON array of project IDs
    created_at TIMESTAMP
);
```

---

## API Specifications

### CLI Commands

```bash
# Initialize new project
codeframe init <project-name> [--template <name>]

# Start/resume project
codeframe start [<project-name>]
codeframe resume [<project-name>]

# Pause project
codeframe pause [<project-name>]

# Check status
codeframe status [<project-name>]

# Configuration
codeframe config set <key> <value>
codeframe config get <key>

# Checkpoints
codeframe checkpoint create [--message <msg>]
codeframe checkpoints list

# Agents
codeframe agents list
codeframe agents status <agent-id>
```

### Python API (for programmatic use)

```python
from codeframe import Project, LeadAgent

# Initialize project
project = Project.create("my-app")

# Configure
project.config.set("providers.lead_agent", "claude")
project.config.set("notifications.sync_blockers.channels", ["email", "sms"])

# Start
project.start()

# Query status
status = project.get_status()
print(f"Progress: {status.completion_percentage}%")

# Interact with Lead Agent
lead = project.get_lead_agent()
response = lead.chat("How's it going?")
print(response)
```

---

## MVP Scope & Roadmap

### Phase 1: Core Orchestration (Weeks 1-3)

**Goals**: Single-user, local execution, basic coordination

**Deliverables**:
- [x] Lead Agent with Socratic discovery
- [x] SQLite state management
- [x] Task queue with dependency resolution
- [x] Single worker agent (Backend, Claude)
- [x] Flash save/recovery system
- [x] CLI: `init`, `start`, `pause`, `resume`, `status`

**Excluded from MVP**:
- Multi-user collaboration
- Project templates
- Global memory
- Cost budgets (monitor only, no limits)
- Advanced rollback (basic git reset only)

### Phase 2: Multi-Agent Execution (Weeks 4-5)

**Goals**: Parallel execution, self-correction

**Deliverables**:
- [ ] Frontend + Test worker agents
- [ ] Parallel task execution
- [ ] Git integration (auto-commits)
- [ ] Basic blocker escalation (console for MVP)
- [ ] Test runner integration (Python, TypeScript, Rust)
- [ ] Self-correction loops

### Phase 3: Status Server (Weeks 6-7)

**Goals**: Remote monitoring, chat interface

**Deliverables**:
- [ ] FastAPI backend
- [ ] Web UI dashboard
- [ ] Chat interface with Lead Agent
- [ ] Real-time WebSocket updates
- [ ] Tailscale accessibility setup

### Phase 4: Production Features (Weeks 8-9)

**Goals**: Notifications, metrics, polish

**Deliverables**:
- [ ] Multi-channel notifications (Zapier + desktop)
- [ ] Review Agent
- [ ] Metrics collection (tokens, cost, time)
- [ ] Enhanced context management
- [ ] Documentation

### Post-MVP Enhancements

**Future Versions**:
- Project templates
- Global memory across projects
- Multi-user collaboration
- Cost budgets and limits
- Advanced rollback capabilities
- Additional LLM providers (Gemini, Llama, etc.)
- Additional language support (Java, Go, etc.)
- User-configurable test runners

---

## Configuration Reference

### Project Config (.codeframe/config.json)

```json
{
  "project_name": "my-app",
  "project_type": "python",

  "providers": {
    "lead_agent": "claude",
    "backend_agent": "claude",
    "frontend_agent": "gpt4",
    "test_agent": "claude",
    "review_agent": "gpt4"
  },

  "agent_management": {
    "backend_agent": {
      "maturity_override": null,
      "auto_progression": true
    },
    "global_policy": {
      "require_review_below_maturity": "supporting",
      "allow_full_autonomy": false
    }
  },

  "interruption_mode": {
    "enabled": true,
    "sync_blockers": ["requirement", "security"],
    "async_blockers": ["technical", "external"],
    "auto_continue": true
  },

  "notifications": {
    "sync_blockers": {
      "enabled": true,
      "channels": ["desktop", "sms", "webhook"],
      "webhook_url": "https://hooks.zapier.com/..."
    },
    "async_blockers": {
      "enabled": true,
      "channels": ["email", "webhook"],
      "batch_interval": 3600
    }
  },

  "test_runner": {
    "framework": "pytest",
    "command": "pytest {path} -v",
    "auto_run": true
  },

  "context_management": {
    "hot_tier_max_tokens": 20000,
    "warm_tier_max_tokens": 40000,
    "importance_threshold_hot": 0.8,
    "importance_threshold_warm": 0.4
  },

  "checkpoints": {
    "auto_save_interval": 1800,
    "pre_compactification": true,
    "per_task_completion": true
  }
}
```

### Global Config (~/.codeframe/global_config.json)

```json
{
  "api_keys": {
    "anthropic_api_key": "sk-ant-...",
    "openai_api_key": "sk-...",
    "twilio_account_sid": "...",
    "twilio_auth_token": "..."
  },

  "defaults": {
    "provider": "claude",
    "model": "claude-sonnet-4"
  },

  "user_preferences": {
    "favorite_stack": {
      "backend": "FastAPI",
      "frontend": "Next.js",
      "structure": "monorepo"
    }
  }
}
```

---

## Security & Privacy

### API Key Management

- Store in `~/.codeframe/global_config.json` (chmod 600)
- Never commit to git (.gitignore enforced)
- Support environment variables (`ANTHROPIC_API_KEY`, etc.)

### Data Privacy

- All data stored locally (filesystem + SQLite)
- No data sent to CodeFRAME servers (open-source, self-hosted)
- Provider APIs follow their respective privacy policies

### Network Security

- Status server: localhost by default
- Remote access: Tailscale (encrypted WireGuard tunnel)
- No public internet exposure without explicit configuration

---

## Performance Considerations

### Token Optimization

- Virtual Project context system reduces redundant token usage by 30-50%
- Importance-based tiering keeps context windows lean
- Flash saves prevent context window exhaustion

### Concurrency

- SQLite handles concurrent reads efficiently
- Write operations serialized through Lead Agent
- Worker agents execute tasks in parallel (no inter-agent locking)

### Scalability

- Single project: 40-50 concurrent tasks sustainable
- Multiple projects: Independent SQLite databases
- Status server: WebSocket limits ~100 concurrent connections

---

## Testing Strategy

### Unit Tests

- Test runner abstraction
- Context importance scoring
- Task dependency resolution
- Maturity progression logic

### Integration Tests

- Multi-agent coordination
- Flash save/recovery
- Notification delivery
- Status server API

### E2E Tests

- Full project lifecycle: init → execution → completion
- Blocker escalation and resolution
- Context tier transitions
- Provider switching

---

## Deployment

### Local Installation

```bash
pip install codeframe
codeframe init --setup  # Interactive setup
```

### Dependencies

- Python 3.11+
- SQLite 3.35+
- Git
- Node.js (if using TypeScript/JavaScript projects)

### Optional

- Tailscale (for remote access)
- Zapier account (for notifications)

---

## Contributing

See `CONTRIBUTING.md` for:
- Code style guidelines
- PR process
- Adding new providers
- Adding new language support

---

## License

MIT License (TBD - confirm with project owner)

---

## Appendix

### Glossary

- **Flash Save**: Pre-compactification checkpoint to prevent context loss
- **Virtual Project**: Context management system with hot/warm/cold tiers
- **Lead Agent**: Central orchestrator responsible for coordination
- **Worker Agent**: Specialized agent for specific tasks (backend, frontend, test, review)
- **Blocker**: Task impediment requiring human input
- **Maturity**: Agent skill level (D1-D4) based on Situational Leadership II

### References

- Situational Leadership II: Blanchard, K. H., Zigarmi, D., & Nelson, R. B. (1993)
- React Virtual DOM: https://react.dev/learn/preserving-and-resetting-state
- Claude Code: https://claude.ai/code
- Beads Issue Tracker: https://github.com/steveyegge/beads

---

**Document Version**: 1.0
**Last Updated**: 2025-01-15
**Status**: Initial Specification for MVP Development
