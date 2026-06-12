"""ralph-claude-code project importer (issue #615).

Reads a ralph project directory and maps it onto CodeFRAME concepts:

- ``.ralph/fix_plan.md``  -> tasks (items under optional sections -> BACKLOG)
- ``.ralph/PROMPT.md``    -> PRD seed content
- ``.ralph/specs/*.md``   -> PRD seed content (appended with attribution)
- ``.ralph/AGENT.md``     -> AGENTS.md "Commands" section
- ``.ralphrc``            -> config hints (OPTIONAL_SECTIONS, ALLOWED_TOOLS)

Ralph runtime state files (``.ralph/status.json``, ``.ralph/.call_count``,
logs, ...) are never read; they are only listed in the import report as
ignored.

This module is headless - no FastAPI or UI imports.
"""

import hashlib
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from codeframe.core.state_machine import TaskStatus

# Section headings in fix_plan.md whose unchecked items do not block ralph's
# exit; they import as BACKLOG instead of READY. Overridable per project via
# OPTIONAL_SECTIONS in .ralphrc (comma-separated).
DEFAULT_OPTIONAL_SECTIONS = [
    "Optional",
    "Future",
    "Nice to Have",
    "Backlog",
    "Later",
    "Someday",
]

# Files inside .ralph/ that the importer reads; everything else is runtime
# state and is reported as ignored.
_RALPH_SOURCE_ENTRIES = {"fix_plan.md", "PROMPT.md", "AGENT.md", "specs"}

_KEY_VALUE_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
# ${VAR} and ${VAR:-default} forms found in generated .ralphrc files
_SHELL_EXPANSION_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::-([^}]*))?\}")
_HEADING_RE = re.compile(r"^(#+)\s+(.+?)\s*$")
_CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s+(.+?)\s*$")

# AGENT.md heading keywords -> AGENTS.md command keys. Ordered: first match
# wins ("Running Tests" must map to test, not dev, despite containing "run").
_COMMAND_SECTION_KEYS = [
    ("test", ("test",)),
    ("build", ("build",)),
    ("install", ("setup", "install")),
    ("dev", ("server", "dev", "run")),
]


class RalphProjectNotFoundError(Exception):
    """Raised when the given path does not contain an importable ralph project."""


@dataclass
class FixPlanItem:
    """One checkbox item from .ralph/fix_plan.md."""

    title: str
    section: str
    checked: bool
    line: int


@dataclass
class RalphProject:
    """Parsed intermediate representation of a ralph project directory."""

    root: Path
    ralphrc: dict[str, str]
    fix_plan_items: list[FixPlanItem]
    prompt: Optional[str]
    agent_md: Optional[str]
    specs: list[tuple[str, str]]
    state_files_ignored: list[str]


@dataclass
class RalphImportReport:
    """Outcome (or dry-run preview) of importing a ralph project."""

    workspace_path: Path
    dry_run: bool
    tasks_created: list[dict] = field(default_factory=list)
    tasks_skipped: list[dict] = field(default_factory=list)
    prd_action: str = "none"  # created | new_version | skipped_identical | none
    prd_title: Optional[str] = None
    agents_md_action: str = "none"  # written | skipped_exists | none
    state_files_ignored: list[str] = field(default_factory=list)


# =============================================================================
# Parsers
# =============================================================================


def parse_ralphrc(path: Path) -> dict[str, str]:
    """Parse a shell-style .ralphrc file into a flat string dict.

    Handles comments, blank lines, single/double quoting, unquoted trailing
    comments, and ``${VAR:-default}`` expansions (resolved to the default
    literal - the importer never reads the caller's environment).
    """
    if not path.is_file():
        return {}

    config: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _KEY_VALUE_RE.match(stripped)
        if not match:
            continue
        key, raw = match.group(1), match.group(2).strip()
        if raw[:1] in ("'", '"'):
            quote = raw[0]
            closing = raw.find(quote, 1)
            value = raw[1:closing] if closing != -1 else raw[1:]
        else:
            value = raw.split(" #", 1)[0].strip()
        config[key] = _SHELL_EXPANSION_RE.sub(lambda m: m.group(1) or "", value)
    return config


