"""No unqualified uniqueness claims in the user-facing docs (#1466).

"Nobody else does this" was refutable from a competitor's own docs: several
review tools now persist learned rules across pull requests. The claim that
holds is narrower -- defects re-verified by a tool, not preferences -- and
docs/VISION.md states it with a pointer to the code for each part.

This guard keeps the broad form from creeping back. A phrase here is not
forbidden English; it is forbidden as a *market* claim. If a new doc needs one
of them for some other meaning, reword it rather than widening an allowlist.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]

DOCS = [ROOT / "README.md", ROOT / "DESIGN_PARTNERS.md", *sorted((ROOT / "docs").glob("*.md"))]

# Each is a claim about every other product, which no doc can substantiate.
UNIQUENESS_CLAIMS = re.compile(
    r"nobody else does|no one else does|the only tool|no other tool|"
    r"unique position|first and only",
    re.IGNORECASE,
)


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_doc_makes_no_unqualified_uniqueness_claim(doc: Path):
    hits = [
        f"{doc.relative_to(ROOT)}:{n}: {line.strip()}"
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1)
        # A line that quotes the retired phrase in order to retire it is fine.
        if UNIQUENESS_CLAIMS.search(line) and "narrower than" not in line
    ]
    assert not hits, "Unqualified uniqueness claim (see #1466):\n" + "\n".join(hits)


def test_vision_states_the_precise_differentiation():
    vision = (ROOT / "docs" / "VISION.md").read_text(encoding="utf-8")
    assert "Other tools remember what your reviewers prefer." in vision
    # Every audit property it leads with names where to check it.
    for anchor in ("_bound_digest", "vacuous_pass", "approved_by", "cf proof show"):
        assert anchor in vision, anchor
