"""#1473 — no "obligation" in anything a proof9 user reads.

The first-run walk found the word in seven places, and the review found four
more that tests of individual messages did not reach. So this checks the
source: every string literal in the plugin's hooks and every manifest field a
user sees. "requirement" is the CLI's word; identifiers like
`r.obligations` (the CLI's JSON field) are code, not text, and are not matched.
"""

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]

#: A quoted or template string literal (one line) that contains the word.
#: Not after a ".": `r.obligations` inside a template expression is the CLI's field name.
LITERAL = re.compile(r"""(['"`])(?:(?!\1).)*(?<!\.)\bobligations?\b(?:(?!\1).)*\1""", re.IGNORECASE)


@pytest.mark.parametrize("path", sorted((ROOT / "proof9" / "hooks").glob("*.ts*")), ids=lambda p: p.name)
def test_no_string_literal_in_the_hooks_says_obligation(path):
    hits = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if not line.lstrip().startswith(("//", "*", "/*")) and LITERAL.search(line)
    ]
    assert not hits, "\n".join(hits)


def test_no_manifest_text_says_obligation():
    texts = json.dumps([
        json.loads((ROOT / "proof9" / ".claude-plugin" / "plugin.json").read_text()),
        json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text()),
    ])
    assert not re.search(r"\bobligations?\b", texts, re.IGNORECASE), texts


def _prose_literals(path: Path, *, skip_docstrings: bool):
    """String constants in a Python module, minus docstrings when asked."""
    import ast

    tree = ast.parse(path.read_text())
    docs = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.body and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if skip_docstrings and id(node) in docs:
                continue
            yield node.lineno, node.value


# #1507: the CLI says what the plugin says. Command docstrings are `--help` text,
# so the CLI module is checked whole; the runner's docstrings are for developers,
# its other strings reach the console. The JSON key and enum code are an API.
@pytest.mark.parametrize(
    "rel, skip_docstrings",
    [("codeframe/cli/proof_commands.py", False), ("codeframe/core/proof/runner.py", True)],
)
def test_no_cli_text_says_obligation(rel, skip_docstrings):
    api = {"obligations", "no_obligations"}
    hits = [
        f"{rel}:{n}: {text[:80]!r}"
        for n, text in _prose_literals(ROOT / rel, skip_docstrings=skip_docstrings)
        if text not in api and re.search(r"\bobligations?\b", text, re.IGNORECASE)
    ]
    assert not hits, "\n".join(hits)