def parse_fix_plan(path: Path) -> list[FixPlanItem]:
    """Extract checkbox items from fix_plan.md, tracking section headings."""
    if not path.is_file():
        return []

    items: list[FixPlanItem] = []
    section = ""
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        heading = _HEADING_RE.match(line)
        if heading:
            section = heading.group(2)
            continue
        checkbox = _CHECKBOX_RE.match(line)
        if checkbox:
            items.append(
                FixPlanItem(
                    title=checkbox.group(2),
                    section=section,
                    checked=checkbox.group(1).lower() == "x",
                    line=lineno,
                )
            )
    return items


def parse_prompt_md(path: Path) -> Optional[str]:
    """Read PROMPT.md content, or None if absent."""
    return path.read_text(encoding="utf-8") if path.is_file() else None


def parse_agent_md(path: Path) -> Optional[str]:
    """Read AGENT.md content, or None if absent."""
    return path.read_text(encoding="utf-8") if path.is_file() else None


def collect_specs(specs_dir: Path) -> list[tuple[str, str]]:
    """Gather (filename, content) for spec markdown files, sorted by name."""
    if not specs_dir.is_dir():
        return []
    return [
        (spec.name, spec.read_text(encoding="utf-8"))
        for spec in sorted(specs_dir.glob("*.md"))
    ]


def load_ralph_project(path: Path) -> RalphProject:
    """Load and validate a ralph project directory.

    Raises:
        RalphProjectNotFoundError: if ``.ralph/`` is missing, or it contains
            neither fix_plan.md nor PROMPT.md.
    """
    root = Path(path).resolve()
    ralph_dir = root / ".ralph"
    if not ralph_dir.is_dir():
        raise RalphProjectNotFoundError(
            f"No ralph project found: {root} has no .ralph/ directory"
        )

    fix_plan_path = ralph_dir / "fix_plan.md"
    prompt_path = ralph_dir / "PROMPT.md"
    if not fix_plan_path.is_file() and not prompt_path.is_file():
        raise RalphProjectNotFoundError(
            f"{ralph_dir} contains neither fix_plan.md nor PROMPT.md; "
            "nothing to import"
        )

    state_files = sorted(
        entry.name
        for entry in ralph_dir.iterdir()
        if entry.name not in _RALPH_SOURCE_ENTRIES
    )

    return RalphProject(
        root=root,
        ralphrc=parse_ralphrc(root / ".ralphrc"),
        fix_plan_items=parse_fix_plan(fix_plan_path),
        prompt=parse_prompt_md(prompt_path),
        agent_md=parse_agent_md(ralph_dir / "AGENT.md"),
        specs=collect_specs(ralph_dir / "specs"),
        state_files_ignored=state_files,
    )


# =============================================================================
# Mappers
# =============================================================================


def _optional_sections(ralphrc: dict[str, str]) -> list[str]:
    raw = ralphrc.get("OPTIONAL_SECTIONS", "").strip()
    if raw:
        return [name.strip() for name in raw.split(",") if name.strip()]
    return DEFAULT_OPTIONAL_SECTIONS


def _is_optional_section(section: str, optional_sections: list[str]) -> bool:
    # Keyword containment so "Future Enhancements" matches "Future",
    # mirroring ralph's own optional-section semantics (ralph issue #239).
    lowered = section.lower()
    return any(name.lower() in lowered for name in optional_sections)


def _external_url(section: str, title: str, seen: set[str]) -> str:
    """Stable idempotency key for a fix_plan item.

    Hashes section + title (not the item's position) so re-imports stay
    idempotent when unrelated items are inserted or removed. Duplicate
    section/title pairs get an ordinal suffix.
    """
    digest = hashlib.sha1(f"{section}|{title}".encode("utf-8")).hexdigest()[:16]
    url = f"ralph://fix_plan.md#{digest}"
    ordinal = 1
    candidate = url
    while candidate in seen:
        ordinal += 1
        candidate = f"{url}-{ordinal}"
    seen.add(candidate)
    return candidate


