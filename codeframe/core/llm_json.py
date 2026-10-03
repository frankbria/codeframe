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
    """Return the first complete JSON array in an LLM response.

    Decodes from each ``[`` in turn, in the raw text and then unfenced, and
    stops at the end of the first array that parses, so prose brackets before it ("[2 of them]")
    and prose after it ("These are the tasks.") are both tolerated. A greedy
    ``\\[...\\]`` search spanned those brackets and reported valid JSON as
    truncated (#1293).

    Raises:
        LLMJsonError: If no JSON array can be decoded from the content.
    """
    # The raw text first: the decoder knows JSON strings, so backticks inside a
    # description (a code example) are inert there, while strip_code_fence would
    # stop at them. The unfenced text is the fallback (#1293 review).
    decoder = json.JSONDecoder()
    for text in (content or "", strip_code_fence(content or "")):
        start = text.find("[")
        while start != -1:
            try:
                value, _ = decoder.raw_decode(text, start)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(value, list):
                    return value
            start = text.find("[", start + 1)
    preview = (content or "")[:200].replace("\n", " ")
    raise LLMJsonError(f"No JSON array in {what}. Content began: {preview!r}")
