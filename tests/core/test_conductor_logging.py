"""Headless-core logging guards (issue #649).

Server-reachable core modules must route runtime chatter through ``logger``
rather than bare ``print()`` — otherwise the output leaks to the FastAPI
server's stdout, violating CLAUDE.md Architecture Rules #1/#3.
"""

import ast
import logging
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _print_call_lines(rel_path: str) -> list[int]:
    """Line numbers of bare ``print(...)`` *call* nodes in a source file.

    AST-based, so ``print(...)`` appearing inside docstrings/strings (e.g. the
    ``Example:`` blocks in ``runtime.py``) is correctly ignored — those are str
    constants, not calls, and never execute.
    """
    tree = ast.parse((_REPO_ROOT / rel_path).read_text())
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    )


@pytest.mark.parametrize(
    "rel_path",
    [
        "codeframe/core/conductor.py",
        "codeframe/core/tasks.py",
        "codeframe/core/runtime.py",
    ],
)
def test_no_bare_print_on_server_reachable_core(rel_path: str):
    offending = _print_call_lines(rel_path)
    assert offending == [], (
        f"{rel_path} has bare print() calls at lines {offending}; "
        f"use logger.* instead (issue #649)."
    )


def test_supervisor_classification_failure_logs_via_logger(tmp_path, caplog):
    """A representative conductor path routes chatter through ``logger``."""
    from codeframe.core.conductor import SupervisorResolver
    from codeframe.core.workspace import create_or_load_workspace

    ws = create_or_load_workspace(tmp_path)
    resolver = SupervisorResolver(ws)

    class _BoomLLM:
        def complete(self, *args, **kwargs):
            raise RuntimeError("llm down")

    resolver._llm = _BoomLLM()  # bypass lazy get_provider()

    with caplog.at_level(logging.WARNING, logger="codeframe.core.conductor"):
        result = resolver._classify_with_supervision("should we use a venv?")

    assert result in {"tactical", "human"}
    assert any("Classification failed" in r.message for r in caplog.records), (
        "expected the classification-failure path to log via logger"
    )
