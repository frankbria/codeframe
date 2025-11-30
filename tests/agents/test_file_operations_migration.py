"""Tests for file operations migration to Claude Agent SDK.

This module tests the migration from direct pathlib operations to SDK tool execution.
Tests cover both SDK mode (use_sdk=True) and fallback mode (use_sdk=False).
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex


@pytest.fixture
def temp_project_root(tmp_path):
    """Create temporary project root directory."""
    return tmp_path / "test_project"


@pytest.fixture
def mock_db():
    """Create mock database instance."""
    db = Mock(spec=Database)
    db.conn = Mock()
    db.conn.cursor = Mock(return_value=Mock())
    return db


@pytest.fixture
def mock_codebase_index():
    """Create mock codebase index."""
    return Mock(spec=CodebaseIndex)


@pytest.fixture
def backend_agent_sdk(mock_db, mock_codebase_index, temp_project_root):
    """Create backend agent with SDK enabled."""
    temp_project_root.mkdir(parents=True, exist_ok=True)

    with patch("codeframe.agents.backend_worker_agent.SDKClientWrapper"):
        agent = BackendWorkerAgent(
            project_id=1,
            db=mock_db,
            codebase_index=mock_codebase_index,
            api_key="test-key",
            project_root=str(temp_project_root),
            use_sdk=True,
        )
        agent.sdk_client = AsyncMock()
        return agent


@pytest.fixture
def backend_agent_no_sdk(mock_db, mock_codebase_index, temp_project_root):
    """Create backend agent with SDK disabled (fallback mode)."""
    temp_project_root.mkdir(parents=True, exist_ok=True)

    agent = BackendWorkerAgent(
        project_id=1,
        db=mock_db,
        codebase_index=mock_codebase_index,
        api_key="test-key",
        project_root=str(temp_project_root),
        use_sdk=False,
    )
    return agent


# ========================================================================
# Test SDK Initialization
# ========================================================================


def test_backend_agent_sdk_initialization(mock_db, mock_codebase_index, temp_project_root):
    """Test that BackendWorkerAgent initializes SDK client when use_sdk=True."""
    temp_project_root.mkdir(parents=True, exist_ok=True)

    with patch("codeframe.agents.backend_worker_agent.SDKClientWrapper") as MockSDK:
        agent = BackendWorkerAgent(
            project_id=1,
            db=mock_db,
            codebase_index=mock_codebase_index,
            api_key="test-key",
            project_root=str(temp_project_root),
            use_sdk=True,
        )

        # Verify SDK client was initialized
        assert agent.use_sdk is True
        MockSDK.assert_called_once()

        # Verify SDK client was configured with correct parameters
        call_args = MockSDK.call_args
        assert call_args.kwargs["api_key"] == "test-key"
        assert call_args.kwargs["model"] == "claude-sonnet-4-20250514"
        assert "Read" in call_args.kwargs["allowed_tools"]
        assert "Write" in call_args.kwargs["allowed_tools"]
        assert call_args.kwargs["cwd"] == str(temp_project_root)
        assert call_args.kwargs["permission_mode"] == "acceptEdits"


def test_backend_agent_no_sdk_initialization(backend_agent_no_sdk):
    """Test that BackendWorkerAgent works without SDK (fallback mode)."""
    assert backend_agent_no_sdk.use_sdk is False
    assert backend_agent_no_sdk.sdk_client is None


# ========================================================================
# Test Code Generation (SDK vs Fallback)
# ========================================================================


@pytest.mark.asyncio
async def test_generate_code_with_sdk(backend_agent_sdk):
    """Test that generate_code uses SDK when enabled."""
    task = {
        "id": 1,
        "title": "Test task",
        "description": "Create a simple function",
    }

    context = {
        "task": task,
        "related_symbols": [],
        "related_files": [],
        "issue_context": None,
    }

    # Mock SDK response with JSON output
    mock_response = {
        "content": json.dumps({
            "files": [
                {
                    "path": "src/example.py",
                    "action": "create",
                    "content": "def hello():\n    pass",
                }
            ],
            "explanation": "Created hello function",
        }),
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }

    backend_agent_sdk.sdk_client.send_message = AsyncMock(return_value=mock_response)

    # Generate code
    result = await backend_agent_sdk.generate_code(context)

    # Verify SDK was called
    backend_agent_sdk.sdk_client.send_message.assert_called_once()

    # Verify result structure
    assert "files" in result
    assert "explanation" in result
    assert len(result["files"]) == 1
    assert result["files"][0]["path"] == "src/example.py"
    assert result["files"][0]["action"] == "create"


@pytest.mark.asyncio
async def test_generate_code_without_sdk(backend_agent_no_sdk):
    """Test that generate_code uses direct Anthropic API when SDK disabled."""
    task = {
        "id": 1,
        "title": "Test task",
        "description": "Create a simple function",
    }

    context = {
        "task": task,
        "related_symbols": [],
        "related_files": [],
        "issue_context": None,
    }

    # Mock Anthropic API response (patch where it's imported - inside the method)
    with patch("anthropic.AsyncAnthropic") as MockAnthropic:
        mock_client = AsyncMock()
        MockAnthropic.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps({
                    "files": [
                        {
                            "path": "src/example.py",
                            "action": "create",
                            "content": "def hello():\n    pass",
                        }
                    ],
                    "explanation": "Created hello function",
                })
            )
        ]

        mock_client.messages.create = AsyncMock(return_value=mock_response)

        # Generate code
        result = await backend_agent_no_sdk.generate_code(context)

        # Verify Anthropic API was called
        mock_client.messages.create.assert_called_once()

        # Verify result structure
        assert "files" in result
        assert "explanation" in result
        assert len(result["files"]) == 1


# ========================================================================
# Test File Operations (SDK vs Fallback)
# ========================================================================


def test_apply_file_changes_with_sdk(backend_agent_sdk, temp_project_root):
    """Test that apply_file_changes skips actual writes when SDK is enabled."""
    files = [
        {
            "path": "src/example.py",
            "action": "create",
            "content": "def hello():\n    pass",
        }
    ]

    # Apply file changes (SDK mode - should NOT write files)
    modified_paths = backend_agent_sdk.apply_file_changes(files)

    # Verify paths returned
    assert modified_paths == ["src/example.py"]

    # Verify file was NOT actually written (SDK handles it)
    # Note: In real scenario, SDK would have written it, but we're testing
    # that apply_file_changes doesn't duplicate the write
    assert not (temp_project_root / "src" / "example.py").exists()


def test_apply_file_changes_without_sdk(backend_agent_no_sdk, temp_project_root):
    """Test that apply_file_changes performs actual writes when SDK disabled."""
    files = [
        {
            "path": "src/example.py",
            "action": "create",
            "content": "def hello():\n    pass",
        }
    ]

    # Apply file changes (non-SDK mode - should write files)
    modified_paths = backend_agent_no_sdk.apply_file_changes(files)

    # Verify paths returned
    assert modified_paths == ["src/example.py"]

    # Verify file was actually written
    target_file = temp_project_root / "src" / "example.py"
    assert target_file.exists()
    assert target_file.read_text() == "def hello():\n    pass"


def test_apply_file_changes_modify_action_no_sdk(backend_agent_no_sdk, temp_project_root):
    """Test modify action in non-SDK mode."""
    # Create initial file
    (temp_project_root / "src").mkdir(parents=True, exist_ok=True)
    initial_file = temp_project_root / "src" / "example.py"
    initial_file.write_text("def old():\n    pass")

    # Modify file
    files = [
        {
            "path": "src/example.py",
            "action": "modify",
            "content": "def new():\n    pass",
        }
    ]

    modified_paths = backend_agent_no_sdk.apply_file_changes(files)

    assert modified_paths == ["src/example.py"]
    assert initial_file.read_text() == "def new():\n    pass"


def test_apply_file_changes_delete_action_no_sdk(backend_agent_no_sdk, temp_project_root):
    """Test delete action in non-SDK mode."""
    # Create file to delete
    (temp_project_root / "src").mkdir(parents=True, exist_ok=True)
    delete_file = temp_project_root / "src" / "example.py"
    delete_file.write_text("def delete_me():\n    pass")

    # Delete file
    files = [
        {
            "path": "src/example.py",
            "action": "delete",
            "content": "",
        }
    ]

    modified_paths = backend_agent_no_sdk.apply_file_changes(files)

    assert modified_paths == ["src/example.py"]
    assert not delete_file.exists()


# ========================================================================
# Test Security Validation
# ========================================================================


def test_apply_file_changes_rejects_absolute_path_sdk(backend_agent_sdk):
    """Test that absolute paths are rejected even in SDK mode."""
    files = [
        {
            "path": "/etc/passwd",
            "action": "create",
            "content": "malicious",
        }
    ]

    with pytest.raises(ValueError, match="Absolute path not allowed"):
        backend_agent_sdk.apply_file_changes(files)


def test_apply_file_changes_rejects_absolute_path_no_sdk(backend_agent_no_sdk):
    """Test that absolute paths are rejected in non-SDK mode."""
    files = [
        {
            "path": "/etc/passwd",
            "action": "create",
            "content": "malicious",
        }
    ]

    with pytest.raises(ValueError, match="Absolute path not allowed"):
        backend_agent_no_sdk.apply_file_changes(files)


def test_apply_file_changes_rejects_path_traversal_sdk(backend_agent_sdk):
    """Test that path traversal is rejected in SDK mode."""
    files = [
        {
            "path": "../../etc/passwd",
            "action": "create",
            "content": "malicious",
        }
    ]

    with pytest.raises(ValueError, match="Path traversal detected"):
        backend_agent_sdk.apply_file_changes(files)


def test_apply_file_changes_rejects_path_traversal_no_sdk(backend_agent_no_sdk):
    """Test that path traversal is rejected in non-SDK mode."""
    files = [
        {
            "path": "../../etc/passwd",
            "action": "create",
            "content": "malicious",
        }
    ]

    with pytest.raises(ValueError, match="Path traversal detected"):
        backend_agent_no_sdk.apply_file_changes(files)


# ========================================================================
# Test Multiple File Changes
# ========================================================================


def test_apply_multiple_files_no_sdk(backend_agent_no_sdk, temp_project_root):
    """Test applying multiple file changes in non-SDK mode."""
    files = [
        {
            "path": "src/file1.py",
            "action": "create",
            "content": "# File 1",
        },
        {
            "path": "src/file2.py",
            "action": "create",
            "content": "# File 2",
        },
        {
            "path": "tests/test_file.py",
            "action": "create",
            "content": "# Test file",
        },
    ]

    modified_paths = backend_agent_no_sdk.apply_file_changes(files)

    assert len(modified_paths) == 3
    assert (temp_project_root / "src" / "file1.py").exists()
    assert (temp_project_root / "src" / "file2.py").exists()
    assert (temp_project_root / "tests" / "test_file.py").exists()


# ========================================================================
# Test Error Handling
# ========================================================================


def test_apply_file_changes_modify_nonexistent_file_no_sdk(backend_agent_no_sdk):
    """Test that modifying nonexistent file raises error in non-SDK mode."""
    files = [
        {
            "path": "src/nonexistent.py",
            "action": "modify",
            "content": "new content",
        }
    ]

    with pytest.raises(FileNotFoundError, match="Cannot modify non-existent file"):
        backend_agent_no_sdk.apply_file_changes(files)


def test_apply_file_changes_delete_nonexistent_file_no_sdk(backend_agent_no_sdk):
    """Test that deleting nonexistent file raises error in non-SDK mode."""
    files = [
        {
            "path": "src/nonexistent.py",
            "action": "delete",
            "content": "",
        }
    ]

    with pytest.raises(FileNotFoundError, match="Cannot delete non-existent file"):
        backend_agent_no_sdk.apply_file_changes(files)


# ========================================================================
# Test System Prompt
# ========================================================================


def test_build_system_prompt_includes_tool_instructions(backend_agent_sdk):
    """Test that system prompt includes SDK tool usage instructions."""
    prompt = backend_agent_sdk._build_system_prompt()

    assert "Write tool" in prompt
    assert "Read tool" in prompt
    assert "creates parent directories" in prompt
    assert "JSON object" in prompt
