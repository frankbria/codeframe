"""Unit tests for SDK Tool Hooks (Task 2.1a).

Tests cover:
- Pre-tool hooks blocking protected file writes
- Pre-tool hooks blocking dangerous bash commands
- Pre-tool hooks allowing safe operations
- Post-tool hooks recording metrics
- Post-tool hooks detecting errors
- Hook builder creating correct structure
- Fallback validation for hook reliability issues
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from codeframe.lib.sdk_hooks import (
    create_quality_gate_pre_hook,
    create_metrics_post_hook,
    build_codeframe_hooks,
    validate_tool_safety_fallback,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Mock database instance."""
    return Mock()


@pytest.fixture
def mock_metrics_tracker():
    """Mock MetricsTracker instance."""
    tracker = Mock()
    tracker.record_token_usage = AsyncMock()
    return tracker


@pytest.fixture
def mock_quality_gates():
    """Mock QualityGates instance."""
    gates = Mock()
    gates.run_all_gates = AsyncMock()
    return gates


@pytest.fixture
def pre_hook():
    """Create pre-tool hook for testing."""
    return create_quality_gate_pre_hook()


@pytest.fixture
def post_hook(mock_db, mock_metrics_tracker):
    """Create post-tool hook for testing."""
    return create_metrics_post_hook(db=mock_db, metrics_tracker=mock_metrics_tracker)


# ============================================================================
# Pre-Tool Hook Tests - Protected File Blocking
# ============================================================================

