# Worker Agent Interface Contract

## Overview

All worker agents in CodeFRAME implement a common interface for task execution. This contract defines the methods and behaviors that all specialized agents (Backend, Frontend, Test) must implement.

**Base Class:** `WorkerAgent` (`/home/frankbria/projects/codeframe/codeframe/agents/worker_agent.py`)

---

## Interface: WorkerAgent

### Base Constructor

```python
def __init__(
    agent_id: str,
    agent_type: str,
    provider: str,
    maturity: AgentMaturity = AgentMaturity.D1,
    system_prompt: str | None = None
)
```

**Parameters:**
- `agent_id` (str): Unique agent identifier (e.g., "backend-worker-001")
- `agent_type` (str): Agent specialization ("backend", "frontend", "test")
- `provider` (str): LLM provider ("anthropic", "openai", etc.)
- `maturity` (AgentMaturity, default=D1): Agent maturity level (D1-D4, P1-P4)
- `system_prompt` (Optional[str]): Custom system prompt for LLM

**State:**
- `current_task: Task | None`: Currently executing task (or None if idle)

---

## Required Methods

### execute_task

```python
async def execute_task(task: Task, project_id: int = 1) -> Dict[str, Any]
```

**Purpose:** Execute a single task end-to-end. This is the main entry point for task execution.

**Parameters:**
- `task` (Task): Task object with:
  - `id` (int): Task ID
  - `title` (str): Task title
  - `description` (str): Task description (may contain JSON spec)
  - `status` (str): Current status
  - `assigned_to` (str): Agent type assigned
  - Additional fields (priority, workflow_step, etc.)
- `project_id` (int, default=1): Project ID for WebSocket broadcasts

**Returns:**
Dictionary with execution result:
```python
{
    "status": str,          # "completed" | "failed" | "blocked"
    "output": str,          # Human-readable output/summary
    "error": Optional[str], # Error message if failed
    # Agent-specific fields:
    "files_modified": List[str],      # BackendWorkerAgent
    "files_created": Dict[str, str],  # FrontendWorkerAgent
    "test_results": Dict[str, Any]    # TestWorkerAgent
}
```

**Behavior:**
1. Set `self.current_task = task`
2. Broadcast `task_status_changed` → "in_progress" (via WebSocket)
3. Parse task description to extract specifications
4. Execute agent-specific logic (see specializations below)
5. Broadcast `task_status_changed` → "completed" or "failed"
6. Return execution result

**Error Handling:**
- Must catch all exceptions and return `{"status": "failed", "error": str(e)}`
- Must broadcast failure status before returning

**Thread Safety:** Async-safe (uses async/await pattern as of Sprint 5)

---

### get_capabilities (Optional)

```python
def get_capabilities() -> List[str]
```

**Purpose:** Return list of task types this agent can handle. Used by task routing/assignment logic.

**Returns:**
List of capability strings (agent-specific):

**Backend Agent:**
```python
[
    "api-endpoint",
    "model-creation",
    "database-migration",
    "business-logic",
    "data-validation",
    "error-handling"
]
```

**Frontend Agent:**
```python
[
    "component",
    "ui-styling",
    "state-management",
    "routing",
    "form-handling",
    "api-integration"
]
```

**Test Agent:**
```python
[
    "unit-test",
    "integration-test",
    "e2e-test",
    "test-fixtures",
    "mocking",
    "test-coverage"
]
```

**Note:** This method is currently optional. Future versions may make it required for advanced task routing.

---

## Specialized Implementations

### BackendWorkerAgent

**File:** `/home/frankbria/projects/codeframe/codeframe/agents/backend_worker_agent.py`

**Constructor:**
```python
def __init__(
    project_id: int,
    db: Database,
    codebase_index: CodebaseIndex,
    provider: str = "anthropic",
    api_key: Optional[str] = None,
    project_root: Path = Path("."),
    ws_manager = None
)
```

**Unique Features:**
- Context building from codebase index
- LLM code generation (Anthropic Claude API)
- File operations (create/modify/delete)
- Test execution (`_run_and_record_tests`)
- Self-correction loop (`_self_correction_loop`, up to 3 attempts)

**execute_task Flow:**
1. Update task status → "in_progress"
2. Build context from codebase (`build_context`)
3. Generate code via LLM (`generate_code`)
4. Apply file changes (`apply_file_changes`)
5. Run tests (`_run_and_record_tests`)
6. If tests fail, run self-correction loop (up to 3 attempts)
7. Update status → "completed" or "blocked"

**Returns:**
```python
{
    "status": "completed" | "failed" | "blocked",
    "files_modified": List[str],
    "output": str,
    "error": Optional[str]
}
```

---

