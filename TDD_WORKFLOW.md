# TDD Workflow for CodeFRAME Sprint 1

**Philosophy**: Write tests FIRST, then implement to make them pass. No code moves forward without >85% coverage and 100% pass rate.

---

## Quick Reference

### TDD Cycle (Red-Green-Refactor)

```
1. 🔴 RED: Write failing test
2. 🟢 GREEN: Write minimal code to pass
3. 🔵 REFACTOR: Improve code quality
4. 📊 COVERAGE: Verify >85% coverage
5. ✅ COMMIT: Only when all tests pass
```

### Run Tests

```bash
# Run all tests with coverage
pytest tests/ --cov=codeframe --cov-report=term-missing --cov-report=html

# Run specific test file
pytest tests/test_database.py -v

# Run tests with coverage threshold enforcement
pytest tests/ --cov=codeframe --cov-fail-under=85

# Generate HTML coverage report
pytest tests/ --cov=codeframe --cov-report=html
# Open: htmlcov/index.html
```

### Check Coverage for Specific Module

```bash
# Coverage for database module only
pytest tests/test_database.py --cov=codeframe.persistence.database --cov-report=term-missing

# Coverage for config module
pytest tests/test_config.py --cov=codeframe.core.config --cov-report=term-missing
```

---

## Sprint 1 TDD Implementation Plan

### cf-12: Environment & Configuration ✅ COMPLETE
- **Coverage**: Manual tests (system Python limitations)
- **Status**: Syntax validated, comprehensive test suite created
- **Next sprint**: Run with proper venv setup

### cf-8: Database CRUD (NEXT)

**TDD Steps**:

**Step 1: Write Database Tests FIRST** (Red)
```python
# tests/test_database.py

def test_create_project():
    """Test creating a project in database."""
    db = Database()
    project = db.create_project(
        name="test-project",
        project_type="python"
    )
    assert project.id is not None
    assert project.name == "test-project"

def test_get_project():
    """Test retrieving a project by ID."""
    db = Database()
    project = db.create_project(name="test")
    retrieved = db.get_project(project.id)
    assert retrieved.id == project.id

def test_update_project_status():
    """Test updating project status."""
    db = Database()
    project = db.create_project(name="test")
    db.update_project(project.id, {"status": "running"})
    updated = db.get_project(project.id)
    assert updated.status == "running"

def test_list_projects():
    """Test listing all projects."""
    db = Database()
    db.create_project(name="project1")
    db.create_project(name="project2")
    projects = db.list_projects()
    assert len(projects) == 2
```

**Step 2: Run Tests - Should FAIL** (Red)
```bash
pytest tests/test_database.py -v
# Expected: FAILED (methods not implemented yet)
```

**Step 3: Implement CRUD Methods** (Green)
```python
# codeframe/persistence/database.py

def create_project(self, name: str, project_type: str = "python") -> Project:
    """Create a new project."""
    # Implementation here
    pass

def get_project(self, project_id: int) -> Optional[Project]:
    """Get project by ID."""
    # Implementation here
    pass

# ... implement remaining methods
```

**Step 4: Run Tests - Should PASS** (Green)
```bash
pytest tests/test_database.py -v
# Expected: PASSED (all tests green)
```

**Step 5: Check Coverage** (Coverage)
```bash
pytest tests/test_database.py --cov=codeframe.persistence.database --cov-report=term-missing
# Required: >85% coverage
# If < 85%: Add more tests for uncovered lines
```

**Step 6: Refactor & Commit** (Refactor)
```bash
# Only commit when:
# - All tests pass (100%)
# - Coverage >85%
# - Code quality checks pass

git add tests/test_database.py codeframe/persistence/database.py
git commit -m "Implement cf-8.1: Database CRUD methods with TDD

- Tests: 15 test cases, 100% pass rate
- Coverage: 92% (exceeds 85% threshold)
- All CRUD operations tested and working"
```

---

## Test Organization

### File Structure
```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_config.py           # Configuration tests
├── test_database.py         # Database CRUD tests
├── test_lead_agent.py       # Lead Agent tests
├── test_server.py           # Status Server API tests
└── integration/             # End-to-end tests
    └── test_cli_flow.py
```

### Fixture Strategy (conftest.py)
```python
import pytest
from pathlib import Path
import tempfile
from codeframe.persistence.database import Database

@pytest.fixture
def temp_db():
    """Provide a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = Database(db_path)
    db.initialize()

    yield db

    # Cleanup
    db.close()
    db_path.unlink()

@pytest.fixture
def sample_project(temp_db):
    """Create a sample project for testing."""
    return temp_db.create_project(
        name="test-project",
        project_type="python"
    )
```

---

## Coverage Standards

### Minimum Coverage by Module

| Module | Minimum Coverage | Notes |
|--------|-----------------|-------|
| `core/config.py` | 85% | Environment and validation |
| `persistence/database.py` | 90% | Critical data layer |
| `agents/lead_agent.py` | 85% | Core agent logic |
| `core/project.py` | 85% | Project lifecycle |
| `ui/server.py` | 80% | API endpoints |
| `cli.py` | 75% | CLI commands (manual testing supplement) |

### What to Test

**✅ Must Test**:
- All public methods and functions
- Error handling and edge cases
- Data validation and constraints
- Database operations (CRUD)
- API endpoints (status codes, payloads)
- Configuration validation
- State transitions (pending → running → completed)

**⚠️ Test with Care**:
- External API calls (mock with `unittest.mock`)
- File system operations (use temp directories)
- Network operations (mock or use local test server)
- Time-dependent behavior (freeze time with `freezegun`)

