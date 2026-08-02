"""Parsing JSON out of an LLM response (#927).

A **leaf module**: stdlib only, so every consumer can converge on it.

Models routinely wrap JSON in a markdown fence, and local / OpenAI-compatible
providers do it more often than Anthropic. Four call sites in this repo each
grew their own fence stripper, in two subtly different shapes — and
``prd_stress_test`` grew none at all, so it did a raw ``json.loads``, swallowed
the failure, and reported "No ambiguities found — PRD is well-specified" after
the user had paid for the call.

The lesson in that bug is the reason this module exists: a parser that returns a
falsy default on failure turns a provider quirk into a clean bill of health.
``parse_json_response`` raises instead, and callers decide what to do about it.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = ["LLMJsonError", "parse_json_response", "strip_code_fence"]

#: A fenced block, with or without a language tag, anywhere in the response.
#: Non-greedy so the *first* complete block wins when a model emits several.
_FENCE_RE = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)```", re.DOTALL)


class LLMJsonError(ValueError):
    """An LLM response could not be parsed as JSON."""


def strip_code_fence(content: str) -> str:
    """Return the contents of the first markdown fence, or the input unchanged.

    Tolerates prose around the block ("Sure! Here you go:"), which local models
    add routinely, and a fence with no language tag.
    """
    match = _FENCE_RE.search(content)
    return match.group(1).strip() if match else content.strip()


def parse_json_response(content: str, *, what: str = "response") -> Any:
    """Parse an LLM response as JSON, stripping any markdown fence.

    Raises:
        LLMJsonError: If the content is empty or is not JSON once unfenced.
            Deliberately an exception rather than a falsy default — the caller
            must not be able to mistake a parse failure for an empty result.
    """
    if not content or not content.strip():
        raise LLMJsonError(f"Empty {what} — nothing to parse")

    stripped = strip_code_fence(content)
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError) as exc:
        preview = stripped[:200].replace("\n", " ")
        raise LLMJsonError(
            f"Could not parse {what} as JSON: {exc}. Content began: {preview!r}"
        ) from exc
