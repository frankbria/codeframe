"""Task context loader for CodeFRAME v2.

Builds context for agent execution by loading task, PRD, and codebase information.
Manages context window size to stay within model limits.

This module is headless - no FastAPI or HTTP dependencies.
"""

import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from codeframe.core.workspace import Workspace
from codeframe.core import tasks, prd, blockers
from codeframe.core.tasks import Task
from codeframe.core.prd import PrdRecord
from codeframe.core.blockers import Blocker, BlockerStatus
from codeframe.core.agents_config import (
    AgentPreferences,
    load_preferences,
    get_default_preferences,
)


# Approximate tokens per character (conservative estimate)
CHARS_PER_TOKEN = 4

# Default context limits
DEFAULT_MAX_TOKENS = 100_000
DEFAULT_FILE_TOKENS = 2_000

# Files to always ignore
DEFAULT_IGNORE_PATTERNS = [
    ".git/*",
    ".git",
    "__pycache__/*",
    "*.pyc",
    ".venv/*",
    "venv/*",
    "node_modules/*",
    ".next/*",
    "dist/*",
    "build/*",
    "*.egg-info/*",
    ".pytest_cache/*",
    ".mypy_cache/*",
    ".ruff_cache/*",
    "*.lock",
    "package-lock.json",
    "*.min.js",
    "*.min.css",
    ".codeframe/*",
]

# File extensions to include by default
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".java", ".kt",
    ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".swift",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".html", ".css", ".scss", ".sql",
}


@dataclass
class FileInfo:
    """Information about a source file.

    Attributes:
        path: Relative path from repo root
        size_bytes: File size in bytes
        extension: File extension
        relevance_score: How relevant to the task (0.0 - 1.0)
    """

    path: str
    size_bytes: int
    extension: str
    relevance_score: float = 0.0


@dataclass
class FileContent:
    """A file with its content loaded.

    Attributes:
        path: Relative path from repo root
        content: File content
        tokens_estimate: Estimated token count
    """

    path: str
    content: str
    tokens_estimate: int


@dataclass
class TaskContext:
    """Complete context for executing a task.

    Attributes:
        task: The task to execute
        prd: Associated PRD (if any)
        blockers: Blockers related to this task
        preferences: Agent preferences from AGENTS.md/CLAUDE.md
        file_tree: List of files in the repository
        relevant_files: Files identified as relevant to the task
        loaded_files: Files with content loaded
        total_tokens: Estimated total token count
        max_tokens: Maximum allowed tokens
    """

    task: Task
    prd: Optional[PrdRecord] = None
    blockers: list[Blocker] = field(default_factory=list)
    preferences: AgentPreferences = field(default_factory=get_default_preferences)
    file_tree: list[FileInfo] = field(default_factory=list)
    relevant_files: list[FileInfo] = field(default_factory=list)
    loaded_files: list[FileContent] = field(default_factory=list)
    total_tokens: int = 0
    max_tokens: int = DEFAULT_MAX_TOKENS

    @property
    def has_prd(self) -> bool:
        """Check if PRD is loaded."""
        return self.prd is not None

    @property
    def has_blockers(self) -> bool:
        """Check if there are any blockers."""
        return len(self.blockers) > 0

    @property
    def open_blockers(self) -> list[Blocker]:
        """Get open blockers only."""
        return [b for b in self.blockers if b.status == BlockerStatus.OPEN]

    @property
    def answered_blockers(self) -> list[Blocker]:
        """Get answered blockers (useful context)."""
        return [b for b in self.blockers if b.status == BlockerStatus.ANSWERED]

    def tokens_remaining(self) -> int:
        """Calculate remaining token budget."""
        return max(0, self.max_tokens - self.total_tokens)

    def to_prompt_context(self) -> str:
        """Convert to a formatted string for LLM prompts.

        Returns:
            Formatted context string
        """
        sections = []

        # Task section
        sections.append("## Task")
        sections.append(f"**Title:** {self.task.title}")
        if self.task.description:
            sections.append(f"**Description:** {self.task.description}")
        sections.append(f"**Status:** {self.task.status.value}")
        sections.append("")

        # PRD section
        if self.prd:
            sections.append("## Requirements (PRD)")
            sections.append(f"**Title:** {self.prd.title}")
            sections.append("")
            sections.append(self.prd.content[:10000])  # Limit PRD content
            sections.append("")

        # Project preferences section (from AGENTS.md/CLAUDE.md)
        if self.preferences and self.preferences.has_preferences():
            pref_section = self.preferences.to_prompt_section()
            if pref_section:
                sections.append(pref_section)
                sections.append("")

        # Blockers section (answered ones are useful context)
        if self.answered_blockers:
            sections.append("## Previous Clarifications")
            for b in self.answered_blockers:
                sections.append(f"**Q:** {b.question}")
                sections.append(f"**A:** {b.answer}")
                sections.append("")

        # File tree summary
        if self.file_tree:
            sections.append("## Repository Structure")
            sections.append(f"Total files: {len(self.file_tree)}")
            # Group by directory
            dirs = {}
            for f in self.file_tree[:100]:  # Limit to first 100
                dir_path = str(Path(f.path).parent)
                if dir_path not in dirs:
                    dirs[dir_path] = []
                dirs[dir_path].append(f.path)
            for dir_path in sorted(dirs.keys())[:20]:  # Limit directories
                sections.append(f"  {dir_path}/")
                for file_path in dirs[dir_path][:5]:  # Limit files per dir
                    sections.append(f"    {Path(file_path).name}")
                if len(dirs[dir_path]) > 5:
                    sections.append(f"    ... and {len(dirs[dir_path]) - 5} more")
            sections.append("")

        # Loaded file contents
        if self.loaded_files:
            sections.append("## Relevant Source Files")
            for f in self.loaded_files:
                sections.append(f"### {f.path}")
                sections.append("```")
                sections.append(f.content)
                sections.append("```")
                sections.append("")

        return "\n".join(sections)


