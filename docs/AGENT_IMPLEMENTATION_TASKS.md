# Agent Implementation Tasks

This document tracks the work needed to replace the stubbed agent execution with a fully functional implementation.

**Goal:** When `codeframe work start <task-id>` runs, an agent should read context, plan an approach, execute code changes, and produce a working implementation.

---

## Current State

**✅ Agent implementation is complete.** The full agent loop is functional via `cf work start <task-id> --execute`.

| Component | Status |
|-----------|--------|
| Workspace/PRD/Tasks CRUD | ✅ Complete |
| Task generation from PRD | ✅ LLM-powered (Anthropic API) |
| Run lifecycle management | ✅ Complete |
| Blocker CRUD | ✅ Complete |
| Verification gates | ✅ Complete |
| Patch/Commit artifacts | ✅ Complete |
| Checkpoints/Summary | ✅ Complete |
| **Agent execution** | ✅ Complete |

---

## Implementation Tasks

### 1. LLM Adapter Interface ✅

**File:** `codeframe/adapters/llm/` (base.py, anthropic.py, mock.py)

Create an abstract interface for LLM providers to decouple agent logic from specific APIs.

- [x] Define `LLMProvider` protocol/abstract class
- [x] Implement `AnthropicProvider` (extract from tasks.py)
- [x] Add configuration for model selection (task-based heuristic via Purpose enum)
- [x] Support streaming responses for long-running operations
- [x] Add token counting and context window management

**Design considerations:**
- Should support tool use / function calling for structured outputs
- Needs retry logic with exponential backoff
- Consider rate limiting for API calls

---

### 2. Task Context Loader ✅

**File:** `codeframe/core/context.py`

Build context for the agent by loading relevant information about the task and codebase.

- [x] Load PRD content associated with the task
- [x] Load task title, description, and any previous attempts
- [x] Analyze codebase structure (file tree, key files)
- [x] Identify relevant files based on task description
- [x] Build a context window that fits model limits
- [x] Support incremental context loading for large codebases

**Context sources:**
- PRD content
- Task metadata
- Codebase file tree
- Relevant source files (by keyword/semantic match)
- Previous blockers and their answers
- Previous run attempts (if any)

---

### 3. Agent Planning Step ✅

**File:** `codeframe/core/planner.py`

Transform a task into an executable implementation plan.

- [x] Generate implementation plan from task + context
- [x] Decompose into discrete steps (file edits, commands, etc.)
- [x] Identify files that need to be created/modified
- [x] Estimate complexity and potential blockers
- [x] Store plan in state for resume capability

**Plan structure:**
```python
@dataclass
class ImplementationPlan:
    task_id: str
    steps: list[PlanStep]
    files_to_modify: list[str]
    files_to_create: list[str]
    estimated_complexity: str  # low/medium/high
```

---

### 4. Code Execution Engine ✅

**File:** `codeframe/core/executor.py`

Execute planned steps by making actual changes to the codebase.

- [x] File read operations (with content caching)
- [x] File write/edit operations (with diff tracking)
- [x] Shell command execution (sandboxed, with timeout)
- [ ] Git operations (stage, diff, branch management) - deferred to patch/commit commands
- [x] Rollback capability for failed operations
- [x] Emit events for each operation

**Security considerations:**
- Sandbox shell commands (no network access, limited paths)
- Require confirmation for destructive operations
- Log all file modifications for audit

---

### 5. Automatic Blocker Detection ✅

**File:** Integrated into `codeframe/core/agent.py`

Detect when the agent is stuck and needs human input.

- [x] Detect repeated failures on same step
- [x] Detect missing information (unclear requirements)
- [x] Detect ambiguous choices requiring human decision
- [x] Detect external dependencies (API keys, services)
- [x] Auto-create blocker with relevant context
- [x] Pause run and transition to BLOCKED state

**Blocker triggers:**
- 3+ failed attempts at same operation
- LLM explicitly requests clarification
- Missing environment variables or credentials
- Test failures that can't be auto-fixed

---

### 6. Gate Integration in Agent Loop ✅

**File:** Integrated into `codeframe/core/agent.py`

Integrate verification gates into the agent execution loop.

- [x] Run gates after each significant change
- [x] Fail fast on broken tests/lint
- [x] Attempt auto-fix for lint issues (ruff --fix)
- [x] Create blocker if tests fail repeatedly
- [x] Track gate results in run state

**Gate strategy:**
- After file modifications: run ruff (fast feedback)
- After completing a logical step: run pytest on affected tests
- Before marking complete: full gate run

---

### 7. Agent Orchestrator ✅

**File:** `codeframe/core/agent.py`

Main orchestration loop that coordinates all components.

- [x] Initialize agent with task context
- [x] Execute planning step
- [x] Loop through plan steps with execution engine
- [x] Handle errors and blocker detection
- [x] Integrate gate verification
- [x] Support pause/resume across sessions
- [x] Emit structured events throughout

**Orchestration flow:**
```
1. Load context (task, PRD, codebase)
2. Generate plan
3. For each step:
   a. Execute step
   b. Run relevant gates
   c. Check for blockers
   d. Emit progress events
4. On completion: run full gates
5. Mark task DONE or BLOCKED
```

---

### 8. Wire into Runtime ✅

**File:** Updated `codeframe/core/runtime.py`

Replace `execute_stub()` with the real agent orchestrator.

- [x] Import and instantiate agent orchestrator
- [x] Pass workspace, run, and task to agent
- [x] Handle agent completion/failure
- [x] Support resume from checkpoint
- [x] Clean up on stop/cancel

---

## Testing Strategy

Each component needs:
- Unit tests with mocked LLM responses
- Integration tests with real (small) codebases
- End-to-end test: PRD → tasks → agent → committed code

**Test fixtures:**
- Sample PRDs with known expected tasks
- Small test repos for agent to modify
- Mock LLM responses for deterministic testing

---

## Implementation Order

Recommended sequence:

1. **LLM Adapter** - Foundation for all agent operations
2. **Context Loader** - Needed before planning can work
3. **Planner** - Enables structured execution
4. **Executor** - Core file/command operations
5. **Orchestrator** - Ties everything together
6. **Blocker Detection** - Human-in-loop handling
7. **Gate Integration** - Quality enforcement
8. **Wire to Runtime** - Final integration

---

## Design Decisions

### Model Selection Strategy

**Approach:** Task-based heuristic with future per-task override.

**Current (heuristic):**
- Planning/complex reasoning → Opus or Sonnet
- Code execution/editing → Sonnet
- Simple generation → Haiku

**Future:** `cf tasks set provider <id> <provider>` to override heuristic per-task.

```python
class ModelSelector:
    def for_planning(self) -> str:      # complex reasoning
    def for_execution(self) -> str:     # balanced
    def for_generation(self) -> str:    # fast/cheap
```

---

## Open Questions

- **Sandboxing:** How strict should command execution be?
- **Context limits:** How to handle codebases larger than context window?
- **Parallelism:** Should agent work on multiple files simultaneously?
- **Recovery:** How to resume after crash mid-execution?

---

## References

- `docs/GOLDEN_PATH.md` - Defines the end-to-end flow
- `docs/CLI_WIREFRAME.md` - Command structure
- `codeframe/core/runtime.py:execute_stub()` - Current placeholder
- `codeframe/core/tasks.py:_generate_tasks_with_llm()` - Existing LLM usage
