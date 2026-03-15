"""Agent preferences loader for CodeFRAME v2.

Loads project-level preferences from CODEFRAME.md, AGENTS.md, and CLAUDE.md files.
These preferences guide agent decision-making for tactical choices like
tooling, file handling, and code style.

CODEFRAME.md supports YAML front matter for typed configuration (engine, gates,
batch settings, hooks) plus a Markdown body for agent instructions.

Supports the AGENTS.md industry standard (OpenAI, Google, GitHub, Anthropic)
as well as CLAUDE.md for Anthropic-specific instructions.

This module is headless - no FastAPI or HTTP dependencies.

References:
- https://agents.md/
- https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AgentPreferences:
    """Project-level preferences for agent decision-making.

    Attributes:
        always_do: Safe autonomous actions the agent should take without asking
        ask_first: Genuinely risky decisions requiring user confirmation
        never_do: Forbidden actions the agent must not perform
        tooling: Tool preferences (e.g., package_manager, test_runner)
        code_style: Code style conventions and formatting preferences
        commands: Executable commands (build, test, lint, etc.)
        raw_content: Original markdown content for passing to LLM
        source_files: List of files that contributed to these preferences
    """

    always_do: list[str] = field(default_factory=list)
    ask_first: list[str] = field(default_factory=list)
    never_do: list[str] = field(default_factory=list)
    tooling: dict[str, str] = field(default_factory=dict)
    code_style: dict[str, str] = field(default_factory=dict)
    commands: dict[str, str] = field(default_factory=dict)
    raw_content: str = ""
    source_files: list[str] = field(default_factory=list)

    def has_preferences(self) -> bool:
        """Check if any preferences are loaded."""
        return bool(
            self.always_do
            or self.ask_first
            or self.never_do
            or self.tooling
            or self.commands
            or self.raw_content
        )

    def to_prompt_section(self) -> str:
        """Convert preferences to a prompt section for LLM.

        Returns:
            Formatted markdown section for inclusion in prompts
        """
        if not self.has_preferences():
            return ""

        sections = ["## Project Preferences"]

        if self.tooling:
            sections.append("\n### Tooling")
            for key, value in self.tooling.items():
                sections.append(f"- **{key}**: {value}")

        if self.commands:
            sections.append("\n### Commands")
            for key, value in self.commands.items():
                sections.append(f"- **{key}**: `{value}`")

        if self.always_do:
            sections.append("\n### Always Do (autonomous actions)")
            for item in self.always_do:
                sections.append(f"- {item}")

        if self.ask_first:
            sections.append("\n### Ask First (require confirmation)")
            for item in self.ask_first:
                sections.append(f"- {item}")

        if self.never_do:
            sections.append("\n### Never Do (forbidden)")
            for item in self.never_do:
                sections.append(f"- {item}")

        if self.code_style:
            sections.append("\n### Code Style")
            for key, value in self.code_style.items():
                sections.append(f"- **{key}**: {value}")

        return "\n".join(sections)


@dataclass
class CodeframeConfig:
    """Typed configuration from CODEFRAME.md YAML front matter.

    Attributes:
        engine: Execution engine (react, plan, claude-code, etc.)
        tech_stack: Natural language tech stack description
        batch: Batch execution settings (max_parallel, default_strategy)
        gates: Verification gates to run (ruff, pytest, mypy, etc.)
        hooks: Lifecycle hooks (before_task, after_task, on_failure, etc.)
        agent: Agent tuning parameters (max_iterations, verbose, etc.)
        raw: Full parsed YAML dict for extensibility
    """

    engine: Optional[str] = None
    tech_stack: Optional[str] = None
    batch: dict = field(default_factory=dict)
    gates: list[str] = field(default_factory=list)
    hooks: dict = field(default_factory=dict)
    agent: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


# Section header patterns for parsing AGENTS.md content
SECTION_PATTERNS = {
    "always_do": re.compile(
        r"#+\s*(?:always\s*do|autonomous|safe\s*actions?)", re.IGNORECASE
    ),
    "ask_first": re.compile(
        r"#+\s*(?:ask\s*first|require\s*confirmation|risky)", re.IGNORECASE
    ),
    "never_do": re.compile(
        r"#+\s*(?:never\s*do|forbidden|prohibited|don't|do\s*not)", re.IGNORECASE
    ),
    "tooling": re.compile(r"#+\s*(?:tooling|tools|preferences)", re.IGNORECASE),
    "commands": re.compile(r"#+\s*(?:commands?|scripts?|build)", re.IGNORECASE),
    "code_style": re.compile(r"#+\s*(?:code\s*style|style|conventions?)", re.IGNORECASE),
}


def _parse_list_items(content: str) -> list[str]:
    """Extract list items from markdown content.

    Args:
        content: Markdown text that may contain list items

    Returns:
        List of extracted items (without bullet prefixes)
    """
    items = []
    for line in content.split("\n"):
        line = line.strip()
        # Match bullet points: -, *, or numbered lists
        if line.startswith(("-", "*", "•")):
            item = line.lstrip("-*• ").strip()
            if item:
                items.append(item)
        elif re.match(r"^\d+\.", line):
            item = re.sub(r"^\d+\.\s*", "", line).strip()
            if item:
                items.append(item)
    return items


def _parse_key_value_items(content: str) -> dict[str, str]:
    """Extract key-value pairs from markdown content.

    Supports formats:
    - **key**: value
    - `key`: value
    - key: value

    Args:
        content: Markdown text with key-value pairs

    Returns:
        Dictionary of key-value pairs
    """
    items = {}
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Strip list markers carefully - don't strip markdown bold asterisks
        # Match patterns like "- " or "* " at start (with space after)
        list_marker_match = re.match(r"^[-*•]\s+", line)
        if list_marker_match:
            line = line[list_marker_match.end():]

        # Try different key-value formats
        # **key**: value
        match = re.match(r"\*\*([^*]+)\*\*:\s*(.+)", line)
        if match:
            items[match.group(1).strip().lower().replace(" ", "_")] = match.group(
                2
            ).strip()
            continue

        # `key`: value
        match = re.match(r"`([^`]+)`:\s*(.+)", line)
        if match:
            items[match.group(1).strip().lower().replace(" ", "_")] = match.group(
                2
            ).strip()
            continue

        # key: value (simple format)
        if ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                key = parts[0].strip().lower().replace(" ", "_")
                value = parts[1].strip()
                if key and value:
                    items[key] = value

    return items


def _split_by_sections(content: str) -> dict[str, str]:
    """Split markdown content by section headers.

    Args:
        content: Full markdown content

    Returns:
        Dictionary mapping section names to their content
    """
    sections = {}
    current_section = None
    current_content = []

    for line in content.split("\n"):
        # Check if this is a header line
        if line.startswith("#"):
            # Save previous section
            if current_section:
                sections[current_section] = "\n".join(current_content)

            # Identify new section
            current_section = None
            for section_name, pattern in SECTION_PATTERNS.items():
                if pattern.search(line):
                    current_section = section_name
                    current_content = []
                    break

            if current_section is None:
                # Unknown section, capture as raw
                current_section = "unknown"
                current_content = [line]
        else:
            current_content.append(line)

    # Save final section
    if current_section:
        sections[current_section] = "\n".join(current_content)

    return sections


def _parse_agents_md(content: str) -> AgentPreferences:
    """Parse AGENTS.md content into structured preferences.

    Args:
        content: Raw markdown content from AGENTS.md

    Returns:
        Parsed AgentPreferences
    """
    prefs = AgentPreferences(raw_content=content)

    sections = _split_by_sections(content)

    if "always_do" in sections:
        prefs.always_do = _parse_list_items(sections["always_do"])

    if "ask_first" in sections:
        prefs.ask_first = _parse_list_items(sections["ask_first"])

    if "never_do" in sections:
        prefs.never_do = _parse_list_items(sections["never_do"])

    if "tooling" in sections:
        prefs.tooling = _parse_key_value_items(sections["tooling"])

    if "commands" in sections:
        prefs.commands = _parse_key_value_items(sections["commands"])

    if "code_style" in sections:
        prefs.code_style = _parse_key_value_items(sections["code_style"])

    return prefs


def parse_codeframe_md(content: str) -> tuple[CodeframeConfig, AgentPreferences]:
    """Parse a CODEFRAME.md file with YAML front matter + Markdown body.

    The file format is:
    ---
    engine: react
    tech_stack: "Python with uv"
    batch:
      max_parallel: 4
    gates:
      - ruff
      - pytest
    hooks:
      before_task: "git checkout -b cf/{{task_id}}"
    agent:
      max_iterations: 30
    ---

    # Project Instructions
    Markdown content here becomes the agent system prompt supplement...

    Returns:
        Tuple of (CodeframeConfig, AgentPreferences)
        CodeframeConfig has the typed YAML settings
        AgentPreferences has the Markdown body as raw_content + any extracted sections
    """
    config = CodeframeConfig()
    prefs = AgentPreferences()

    if not content or not content.strip():
        return config, prefs

    # Extract YAML front matter between --- markers
    yaml_data = {}
    body = content

    stripped = content.strip()
    if stripped.startswith("---"):
        # Find the closing --- marker (skip the opening one)
        after_opening = stripped[3:]
        closing_idx = after_opening.find("\n---")
        if closing_idx >= 0:
            yaml_text = after_opening[:closing_idx].strip()
            # Body starts after the closing ---
            rest = after_opening[closing_idx + 4:]  # skip "\n---"
            body = rest.strip()

            # Parse YAML
            try:
                parsed = yaml.safe_load(yaml_text)
                if isinstance(parsed, dict):
                    yaml_data = parsed
            except yaml.YAMLError:
                logger.warning("Invalid YAML front matter in CODEFRAME.md, skipping")
                body = content  # Treat entire content as body on YAML failure
        else:
            # No closing --- found, treat entire content as body
            body = content

    # Build CodeframeConfig from YAML
    if yaml_data:
        config = CodeframeConfig(
            engine=yaml_data.get("engine"),
            tech_stack=yaml_data.get("tech_stack"),
            batch=yaml_data.get("batch") or {},
            gates=yaml_data.get("gates") or [],
            hooks=yaml_data.get("hooks") or {},
            agent=yaml_data.get("agent") or {},
            raw=yaml_data,
        )

    # Parse Markdown body for AgentPreferences
    if body:
        prefs = _parse_agents_md(body)
    prefs.source_files = ["CODEFRAME.md"]

    # Cross-populate tech_stack into preferences tooling
    if config.tech_stack:
        prefs.tooling["tech_stack"] = config.tech_stack

    return config, prefs


def _merge_preferences(
    base: AgentPreferences, override: AgentPreferences
) -> AgentPreferences:
    """Merge two preference objects, with override taking precedence.

    Args:
        base: Base preferences
        override: Overriding preferences (higher priority)

    Returns:
        Merged AgentPreferences
    """
    return AgentPreferences(
        always_do=override.always_do if override.always_do else base.always_do,
        ask_first=override.ask_first if override.ask_first else base.ask_first,
        never_do=override.never_do if override.never_do else base.never_do,
        tooling={**base.tooling, **override.tooling},
        code_style={**base.code_style, **override.code_style},
        commands={**base.commands, **override.commands},
        raw_content=override.raw_content or base.raw_content,
        source_files=base.source_files + override.source_files,
    )


def load_preferences(workspace_path: Path) -> AgentPreferences:
    """Load and merge agent preferences from CODEFRAME.md, AGENTS.md, and CLAUDE.md.

    Search order (closest wins):
    1. workspace_path/CODEFRAME.md (highest priority)
    2. workspace_path/AGENTS.md
    3. workspace_path/CLAUDE.md (lowest priority)
    4. Parent directories (walking up, same precedence order)
    5. ~/.codeframe/AGENTS.md (global defaults)

    At each directory level, CODEFRAME.md > AGENTS.md > CLAUDE.md.

    Args:
        workspace_path: Path to the workspace/repository root

    Returns:
        Merged AgentPreferences from all found files
    """
    workspace_path = Path(workspace_path).resolve()
    prefs = AgentPreferences()
    found_files = []

    # Search order: global defaults first, then walk up to workspace (closest wins)
    search_paths: list[tuple[Path, bool]] = []  # (path, is_codeframe_md)

    # 1. Global defaults (lowest priority)
    global_config = Path.home() / ".codeframe" / "AGENTS.md"
    if global_config.exists():
        search_paths.append((global_config, False))

    # 2. Walk from root to workspace (so workspace files override parents)
    current = workspace_path
    path_chain = []
    while current != current.parent:
        path_chain.append(current)
        current = current.parent

    # Reverse so we go from ancestors to workspace (closest wins)
    for dir_path in reversed(path_chain):
        # CLAUDE.md first (lowest priority at same level)
        claude_md = dir_path / "CLAUDE.md"
        if claude_md.exists():
            search_paths.append((claude_md, False))

        # AGENTS.md second (medium priority at same level)
        agents_md = dir_path / "AGENTS.md"
        if agents_md.exists():
            search_paths.append((agents_md, False))

        # CODEFRAME.md third (highest priority at same level)
        codeframe_md = dir_path / "CODEFRAME.md"
        if codeframe_md.exists():
            search_paths.append((codeframe_md, True))

    # Process all found files
    for file_path, is_codeframe in search_paths:
        try:
            content = file_path.read_text(encoding="utf-8")
            if is_codeframe:
                _, file_prefs = parse_codeframe_md(content)
                file_prefs.source_files = [str(file_path)]
            else:
                file_prefs = _parse_agents_md(content)
                file_prefs.source_files = [str(file_path)]
            prefs = _merge_preferences(prefs, file_prefs)
            found_files.append(str(file_path))
        except (OSError, UnicodeDecodeError):
            # Log but don't fail on file read errors
            pass

    # If no config files were found, use sensible defaults
    if not prefs.has_preferences():
        return get_default_preferences()

    return prefs


def get_default_preferences() -> AgentPreferences:
    """Get sensible default preferences when no AGENTS.md exists.

    These defaults encourage autonomous decision-making for tactical choices
    while preserving caution for genuinely risky operations.

    Returns:
        Default AgentPreferences
    """
    return AgentPreferences(
        always_do=[
            "Choose between equivalent implementation approaches",
            "Decide file organization and naming",
            "Select library versions (prefer latest stable)",
            "Handle existing files (overwrite, merge, or extend as appropriate)",
            "Choose test frameworks and configurations",
            "Make code style decisions following existing patterns",
            "Install dependencies using the detected package manager",
            "Create directories as needed",
            "Fix linting errors automatically",
        ],
        ask_first=[
            "Delete critical configuration files",
            "Make breaking API changes",
            "Modify security-sensitive code without explicit request",
            "Remove or disable tests",
            "Change database schemas in production",
        ],
        never_do=[
            "Commit secrets, API keys, or credentials",
            "Delete .git directory or history",
            "Push to main/master without explicit permission",
            "Modify files outside the workspace",
            "Execute commands that could cause data loss",
            "Bypass security checks or validation",
        ],
        tooling={
            "package_manager": "detect from lockfiles (uv > pip for Python, npm > yarn for JS)",
            "test_runner": "detect from project (pytest for Python, jest for JS)",
            "linter": "detect from project (ruff for Python, eslint for JS)",
        },
        commands={
            "python_install": "uv sync",
            "python_test": "uv run pytest",
            "python_lint": "uv run ruff check --fix .",
            "js_install": "npm install",
            "js_test": "npm test",
            "js_lint": "npm run lint",
        },
        raw_content="",
        source_files=["<defaults>"],
    )


def get_codeframe_config(workspace_path: Path) -> Optional[CodeframeConfig]:
    """Load CodeframeConfig from CODEFRAME.md if present.

    Searches for CODEFRAME.md starting from workspace_path, walking up to root.
    Returns None if no CODEFRAME.md is found.

    Args:
        workspace_path: Path to the workspace/repository root

    Returns:
        CodeframeConfig if CODEFRAME.md is found, None otherwise
    """
    workspace_path = Path(workspace_path).resolve()

    current = workspace_path
    while current != current.parent:
        codeframe_md = current / "CODEFRAME.md"
        if codeframe_md.exists():
            try:
                content = codeframe_md.read_text(encoding="utf-8")
                config, _ = parse_codeframe_md(content)
                return config
            except (OSError, UnicodeDecodeError):
                return None
        current = current.parent

    return None
