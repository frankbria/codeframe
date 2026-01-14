"""Agent planning module for CodeFRAME v2.

Transforms task context into an executable implementation plan.
Uses LLM to analyze requirements and decompose into actionable steps.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from codeframe.core.context import TaskContext
from codeframe.adapters.llm import LLMProvider, Purpose


class StepType(str, Enum):
    """Type of implementation step."""

    FILE_CREATE = "file_create"  # Create a new file
    FILE_EDIT = "file_edit"  # Edit an existing file
    FILE_DELETE = "file_delete"  # Delete a file
    SHELL_COMMAND = "shell_command"  # Run a shell command
    VERIFICATION = "verification"  # Run tests/linting


class Complexity(str, Enum):
    """Estimated task complexity."""

    LOW = "low"  # Simple change, < 50 lines
    MEDIUM = "medium"  # Moderate change, 50-200 lines
    HIGH = "high"  # Complex change, > 200 lines or architectural


@dataclass
class PlanStep:
    """A single step in an implementation plan.

    Attributes:
        index: Step number (1-based)
        type: Type of operation
        description: What this step accomplishes
        target: File path or command target
        details: Additional details (e.g., what to change)
        depends_on: Indices of steps this depends on
    """

    index: int
    type: StepType
    description: str
    target: str
    details: str = ""
    depends_on: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "index": self.index,
            "type": self.type.value,
            "description": self.description,
            "target": self.target,
            "details": self.details,
            "depends_on": self.depends_on,
        }


@dataclass
class ImplementationPlan:
    """Complete plan for implementing a task.

    Attributes:
        task_id: ID of the task this plan is for
        summary: Brief summary of the approach
        steps: Ordered list of implementation steps
        files_to_create: New files that will be created
        files_to_modify: Existing files that will be changed
        estimated_complexity: Overall complexity estimate
        considerations: Important notes or warnings
    """

    task_id: str
    summary: str
    steps: list[PlanStep]
    files_to_create: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    estimated_complexity: Complexity = Complexity.MEDIUM
    considerations: list[str] = field(default_factory=list)

    @property
    def total_steps(self) -> int:
        """Total number of steps."""
        return len(self.steps)

    @property
    def file_operations(self) -> list[PlanStep]:
        """Steps that involve file operations."""
        return [
            s for s in self.steps
            if s.type in {StepType.FILE_CREATE, StepType.FILE_EDIT, StepType.FILE_DELETE}
        ]

    @property
    def commands(self) -> list[PlanStep]:
        """Steps that involve shell commands."""
        return [s for s in self.steps if s.type == StepType.SHELL_COMMAND]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "steps": [s.to_dict() for s in self.steps],
            "files_to_create": self.files_to_create,
            "files_to_modify": self.files_to_modify,
            "estimated_complexity": self.estimated_complexity.value,
            "considerations": self.considerations,
        }

    def to_markdown(self) -> str:
        """Convert to markdown format for display."""
        lines = [
            f"# Implementation Plan",
            f"",
            f"**Task:** {self.task_id}",
            f"**Complexity:** {self.estimated_complexity.value}",
            f"",
            f"## Summary",
            f"{self.summary}",
            f"",
        ]

        if self.files_to_create:
            lines.append("## Files to Create")
            for f in self.files_to_create:
                lines.append(f"- `{f}`")
            lines.append("")

        if self.files_to_modify:
            lines.append("## Files to Modify")
            for f in self.files_to_modify:
                lines.append(f"- `{f}`")
            lines.append("")

        lines.append("## Steps")
        for step in self.steps:
            deps = f" (depends on: {step.depends_on})" if step.depends_on else ""
            lines.append(f"{step.index}. **[{step.type.value}]** {step.description}{deps}")
            lines.append(f"   - Target: `{step.target}`")
            if step.details:
                lines.append(f"   - Details: {step.details[:200]}")
            lines.append("")

        if self.considerations:
            lines.append("## Considerations")
            for c in self.considerations:
                lines.append(f"- {c}")

        return "\n".join(lines)


PLANNING_SYSTEM_PROMPT = """You are a software implementation planner. Your job is to analyze a task and its context, then create a detailed implementation plan.

You must return a valid JSON object with this structure:
{
    "summary": "Brief description of the implementation approach",
    "steps": [
        {
            "index": 1,
            "type": "file_create|file_edit|file_delete|shell_command|verification",
            "description": "What this step accomplishes",
            "target": "path/to/file.py or command",
            "details": "Specific changes or command arguments",
            "depends_on": []
        }
    ],
    "files_to_create": ["path/to/new/file.py"],
    "files_to_modify": ["path/to/existing/file.py"],
    "estimated_complexity": "low|medium|high",
    "considerations": ["Important note or warning"]
}

Guidelines:
1. Break work into small, focused steps (each step should do ONE thing)
2. Order steps by dependency (later steps can depend on earlier ones)
3. Include verification steps after significant changes
4. Be specific about what files to modify and what changes to make
5. Consider edge cases and potential issues
6. Keep the plan achievable - don't over-engineer

