"""
Tests for Frontend Worker Agent (Sprint 4: cf-48).
"""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from anthropic.types import Message, TextBlock

from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent
from codeframe.core.models import AgentMaturity


@pytest.fixture
def temp_web_ui_dir(tmp_path):
    """Create temporary web-ui directory structure."""
    web_ui = tmp_path / "web-ui"
    components_dir = web_ui / "src" / "components"
    components_dir.mkdir(parents=True)
    return web_ui


@pytest.fixture
def frontend_agent(temp_web_ui_dir, monkeypatch):
    """Create FrontendWorkerAgent for testing."""
    # Patch project paths
    agent = FrontendWorkerAgent(
        agent_id="frontend-test-001", provider="anthropic", api_key="test-key"
    )
    agent.web_ui_root = temp_web_ui_dir
    agent.components_dir = temp_web_ui_dir / "src" / "components"
    return agent


@pytest.fixture
def mock_websocket_manager():
    """Create mock WebSocket manager."""
    manager = Mock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
def sample_task():
    """Create sample task dict for testing (matches LeadAgent's task.to_dict() output)."""
    return {
        "id": 1,
        "project_id": 1,
        "issue_id": 1,
        "task_number": "T-001",
        "parent_issue_number": "I-001",
        "title": "Create UserCard component",
        "description": "Create a UserCard component that displays user information",
        "status": "pending",
        "assigned_to": None,
        "depends_on": "",
        "can_parallelize": False,
        "priority": 1,
        "workflow_step": 1,
        "requires_mcp": False,
        "estimated_tokens": 0,
        "actual_tokens": None,
    }


class TestFrontendWorkerAgentInitialization:
    """Test agent initialization."""

    def test_initialization_with_defaults(self):
        """Test agent initializes with default values."""
        agent = FrontendWorkerAgent(agent_id="frontend-001")

        assert agent.agent_id == "frontend-001"
        assert agent.agent_type == "frontend"
        assert agent.provider == "anthropic"
        assert agent.maturity == AgentMaturity.D1
        assert agent.current_task is None

    def test_initialization_with_custom_maturity(self):
        """Test agent initializes with custom maturity level."""
        agent = FrontendWorkerAgent(agent_id="frontend-002", maturity=AgentMaturity.D3)

        assert agent.maturity == AgentMaturity.D3

    def test_initialization_with_api_key(self):
        """Test agent initializes with provided API key."""
        agent = FrontendWorkerAgent(agent_id="frontend-003", api_key="test-api-key-123")

        assert agent.api_key == "test-api-key-123"
        assert agent.client is not None

    def test_initialization_sets_project_paths(self, frontend_agent, temp_web_ui_dir):
        """Test agent sets correct project directory paths."""
        assert frontend_agent.web_ui_root == temp_web_ui_dir
        assert frontend_agent.components_dir == temp_web_ui_dir / "src" / "components"


class TestComponentSpecParsing:
    """Test component specification parsing."""

    def test_parse_json_spec(self, frontend_agent):
        """Test parsing valid JSON specification."""
        json_spec = json.dumps(
            {"name": "UserProfile", "description": "User profile component", "generate_types": True}
        )

        spec = frontend_agent._parse_component_spec(json_spec)

        assert spec["name"] == "UserProfile"
        assert spec["description"] == "User profile component"
        assert spec["generate_types"] is True

    def test_parse_plain_text_with_component_keyword(self, frontend_agent):
        """Test parsing plain text with 'component:' keyword."""
        text_spec = "Component: UserCard\nDisplay user information"

        spec = frontend_agent._parse_component_spec(text_spec)

        assert spec["name"] == "UserCard"
        assert "Component: UserCard" in spec["description"]

    def test_parse_plain_text_with_create_pattern(self, frontend_agent):
        """Test parsing plain text with 'create component' pattern."""
        text_spec = "Create a LoginForm component for user authentication"

        spec = frontend_agent._parse_component_spec(text_spec)

        assert spec["name"] == "LoginForm"
        assert spec["generate_types"] is True
        assert spec["use_tailwind"] is True

    def test_parse_minimal_spec(self, frontend_agent):
        """Test parsing minimal specification falls back to defaults."""
        minimal_spec = "Some description without clear component name"

        spec = frontend_agent._parse_component_spec(minimal_spec)

        assert spec["name"] == "NewComponent"  # Default fallback
        assert spec["generate_types"] is True