@pytest.mark.asyncio
async def test_pre_hook_blocks_env_file(pre_hook):
    """Test that pre-hook blocks writes to .env files."""
    input_data = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/app/.env"},
    }

    result = await pre_hook(input_data, "test-123", None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert ".env" in result["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.asyncio
async def test_pre_hook_blocks_env_variants(pre_hook):
    """Test blocking of .env.local, .env.production, etc."""
    test_cases = [
        "/app/.env.local",
        "/app/.env.production",
        "/app/.env.test",
        "/config/.env.development",
    ]

    for file_path in test_cases:
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert "hookSpecificOutput" in result, f"Failed for {file_path}"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_pre_hook_blocks_credentials_json(pre_hook):
    """Test that pre-hook blocks writes to credentials.json."""
    input_data = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/config/credentials.json"},
    }

    result = await pre_hook(input_data, "test-123", None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "credentials.json" in result["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.asyncio
async def test_pre_hook_blocks_secrets_yaml(pre_hook):
    """Test blocking of secrets.yaml and secrets.yml."""
    test_cases = [
        "/app/secrets.yaml",
        "/app/secrets.yml",
    ]

    for file_path in test_cases:
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_pre_hook_blocks_private_keys(pre_hook):
    """Test blocking of .pem, .key files."""
    test_cases = [
        "/app/cert.pem",
        "/app/private.key",
        "/app/id_rsa",
        "/app/id_dsa",
    ]

    for file_path in test_cases:
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert "hookSpecificOutput" in result, f"Failed for {file_path}"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_pre_hook_blocks_git_directory(pre_hook):
    """Test blocking of .git/ internals."""
    input_data = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/app/.git/HEAD"},
    }

    result = await pre_hook(input_data, "test-123", None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ============================================================================
# Pre-Tool Hook Tests - Dangerous Bash Commands
# ============================================================================

@pytest.mark.asyncio
async def test_pre_hook_blocks_rm_rf_root(pre_hook):
    """Test that pre-hook blocks 'rm -rf /' command."""
    input_data = {
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /"},
    }

    result = await pre_hook(input_data, "test-123", None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "dangerous" in result["hookSpecificOutput"]["permissionDecisionReason"].lower()


@pytest.mark.asyncio
async def test_pre_hook_blocks_fork_bomb(pre_hook):
    """Test blocking of fork bomb command."""
    input_data = {
        "tool_name": "Bash",
        "tool_input": {"command": ":(){ :|:& };:"},
    }

    result = await pre_hook(input_data, "test-123", None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_pre_hook_blocks_disk_wipe(pre_hook):
    """Test blocking of dd disk wipe commands."""
    test_cases = [
        "dd if=/dev/zero of=/dev/sda",
        "dd if=/dev/zero of=/dev/nvme0n1",
    ]

    for command in test_cases:
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert "hookSpecificOutput" in result, f"Failed for {command}"
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_pre_hook_blocks_filesystem_format(pre_hook):
    """Test blocking of mkfs commands."""
    test_cases = [
        "mkfs.ext4 /dev/sda1",
        "mkfs.ntfs /dev/sdb1",
    ]

    for command in test_cases:
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_pre_hook_blocks_chmod_777_root(pre_hook):
    """Test blocking of chmod -R 777 / command."""
    input_data = {
        "tool_name": "Bash",
        "tool_input": {"command": "chmod -R 777 /"},
    }

    result = await pre_hook(input_data, "test-123", None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ============================================================================
# Pre-Tool Hook Tests - Safe Operations
# ============================================================================

@pytest.mark.asyncio
async def test_pre_hook_allows_safe_file_write(pre_hook):
    """Test that pre-hook allows writes to safe files."""
    test_cases = [
        "/app/src/main.py",
        "/app/config/settings.json",
        "/app/README.md",
        "/app/tests/test_app.py",
    ]

    for file_path in test_cases:
        input_data = {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert result == {}, f"Incorrectly blocked safe file: {file_path}"


@pytest.mark.asyncio
async def test_pre_hook_allows_safe_bash_commands(pre_hook):
    """Test that pre-hook allows safe bash commands."""
    test_cases = [
        "echo 'Hello World'",
        "ls -la",
        "git status",
        "pytest tests/",
        "npm install",
        "python -m pytest",
    ]

    for command in test_cases:
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert result == {}, f"Incorrectly blocked safe command: {command}"


@pytest.mark.asyncio
async def test_pre_hook_allows_safe_rm_commands(pre_hook):
    """Test that pre-hook allows safe rm commands (not / or /*)."""
    test_cases = [
        "rm temp.txt",
        "rm -rf build/",
        "rm -f *.pyc",
    ]

    for command in test_cases:
        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

        result = await pre_hook(input_data, "test-123", None)

        assert result == {}, f"Incorrectly blocked safe rm: {command}"


@pytest.mark.asyncio
async def test_pre_hook_allows_other_tools(pre_hook):
    """Test that pre-hook allows other tools (Read, Grep, etc.)."""
    test_cases = [
        {"tool_name": "Read", "tool_input": {"file_path": "/app/.env"}},
        {"tool_name": "Grep", "tool_input": {"pattern": "TODO"}},
        {"tool_name": "Edit", "tool_input": {"file_path": "/app/main.py"}},
    ]

    for input_data in test_cases:
        result = await pre_hook(input_data, "test-123", None)
        assert result == {}, f"Incorrectly blocked tool: {input_data['tool_name']}"


# ============================================================================
# Post-Tool Hook Tests - Metrics Recording
# ============================================================================

@pytest.mark.asyncio
async def test_post_hook_records_write_tool_usage(post_hook):
    """Test that post-hook records Write tool usage."""
    input_data = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/app/main.py"},
        "tool_response": "File written successfully",
    }

    result = await post_hook(input_data, "test-123", None)

    # Post-hook doesn't block, just logs
    assert result == {}


@pytest.mark.asyncio
async def test_post_hook_records_bash_tool_usage(post_hook):
    """Test that post-hook records Bash tool usage."""
    input_data = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
        "tool_response": "total 42\ndrwxr-xr-x...",
    }

    result = await post_hook(input_data, "test-123", None)

    assert result == {}


@pytest.mark.asyncio
async def test_post_hook_detects_error_in_response(post_hook, caplog):
    """Test that post-hook detects errors in tool response."""
    input_data = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls /nonexistent"},
        "tool_response": "error: No such file or directory",
    }

    with caplog.at_level("WARNING"):
        result = await post_hook(input_data, "test-123", None)

    assert result == {}
    assert "error" in caplog.text.lower()


@pytest.mark.asyncio
async def test_post_hook_ignores_non_tracked_tools(post_hook):
    """Test that post-hook ignores non-tracked tools (Read, Grep)."""
    input_data = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/app/main.py"},
        "tool_response": "def main(): pass",
    }

    result = await post_hook(input_data, "test-123", None)

    assert result == {}


# ============================================================================
# Hook Builder Tests
# ============================================================================

@patch("codeframe.lib.sdk_hooks.SDK_AVAILABLE", True)
@patch("codeframe.lib.sdk_hooks.HookMatcher")
def test_build_codeframe_hooks_structure(mock_hook_matcher, mock_db, mock_metrics_tracker):
    """Test that build_codeframe_hooks creates correct structure."""
    hooks = build_codeframe_hooks(
        db=mock_db,
        metrics_tracker=mock_metrics_tracker,
    )

    assert "PreToolUse" in hooks
    assert "PostToolUse" in hooks
    assert isinstance(hooks["PreToolUse"], list)
    assert isinstance(hooks["PostToolUse"], list)


@patch("codeframe.lib.sdk_hooks.SDK_AVAILABLE", False)
def test_build_codeframe_hooks_sdk_not_available(mock_db, caplog):
    """Test that build_codeframe_hooks handles missing SDK gracefully."""
    with caplog.at_level("WARNING"):
        hooks = build_codeframe_hooks(db=mock_db)

    assert hooks == {}
    assert "not available" in caplog.text


def test_build_codeframe_hooks_creates_tracker_if_none(mock_db):
    """Test that build_codeframe_hooks creates MetricsTracker if not provided."""
    with patch("codeframe.lib.sdk_hooks.SDK_AVAILABLE", True), \
         patch("codeframe.lib.sdk_hooks.HookMatcher"), \
         patch("codeframe.lib.metrics_tracker.MetricsTracker") as mock_tracker_class:

        hooks = build_codeframe_hooks(db=mock_db, metrics_tracker=None)

        # MetricsTracker should be created with db
        mock_tracker_class.assert_called_once_with(db=mock_db)


# ============================================================================
# Fallback Validation Tests
# ============================================================================

def test_fallback_validation_blocks_protected_file():
    """Test fallback validation blocks protected file writes."""
    error = validate_tool_safety_fallback(
        "Write",
        {"file_path": "/app/.env"}
    )

    assert error is not None
    assert ".env" in error


def test_fallback_validation_blocks_dangerous_command():
    """Test fallback validation blocks dangerous bash commands."""
    error = validate_tool_safety_fallback(
        "Bash",
        {"command": "rm -rf /"}
    )

    assert error is not None
    assert "dangerous" in error.lower()


def test_fallback_validation_allows_safe_operations():
    """Test fallback validation allows safe operations."""
    # Safe write
    error = validate_tool_safety_fallback(
        "Write",
        {"file_path": "/app/main.py"}
    )
    assert error is None

    # Safe bash
    error = validate_tool_safety_fallback(
        "Bash",
        {"command": "echo 'hello'"}
    )
    assert error is None


def test_fallback_validation_handles_missing_input():
    """Test fallback validation handles missing tool_input gracefully."""
    # Missing file_path
    error = validate_tool_safety_fallback("Write", {})
    assert error is None  # No file_path = no pattern match

    # Missing command
    error = validate_tool_safety_fallback("Bash", {})
    assert error is None  # No command = no pattern match


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.asyncio
async def test_pre_hook_handles_missing_tool_name(pre_hook):
    """Test pre-hook handles missing tool_name gracefully."""
    input_data = {
        "tool_input": {"file_path": "/app/.env"},
    }

    result = await pre_hook(input_data, "test-123", None)

    # Should not crash, just return empty (allow)
    assert result == {}


@pytest.mark.asyncio
async def test_pre_hook_handles_missing_tool_input(pre_hook):
    """Test pre-hook handles missing tool_input gracefully."""
    input_data = {
        "tool_name": "Write",
    }

    result = await pre_hook(input_data, "test-123", None)

    # Should not crash
    assert result == {}


@pytest.mark.asyncio
async def test_post_hook_handles_empty_input(post_hook):
    """Test post-hook handles empty input gracefully."""
    input_data = {}

    result = await post_hook(input_data, "test-123", None)

    # Should not crash
    assert result == {}


@pytest.mark.asyncio
async def test_pre_hook_case_insensitive_matching(pre_hook):
    """Test pre-hook performs case-insensitive pattern matching."""
    # Uppercase .ENV should still be blocked
    input_data = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/app/.ENV"},
    }

    result = await pre_hook(input_data, "test-123", None)

    assert "hookSpecificOutput" in result
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ============================================================================
# Integration Test
# ============================================================================

@pytest.mark.asyncio
async def test_pre_and_post_hooks_integration(mock_db, mock_metrics_tracker):
    """Test pre-hook and post-hook working together."""
    pre_hook = create_quality_gate_pre_hook()
    post_hook = create_metrics_post_hook(db=mock_db, metrics_tracker=mock_metrics_tracker)

    # Test 1: Safe operation should pass both hooks
    safe_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/app/main.py"},
        "tool_response": "File written",
    }

    pre_result = await pre_hook(safe_input, "test-123", None)
    assert pre_result == {}

    post_result = await post_hook(safe_input, "test-123", None)
    assert post_result == {}

    # Test 2: Unsafe operation should be blocked by pre-hook
    unsafe_input = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/app/.env"},
    }

    pre_result = await pre_hook(unsafe_input, "test-123", None)
    assert pre_result["hookSpecificOutput"]["permissionDecision"] == "deny"
    # Post-hook wouldn't be called since pre-hook blocks it