### FrontendWorkerAgent

**File:** `/home/frankbria/projects/codeframe/codeframe/agents/frontend_worker_agent.py`

**Constructor:**
```python
def __init__(
    agent_id: str,
    provider: str = "anthropic",
    maturity: AgentMaturity = AgentMaturity.D1,
    api_key: Optional[str] = None,
    websocket_manager=None
)
```

**Unique Features:**
- React component generation (functional components + TypeScript)
- Tailwind CSS styling
- Component file creation in `web-ui/src/components/`
- Auto-update imports/exports in `index.ts`

**execute_task Flow:**
1. Parse task description → component spec (JSON or plain text)
2. Generate React component via LLM (`_generate_react_component`)
3. Generate TypeScript types if needed
4. Create component files (`_create_component_files`)
5. Update imports/exports (`_update_imports_exports`)

**Returns:**
```python
{
    "status": "completed" | "failed",
    "output": str,
    "files_created": {
        "component": str,  # Path to .tsx file
        "types": str       # Optional path to .types.ts file
    },
    "component_name": str,
    "error": Optional[str]
}
```

---

### TestWorkerAgent

**File:** `/home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py`

**Constructor:**
```python
def __init__(
    agent_id: str,
    provider: str = "anthropic",
    maturity: AgentMaturity = AgentMaturity.D1,
    api_key: Optional[str] = None,
    websocket_manager=None,
    max_correction_attempts: int = 3
)
```

**Unique Features:**
- pytest test generation
- Code analysis (target file parsing)
- Test execution via subprocess
- Self-correction loop (up to 3 attempts)

**execute_task Flow:**
1. Parse task description → test spec (target file, test name)
2. Analyze target code (`_analyze_target_code`)
3. Generate pytest tests via LLM (`_generate_pytest_tests`)
4. Create test file in `tests/` directory
5. Execute tests and self-correct if needed (`_execute_and_correct_tests`)

**Returns:**
```python
{
    "status": "completed" | "failed",
    "output": str,
    "test_file": str,
    "test_results": {
        "passed": bool,
        "attempts": int,
        "passed_count": int,
        "failed_count": int,
        "errors_count": int,
        "total_count": int,
        "output": str
    },
    "error": Optional[str]
}
```

---

## Common Patterns

### Task Description Parsing

All agents parse task descriptions to extract specifications:

1. **Try JSON parse first:**
   ```python
   try:
       spec = json.loads(task.description)
   except (json.JSONDecodeError, TypeError):
       # Fall back to plain text parsing
   ```

2. **Fallback to plain text heuristics:**
   - Regex patterns for common keywords
   - Line-by-line scanning
   - Default values for missing fields

### LLM Integration

All agents use **AsyncAnthropic** client (Sprint 5):

```python
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=self.api_key)

response = await client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=2000-4000,
    messages=[{"role": "user", "content": prompt}]
)

code = response.content[0].text
```

**Model:** `claude-3-5-sonnet-20241022` (BackendWorkerAgent uses `claude-sonnet-4-20250514`)

### WebSocket Broadcasts

All agents broadcast task status changes (if `websocket_manager` available):

```python
from codeframe.ui.websocket_broadcasts import broadcast_task_status

await broadcast_task_status(
    self.websocket_manager,
    project_id,
    task.id,
    "in_progress" | "completed" | "failed",
    agent_id=self.agent_id,
    progress=0-100  # Optional
)
```

---

## Error Handling Contract

### All agents MUST:

1. **Catch all exceptions** in `execute_task`:
   ```python
   try:
       # Task execution logic
   except Exception as e:
       logger.error(f"Agent {self.agent_id} failed task {task.id}: {e}")
       return {"status": "failed", "error": str(e)}
   ```

2. **Broadcast failure status** before returning
3. **Never raise unhandled exceptions** from `execute_task`
4. **Return structured result** (always include `status` field)

---

## Testing Interface

All worker agents should be testable with:

```python
# Create agent
agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index)

# Create task
task = Task(
    id=1,
    title="Create API endpoint",
    description="...",
    status="pending",
    assigned_to="backend-worker"
)

# Execute
result = await agent.execute_task(task, project_id=1)

# Verify
assert result["status"] == "completed"
assert "files_modified" in result
```

---

## Sprint Context

**Sprint 4 (cf-24):** Multi-Agent Coordination
**Sprint 5 (cf-48):** Async Migration (async/await pattern)

**Dependencies:**
- Database (cf-8)
- CodebaseIndex (cf-32)
- WebSocket Broadcasts (cf-45)
- Anthropic Claude API

**Related Specs:**
- [Agent Pool API](./agent-pool-api.md)
- [WebSocket Events](./websocket-events.md)
