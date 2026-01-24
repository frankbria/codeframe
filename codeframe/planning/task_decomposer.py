"""Task Decomposition from Issues.

This module handles decomposing high-level issues into atomic tasks with
sequential dependencies. Following the hierarchical numbering scheme from
CONCEPTS_RESOLVED.md.

Key Rules:
- Tasks within an issue are SEQUENTIAL (cannot parallelize)
- Each task depends on the previous task
- can_parallelize is ALWAYS FALSE within an issue
- Task numbers follow pattern: {issue_number}.{task_idx}
"""

import logging
import re
from typing import List
from codeframe.core.models import Issue, Task, TaskStatus
from codeframe.providers.anthropic import AnthropicProvider


logger = logging.getLogger(__name__)


class TaskDecomposer:
    """Decomposes issues into atomic tasks with sequential dependencies."""

    def __init__(self):
        """Initialize TaskDecomposer."""
        logger.debug("Initialized TaskDecomposer")

    def decompose_issue(self, issue: Issue, provider: AnthropicProvider) -> List[Task]:
        """Decompose issue into atomic tasks with sequential dependencies.

        Args:
            issue: Issue to decompose
            provider: AnthropicProvider for LLM-powered decomposition

        Returns:
            List of Task objects with sequential numbering and dependencies

        Raises:
            ValueError: If issue is invalid or decomposition fails
        """
        # Validate issue
        if not issue.issue_number or not issue.title:
            raise ValueError("Issue must have issue_number and title")

        logger.info(f"Decomposing issue {issue.issue_number}: {issue.title}")

        # Build decomposition prompt
        prompt = self.build_decomposition_prompt(issue)

        # Send to Claude API
        try:
            response = provider.send_message([{"role": "user", "content": prompt}])

            claude_response = response["content"]

            # Log token usage
            usage = response.get("usage", {})
            logger.debug(
                f"Token usage - Input: {usage.get('input_tokens', 0)}, "
                f"Output: {usage.get('output_tokens', 0)}"
            )

        except Exception as e:
            logger.error(f"Failed to decompose issue via Claude: {e}", exc_info=True)
            raise

        # Parse Claude response into tasks
        tasks = self.parse_claude_response(claude_response, issue)

        # Create dependency chain
        tasks = self.create_dependency_chain(tasks)

        logger.info(f"Decomposed issue {issue.issue_number} into {len(tasks)} tasks")
        return tasks

    def build_decomposition_prompt(self, issue: Issue) -> str:
        """Build prompt for Claude to decompose issue into tasks with effort estimation.

        Args:
            issue: Issue to decompose

        Returns:
            Prompt string for Claude API with effort estimation requirements
        """
        prompt = f"""You are a technical project manager decomposing a software development issue into atomic tasks.

**Issue to Decompose:**
Title: {issue.title}
Description: {issue.description}

**Requirements:**
1. Break down the issue into 3-8 atomic, actionable tasks
2. Each task should be independently implementable and testable
3. Tasks should be ordered logically (dependencies will be handled automatically)
4. For simple issues, use 3-4 tasks; for complex issues, use 6-8 tasks
5. Each task should have a clear, concise title and detailed description

**Effort Estimation Requirements:**
For each task, provide:
- Complexity: Rate complexity from 1-5 (1=trivial, 2=simple, 3=moderate, 4=complex, 5=very complex)
- Estimated Hours: Time estimate in hours based on task scope
- Uncertainty: Assessment of estimate confidence (low, medium, or high)

**Output Format:**
For each task, use this format:

1. Task Title - Brief description of what to do
   Complexity: [1-5]
   Estimated Hours: [number]
   Uncertainty: [low/medium/high]

Example:
1. Create User model - Implement User database model with fields: username, email, password_hash
   Complexity: 2
   Estimated Hours: 2
   Uncertainty: low

2. Implement password hashing - Add bcrypt hashing for secure password storage
   Complexity: 3
   Estimated Hours: 3
   Uncertainty: low

3. Create login endpoint - Implement POST /api/login with JWT token generation
   Complexity: 4
   Estimated Hours: 5
   Uncertainty: medium

Now decompose the issue above into {self._estimate_task_count(issue)} atomic tasks with effort estimates:"""

        return prompt

    def parse_claude_response(self, response: str, issue: Issue) -> List[Task]:
        """Parse Claude response into Task objects with effort estimation.

        Args:
            response: Claude API response text
            issue: Parent issue for tasks

        Returns:
            List of Task objects with effort estimation fields populated

        Raises:
            ValueError: If response is empty or invalid
        """
        if not response or not response.strip():
            raise ValueError("Empty response from Claude API")

        # Split response into task blocks (each starting with a number)
        task_blocks = self._split_into_task_blocks(response)

        if not task_blocks:
            raise ValueError("No tasks found in Claude response")

        tasks = []
        for idx, block in enumerate(task_blocks, start=1):
            # Parse title and description from the first line
            title, description = self._parse_task_title_description(block)

            if not title:
                continue

            # Parse effort estimation data
            complexity = self._parse_complexity(block)
            estimated_hours = self._parse_estimated_hours(block)
            uncertainty = self._parse_uncertainty(block)

            # Create task number: {issue_number}.{task_idx}
            task_number = f"{issue.issue_number}.{idx}"

            task = Task(
                project_id=issue.project_id,
                issue_id=issue.id,
                task_number=task_number,
                parent_issue_number=issue.issue_number,
                title=title,
                description=description,
                status=TaskStatus.PENDING,
                depends_on="",  # Will be set in create_dependency_chain
                can_parallelize=False,  # Always FALSE within issue
                priority=issue.priority,
                workflow_step=issue.workflow_step,
                complexity_score=complexity,
                estimated_hours=estimated_hours,
                uncertainty_level=uncertainty,
            )

            tasks.append(task)

        if not tasks:
            raise ValueError("Failed to parse tasks from Claude response")

        # Enforce 3-8 tasks limit
        if len(tasks) < 3:
            logger.warning(f"Only {len(tasks)} tasks generated, minimum is 3")
        elif len(tasks) > 8:
            logger.warning(f"Too many tasks generated ({len(tasks)}), truncating to 8")
            tasks = tasks[:8]
            # Renumber truncated tasks
            for idx, task in enumerate(tasks, start=1):
                task.task_number = f"{issue.issue_number}.{idx}"

        logger.debug(f"Parsed {len(tasks)} tasks from Claude response")
        return tasks

    def _split_into_task_blocks(self, response: str) -> List[str]:
        """Split response into individual task blocks.

        Args:
            response: Full Claude response

        Returns:
            List of task block strings
        """
        # Split on task number patterns (e.g., "1.", "2.", "Task 1:", etc.)
        # Allow optional leading whitespace
        pattern = r"(?:^|\n)\s*(?:Task\s+)?(\d+)[.):]\s*"
        parts = re.split(pattern, response, flags=re.MULTILINE | re.IGNORECASE)

        # Reconstruct blocks (alternating: empty/preamble, number, content, number, content...)
        blocks = []
        i = 1  # Skip first part (preamble before first task)
        while i < len(parts):
            if i < len(parts) and parts[i].isdigit():
                block = parts[i + 1] if i + 1 < len(parts) else ""
                blocks.append(block)
                i += 2
            else:
                i += 1

        return blocks

    def _parse_task_title_description(self, block: str) -> tuple:
        """Parse task title and description from a task block.

        Args:
            block: Single task block text

        Returns:
            Tuple of (title, description)
        """
        lines = block.strip().split("\n")
        if not lines:
            return "", ""

        first_line = lines[0].strip()

        # Check for "Title - Description" format
        if " - " in first_line:
            parts = first_line.split(" - ", 1)
            title = parts[0].strip()
            description = parts[1].strip() if len(parts) > 1 else title
        else:
            title = first_line
            description = title

        return title, description

    def _parse_complexity(self, block: str) -> int | None:
        """Parse complexity score from task block.

        Args:
            block: Single task block text

        Returns:
            Complexity score (1-5) or None if not found
        """
        # Match "Complexity: 3" or "Complexity: 5" patterns
        pattern = r"(?:^|\n)\s*Complexity:\s*(\d+)"
        match = re.search(pattern, block, re.IGNORECASE)

        if match:
            try:
                score = int(match.group(1))
                # Normalize to 1-5 range
                if score < 1:
                    return 1
                elif score > 5:
                    return 5
                return score
            except ValueError:
                return None
        return None

    def _parse_estimated_hours(self, block: str) -> float | None:
        """Parse estimated hours from task block.

        Args:
            block: Single task block text

        Returns:
            Estimated hours or None if not found
        """
        # Match "Estimated Hours: 2.5" or "Estimated Hours: 3" patterns
        pattern = r"(?:^|\n)\s*Estimated\s*Hours:\s*(\d+(?:\.\d+)?)"
        match = re.search(pattern, block, re.IGNORECASE)

        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None

    def _parse_uncertainty(self, block: str) -> str | None:
        """Parse uncertainty level from task block.

        Args:
            block: Single task block text

        Returns:
            Uncertainty level ("low", "medium", "high") or None if not found
        """
        # Match "Uncertainty: low" or "Uncertainty: medium" patterns
        pattern = r"(?:^|\n)\s*Uncertainty:\s*(low|medium|high)"
        match = re.search(pattern, block, re.IGNORECASE)

        if match:
            return match.group(1).lower()
        return None

    def create_dependency_chain(self, tasks: List[Task]) -> List[Task]:
        """Create sequential dependency chain for tasks.

        Each task depends on the previous task (except the first).

        Args:
            tasks: List of tasks (in order)

        Returns:
            List of tasks with dependencies set
        """
        if not tasks:
            return tasks

        # First task has no dependencies
        tasks[0].depends_on = ""

        # Each subsequent task depends on the previous one
        for idx in range(1, len(tasks)):
            prev_task = tasks[idx - 1]
            tasks[idx].depends_on = prev_task.task_number

        logger.debug(f"Created dependency chain for {len(tasks)} tasks")
        return tasks

    def _estimate_task_count(self, issue: Issue) -> str:
        """Estimate appropriate task count based on issue complexity.

        Args:
            issue: Issue to analyze

        Returns:
            Suggested task count range as string (e.g., "3-4" or "6-8")
        """
        # Simple heuristic based on description length
        desc_length = len(issue.description) if issue.description else 0

        if desc_length < 100:
            return "3-4"
        elif desc_length < 300:
            return "4-6"
        else:
            return "6-8"
