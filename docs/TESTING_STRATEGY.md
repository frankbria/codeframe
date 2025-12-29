# Testing Strategy for CodeFRAME

This document outlines the testing philosophy, guidelines, and best practices for the CodeFRAME project.

## Testing Philosophy

### Core Principles

1. **Real Implementations Over Mocks**: Prefer testing with real components when possible. Mocking should only be used for external services that are impractical to use in tests.

2. **Mock Boundaries, Not Internals**: Only mock at system boundaries (external APIs, network calls). Never mock internal methods or classes to make tests pass.

3. **Tests Should Fail When Code Breaks**: If removing a function or breaking logic doesn't cause a test to fail, the test is not valuable.

4. **Integration Tests for Workflows**: Test complete workflows with real database and file operations. Unit tests should focus on pure logic.

## Test Categories

### Unit Tests
- **Purpose**: Test individual functions and classes in isolation
- **Mock Policy**: Mock only external I/O (network, external APIs)
- **Location**: `tests/` directory (excluding `tests/integration/`)
- **Run Command**: `pytest -m "not integration"`

**Good Unit Test Example**:
```python
def test_sanitize_prompt_removes_special_chars():
    """Test pure logic - no mocking needed."""
    result = sanitize_prompt_input("Hello <script>alert()</script>")
    assert "<script>" not in result
```

**Bad Unit Test Example**:
```python
@patch("module.execute_task")  # ❌ Mocking the method being tested!
def test_execute_task(mock_execute):
    mock_execute.return_value = {"status": "completed"}
    result = execute_task(task)  # This tests nothing!
    assert result["status"] == "completed"
```

### Integration Tests
- **Purpose**: Test component interactions with real implementations
- **Mock Policy**: Mock only external services (Anthropic API, OpenAI, GitHub)
- **Location**: `tests/integration/`
- **Run Command**: `pytest -m integration`

**Good Integration Test Example**:
```python
@pytest.mark.integration
async def test_token_usage_recorded_in_database(real_db):
    """Uses real database to verify token tracking works."""
    agent = WorkerAgent(db=real_db, agent_id="test-agent")

    # Mock only the external LLM API
    with patch("anthropic.AsyncAnthropic") as mock_api:
        mock_api.return_value.messages.create.return_value = mock_response
        result = await agent.execute_task(task)

    # Verify real database was updated
    cursor = real_db.conn.cursor()
    cursor.execute("SELECT * FROM token_usage WHERE task_id = ?", (task.id,))
    assert cursor.fetchone() is not None
```

### End-to-End Tests (E2E)
- **Purpose**: Test complete user workflows through the UI
- **Mock Policy**: None - tests real system end-to-end
- **Location**: `e2e/` directory
- **Run Command**: `npx playwright test`

## What to Mock (and What Not to Mock)

### ✅ Acceptable to Mock

| Component | Why |
|-----------|-----|
| `AsyncAnthropic` | External API, costs money, rate limited |
| `AsyncOpenAI` | External API, costs money, rate limited |
| `github.Github` | External API, requires auth |
| `requests.get/post` | External network calls |
| `httpx.AsyncClient` | External network calls |
| `subprocess.run` for external tools | Only for CI tools that aren't installed |

### ❌ Never Mock These

| Component | Why |
|-----------|-----|
| `Database` class | Core functionality, use `:memory:` SQLite |
| `execute_task()` | Core agent functionality being tested |
| `apply_file_changes()` | Core file operation logic |
| `QualityGates.run_*_gate()` | Quality enforcement logic |
| Repository classes | Use real in-memory database |
| Internal helper methods | Test through public interface |

## Test Fixtures

### Database Fixtures

```python
# Real in-memory database - use for most integration tests
@pytest.fixture
def real_db():
    db = Database(":memory:")
    db.initialize()
    yield db
    db.conn.close()

# File-backed database - use when testing persistence
@pytest.fixture
def real_db_file(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    db.initialize()
    yield db
    db.conn.close()
```

### LLM Mock Fixtures

```python
@pytest.fixture
def mock_anthropic_api():
    with patch("anthropic.AsyncAnthropic") as mock:
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.content = [Mock(text="Task completed")]
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)
        mock_client.messages.create.return_value = mock_response
        mock.return_value = mock_client
        yield mock_client
```

### Workspace Fixtures

```python
@pytest.fixture
def test_workspace(tmp_path):
    """Real temp directory for file operations."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "tests").mkdir()
    yield workspace
```

## Running Tests

### Quick Commands

```bash
# Run all tests
uv run pytest

# Run only unit tests (fast)
uv run pytest -m "not integration and not slow"

# Run only integration tests
uv run pytest -m integration

# Run tests with coverage
uv run pytest --cov=codeframe --cov-report=html

# Run specific test file
uv run pytest tests/integration/test_worker_agent_execution.py -v

# Run tests matching a pattern
uv run pytest -k "token_usage" -v
```

### CI Configuration

The CI pipeline should run tests in this order:

1. **Lint & Type Check** (fastest)
   ```bash
   ruff check .
   mypy codeframe/
   ```

2. **Unit Tests** (fast, ~30 seconds)
   ```bash
   pytest -m "not integration and not slow and not e2e"
   ```

3. **Integration Tests** (medium, ~2 minutes)
   ```bash
   pytest -m integration
   ```

4. **E2E Tests** (slow, ~5 minutes)
   ```bash
   npx playwright test
   ```

## Writing New Tests

### Test Naming Convention

```python
# Unit test: test_{method_name}_{scenario}
def test_sanitize_prompt_removes_html_tags():
    ...

# Integration test: test_{workflow}_{expected_outcome}
async def test_token_usage_recorded_after_task_execution():
    ...

# E2E test: test_{user_story}
def test_user_can_create_project_and_run_first_task():
    ...
```

### Test Structure (Arrange-Act-Assert)

```python
async def test_example(real_db):
    # Arrange - Setup test data and dependencies
    project_id = real_db.create_project(name="test", ...)
    agent = WorkerAgent(db=real_db, ...)

    # Act - Perform the action being tested
    with patch("anthropic.AsyncAnthropic") as mock_api:
        result = await agent.execute_task(task)

    # Assert - Verify the expected outcome
    assert result["status"] == "completed"
    cursor = real_db.conn.cursor()
    cursor.execute("SELECT * FROM token_usage")
    assert cursor.fetchone() is not None
```

## Audit Tool

Use the test audit script to identify over-mocked tests:

```bash
python scripts/audit_mocked_tests.py
```

This generates a report categorizing tests by mock severity:
- **HIGH**: Tests that mock core functionality (need rewrite)
- **MEDIUM**: Tests with heavy mocking (review needed)
- **LOW**: Acceptable mocking (external services only)

## Coverage Goals

- **Overall**: ≥85% line coverage
- **Core modules** (`agents/`, `lib/`, `persistence/`): ≥90%
- **UI components**: ≥70%

## Troubleshooting

### "Test passes but shouldn't"
- Check if you're mocking the method being tested
- Run the audit script to find over-mocked tests
- Verify the test actually exercises the code path

### "Integration test is flaky"
- Ensure proper cleanup in fixtures
- Check for shared state between tests
- Use isolated database instances per test

### "Test is too slow"
- Move to integration tests if it needs real I/O
- Mock only external calls, not internal logic
- Consider using `pytest-xdist` for parallelization