Return ONLY the JSON object, no additional text."""


class Planner:
    """Creates implementation plans from task context.

    Uses LLM to analyze requirements and generate structured plans.
    """

    def __init__(self, llm_provider: LLMProvider):
        """Initialize the planner.

        Args:
            llm_provider: LLM provider for generating plans
        """
        self.llm = llm_provider

    def create_plan(self, context: TaskContext) -> ImplementationPlan:
        """Create an implementation plan from task context.

        Args:
            context: Loaded task context

        Returns:
            ImplementationPlan with steps to execute

        Raises:
            ValueError: If plan generation fails
        """
        # Build the planning prompt
        prompt = self._build_prompt(context)

        # Call LLM with planning purpose (uses stronger model)
        response = self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.PLANNING,
            system=PLANNING_SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.0,
        )

        # Parse the response into a plan
        return self._parse_plan(response.content, context.task.id)

    def _build_prompt(self, context: TaskContext) -> str:
        """Build the planning prompt from context.

        Args:
            context: Task context

        Returns:
            Formatted prompt string
        """
        sections = []

        # Task information
        sections.append("## Task to Implement")
        sections.append(f"Title: {context.task.title}")
        if context.task.description:
            sections.append(f"Description: {context.task.description}")
        sections.append("")

        # PRD if available
        if context.prd:
            sections.append("## Product Requirements")
            # Limit PRD content to avoid overwhelming the plan
            prd_content = context.prd.content[:5000]
            sections.append(prd_content)
            sections.append("")

        # Previous clarifications
        if context.answered_blockers:
            sections.append("## Clarifications")
            for b in context.answered_blockers:
                sections.append(f"Q: {b.question}")
                sections.append(f"A: {b.answer}")
            sections.append("")

        # Repository structure
        if context.file_tree:
            sections.append("## Repository Structure")
            sections.append(f"Total files: {len(context.file_tree)}")
            # Show top relevant files
            for f in context.relevant_files[:20]:
                sections.append(f"  - {f.path}")
            sections.append("")

        # Loaded file contents
        if context.loaded_files:
            sections.append("## Relevant Source Files")
            for f in context.loaded_files[:5]:  # Limit to top 5
                sections.append(f"### {f.path}")
                sections.append("```")
                # Truncate large files in prompt
                content = f.content[:3000]
                sections.append(content)
                if len(f.content) > 3000:
                    sections.append("... (truncated)")
                sections.append("```")
                sections.append("")

        sections.append("## Instructions")
        sections.append("Create an implementation plan for this task.")
        sections.append("Return a JSON object with the plan structure.")

        return "\n".join(sections)

    def _parse_plan(self, response_text: str, task_id: str) -> ImplementationPlan:
        """Parse LLM response into an ImplementationPlan.

        Args:
            response_text: Raw LLM response
            task_id: Task ID for the plan

        Returns:
            Parsed ImplementationPlan

        Raises:
            ValueError: If parsing fails
        """
        # Try to extract JSON from response
        try:
            # Find JSON object in response
            json_match = re.search(r"\{[\s\S]*\}", response_text)
            if not json_match:
                raise ValueError("No JSON object found in response")

            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse plan JSON: {e}")

        # Build plan from parsed data
        steps = []
        for step_data in data.get("steps", []):
            step_type = self._parse_step_type(step_data.get("type", "file_edit"))
            steps.append(PlanStep(
                index=step_data.get("index", len(steps) + 1),
                type=step_type,
                description=step_data.get("description", ""),
                target=step_data.get("target", ""),
                details=step_data.get("details", ""),
                depends_on=step_data.get("depends_on", []),
            ))

        complexity = self._parse_complexity(
            data.get("estimated_complexity", "medium")
        )

        return ImplementationPlan(
            task_id=task_id,
            summary=data.get("summary", "No summary provided"),
            steps=steps,
            files_to_create=data.get("files_to_create", []),
            files_to_modify=data.get("files_to_modify", []),
            estimated_complexity=complexity,
            considerations=data.get("considerations", []),
        )

    def _parse_step_type(self, type_str: str) -> StepType:
        """Parse step type string to enum."""
        type_map = {
            "file_create": StepType.FILE_CREATE,
            "file_edit": StepType.FILE_EDIT,
            "file_delete": StepType.FILE_DELETE,
            "shell_command": StepType.SHELL_COMMAND,
            "verification": StepType.VERIFICATION,
        }
        return type_map.get(type_str.lower(), StepType.FILE_EDIT)

    def _parse_complexity(self, complexity_str: str) -> Complexity:
        """Parse complexity string to enum."""
        complexity_map = {
            "low": Complexity.LOW,
            "medium": Complexity.MEDIUM,
            "high": Complexity.HIGH,
        }
        return complexity_map.get(complexity_str.lower(), Complexity.MEDIUM)
