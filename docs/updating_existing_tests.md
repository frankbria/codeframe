# Updating Existing Tests for SDK Migration

## Overview
After migrating agents to use the Claude Agent SDK, existing tests need minor updates to continue working. This document explains the required changes.

## Why Tests Are Failing

The migrated `BackendWorkerAgent` now defaults to `use_sdk=True`, which means:

1. Files are written by the SDK's Write tool, not directly by `apply_file_changes()`
2. Code generation uses SDK message passing, not direct Anthropic API calls
3. The SDK client needs to be mocked or disabled for unit tests

## Solution: Set use_sdk=False for Unit Tests

### Before Migration
```python
def test_apply_file_changes_creates_new_file(tmp_path):
    agent = BackendWorkerAgent(
        project_id=1,
        db=mock_db,
        codebase_index=mock_index,
        project_root=tmp_path  # Path object
    )

    files = [{"path": "src/example.py", "action": "create", "content": "..."}]
    agent.apply_file_changes(files)

    assert (tmp_path / "src" / "example.py").exists()
```

### After Migration
```python
def test_apply_file_changes_creates_new_file(tmp_path):
    agent = BackendWorkerAgent(
        project_id=1,
        db=mock_db,
        codebase_index=mock_index,
        project_root=str(tmp_path),  # String path (SDK compatibility)
        use_sdk=False  # Disable SDK for direct file operation testing
    )

    files = [{"path": "src/example.py", "action": "create", "content": "..."}]
    agent.apply_file_changes(files)

    assert (tmp_path / "src" / "example.py").exists()
```

## Required Changes

### 1. Constructor Updates

**Change Required:**
- Convert `project_root` from Path to str
- Add `use_sdk=False` parameter

**Example:**
```python
# BEFORE
agent = BackendWorkerAgent(
    project_id=1,
    db=db,
    codebase_index=index,
    project_root=tmp_path
)

# AFTER
agent = BackendWorkerAgent(
    project_id=1,
    db=db,
    codebase_index=index,
    project_root=str(tmp_path),
    use_sdk=False
)
```

### 2. Code Generation Tests

Tests that mock Anthropic API responses need `use_sdk=False`:

```python
# BEFORE
with patch("codeframe.agents.backend_worker_agent.AsyncAnthropic") as Mock:
    agent = BackendWorkerAgent(...)
    result = await agent.generate_code(context)

# AFTER
with patch("anthropic.AsyncAnthropic") as Mock:  # Patch at import location
    agent = BackendWorkerAgent(..., use_sdk=False)
    result = await agent.generate_code(context)
```

### 3. File Operation Tests

All tests validating direct file operations need `use_sdk=False`:

```python
def test_apply_file_changes_modifies_existing_file(tmp_path):
    # Create initial file
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.py").write_text("old content")

    # Create agent with SDK disabled
    agent = BackendWorkerAgent(
        project_id=1,
        db=mock_db,
        codebase_index=mock_index,
        project_root=str(tmp_path),
        use_sdk=False  # Required for testing direct file ops
    )

    files = [{"path": "src/example.py", "action": "modify", "content": "new content"}]
    agent.apply_file_changes(files)

    assert (tmp_path / "src" / "example.py").read_text() == "new content"
```

## Batch Update Script

To update all tests in a file, follow this pattern:

### 1. Update Fixtures
```python
# BEFORE
@pytest.fixture
def backend_agent(mock_db, mock_index, tmp_path):
    return BackendWorkerAgent(
        project_id=1,
        db=mock_db,
        codebase_index=mock_index,
        project_root=tmp_path
    )

# AFTER
@pytest.fixture
def backend_agent(mock_db, mock_index, tmp_path):
    return BackendWorkerAgent(
        project_id=1,
        db=mock_db,
        codebase_index=mock_index,
        project_root=str(tmp_path),
        use_sdk=False  # Disable for unit tests
    )
```

### 2. Search and Replace
```bash
# Find all BackendWorkerAgent instantiations
grep -n "BackendWorkerAgent(" tests/agents/test_backend_worker_agent.py

# Update each one:
# 1. Convert project_root to str: project_root=str(tmp_path)
# 2. Add use_sdk=False parameter
```

## When NOT to Use use_sdk=False

### SDK Integration Tests

If you're testing SDK integration specifically, use `use_sdk=True` and mock the SDK client:

```python
def test_agent_uses_sdk_for_file_operations():
    with patch("codeframe.agents.backend_worker_agent.SDKClientWrapper") as MockSDK:
        agent = BackendWorkerAgent(
            project_id=1,
            db=mock_db,
            codebase_index=mock_index,
            project_root="/path/to/project",
            use_sdk=True  # Test SDK integration
        )

        # Verify SDK was initialized
        MockSDK.assert_called_once()
```

## Common Errors and Fixes

### Error 1: "Exception: Command failed with exit code 1"
**Cause:** Test is using SDK mode and SDK is trying to execute tools
**Fix:** Add `use_sdk=False` to agent constructor

### Error 2: "AssertionError: assert 'class User:\n    pass\n' == 'class User:\n    def __init__(self):\n        pass\n'"
**Cause:** File content mismatch because SDK wrote different content than expected
**Fix:** Add `use_sdk=False` or adjust test expectations for SDK output

### Error 3: "Failed: DID NOT RAISE <class 'FileNotFoundError'>"
**Cause:** SDK handles errors differently than direct file operations
**Fix:** Add `use_sdk=False` to test direct error handling

## Testing Both Modes

For comprehensive coverage, create separate test classes:

```python
class TestBackendWorkerAgentDirectMode:
    """Tests using direct file operations (use_sdk=False)"""

    @pytest.fixture
    def agent(self, tmp_path):
        return BackendWorkerAgent(
            project_id=1,
            db=mock_db,
            codebase_index=mock_index,
            project_root=str(tmp_path),
            use_sdk=False
        )

    def test_file_operations(self, agent):
        # Test direct file operations
        ...


class TestBackendWorkerAgentSDKMode:
    """Tests using SDK (use_sdk=True)"""

    @pytest.fixture
    def agent(self, tmp_path):
        with patch("codeframe.agents.backend_worker_agent.SDKClientWrapper"):
            agent = BackendWorkerAgent(
                project_id=1,
                db=mock_db,
                codebase_index=mock_index,
                project_root=str(tmp_path),
                use_sdk=True
            )
            agent.sdk_client = AsyncMock()
            return agent

    def test_sdk_integration(self, agent):
        # Test SDK integration
        ...
```

## Summary of Changes

| Test Type | Required Change |
|-----------|----------------|
| File operations | Add `use_sdk=False` |
| Anthropic API mocks | Add `use_sdk=False` + patch at `anthropic.AsyncAnthropic` |
| Path handling | Convert Path to str: `project_root=str(tmp_path)` |
| SDK integration | Keep `use_sdk=True`, mock `SDKClientWrapper` |

## Files to Update

Based on test failures:

```bash
# Update these test files:
tests/agents/test_backend_worker_agent.py  # 19 failures
tests/agents/test_frontend_worker_agent.py  # After frontend migration
tests/agents/test_test_worker_agent.py  # After test agent migration
```

## Next Steps

1. Update `tests/agents/test_backend_worker_agent.py` fixtures to use `use_sdk=False`
2. Convert all `project_root` parameters to `str(tmp_path)`
3. Run tests to verify all pass
4. Repeat for frontend and test agents after migration
