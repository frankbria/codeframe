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

__all__ = ["LLMJsonError", "extract_json_array", "parse_json_response", "strip_code_fence"]

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


def extract_json_array(content: str, *, what: str = "response") -> list:
    """Return the top-level JSON array in an LLM response.

    Decodes from each ``[`` in turn and stops at the first array that is a
    plausible result, so prose and a markdown fence around it are tolerated, and
    backticks inside a JSON string (a code example) are inert: the decoder knows
    strings, where a fence stripper would stop at them. Two rules keep the scan
    from settling on the wrong array (#1293 reviews):

    - an array of objects (``[`` then ``{``) that fails to decode means the
      reply's array is malformed or cut off: raise, rather than let one of its
      nested arrays stand in for the whole result;
    - a list of scalars (prose like ``Tasks [1]:``) is skipped; only an empty
      list or one holding an object counts.

    Raises:
        LLMJsonError: If no such array can be decoded from the content.
    """
    text = content or ""
    decoder = json.JSONDecoder()
    start = text.find("[")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError as exc:
            if text[start + 1:].lstrip().startswith("{"):
                raise LLMJsonError(
                    f"The JSON array in {what} is malformed or incomplete: {exc}"
                ) from exc
        else:
            if isinstance(value, list) and (
                not value or any(isinstance(item, dict) for item in value)
            ):
                return value
        start = text.find("[", start + 1)
    preview = text[:200].replace("\n", " ")
    raise LLMJsonError(f"No JSON array in {what}. Content began: {preview!r}")