def map_tasks(project: RalphProject) -> tuple[list[dict], list[dict]]:
    """Map fix_plan items to task specs ready for ``tasks.create()``.

    Returns:
        (mapped, skipped) - mapped task dicts in file order, and checked
        items skipped with a reason.
    """
    optional_sections = _optional_sections(project.ralphrc)
    mapped: list[dict] = []
    skipped: list[dict] = []
    seen_urls: set[str] = set()

    for item in project.fix_plan_items:
        if item.checked:
            skipped.append(
                {
                    "title": item.title,
                    "section": item.section,
                    "reason": "already completed in fix_plan.md",
                }
            )
            continue

        status = (
            TaskStatus.BACKLOG
            if _is_optional_section(item.section, optional_sections)
            else TaskStatus.READY
        )
        mapped.append(
            {
                "title": item.title,
                "description": (
                    f"Imported from .ralph/fix_plan.md "
                    f"(section: {item.section or 'top level'}, line {item.line})."
                ),
                "status": status,
                "priority": len(mapped),
                "external_url": _external_url(item.section, item.title, seen_urls),
                "section": item.section,
            }
        )

    return mapped, skipped


def map_prd_content(project: RalphProject) -> Optional[dict]:
    """Combine PROMPT.md and specs into PRD content with source attribution.

    Returns None when the project has neither.
    """
    if not project.prompt and not project.specs:
        return None

    project_name = project.ralphrc.get("PROJECT_NAME") or project.root.name
    title = f"{project_name} (imported from ralph)"
    sections = [f"# {title}"]
    sources: list[str] = []

    if project.prompt:
        sections.append(f"## Source: .ralph/PROMPT.md\n\n{project.prompt.strip()}")
        sources.append(".ralph/PROMPT.md")
    for name, content in project.specs:
        sections.append(f"## Source: .ralph/specs/{name}\n\n{content.strip()}")
        sources.append(f".ralph/specs/{name}")

    return {
        "title": title,
        "content": "\n\n".join(sections) + "\n",
        "metadata": {"ralph_import": True, "sources": sources},
    }


def _extract_agent_commands(agent_md: str) -> dict[str, str]:
    """Pull one representative command per known AGENT.md section.

    Takes the first non-comment line inside a code fence under each
    recognized heading (Setup/Tests/Build/Server).
    """
    commands: dict[str, str] = {}
    current_key: Optional[str] = None
    in_fence = False

    for line in agent_md.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            # Comment lines inside fences are bash comments, not headings.
            if current_key and current_key not in commands:
                candidate = line.strip()
                if candidate and not candidate.startswith("#"):
                    commands[current_key] = candidate
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            text = heading.group(2).lower()
            current_key = None
            for key, keywords in _COMMAND_SECTION_KEYS:
                if any(keyword in text for keyword in keywords):
                    current_key = key
                    break

    return commands


def map_agent_preferences(project: RalphProject) -> Optional[dict]:
    """Build AGENTS.md content from AGENT.md commands and ALLOWED_TOOLS.

    The output uses the standard section format parsed by
    ``codeframe.core.agents_config.load_preferences()``. Returns None when
    the project has neither source.
    """
    commands = _extract_agent_commands(project.agent_md) if project.agent_md else {}
    allowed_tools = project.ralphrc.get("ALLOWED_TOOLS", "").strip()
    if not commands and not allowed_tools:
        return None

    lines = ["# Agent Preferences (imported from ralph)", ""]
    if commands:
        lines += ["## Commands", ""]
        lines += [f"- **{key}**: {value}" for key, value in commands.items()]
        lines.append("")
    if allowed_tools:
        lines += [
            "## Always Do",
            "",
            f"- Use the tools ralph permitted (ALLOWED_TOOLS): {allowed_tools}",
            "",
        ]

    return {
        "title": "Agent Preferences (imported from ralph)",
        "content": "\n".join(lines),
        "metadata": {"ralph_import": True},
    }


# =============================================================================
# Import orchestration
# =============================================================================