**❌ Don't Test**:
- Third-party library internals (trust anthropic, pydantic, etc.)
- Python standard library
- Simple getters/setters with no logic
- `__repr__` and `__str__` (exclude with pragma)

---

## Testing Best Practices

### 1. Arrange-Act-Assert (AAA) Pattern
```python
def test_create_project():
    # ARRANGE: Set up test data
    db = Database()
    project_name = "test-project"

    # ACT: Execute the operation
    project = db.create_project(name=project_name)

    # ASSERT: Verify the result
    assert project.name == project_name
    assert project.id is not None
```

### 2. One Assertion Per Test (when possible)
```python
# Good: Focused test
def test_project_has_id():
    project = db.create_project(name="test")
    assert project.id is not None

def test_project_has_correct_name():
    project = db.create_project(name="test")
    assert project.name == "test"

# Acceptable: Related assertions
def test_project_defaults():
    project = db.create_project(name="test")
    assert project.status == "pending"
    assert project.project_type == "python"
```

### 3. Test Naming Convention
```python
# Format: test_<what>_<condition>_<expected>

def test_create_project_with_valid_data_succeeds():
    """Test that creating a project with valid data succeeds."""
    pass

def test_get_project_with_invalid_id_returns_none():
    """Test that getting a project with invalid ID returns None."""
    pass

def test_update_project_status_with_running_changes_status():
    """Test that updating project status to running changes the status."""
    pass
```

### 4. Mock External Dependencies
```python
from unittest.mock import Mock, patch

def test_lead_agent_calls_anthropic_api():
    """Test that Lead Agent calls Anthropic API."""
    with patch('anthropic.Anthropic') as mock_anthropic:
        mock_client = Mock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = Mock(
            content=[Mock(text="Hello!")]
        )

        agent = LeadAgent(project_id=1)
        response = agent.chat("Hi")

        assert response == "Hello!"
        mock_client.messages.create.assert_called_once()
```

### 5. Use Fixtures for Common Setup
```python
@pytest.fixture
def agent_with_conversation(temp_db, sample_project):
    """Agent with existing conversation history."""
    agent = LeadAgent(sample_project.id)
    agent.chat("Hello")
    agent.chat("What can you do?")
    return agent

def test_conversation_history_persists(agent_with_conversation):
    """Test that conversation history is saved."""
    messages = agent_with_conversation.get_conversation()
    assert len(messages) >= 4  # 2 user + 2 assistant
```

---

## Quality Gates

### Before Committing ANY Code

```bash
# 1. Run all tests
pytest tests/ -v

# 2. Check coverage
pytest tests/ --cov=codeframe --cov-fail-under=85

# 3. Run linter (if available)
ruff check codeframe/

# 4. Run type checker (if available)
mypy codeframe/

# All must pass ✅ before git commit
```

### Pre-Commit Checklist

- [ ] All new code has tests written FIRST
- [ ] All tests pass (100% pass rate)
- [ ] Coverage >85% for modified modules
- [ ] No debugging print statements
- [ ] Code follows project style
- [ ] Docstrings added for public methods
- [ ] CHANGELOG or commit message documents changes

---

## Troubleshooting

### "Coverage below 85%"

**Solution**: Add tests for uncovered lines
```bash
# Find uncovered lines
pytest tests/ --cov=codeframe --cov-report=term-missing

# Shows:
# database.py  87%  45-47, 89

# Add test for lines 45-47 and 89
```

### "Import errors in tests"

**Solution**: Install package in editable mode
```bash
pip install -e ".[dev]"
```

### "Fixture not found"

**Solution**: Check conftest.py exists
```python
# tests/conftest.py should have:
import pytest

@pytest.fixture
def your_fixture():
    return "value"
```

### "Tests too slow"

**Solution**: Use pytest markers
```python
# Mark slow tests
@pytest.mark.slow
def test_large_dataset():
    pass

# Run fast tests only
pytest tests/ -m "not slow"
```

---

## Sprint 1 Testing Goals

**By End of Sprint 1**:
- ✅ >85% coverage for all core modules
- ✅ 100% test pass rate on all platforms
- ✅ Zero manual testing dependencies for core logic
- ✅ Fast test suite (<30 seconds for all tests)
- ✅ Clear test documentation

**Success Metrics**:
```
Tests: 50+ test cases
Coverage: >85% across all modules
Pass Rate: 100%
Execution Time: <30 seconds
```

---

## Example: Complete TDD Cycle for cf-8.1

```bash
# Day 1: Database CRUD

# 1. Write tests FIRST (test_database.py)
# 2. Run tests - FAIL (expected)
pytest tests/test_database.py -v
# FAILED (15 tests, 0 passed)

# 3. Implement methods (database.py)
# 4. Run tests - PASS
pytest tests/test_database.py -v
# PASSED (15 tests, 15 passed)

# 5. Check coverage
pytest tests/test_database.py --cov=codeframe.persistence.database --cov-report=term-missing
# Coverage: 92% (exceeds 85%)

# 6. Commit
git add tests/test_database.py codeframe/persistence/database.py
git commit -m "cf-8.1: Database CRUD with TDD (92% coverage, 100% pass)"
```

---

## Remember

> **"If it's not tested, it's broken."**

Every line of production code should be covered by tests. Write tests FIRST, implement to make them pass, then refactor with confidence.

**No exceptions. No shortcuts. Quality is not negotiable.** ✅
