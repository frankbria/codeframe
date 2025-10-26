# Worker Agents API Reference

## Overview

Worker agents are specialized agents that execute specific types of tasks. CodeFRAME provides three worker agent types:
- **BackendWorkerAgent**: Backend code generation (Python APIs, database models)
- **FrontendWorkerAgent**: Frontend code generation (React components, TypeScript)
- **TestWorkerAgent**: Test generation and execution (pytest)

All worker agents extend the base `WorkerAgent` class and share common interfaces.

## FrontendWorkerAgent

**Module**: `codeframe.agents.frontend_worker_agent`

**Purpose**: Generate React components and TypeScript code for frontend tasks.

### Constructor

```python
def __init__(
    self,
    agent_id: str,
    provider: str = "anthropic",
    maturity: AgentMaturity = AgentMaturity.D1,
    api_key: Optional[str] = None,
    websocket_manager=None
)
```

**Parameters**:
- `agent_id` (str): Unique identifier for this agent
- `provider` (str): AI provider ("anthropic" or "openai")
- `maturity` (AgentMaturity): Maturity level (D1-D4)
- `api_key` (str, optional): API key for AI provider
- `websocket_manager` (optional): WebSocket manager for status broadcasts

**Example**:
```python
from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent

agent = FrontendWorkerAgent(
    agent_id="frontend-001",
    provider="anthropic"
)
```

### execute_task(task)

Execute a frontend development task.

```python
def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]
```

**Parameters**:
- `task` (dict): Task specification with keys:
  - `title` (str): Task title
  - `description` (str): Component specification
  - `id` (int): Task ID

**Returns**:
- `dict`: Execution result with keys:
  - `status` (str): "completed" or "failed"
  - `files_modified` (list): List of created/modified file paths
  - `output` (str): Component code generated
  - `error` (str, optional): Error message if failed

**Example**:
```python
task = {
    "id": 1,
    "title": "UserProfile Component",
    "description": "Create React component to display user profile with avatar, name, and bio"
}

result = agent.execute_task(task)
print(f"Status: {result['status']}")
print(f"Files: {result['files_modified']}")
```

### Supported Components

- **Function Components**: Stateless and stateful
- **TypeScript Types**: Interfaces, types, enums
- **Tailwind CSS**: Styled components
- **React Hooks**: useState, useEffect, custom hooks
- **Form Components**: Input, textarea, select elements
- **Data Display**: Tables, lists, cards
- **Navigation**: Links, menus, breadcrumbs

**Example Task Descriptions**:
```python
# Simple component
"Create a Button component with primary/secondary variants"

# Complex component
"Create a UserTable component with sorting, filtering, and pagination"

# TypeScript types
"Create TypeScript interfaces for User, Post, and Comment models"
```

## TestWorkerAgent

**Module**: `codeframe.agents.test_worker_agent`

**Purpose**: Generate and execute pytest test cases with self-correction loop.

### Constructor

```python
def __init__(
    self,
    agent_id: str,
    provider: str = "anthropic",
    maturity: AgentMaturity = AgentMaturity.D1,
    api_key: Optional[str] = None,
    websocket_manager=None,
    max_correction_attempts: int = 3
)
```

**Parameters**:
- `agent_id` (str): Unique identifier for this agent
- `provider` (str): AI provider ("anthropic" or "openai")
- `maturity` (AgentMaturity): Maturity level (D1-D4)
- `api_key` (str, optional): API key for AI provider
- `websocket_manager` (optional): WebSocket manager for status broadcasts
- `max_correction_attempts` (int): Maximum self-correction attempts (default: 3)

**Example**:
```python
from codeframe.agents.test_worker_agent import TestWorkerAgent

agent = TestWorkerAgent(
    agent_id="test-001",
    max_correction_attempts=3
)
```

### execute_task(task)

Execute a test generation task with self-correction.

```python
def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]
```

**Parameters**:
- `task` (dict): Task specification with keys:
  - `title` (str): Task title
  - `description` (str): Test requirements
  - `id` (int): Task ID