def _find_ralph_prd(workspace, prd_module):
    """Find the most recent PRD previously imported from ralph, if any."""
    for record in prd_module.list_all(workspace):
        if record.metadata.get("ralph_import"):
            return record
    return None


def import_ralph_project(
    ralph_path: Path,
    workspace_path: Optional[Path] = None,
    dry_run: bool = False,
) -> RalphImportReport:
    """Import a ralph project into a CodeFRAME workspace.

    Idempotent: re-runs skip tasks already imported (keyed on
    ``external_url``), skip the PRD when its content is unchanged (new
    version when it changed), and never overwrite an existing AGENTS.md.

    Args:
        ralph_path: Root of the ralph project (contains ``.ralph/``).
        workspace_path: Target CodeFRAME workspace root. Defaults to the
            ralph project root (import in place).
        dry_run: When True, compute the full mapping report without
            creating the workspace or writing anything.

    Returns:
        RalphImportReport describing what was created, skipped, and ignored.

    Raises:
        RalphProjectNotFoundError: if ``ralph_path`` is not a ralph project.
    """
    from codeframe.core import prd, tasks
    from codeframe.core.workspace import (
        create_or_load_workspace,
        get_workspace,
        workspace_exists,
    )

    project = load_ralph_project(Path(ralph_path))
    target = Path(workspace_path).resolve() if workspace_path else project.root

    mapped_tasks, mapping_skipped = map_tasks(project)
    prd_mapping = map_prd_content(project)
    agents_mapping = map_agent_preferences(project)

    report = RalphImportReport(
        workspace_path=target,
        dry_run=dry_run,
        tasks_skipped=list(mapping_skipped),
        state_files_ignored=list(project.state_files_ignored),
    )

    workspace = None
    if dry_run:
        if workspace_exists(target):
            workspace = get_workspace(target)
    else:
        workspace = create_or_load_workspace(target)

    # PRD first so created tasks can link to it via prd_id.
    prd_id: Optional[str] = None
    if prd_mapping is not None:
        existing = _find_ralph_prd(workspace, prd) if workspace else None
        if existing is None:
            report.prd_action = "created"
            report.prd_title = prd_mapping["title"]
            if not dry_run:
                record = prd.store(
                    workspace,
                    prd_mapping["content"],
                    title=prd_mapping["title"],
                    metadata=prd_mapping["metadata"],
                )
                prd_id = record.id
        elif existing.content == prd_mapping["content"]:
            report.prd_action = "skipped_identical"
            report.prd_title = existing.title
            prd_id = existing.id
        else:
            report.prd_action = "new_version"
            report.prd_title = existing.title
            if not dry_run:
                record = prd.create_new_version(
                    workspace,
                    existing.id,
                    prd_mapping["content"],
                    change_summary="Re-imported from ralph (source files changed)",
                )
                prd_id = record.id if record else existing.id

    for spec in mapped_tasks:
        already = (
            tasks.get_by_external_url(workspace, spec["external_url"])
            if workspace
            else None
        )
        if already is not None:
            report.tasks_skipped.append(
                {
                    "title": spec["title"],
                    "section": spec["section"],
                    "reason": "already imported",
                }
            )
            continue
        if not dry_run:
            try:
                tasks.create(
                    workspace,
                    title=spec["title"],
                    description=spec["description"],
                    status=spec["status"],
                    priority=spec["priority"],
                    prd_id=prd_id,
                    external_url=spec["external_url"],
                )
            except sqlite3.IntegrityError:
                # Lost a race with a concurrent import of the same item; the
                # UNIQUE(workspace_id, external_url) index makes this safe.
                report.tasks_skipped.append(
                    {
                        "title": spec["title"],
                        "section": spec["section"],
                        "reason": "already imported",
                    }
                )
                continue
        report.tasks_created.append(spec)

    if agents_mapping is not None:
        agents_path = target / "AGENTS.md"
        if agents_path.exists():
            report.agents_md_action = "skipped_exists"
        else:
            report.agents_md_action = "written"
            if not dry_run:
                agents_path.write_text(
                    agents_mapping["content"], encoding="utf-8"
                )

    return report
