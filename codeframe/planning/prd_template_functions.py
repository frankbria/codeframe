"""Jinja2 template functions for PRD rendering.

This module provides custom filters and functions for use in PRD templates:
- bullet_list: Convert list to markdown bullets
- numbered_list: Convert list to numbered list
- table: Generate markdown table
- summarize: Summarize long text (placeholder for LLM call)
"""

from typing import Any


def bullet_list(items: list[str]) -> str:
    """Convert a list to markdown bullet points.

    Args:
        items: List of strings to convert

    Returns:
        Markdown formatted bullet list
    """
    if not items:
        return ""
    return "\n".join(f"- {item}" for item in items)


def numbered_list(items: list[str]) -> str:
    """Convert a list to a numbered markdown list.

    Args:
        items: List of strings to convert

    Returns:
        Markdown formatted numbered list
    """
    if not items:
        return ""
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))


def table(items: list[dict[str, Any]], columns: list[str]) -> str:
    """Generate a markdown table from a list of dictionaries.

    Args:
        items: List of dictionaries with data
        columns: Column names to include in table

    Returns:
        Markdown formatted table
    """
    if not items or not columns:
        return ""

    # Header row
    header = "| " + " | ".join(columns) + " |"

    # Separator row
    separator = "| " + " | ".join("---" for _ in columns) + " |"

    # Data rows
    rows = []
    for item in items:
        row_values = [str(item.get(col, "")) for col in columns]
        rows.append("| " + " | ".join(row_values) + " |")

    return "\n".join([header, separator] + rows)


def summarize(text: str, max_words: int = 50) -> str:
    """Summarize long text (placeholder - truncates for now).

    In a future version, this could call an LLM for proper summarization.

    Args:
        text: Text to summarize
        max_words: Maximum words in summary

    Returns:
        Summarized text
    """
    if not text:
        return ""

    words = text.split()
    if len(words) <= max_words:
        return text

    return " ".join(words[:max_words]) + "..."


def join_list(items: list[str], separator: str = ", ") -> str:
    """Join a list into a string with separator.

    Args:
        items: List of strings to join
        separator: Separator between items

    Returns:
        Joined string
    """
    if not items:
        return ""
    return separator.join(str(item) for item in items)


def format_constraints(constraints: dict[str, Any]) -> str:
    """Format constraints dictionary as markdown.

    Args:
        constraints: Dictionary of constraint types to values

    Returns:
        Markdown formatted constraints
    """
    if not constraints:
        return "No specific constraints defined."

    lines = []
    for key, value in constraints.items():
        if isinstance(value, list):
            value_str = ", ".join(str(v) for v in value)
        else:
            value_str = str(value)
        lines.append(f"- **{key.title()}**: {value_str}")

    return "\n".join(lines)


# Registry of all template functions
TEMPLATE_FUNCTIONS = {
    "bullet_list": bullet_list,
    "numbered_list": numbered_list,
    "table": table,
    "summarize": summarize,
    "join_list": join_list,
    "format_constraints": format_constraints,
}
