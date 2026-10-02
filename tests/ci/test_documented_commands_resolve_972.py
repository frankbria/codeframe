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

# The leading subcommand name in a word. Underscores are allowed even though
# every command today is hyphenated: if this rejected them, an underscored
# command name would silently end the walk instead of being checked, which is
# the exact blind spot this test exists to close.
#
# It matches a PREFIX, not the whole word, so `stop<batch_id>` and `stop(x)`
# both yield `stop`. INVOCATION gets that truncation for free from its per-word
# charset; without it here the two extraction paths disagree about the same
# content, and a phantom glued to a placeholder escapes the bare-command walk.
# A word with no such prefix at all (`--flag`, `<task_id>`, `TASK`) ends the path.
SUBCOMMAND = re.compile(r"^[a-z][a-z0-9_-]*")

# The docs also name commands without the binary: checklist and roadmap entries
# like ``- `work batch cancel` ✓ DONE``. Those went unchecked until GLM review on
# #1196 pointed out the gap, so a phantom could hide there indefinitely. Only a
# backticked span whose FIRST word is a real top-level command is considered —
# without that anchor, any backticked prose would be walked as a command path.
BACKTICKED = re.compile(r"`([a-z][^`]*)`")

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
        match = SUBCOMMAND.match(word) if subcommands else None
        if not match:
            return None
        name = match.group(0)
        if name not in subcommands:
            return " ".join(path + [name])
        node = subcommands[name]
        path.append(name)
    return None


def _documented_commands():
    """Yield (location, command_path, source_line) for every doc invocation."""
    top_level = set(_command_tree().commands)
    for doc in DOC_FILES:
        rel = doc.relative_to(REPO_ROOT)
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if NOT_IMPLEMENTED_MARKER in line:
                continue
            spans = [m.group(1) for m in INVOCATION.finditer(line)]
            spans += [
                m.group(1)
                for m in BACKTICKED.finditer(line)
                if m.group(1).split()[:1] and m.group(1).split()[0] in top_level
            ]
            for span in spans:
                # `pr create|list|merge` documents three commands on one line.
                alternatives = [word.split("|") for word in span.split()]
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


# ---------------------------------------------------------------------------
# Required arguments (#1273): a documented invocation that cannot run as typed
# ---------------------------------------------------------------------------


def _code_block_invocations():
    """Yield (location, leaf_command, argv_after_path, line) for every
    executable-looking invocation: inside a fenced code block, not a
    ``a|b|c`` listing. Prose and listings name commands; code blocks run them."""
    import shlex

    root = _command_tree()
    for doc in DOC_FILES:
        rel = doc.relative_to(REPO_ROOT)
        fenced = False
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if not fenced or NOT_IMPLEMENTED_MARKER in line:
                continue
            code = line.split(" #", 1)[0]  # trailing shell comment
            m = INVOCATION.search(code)
            if not m or "|" in m.group(1):
                continue
            try:
                tokens = shlex.split(code[m.start(1):])
            except ValueError:
                continue
            node, used = root, 0
            for tok in tokens:
                subcommands = getattr(node, "commands", None)
                if not subcommands or tok not in subcommands:
                    break
                node, used = subcommands[tok], used + 1
            if used == 0:
                continue  # unresolved: the test above owns it
            yield f"{rel}:{lineno}", node, tokens[used:], line.strip()


def _positional_count(command, argv):
    """How many positional values ``argv`` gives ``command`` (options skipped)."""
    takes_value = {
        opt
        for p in command.params
        if not getattr(p, "is_flag", False) and getattr(p, "opts", None) and p.param_type_name == "option"
        for opt in p.opts + p.secondary_opts
    }
    count, skip = 0, False
    for tok in argv:
        if skip:
            skip = False
        elif tok.startswith("-"):
            skip = tok in takes_value and "=" not in tok
        else:
            count += 1
    return count


def test_documented_invocations_carry_their_required_arguments():
    """`cf pr merge` without the PR number is a doc that cannot run (#1273)."""
    failures = []
    for location, command, argv, line in _code_block_invocations():
        if getattr(command, "commands", None) is not None:
            runs_alone = getattr(command, "invoke_without_command", False)  # `cf dashboard`
            if not runs_alone and not any(not a.startswith("-") for a in argv) and "--help" not in argv:
                # `cf commit` alone prints help; the real command is a subcommand.
                failures.append(f"  {location}: a command group, prints help only — in: {line[:100]}")
            continue
        required = [
            p for p in command.params
            if p.param_type_name == "argument" and p.required
        ]
        if _positional_count(command, argv) < len(required):
            names = ", ".join(p.name.upper() for p in required)
            failures.append(f"  {location}: needs {names} — in: {line[:100]}")
    assert not failures, (
        "Documented invocations are missing required arguments:\n" + "\n".join(failures)
    )


def test_the_argument_check_sees_code_blocks():
    """Guard the guard."""
    assert len(list(_code_block_invocations())) > 30
