"""PRD stress test via recursive decomposition.

Recursively decomposes PRD goals using a tri-state classification
(atomic / composite / ambiguous) to surface requirements gaps and
generate a technical specification. This is a human-facing discovery
tool — not a task generator.

This module is headless — no FastAPI or HTTP dependencies.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from codeframe.adapters.llm.base import Purpose

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class Classification(str, Enum):
    ATOMIC = "atomic"
    COMPOSITE = "composite"
    AMBIGUOUS = "ambiguous"


@dataclass
class DecompositionNode:
    id: str
    title: str
    description: str
    classification: Classification
    children: list["DecompositionNode"]
    lineage: list[str]
    depth: int
    complexity_hint: Optional[str] = None
    ambiguity_id: Optional[str] = None


@dataclass
class Ambiguity:
    id: str
    label: str
    source_node_title: str
    questions: list[str]
    recommendation: str
    resolved_answer: Optional[str] = None


@dataclass
class StressTestResult:
    prd_title: str
    tree: list[DecompositionNode]
    ambiguities: list[Ambiguity]
    tech_spec_markdown: str
    ambiguity_report: str


# ---------------------------------------------------------------------------
# Prompt Constants
# ---------------------------------------------------------------------------


GOAL_EXTRACTION_SYSTEM = (
    "You are a requirements analyst. Given a Product Requirements Document, "
    "extract the high-level deliverable goals — the major features or systems "
    "that need to be built. Return ONLY a JSON array of short goal strings. "
    "Example: [\"User Authentication\", \"Invoice Management\", \"PDF Export\"]"
)

CLASSIFY_AND_DECOMPOSE_SYSTEM = """\
You are a recursive requirements decomposer. Given a goal, its context (lineage \
of ancestor goals), and the original PRD, classify the goal into exactly one of:

- "atomic": Small enough to implement directly (1-2 days of work). The PRD \
provides enough detail.
- "composite": Clearly needs breakdown into sub-goals. The PRD provides \
enough detail to know what the pieces are.
- "ambiguous": You CANNOT confidently classify because the PRD is missing \
critical information. You must explain what's missing.

Return a JSON object with these fields:
{
  "classification": "atomic" | "composite" | "ambiguous",
  "children": [{"title": "...", "description": "..."}],  // only if composite
  "ambiguity_label": "SHORT LABEL",                       // only if ambiguous
  "questions": ["question 1", "question 2"],              // only if ambiguous
  "recommendation": "what to add to the PRD",             // only if ambiguous
  "complexity_hint": "Low" | "Low-Medium" | "Medium" | "High"  // always
}