**Returns**:
- `dict`: Execution result with keys:
  - `status` (str): "completed" or "failed"
  - `files_modified` (list): List of test files created
  - `output` (str): Test execution results
  - `test_results` (dict): Detailed test metrics
    - `passed` (int): Number of tests passed
    - `failed` (int): Number of tests failed
    - `total` (int): Total tests executed
  - `error` (str, optional): Error message if failed
  - `correction_attempts` (int): Number of self-corrections made

**Example**:
```python
task = {
    "id": 1,
    "title": "Test UserService",
    "description": "Create unit tests for UserService class covering create, read, update, delete operations"
}

result = agent.execute_task(task)
print(f"Status: {result['status']}")
print(f"Tests: {result['test_results']['passed']}/{result['test_results']['total']} passed")
print(f"Corrections: {result['correction_attempts']}")
```

### Self-Correction Loop

The TestWorkerAgent includes an automatic self-correction loop:

1. **Generate Tests**: Creates pytest test code
2. **Execute Tests**: Runs tests with pytest
3. **Analyze Failures**: If tests fail, analyzes error messages
4. **Fix Tests**: Generates corrected test code
5. **Retry**: Re-executes (max 3 attempts)

**Example**:
```python
# Agent automatically corrects failing tests
result = agent.execute_task(task)

# After self-correction:
# correction_attempts: 2
# test_results: {"passed": 10, "failed": 0, "total": 10}
```

### Supported Test Types

- **Unit Tests**: Function and class testing
- **Parametrized Tests**: Using `@pytest.mark.parametrize`
- **Fixtures**: Setup and teardown
- **Mocking**: Using `unittest.mock`
- **Async Tests**: Using `@pytest.mark.asyncio`
- **Exception Tests**: Using `pytest.raises`

**Example Task Descriptions**:
```python
# Basic unit tests
"Create unit tests for calculate_total() function"

# Parametrized tests
"Create parametrized tests for validate_email() with valid and invalid cases"

# Integration tests
"Create integration tests for API endpoints /users/create and /users/list"
```

## BackendWorkerAgent

**Module**: `codeframe.agents.backend_worker_agent`

**Purpose**: Generate backend code (Python APIs, database models, business logic).

### Constructor

```python
def __init__(
    self,
    project_id: int,
    db: Database,
    codebase_index=None,
    provider: str = "anthropic",
    api_key: Optional[str] = None
)
```

**Parameters**:
- `project_id` (int): Project ID
- `db` (Database): Database instance
- `codebase_index` (optional): Codebase index for context
- `provider` (str): AI provider ("anthropic" or "openai")
- `api_key` (str, optional): API key for AI provider

**Example**:
```python
from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.persistence.database import Database

db = Database("codeframe.db")
db.initialize()

agent = BackendWorkerAgent(
    project_id=1,
    db=db,
    provider="anthropic"
)
```

### execute_task(task)

Execute a backend development task.

```python
def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]
```

**Parameters**:
- `task` (dict): Task specification

**Returns**:
- `dict`: Execution result (same structure as FrontendWorkerAgent)

**Example**:
```python
task = {
    "id": 1,
    "title": "User API",
    "description": "Create FastAPI endpoint for user CRUD operations"
}

result = agent.execute_task(task)
```

### Supported Backend Features

- **API Endpoints**: FastAPI routes and handlers
- **Database Models**: SQLAlchemy models
- **Business Logic**: Service classes and functions
- **Data Validation**: Pydantic schemas
- **Authentication**: JWT, OAuth integration
- **Database Queries**: CRUD operations

## Common Patterns

### Error Handling

All agents follow consistent error handling:

```python
try:
    result = agent.execute_task(task)
    if result['status'] == 'completed':
        print(f"Success! Files: {result['files_modified']}")
    else:
        print(f"Failed: {result['error']}")
except Exception as e:
    print(f"Agent error: {e}")
```

### Result Structure

All agents return consistent result structure:

```python
{
    "status": "completed",  # or "failed"
    "files_modified": ["path/to/file1.py", "path/to/file2.tsx"],
    "output": "Generated code or execution output",
    "error": None,  # or error message string
    "test_results": {  # TestWorkerAgent only
        "passed": 10,
        "failed": 0,
        "total": 10
    },
    "correction_attempts": 2  # TestWorkerAgent only
}
```

### WebSocket Broadcasting

Agents broadcast status updates when `websocket_manager` provided:

```python
agent = FrontendWorkerAgent(
    agent_id="frontend-001",
    websocket_manager=ws_manager
)

# Broadcasts these events automatically:
# - task_started: When task execution begins
# - task_completed: When task finishes successfully
# - task_failed: When task fails
```

## Best Practices

### Task Description Guidelines

**Good task descriptions**:
- Clear and specific
- Include component/API requirements
- Specify data models or types
- Mention styling framework (Tailwind)

**Examples**:
```python
# Good
"Create a UserCard component with avatar, name, email, and role. Use Tailwind CSS."

# Better
"Create a UserCard component that displays:
- User avatar (circular, 48px)
- Full name (bold, 16px)
- Email (gray, 14px)
- Role badge (colored by role: admin=red, user=blue)
Style with Tailwind CSS. Make it responsive."
```

### Agent Selection

Choose the right agent type for each task:

- **Frontend**: UI components, TypeScript types, client-side logic
- **Backend**: APIs, database models, server-side business logic
- **Test**: Unit tests, integration tests, test fixtures

### Performance Optimization

1. **Reuse agents**: Don't create new agent for each task
2. **Batch similar tasks**: Group tasks by type for same agent
3. **Parallel execution**: Run multiple agents concurrently
4. **Cache results**: Store generated code to avoid regeneration

```python
# Good - reuse agent
agent = FrontendWorkerAgent(agent_id="frontend-001")
for task in frontend_tasks:
    result = agent.execute_task(task)

# Bad - creates new agent each time
for task in frontend_tasks:
    agent = FrontendWorkerAgent(agent_id=f"frontend-{task.id}")
    result = agent.execute_task(task)
```

## Testing Worker Agents

### Unit Testing

```python
from unittest.mock import Mock, patch
from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent

def test_frontend_agent():
    agent = FrontendWorkerAgent(agent_id="test-001")

    task = {
        "id": 1,
        "title": "Button Component",
        "description": "Create a Button component"
    }

    with patch('anthropic.Client') as mock_client:
        mock_client.return_value.messages.create.return_value.content = "component code"

        result = agent.execute_task(task)

        assert result['status'] == 'completed'
        assert len(result['files_modified']) > 0
```

### Integration Testing

```python
import pytest
from codeframe.agents.test_worker_agent import TestWorkerAgent

@pytest.mark.asyncio
async def test_test_agent_integration():
    agent = TestWorkerAgent(
        agent_id="test-001",
        max_correction_attempts=3
    )

    task = {
        "id": 1,
        "title": "Test Calculator",
        "description": "Create tests for add() and subtract() functions"
    }

    result = agent.execute_task(task)

    assert result['status'] == 'completed'
    assert result['test_results']['total'] > 0
    assert result['correction_attempts'] <= 3
```

## Troubleshooting

### Agent Creation Fails

**Symptom**: Agent constructor raises exception

**Causes**:
- Invalid API key
- Missing provider parameter
- Network connectivity issues

**Solution**:
```python
try:
    agent = FrontendWorkerAgent(agent_id="frontend-001")
except Exception as e:
    print(f"Agent creation failed: {e}")
    # Check API key, network, provider
```

### Task Execution Fails

**Symptom**: `execute_task()` returns `status: "failed"`

**Causes**:
- Vague task description
- Missing context/requirements
- API rate limits
- Invalid specifications

**Solution**:
```python
result = agent.execute_task(task)
if result['status'] == 'failed':
    print(f"Task failed: {result['error']}")
    # Review task description
    # Check API limits
    # Verify specifications
```

### Self-Correction Loop Exhausted

**Symptom**: TestWorkerAgent fails after 3 correction attempts

**Causes**:
- Invalid test specifications
- Incorrect target code
- Unsolvable test requirements

**Solution**:
```python
result = agent.execute_task(task)
if result['correction_attempts'] >= 3:
    print("Max corrections reached")
    print(f"Test results: {result['test_results']}")
    # Review test requirements
    # Check target code correctness
    # Simplify test specifications
```

## See Also

- [AgentPoolManager API](./agent_pool_manager.md)
- [DependencyResolver API](./dependency_resolver.md)
- [LeadAgent API](./lead_agent.md)
- [Multi-Agent Execution Guide](../user/multi-agent-guide.md)