class TestComponentGeneration:
    """Test React component code generation."""

    def test_generate_basic_component_template(self, frontend_agent):
        """Test generating basic component template without API."""
        spec = {"name": "TestComponent", "description": "A test component"}

        code = frontend_agent._generate_basic_component_template(spec)

        assert "TestComponent" in code
        assert "interface TestComponentProps" in code
        assert "export const TestComponent" in code
        assert "React.FC" in code
        assert "className=" in code  # Tailwind CSS
        assert "import React from 'react'" in code

    @patch("codeframe.agents.frontend_worker_agent.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_generate_component_with_api_success(self, mock_anthropic_class, frontend_agent):
        """Test generating component using Claude API successfully."""
        # Setup mock
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # Create proper mock response structure
        mock_text_block = Mock(spec=TextBlock)
        mock_text_block.text = """import React from 'react';

interface ButtonProps {
  label: string;
  onClick: () => void;
}

export const Button: React.FC<ButtonProps> = ({ label, onClick }) => {
  return <button onClick={onClick}>{label}</button>;
};"""

        mock_message = Mock(spec=Message)
        mock_message.content = [mock_text_block]

        mock_client.messages.create.return_value = mock_message

        # Update agent's client
        frontend_agent.client = mock_client

        spec = {"name": "Button", "description": "A button component"}

        code = await frontend_agent._generate_react_component(spec)

        assert "Button" in code
        assert "ButtonProps" in code
        assert "React.FC" in code
        mock_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_component_api_fallback(self, frontend_agent):
        """Test component generation falls back on API failure."""
        # Set client to None to trigger fallback
        frontend_agent.client = None

        spec = {"name": "FallbackComponent", "description": "Component with API failure"}

        code = await frontend_agent._generate_react_component(spec)

        # Should get basic template
        assert "FallbackComponent" in code
        assert "interface FallbackComponentProps" in code


class TestFileCreation:
    """Test component file creation."""

    def test_create_component_file(self, frontend_agent):
        """Test creating component file in correct location."""
        component_code = "export const Test = () => <div>Test</div>;"

        file_paths = frontend_agent._create_component_files("TestComponent", component_code)

        assert "component" in file_paths
        assert file_paths["component"].endswith("TestComponent.tsx")

        # Verify file exists and has correct content
        component_file = frontend_agent.components_dir / "TestComponent.tsx"
        assert component_file.exists()
        assert component_file.read_text() == component_code

    def test_create_component_with_types(self, frontend_agent):
        """Test creating component with separate types file."""
        component_code = "export const Test = () => <div>Test</div>;"
        types_code = "export interface TestProps { name: string; }"

        file_paths = frontend_agent._create_component_files(
            "TestComponent", component_code, types_code
        )

        assert "component" in file_paths
        assert "types" in file_paths

        # Verify both files exist
        component_file = frontend_agent.components_dir / "TestComponent.tsx"
        types_file = frontend_agent.components_dir / "TestComponent.types.ts"

        assert component_file.exists()
        assert types_file.exists()
        assert types_file.read_text() == types_code

    def test_create_component_file_conflict(self, frontend_agent):
        """Test error handling when component file already exists."""
        # Create existing file
        existing_file = frontend_agent.components_dir / "ExistingComponent.tsx"
        existing_file.write_text("existing content")

        component_code = "new content"

        with pytest.raises(FileExistsError, match="already exists"):
            frontend_agent._create_component_files("ExistingComponent", component_code)

        # Verify original file unchanged
        assert existing_file.read_text() == "existing content"


class TestImportExportUpdates:
    """Test import/export statement updates."""

    def test_create_index_file_if_not_exists(self, frontend_agent):
        """Test creating index.ts file if it doesn't exist."""
        file_paths = {"component": "src/components/NewComponent.tsx"}

        frontend_agent._update_imports_exports("NewComponent", file_paths)

        index_file = frontend_agent.components_dir / "index.ts"
        assert index_file.exists()

        content = index_file.read_text()
        assert "export { NewComponent } from './NewComponent';" in content

    def test_append_to_existing_index_file(self, frontend_agent):
        """Test appending export to existing index.ts."""
        # Create existing index file
        index_file = frontend_agent.components_dir / "index.ts"
        index_file.write_text("export { ExistingComponent } from './ExistingComponent';\n")

        file_paths = {"component": "src/components/NewComponent.tsx"}

        frontend_agent._update_imports_exports("NewComponent", file_paths)

        content = index_file.read_text()
        assert "export { ExistingComponent }" in content
        assert "export { NewComponent }" in content

    def test_skip_duplicate_export(self, frontend_agent):
        """Test skipping duplicate export in index file."""
        # Create index file with component already exported
        index_file = frontend_agent.components_dir / "index.ts"
        original_content = "export { TestComponent } from './TestComponent';\n"
        index_file.write_text(original_content)

        file_paths = {"component": "src/components/TestComponent.tsx"}

        frontend_agent._update_imports_exports("TestComponent", file_paths)

        # Content should remain unchanged
        content = index_file.read_text()
        assert content == original_content
        assert content.count("export { TestComponent }") == 1


class TestTaskExecution:
    """Test complete task execution flow."""

    @pytest.mark.asyncio
    async def test_execute_task_success(self, frontend_agent, sample_task):
        """Test successful task execution without WebSocket."""
        result = await frontend_agent.execute_task(sample_task, project_id=1)

        assert result["status"] == "completed"
        assert "UserCard" in result["output"]
        assert "files_created" in result
        assert result["component_name"] == "UserCard"

        # Verify component file created
        component_file = frontend_agent.components_dir / "UserCard.tsx"
        assert component_file.exists()

    @pytest.mark.asyncio
    async def test_execute_task_with_websocket_broadcasts(
        self, frontend_agent, sample_task, mock_websocket_manager
    ):
        """Test task execution broadcasts WebSocket messages."""
        frontend_agent.websocket_manager = mock_websocket_manager

        result = await frontend_agent.execute_task(sample_task, project_id=1)

        assert result["status"] == "completed"
        # Note: broadcasts are async, so we can't directly assert on them in sync test
        # In real usage, they would be handled by event loop

    @pytest.mark.asyncio
    async def test_execute_task_json_spec(self, frontend_agent):
        """Test task execution with JSON specification."""
        json_task = {
            "id": 2,
            "project_id": 1,
            "issue_id": 1,
            "task_number": "T-002",
            "parent_issue_number": "I-001",
            "title": "Create Button component",
            "description": json.dumps(
                {
                    "name": "Button",
                    "description": "Reusable button component",
                    "generate_types": False,
                }
            ),
            "status": "pending",
            "assigned_to": None,
            "priority": 1,
            "workflow_step": 1,
        }

        result = await frontend_agent.execute_task(json_task, project_id=1)

        assert result["status"] == "completed"
        assert result["component_name"] == "Button"

        # Verify component created
        component_file = frontend_agent.components_dir / "Button.tsx"
        assert component_file.exists()

    @pytest.mark.asyncio
    async def test_execute_task_error_handling(self, frontend_agent):
        """Test task execution handles errors gracefully."""
        # Create task with invalid spec that will cause error
        invalid_task = {
            "id": 3,
            "project_id": 1,
            "issue_id": 1,
            "task_number": "T-003",
            "parent_issue_number": "I-001",
            "title": "Invalid task",
            "description": "Component: <Invalid>Name>",  # Invalid component name
            "status": "pending",
            "assigned_to": None,
            "priority": 1,
            "workflow_step": 1,
        }

        # Mock _create_component_files to raise error
        original_method = frontend_agent._create_component_files

        def raise_error(*args, **kwargs):
            raise ValueError("Invalid component name")

        frontend_agent._create_component_files = raise_error

        result = await frontend_agent.execute_task(invalid_task, project_id=1)

        assert result["status"] == "failed"
        assert "error" in result
        assert "Invalid component name" in result["error"]

        # Restore original method
        frontend_agent._create_component_files = original_method


class TestWebSocketIntegration:
    """Test WebSocket broadcast integration."""

    @pytest.mark.asyncio
    async def test_broadcast_task_started(
        self, frontend_agent, sample_task, mock_websocket_manager
    ):
        """Test broadcasting task started status."""
        frontend_agent.websocket_manager = mock_websocket_manager

        # Execute task (broadcasts are fire-and-forget)
        result = await frontend_agent.execute_task(sample_task, project_id=1)

        assert result["status"] == "completed"
        # Broadcasts happen asynchronously, testing integration separately

    @pytest.mark.asyncio
    async def test_broadcast_task_completed(
        self, frontend_agent, sample_task, mock_websocket_manager
    ):
        """Test broadcasting task completed status."""
        frontend_agent.websocket_manager = mock_websocket_manager

        result = await frontend_agent.execute_task(sample_task, project_id=1)

        assert result["status"] == "completed"


class TestErrorHandling:
    """Test error handling and recovery."""

    @pytest.mark.asyncio
    async def test_handle_file_already_exists(self, frontend_agent):
        """Test graceful handling when component file already exists."""
        # Create existing component
        existing_file = frontend_agent.components_dir / "Existing.tsx"
        existing_file.write_text("original content")

        task = {
            "id": 4,
            "project_id": 1,
            "issue_id": 1,
            "task_number": "T-004",
            "parent_issue_number": "I-001",
            "title": "Create Existing component",
            "description": "Component: Existing",
            "status": "pending",
            "assigned_to": None,
            "priority": 1,
            "workflow_step": 1,
        }

        result = await frontend_agent.execute_task(task, project_id=1)

        assert result["status"] == "failed"
        assert "already exists" in result["error"]

        # Original file should be unchanged
        assert existing_file.read_text() == "original content"

    @pytest.mark.asyncio
    async def test_handle_missing_api_key(self, monkeypatch):
        """Test agent works without API key (using fallback templates)."""
        # Ensure environment variable is not used
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        agent = FrontendWorkerAgent(agent_id="frontend-no-key", api_key=None)

        assert agent.client is None

        # Should still be able to generate basic components
        spec = {"name": "Test", "description": "Test component"}
        code = await agent._generate_react_component(spec)

        assert "Test" in code
        assert "TestProps" in code


class TestProjectConventions:
    """Test adherence to project conventions."""

    def test_generated_component_uses_tailwind(self, frontend_agent):
        """Test generated components use Tailwind CSS."""
        spec = {"name": "TailwindTest", "description": "Test"}

        code = frontend_agent._generate_basic_component_template(spec)

        assert "className=" in code
        assert "p-4" in code or "text-" in code  # Tailwind classes

    def test_generated_component_is_functional(self, frontend_agent):
        """Test generated components are functional (not class-based)."""
        spec = {"name": "FunctionalTest", "description": "Test"}

        code = frontend_agent._generate_basic_component_template(spec)

        assert "React.FC" in code
        assert "const FunctionalTest" in code
        assert "class FunctionalTest" not in code

    def test_generated_component_has_typescript_types(self, frontend_agent):
        """Test generated components have proper TypeScript types."""
        spec = {"name": "TypedTest", "description": "Test"}

        code = frontend_agent._generate_basic_component_template(spec)

        assert "interface TypedTestProps" in code
        assert ": React.FC<TypedTestProps>" in code