Return ONLY valid JSON. No markdown wrapping."""

AMBIGUITY_RESOLUTION_SYSTEM = (
    "You are a PRD editor. Given the original PRD content and a set of resolved "
    "ambiguities (question + answer pairs), update the PRD to incorporate the "
    "new information. Preserve the original structure and tone. Return the "
    "complete updated PRD content."
)


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------


def extract_goals(prd_content: str, provider) -> list[str]:
    """Extract high-level deliverable goals from a PRD."""
    response = provider.complete(
        messages=[{"role": "user", "content": prd_content}],
        purpose=Purpose.PLANNING,
        system=GOAL_EXTRACTION_SYSTEM,
        max_tokens=1024,
        temperature=0.0,
    )
    try:
        goals = json.loads(response.content)
        if isinstance(goals, list):
            return [str(g) for g in goals]
        logger.warning("Goal extraction returned non-list: %s", type(goals).__name__)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse goal extraction response: %s", exc)
    return []


def classify_and_decompose(
    title: str,
    description: str,
    lineage: list[str],
    prd_content: str,
    depth: int,
    provider,
) -> tuple[Classification, list[dict], Optional[Ambiguity], str]:
    """Classify a goal node and optionally decompose or flag ambiguity."""
    lineage_ctx = ""
    if lineage:
        lineage_ctx = "\n\nAncestor context:\n" + "\n".join(
            f"- {desc}" for desc in lineage
        )

    user_msg = (
        f"Goal: {title}\n"
        f"Description: {description}\n"
        f"Depth: {depth}{lineage_ctx}\n\n"
        f"PRD:\n{prd_content}"
    )

    response = provider.complete(
        messages=[{"role": "user", "content": user_msg}],
        purpose=Purpose.PLANNING,
        system=CLASSIFY_AND_DECOMPOSE_SYSTEM,
        max_tokens=2048,
        temperature=0.0,
    )

    try:
        data = json.loads(response.content)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Failed to parse classification for '%s': %s", title, exc)
        return Classification.ATOMIC, [], None, "Low"

    raw_cls = data.get("classification", "atomic").lower()
    try:
        cls = Classification(raw_cls)
    except ValueError:
        cls = Classification.ATOMIC

    complexity = data.get("complexity_hint", "Low")
    raw_children = data.get("children", []) if cls == Classification.COMPOSITE else []
    # Validate children are dicts with expected keys
    children = [
        c for c in raw_children
        if isinstance(c, dict) and ("title" in c or "description" in c)
    ]

    ambiguity = None
    if cls == Classification.AMBIGUOUS:
        ambiguity = Ambiguity(
            id=str(uuid.uuid4()),
            label=data.get("ambiguity_label", "UNSPECIFIED"),
            source_node_title=title,
            questions=data.get("questions", []),
            recommendation=data.get("recommendation", ""),
        )

    return cls, children, ambiguity, complexity


def recursive_decompose(
    title: str,
    description: str,
    lineage: list[str],
    prd_content: str,
    depth: int,
    max_depth: int,
    ambiguities: list[Ambiguity],
    provider,
) -> DecompositionNode:
    """Recursively decompose a goal, collecting ambiguities along the way."""
    # Force leaf at max depth
    if depth >= max_depth:
        return DecompositionNode(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            classification=Classification.ATOMIC,
            children=[],
            lineage=lineage,
            depth=depth,
            complexity_hint="Unknown",
        )

    cls, child_dicts, ambiguity, complexity = classify_and_decompose(
        title, description, lineage, prd_content, depth, provider,
    )

    if ambiguity:
        ambiguities.append(ambiguity)

    children = []
    if cls == Classification.COMPOSITE:
        child_lineage = lineage + [title]
        for child_dict in child_dicts:
            child_node = recursive_decompose(
                child_dict.get("title", "Untitled"),
                child_dict.get("description", ""),
                child_lineage,
                prd_content,
                depth + 1,
                max_depth,
                ambiguities,
                provider,
            )
            children.append(child_node)

    return DecompositionNode(
        id=str(uuid.uuid4()),
        title=title,
        description=description,
        classification=cls,
        children=children,
        lineage=lineage,
        depth=depth,
        complexity_hint=complexity,
        ambiguity_id=ambiguity.id if ambiguity else None,
    )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_tech_spec(
    tree: list[DecompositionNode], ambiguities: list[Ambiguity]
) -> str:
    """Render the decomposition tree as a markdown technical specification."""
    amb_map = {a.id: i + 1 for i, a in enumerate(ambiguities)}
    lines = ["# Technical Specification\n"]

    for node in tree:
        _render_spec_node(node, lines, amb_map, header_level=2)

    return "\n".join(lines)


def _render_spec_node(
    node: DecompositionNode,
    lines: list[str],
    amb_map: dict[str, int],
    header_level: int,
) -> None:
    """Recursively render a node into the tech spec."""
    prefix = "#" * min(header_level, 6)
    lines.append(f"{prefix} {node.title}")

    if node.classification == Classification.AMBIGUOUS:
        amb_num = amb_map.get(node.ambiguity_id, "?") if node.ambiguity_id else "?"
        lines.append(f"**[NEEDS CLARIFICATION — see ambiguity #{amb_num}]**\n")
    elif node.classification == Classification.ATOMIC:
        lines.append(f"- {node.description}")
        if node.complexity_hint:
            lines.append(f"- Estimated complexity: {node.complexity_hint}")
        lines.append("")
    else:
        lines.append("")

    for child in node.children:
        _render_spec_node(child, lines, amb_map, header_level + 1)


def render_ambiguity_report(ambiguities: list[Ambiguity]) -> str:
    """Render the ambiguity list as a human-readable report."""
    if not ambiguities:
        return "No ambiguities found — PRD is well-specified for decomposition."

    lines = [
        f"PRD Stress Test — {len(ambiguities)} ambiguities found:\n",
    ]

    for i, amb in enumerate(ambiguities, 1):
        lines.append(
            f"{i}. {amb.label} (from decomposing \"{amb.source_node_title}\")"
        )
        lines.append("   The PRD doesn't specify:")
        for q in amb.questions:
            lines.append(f"   - {q}")
        lines.append(f"   → Recommendation: {amb.recommendation}")
        if amb.resolved_answer:
            lines.append(f"   ✓ Resolved: {amb.resolved_answer}")
        lines.append("")

    return "\n".join(lines)


def resolve_ambiguities_into_prd(
    prd_content: str,
    ambiguities: list[Ambiguity],
    provider,
) -> str:
    """Use LLM to update PRD content with resolved ambiguity answers."""
    resolved = [a for a in ambiguities if a.resolved_answer]
    if not resolved:
        return prd_content

    resolution_text = "\n".join(
        f"- {a.label}: {', '.join(a.questions)} → Answer: {a.resolved_answer}"
        for a in resolved
    )

    response = provider.complete(
        messages=[{
            "role": "user",
            "content": (
                f"Original PRD:\n{prd_content}\n\n"
                f"Resolved ambiguities:\n{resolution_text}\n\n"
                "Update the PRD to incorporate these answers."
            ),
        }],
        purpose=Purpose.PLANNING,
        system=AMBIGUITY_RESOLUTION_SYSTEM,
        max_tokens=8192,
        temperature=0.0,
    )
    updated = response.content.strip()
    if not updated or len(updated) < len(prd_content) // 2:
        logger.warning(
            "PRD rewrite looks truncated (%d chars vs original %d), returning original",
            len(updated), len(prd_content),
        )
        return prd_content
    return updated


# ---------------------------------------------------------------------------
# Top-level Orchestrator
# ---------------------------------------------------------------------------


def stress_test_prd(
    prd_content: str, provider, max_depth: int = 3
) -> StressTestResult:
    """Run the full PRD stress test: extract goals → recursive decompose → render."""
    goals = extract_goals(prd_content, provider)

    tree: list[DecompositionNode] = []
    ambiguities: list[Ambiguity] = []

    for goal in goals:
        node = recursive_decompose(
            title=goal,
            description=goal,
            lineage=[],
            prd_content=prd_content,
            depth=0,
            max_depth=max_depth,
            ambiguities=ambiguities,
            provider=provider,
        )
        tree.append(node)

    tech_spec = render_tech_spec(tree, ambiguities)
    amb_report = render_ambiguity_report(ambiguities)

    # Extract title from PRD (first heading or first line)
    prd_title = "Untitled"
    for line in prd_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            prd_title = stripped[2:].strip()
            break
        if stripped:
            prd_title = stripped[:80]
            break

    return StressTestResult(
        prd_title=prd_title,
        tree=tree,
        ambiguities=ambiguities,
        tech_spec_markdown=tech_spec,
        ambiguity_report=amb_report,
    )
