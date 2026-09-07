"""Every ``cf``/``codeframe`` command in the docs must exist (#972).

Stale docs are expensive: a phantom command is a support ticket, or an agent
turn wasted discovering the command was never built. #614 found eight of them
by hand; this test is the repeatable version, so the next one cannot ship.

The rule: every command path a shipped doc spells out either resolves in the
live Typer tree, or its line is explicitly marked ``NOT IMPLEMENTED``.
``GOLDEN_PATH.md`` and ``CLI_WIREFRAME.md`` are specs of intended behaviour, so
marking is the honest option there — deleting would lose the design intent.
"""

import itertools
import re
from pathlib import Path

import pytest
import typer.main

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]

# Docs a user actually reads. Everything under docs/archive is history.
DOC_FILES = [REPO_ROOT / "README.md", REPO_ROOT / "CLAUDE.md"] + sorted(
    (REPO_ROOT / "docs").glob("*.md")
)

# `cf work batch run`, `codeframe pr create|list|merge`. The lookbehind keeps
# `codeframe/core/foo.py` and `--codeframe` from reading as invocations.
INVOCATION = re.compile(r"(?<![\w./-])(?:cf|codeframe)((?:\s+[a-z][a-z0-9_|-]*)+)")

# A subcommand name. Anything else (a flag, `<task_id>`, `TASK`) ends the path.
SUBCOMMAND = re.compile(r"^[a-z][a-z0-9-]*$")

NOT_IMPLEMENTED_MARKER = "NOT IMPLEMENTED"


def _command_tree():
    return typer.main.get_command(app)


def _unresolvable(root, words):
    """Return the first command path in `words` the Typer tree does not have.

    Walks word by word from the root. Stops at the first token that is not a
    subcommand name (a flag or an argument placeholder) or once a leaf command
    is reached — everything after that is arguments, not command names.
    """
    node, path = root, []
    for word in words:
        subcommands = getattr(node, "commands", None)
        if not subcommands or not SUBCOMMAND.match(word):
            return None
        if word not in subcommands:
            return " ".join(path + [word])
        node = subcommands[word]
        path.append(word)
    return None


def _documented_commands():
    """Yield (location, command_path, source_line) for every doc invocation."""
    for doc in DOC_FILES:
        rel = doc.relative_to(REPO_ROOT)
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if NOT_IMPLEMENTED_MARKER in line:
                continue
            for match in INVOCATION.finditer(line):
                # `pr create|list|merge` documents three commands on one line.
                alternatives = [word.split("|") for word in match.group(1).split()]
                for words in itertools.product(*alternatives):
                    yield f"{rel}:{lineno}", words, line.strip()


def test_every_documented_command_resolves():
    root = _command_tree()
    failures = []
    seen = set()
    for location, words, line in _documented_commands():
        phantom = _unresolvable(root, words)
        if phantom and (location, phantom) not in seen:
            seen.add((location, phantom))
            failures.append(f"  {location}: `{phantom}` — in: {line[:100]}")

    assert not failures, (
        "Docs name commands the CLI does not have. Fix the doc, or mark the line "
        f"`{NOT_IMPLEMENTED_MARKER}` if it is intended-but-unbuilt:\n"
        + "\n".join(failures)
    )


def test_extractor_still_sees_the_cli():
    """Guard the guard: a regex that matches nothing would pass vacuously."""
    root = _command_tree()
    resolved = [
        words
        for _, words, _ in _documented_commands()
        if _unresolvable(root, words) is None
    ]
    assert len(resolved) > 50, f"extractor found only {len(resolved)} commands in docs"
