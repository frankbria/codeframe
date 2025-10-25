"""
Frontend Worker Agent for React/TypeScript component generation (Sprint 4: cf-48).

This agent specializes in generating React components with TypeScript,
following project conventions (Tailwind CSS, functional components).
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from anthropic import Anthropic

from codeframe.core.models import Task, AgentMaturity
from codeframe.agents.worker_agent import WorkerAgent

logger = logging.getLogger(__name__)


class FrontendWorkerAgent(WorkerAgent):
    """
    Frontend Worker Agent - Specialized in React/TypeScript component generation.

    Capabilities:
    - Generate functional React components with TypeScript
    - Create TypeScript interfaces for props and state
    - Follow project conventions (Tailwind CSS, functional components)
    - Auto-update imports and exports
    - Integrate with WebSocket broadcasts for real-time status
    """

    def __init__(
        self,
        agent_id: str,
        provider: str = "anthropic",
        maturity: AgentMaturity = AgentMaturity.D1,
        api_key: Optional[str] = None,
        websocket_manager=None
    ):
        """
        Initialize Frontend Worker Agent.

        Args:
            agent_id: Unique agent identifier
            provider: LLM provider (default: anthropic)
            maturity: Agent maturity level
            api_key: API key for LLM provider (uses ANTHROPIC_API_KEY env var if not provided)
            websocket_manager: WebSocket connection manager for broadcasts
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="frontend",
            provider=provider,
            maturity=maturity,
            system_prompt=self._build_system_prompt()
        )
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = Anthropic(api_key=self.api_key) if self.api_key else None
        self.websocket_manager = websocket_manager
        self.project_root = Path(__file__).parent.parent.parent  # codeframe/
        self.web_ui_root = self.project_root / "web-ui"
        self.components_dir = self.web_ui_root / "src" / "components"

    def _broadcast_async(
        self,
        project_id: int,
        task_id: int,
        status: str,
        agent_id: Optional[str] = None,
        progress: Optional[int] = None
    ) -> None:
        """
        Helper to broadcast task status (handles async event loop safely).

        Args:
            project_id: Project ID
            task_id: Task ID
            status: Task status
            agent_id: Optional agent ID
            progress: Optional progress percentage
        """
        if not self.websocket_manager:
            return

        import asyncio
        from codeframe.ui.websocket_broadcasts import broadcast_task_status

        try:
            # Check if there's a running event loop
            loop = asyncio.get_running_loop()
            # If we're already in an async context, create task
            loop.create_task(
                broadcast_task_status(
                    self.websocket_manager,
                    project_id,
                    task_id,
                    status,
                    agent_id=agent_id,
                    progress=progress
                )
            )
        except RuntimeError:
            # No running event loop - skip broadcast in sync context
            # This is expected in synchronous test environments
            logger.debug(
                f"Skipped broadcast (no event loop): task {task_id} → {status}"
            )

    def _build_system_prompt(self) -> str:
        """Build system prompt for frontend-specific tasks."""
        return """You are a Frontend Worker Agent specializing in React/TypeScript development.

Your responsibilities:
1. Generate clean, functional React components using TypeScript
2. Follow project conventions:
   - Functional components with hooks (not class components)
   - Tailwind CSS for styling (no inline styles, CSS modules, or styled-components)
   - TypeScript interfaces for props and state
   - Proper prop destructuring
3. Create well-typed TypeScript interfaces
4. Write accessible, semantic HTML
5. Follow React best practices (key props, useCallback, useMemo when appropriate)

Output format:
- Provide complete, working code
- Include all necessary imports
- Add brief comments for complex logic only
- Ensure proper TypeScript typing (no 'any' types)
"""

    def execute_task(self, task: Task, project_id: int = 1) -> Dict[str, Any]:
        """
        Execute frontend task: generate React component.

        Args:
            task: Task to execute with component specification
            project_id: Project ID for WebSocket broadcasts

        Returns:
            Execution result with status and output
        """
        self.current_task = task

        try:
            # Broadcast task started
            if self.websocket_manager:
                self._broadcast_async(
                    project_id,
                    task.id,
                    "in_progress",
                    agent_id=self.agent_id,
                    progress=0
                )

            logger.info(f"Frontend agent {self.agent_id} executing task {task.id}: {task.title}")

            # Parse task description for component spec
            component_spec = self._parse_component_spec(task.description)

            # Generate component code
            component_code = self._generate_react_component(component_spec)

            # Generate TypeScript types if needed
            if component_spec.get("generate_types"):
                types_code = self._generate_typescript_types(component_spec)
            else:
                types_code = None

            # Create files in correct location
            file_paths = self._create_component_files(
                component_spec["name"],
                component_code,
                types_code
            )

            # Update imports/exports
            self._update_imports_exports(component_spec["name"], file_paths)

            # Broadcast completion
            if self.websocket_manager:
                self._broadcast_async(
                    project_id,
                    task.id,
                    "completed",
                    agent_id=self.agent_id,
                    progress=100
                )

            logger.info(f"Frontend agent {self.agent_id} completed task {task.id}")

            return {
                "status": "completed",
                "output": f"Generated component: {component_spec['name']}",
                "files_created": file_paths,
                "component_name": component_spec["name"]
            }

        except Exception as e:
            logger.error(f"Frontend agent {self.agent_id} failed task {task.id}: {e}")

            # Broadcast failure
            if self.websocket_manager:
                self._broadcast_async(
                    project_id,
                    task.id,
                    "failed",
                    agent_id=self.agent_id
                )

            return {
                "status": "failed",
                "output": str(e),
                "error": str(e)
            }

    def _parse_component_spec(self, description: str) -> Dict[str, Any]:
        """
        Parse task description to extract component specification.

        Args:
            description: Task description (plain text or JSON)

        Returns:
            Component specification dict
        """
        # Try parsing as JSON first
        try:
            spec = json.loads(description)
            if "name" in spec:
                return spec
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: extract from plain text
        # Simple heuristic: first word/phrase is component name
        lines = description.strip().split("\n")
        name = "NewComponent"

        # Look for common patterns
        for line in lines:
            if "component:" in line.lower():
                name = line.split(":")[-1].strip()
                break
            elif "create" in line.lower() and "component" in line.lower():
                # Extract PascalCase words (skip "Create" and "component" keywords)
                words = line.split()
                for i, word in enumerate(words):
                    # Skip keywords and find PascalCase component name
                    if (word[0].isupper() and
                        word.lower() not in ['create', 'component', 'a', 'the'] and
                        "component" not in word.lower()):
                        name = word
                        break

        return {
            "name": name,
            "description": description,
            "generate_types": True,
            "use_tailwind": True
        }

    def _generate_react_component(self, spec: Dict[str, Any]) -> str:
        """
        Generate React component code using Claude API.

        Args:
            spec: Component specification

        Returns:
            Component code as string
        """
        if not self.client:
            # Fallback: generate basic component template
            return self._generate_basic_component_template(spec)

        prompt = f"""Generate a React functional component with the following specification:

Component Name: {spec['name']}
Description: {spec.get('description', 'A new React component')}

Requirements:
- Functional component with TypeScript
- Use Tailwind CSS for styling
- Include proper TypeScript interfaces for props
- Follow React best practices
- Add accessibility attributes (ARIA) where appropriate

Provide ONLY the component code, no explanations."""

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract code from response
            code = response.content[0].text

            # Remove markdown code blocks if present
            if "```" in code:
                code = code.split("```")[1]
                if code.startswith("tsx") or code.startswith("typescript"):
                    code = "\n".join(code.split("\n")[1:])

            return code.strip()

        except Exception as e:
            logger.error(f"Failed to generate component with Claude API: {e}")
            return self._generate_basic_component_template(spec)

    def _generate_basic_component_template(self, spec: Dict[str, Any]) -> str:
        """
        Generate basic component template as fallback.

        Args:
            spec: Component specification

        Returns:
            Basic component code
        """
        name = spec["name"]
        description = spec.get("description", "A new component")

        return f"""import React from 'react';

interface {name}Props {{
  // Add props here
}}

/**
 * {description}
 */
export const {name}: React.FC<{name}Props> = (props) => {{
  return (
    <div className="p-4">
      <h2 className="text-xl font-bold">{name}</h2>
      <p className="text-gray-600">Component implementation</p>
    </div>
  );
}};
"""

    def _generate_typescript_types(self, spec: Dict[str, Any]) -> Optional[str]:
        """
        Generate TypeScript type definitions for component.

        Args:
            spec: Component specification

        Returns:
            TypeScript types as string, or None if not needed
        """
        # For now, types are included in component file
        # In future, could extract to separate types file
        return None

    def _create_component_files(
        self,
        component_name: str,
        component_code: str,
        types_code: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Create component files in correct directory structure.

        Args:
            component_name: Name of component
            component_code: Component source code
            types_code: Optional TypeScript types

        Returns:
            Dict of created file paths
        """
        # Ensure components directory exists
        self.components_dir.mkdir(parents=True, exist_ok=True)

        # Component file path
        component_file = self.components_dir / f"{component_name}.tsx"

        # Check for conflicts
        if component_file.exists():
            raise FileExistsError(
                f"Component file already exists: {component_file}. "
                "Please choose a different name or delete the existing file."
            )

        # Write component file
        component_file.write_text(component_code, encoding="utf-8")

        # Use relative path from web_ui_root if within temp dir (testing)
        try:
            relative_path = component_file.relative_to(self.project_root)
        except ValueError:
            # In testing with tmp directories
            relative_path = component_file.relative_to(self.web_ui_root.parent)

        file_paths = {
            "component": str(relative_path)
        }

        # Write types file if provided
        if types_code:
            types_file = self.components_dir / f"{component_name}.types.ts"
            types_file.write_text(types_code, encoding="utf-8")

            try:
                types_relative = types_file.relative_to(self.project_root)
            except ValueError:
                types_relative = types_file.relative_to(self.web_ui_root.parent)

            file_paths["types"] = str(types_relative)

        return file_paths

    def _update_imports_exports(
        self,
        component_name: str,
        file_paths: Dict[str, str]
    ) -> None:
        """
        Update import/export statements in index files.

        Args:
            component_name: Name of component
            file_paths: Dict of created file paths
        """
        # Update components/index.ts if it exists
        index_file = self.components_dir / "index.ts"

        if not index_file.exists():
            # Create index file
            index_file.write_text(
                f"export {{ {component_name} }} from './{component_name}';\n",
                encoding="utf-8"
            )
        else:
            # Append export
            current_content = index_file.read_text(encoding="utf-8")
            if f"export {{ {component_name} }}" not in current_content:
                index_file.write_text(
                    current_content + f"export {{ {component_name} }} from './{component_name}';\n",
                    encoding="utf-8"
                )
