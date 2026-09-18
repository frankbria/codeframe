"""Two roadmap documents disagreed about what shipped (#1246).

`docs/PRODUCT_ROADMAP.md` carried status markers in its `##`/`###` headers *and*
in its Summary table, and the headers rotted: "Phase 4 ❌ NOT STARTED" above a
table row saying 4A was in progress, "Phase 5 ❌ NOT STARTED" above four
sections describing shipped work. `README.md` then checked `[x]` against a phase
the roadmap called in progress — on the merge gate, the load-bearing sentence of
`docs/VISION.md`.

The fix makes the Summary table the single status authority and these checks
keep it that way. Like `test_ops_hygiene_969.py`, they pin the defect *class*:
a header that carries a status marker at all (so it cannot drift from the
table), a README checkbox that disagrees with the table row it maps to, and a
"Current focus" that names a phase the table already calls complete. Every
check asserts it found something to check, so it cannot pass by failing to
find the table.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP = REPO_ROOT / "docs" / "PRODUCT_ROADMAP.md"
README = REPO_ROOT / "README.md"

COMPLETE = "✅"

#: A status marker as the headers used to carry them. Case-sensitive on purpose:
#: "Phase 4 — Complete the SHIP Phase" is a verb, "✅ COMPLETE" is a status.
HEADER_STATUS = re.compile(r"✅|🚧|❌|\bCOMPLETE\b|\bPARTIAL\b|\bNOT STARTED\b|\bIN PROGRESS\b")

#: `| 4A | PR status + PROOF9 merge gate | ✅ Complete ... | #571, #731 |`
TABLE_ROW = re.compile(r"^\|\s*(\d+(?:\.\d+)?[A-Z]?)\s*\|[^|]*\|\s*(✅|🚧|❌)", re.MULTILINE)

HEADER = re.compile(r"^#{2,3} (.+)$", re.MULTILINE)
CHECKBOX = re.compile(r"^\s*- \[([ x])\] (.+)$", re.MULTILINE)
CURRENT_FOCUS = re.compile(r"\*\*Current focus\*\*:\s*Phase\s+(\d+(?:\.\d+)?[A-Z]?)")

#: README roadmap checkbox → roadmap phase, keyed on a stable fragment of the
#: checkbox text. A reworded README line fails the "found it" assertion below
#: rather than silently dropping out of the check.
README_PHASE_OF = {
    "Interactive Agent Sessions": "3.5A",
    "Run gates from the web UI": "3.5B",
    "Run gates button": "3.5B",
    "Glitch capture web UI": "3.5C",
    "Glitch capture form": "3.5C",
    "Merge gating on PROOF9 pass": "4A",
    "PR status tracking + CI check display": "4A",
    "PR status panel with PROOF9-gated merge button": "4A",
    "Post-merge glitch capture loop": "4B",
}


def _section(text: str, title: str) -> str:
    """The body of `## <title>` up to the next `## ` header."""
    match = re.search(
        rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    assert match, f"no `## {title}` section — this check would pass vacuously"
    return match.group(1)


@pytest.fixture(scope="module")
def roadmap() -> str:
    return ROADMAP.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def table(roadmap: str) -> dict[str, str]:
    """Phase id → status glyph, from the Summary table — the one authority."""
    rows = dict(TABLE_ROW.findall(_section(roadmap, "Summary")))
    assert len(rows) >= 5, f"Summary table parsed to {rows} — the checks below would be vacuous"
    missing = set(README_PHASE_OF.values()) - rows.keys()
    assert not missing, f"README maps to phases the Summary table does not list: {missing}"
    return rows


class TestTheSummaryTableIsTheOnlyStatusAuthority:
    def test_no_header_carries_a_status_marker(self, roadmap: str):
        """A marker in a header is a second authority, and it rotted (AC1, AC3)."""
        headers = HEADER.findall(roadmap)
        assert len(headers) >= 5, "no headers found — this check would pass vacuously"
        offenders = [h for h in headers if HEADER_STATUS.search(h)]
        assert not offenders, f"status markers belong in the Summary table only: {offenders}"

    def test_current_focus_is_not_a_phase_the_table_calls_complete(
        self, roadmap: str, table: dict[str, str]
    ):
        match = CURRENT_FOCUS.search(_section(roadmap, "Summary"))
        assert match, "no `**Current focus**: Phase X` line — this check would pass vacuously"
        phase = match.group(1)
        assert phase in table, f"Current focus names phase {phase}, which the table does not list"
        assert (
            table[phase] != COMPLETE
        ), f"Current focus is Phase {phase}, which the table marks ✅ Complete"


class TestTheReadmeAgreesWithTheRoadmap:
    def test_every_mapped_checkbox_matches_its_table_row(self, table: dict[str, str]):
        """A `[x]` claims completion; a `[ ]` denies it. Both must match the table (AC2)."""
        checkboxes = CHECKBOX.findall(_section(README.read_text(encoding="utf-8"), "Roadmap"))
        assert checkboxes, "no README roadmap checkboxes — this check would pass vacuously"

        mismatches = []
        for fragment, phase in README_PHASE_OF.items():
            hits = [(mark, text) for mark, text in checkboxes if fragment in text]
            assert (
                len(hits) == 1
            ), f"expected exactly one README roadmap line containing {fragment!r}, found {hits}"
            mark, text = hits[0]
            checked = mark == "x"
            if checked != (table[phase] == COMPLETE):
                mismatches.append(f"README `[{mark}] {text}` vs roadmap {phase} = {table[phase]}")

        assert not mismatches, "README and roadmap disagree:\n" + "\n".join(mismatches)