class ContextLoader:
    """Loads and builds context for task execution.

    Handles loading task metadata, PRD content, codebase structure,
    and relevant file contents while respecting token limits.
    """

    def __init__(
        self,
        workspace: Workspace,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        ignore_patterns: Optional[list[str]] = None,
    ):
        """Initialize the context loader.

        Args:
            workspace: Target workspace
            max_tokens: Maximum tokens for context
            ignore_patterns: File patterns to ignore
        """
        self.workspace = workspace
        self.max_tokens = max_tokens
        self.ignore_patterns = ignore_patterns or DEFAULT_IGNORE_PATTERNS

    def load(self, task_id: str) -> TaskContext:
        """Load complete context for a task.

        Args:
            task_id: Task to load context for

        Returns:
            TaskContext with all loaded information

        Raises:
            ValueError: If task not found
        """
        # Load task
        task = tasks.get(self.workspace, task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        context = TaskContext(task=task, max_tokens=self.max_tokens)

        # Load agent preferences from AGENTS.md/CLAUDE.md
        context.preferences = load_preferences(self.workspace.repo_path)

        # Load PRD if associated
        if task.prd_id:
            context.prd = prd.get_by_id(self.workspace, task.prd_id)

        # Load blockers for this task
        context.blockers = blockers.list_for_task(self.workspace, task_id)

        # Build file tree
        context.file_tree = self._scan_file_tree()

        # Score and select relevant files
        context.relevant_files = self._score_relevance(
            context.file_tree, task, context.prd
        )

        # Load file contents within token budget
        self._load_file_contents(context)

        return context

    def _scan_file_tree(self) -> list[FileInfo]:
        """Scan repository for source files.

        Returns:
            List of FileInfo for all relevant files
        """
        files = []
        repo_path = self.workspace.repo_path

        for root, dirs, filenames in os.walk(repo_path):
            # Filter directories
            dirs[:] = [
                d for d in dirs
                if not self._should_ignore(os.path.join(root, d), repo_path)
            ]

            for filename in filenames:
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, repo_path)

                if self._should_ignore(file_path, repo_path):
                    continue

                ext = os.path.splitext(filename)[1].lower()
                if ext not in CODE_EXTENSIONS:
                    continue

                try:
                    size = os.path.getsize(file_path)
                    files.append(FileInfo(
                        path=rel_path,
                        size_bytes=size,
                        extension=ext,
                    ))
                except OSError:
                    continue

        return files

    def _should_ignore(self, path: str, repo_path: Path) -> bool:
        """Check if a path should be ignored.

        Args:
            path: Absolute path to check
            repo_path: Repository root path

        Returns:
            True if path should be ignored
        """
        rel_path = os.path.relpath(path, repo_path)

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            if fnmatch.fnmatch(os.path.basename(path), pattern):
                return True

        return False

    def _score_relevance(
        self,
        files: list[FileInfo],
        task: Task,
        prd_record: Optional[PrdRecord],
    ) -> list[FileInfo]:
        """Score files by relevance to the task.

        Uses keyword matching from task title/description and PRD.

        Args:
            files: Files to score
            task: Target task
            prd_record: Associated PRD (if any)

        Returns:
            Files sorted by relevance score (highest first)
        """
        # Extract keywords from task and PRD
        keywords = self._extract_keywords(task.title + " " + task.description)
        if prd_record:
            keywords.update(self._extract_keywords(prd_record.content[:5000]))

        scored_files = []
        for file_info in files:
            score = self._calculate_relevance(file_info, keywords)
            file_info.relevance_score = score
            scored_files.append(file_info)

        # Sort by relevance (highest first)
        scored_files.sort(key=lambda f: f.relevance_score, reverse=True)

        return scored_files

    def _extract_keywords(self, text: str) -> set[str]:
        """Extract meaningful keywords from text.

        Args:
            text: Text to extract keywords from

        Returns:
            Set of lowercase keywords
        """
        # Remove markdown formatting
        text = re.sub(r"[#*`\[\]()]", " ", text)

        # Split into words
        words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", text.lower())

        # Filter out common words
        stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "are", "was", "were",
            "be", "been", "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "must",
            "this", "that", "these", "those", "it", "its",
            "as", "if", "then", "else", "when", "where", "which", "who",
            "what", "how", "why", "all", "each", "every", "both", "few",
            "more", "most", "other", "some", "such", "no", "not", "only",
            "own", "same", "so", "than", "too", "very", "just", "can",
        }

        keywords = {w for w in words if len(w) > 2 and w not in stopwords}
        return keywords

    def _calculate_relevance(
        self, file_info: FileInfo, keywords: set[str]
    ) -> float:
        """Calculate relevance score for a file.

        Args:
            file_info: File to score
            keywords: Keywords to match against

        Returns:
            Relevance score (0.0 - 1.0)
        """
        score = 0.0
        path_lower = file_info.path.lower()
        path_parts = set(re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", path_lower))

        # Match keywords in path
        matches = path_parts.intersection(keywords)
        if matches:
            score += len(matches) * 0.2

        # Boost for certain file types
        if file_info.extension == ".py":
            score += 0.1
        elif file_info.extension in {".ts", ".tsx", ".js", ".jsx"}:
            score += 0.08
        elif file_info.extension == ".md":
            score += 0.05

        # Boost for key filenames
        filename = os.path.basename(file_info.path).lower()
        if filename in {"readme.md", "readme.txt"}:
            score += 0.15
        elif filename in {"main.py", "app.py", "index.ts", "index.js"}:
            score += 0.12
        elif "test" in filename:
            score += 0.05

        # Penalize very large files
        if file_info.size_bytes > 50000:
            score *= 0.5
        elif file_info.size_bytes > 20000:
            score *= 0.8

        return min(score, 1.0)

    def _load_file_contents(self, context: TaskContext) -> None:
        """Load file contents within token budget.

        Modifies context in place to add loaded_files and update total_tokens.

        Args:
            context: Context to update
        """
        # Reserve tokens for task metadata and PRD
        reserved_tokens = 0
        if context.task:
            reserved_tokens += self._estimate_tokens(
                context.task.title + context.task.description
            )
        if context.prd:
            reserved_tokens += self._estimate_tokens(context.prd.content[:10000])

        available_tokens = self.max_tokens - reserved_tokens
        context.total_tokens = reserved_tokens

        # Load files by relevance until budget exhausted
        for file_info in context.relevant_files:
            if context.tokens_remaining() < DEFAULT_FILE_TOKENS:
                break

            file_content = self._load_file(file_info)
            if file_content:
                if file_content.tokens_estimate <= context.tokens_remaining():
                    context.loaded_files.append(file_content)
                    context.total_tokens += file_content.tokens_estimate

    def _load_file(self, file_info: FileInfo) -> Optional[FileContent]:
        """Load content of a single file.

        Args:
            file_info: File to load

        Returns:
            FileContent or None if file can't be read
        """
        file_path = self.workspace.repo_path / file_info.path

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")

            # Truncate very large files
            max_chars = DEFAULT_FILE_TOKENS * CHARS_PER_TOKEN
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... (truncated)"

            return FileContent(
                path=file_info.path,
                content=content,
                tokens_estimate=self._estimate_tokens(content),
            )
        except Exception:
            return None

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // CHARS_PER_TOKEN
