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
