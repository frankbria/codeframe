"""GOLDEN_PATH.md's state machine is the code's (#1304).

The doc listed an IN_REVIEW state and PR-driven transitions that were never
built, and CLAUDE.md tells agents to follow this file first.
"""

import re
from pathlib import Path

import pytest

from codeframe.core.state_machine import ALLOWED_TRANSITIONS, TaskStatus

pytestmark = pytest.mark.v2

DOC = Path(__file__).resolve().parents[2] / "docs" / "GOLDEN_PATH.md"


def _section() -> str:
    text = DOC.read_text()
    start = text.index("## State Machine (authoritative)")
    return text[start:text.index("\n---", start)]


def test_documented_statuses_are_the_real_ones():
    documented = set(re.findall(r"^- `([A-Z_]+)` - ", _section(), re.M))
    assert documented == {s.value for s in TaskStatus}


def test_documented_transitions_are_the_real_ones():
    documented = {}
    for src, targets in re.findall(r"^- ([A-Z_]+) -> (.+)$", _section(), re.M):
        documented[src] = set() if targets.strip() == "(none)" else {t.strip() for t in targets.split(",")}
    assert documented == {s.value: {t.value for t in ts} for s, ts in ALLOWED_TRANSITIONS.items()}
