"""The design-partner program had no written offer (#619).

Announcement traffic is a one-shot event: when it arrives there has to be a page
that says what a partner gets, what they owe, and where to apply. #618 shipped
the intake path (`hello@codeframe.sh` + the pinned Discussion); this pins that
`DESIGN_PARTNERS.md` exists, states the four things the issue asked for, and
reuses that same intake rather than inventing a second one that nobody watches.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "DESIGN_PARTNERS.md"


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text()


class TestTheProgramIsWrittenDown:
    def test_the_doc_exists(self):
        assert DOC.exists(), "DESIGN_PARTNERS.md is the program; without it there is none"

    def test_it_says_what_partners_get_and_what_they_commit(self, text: str):
        """AC1. Both halves, or it is a wish list rather than a deal."""
        headings = re.findall(r"^#{2,3} (.+)$", text, re.MULTILINE)
        joined = " | ".join(headings).lower()

        assert "what you get" in joined, f"no offer section; headings were {headings}"
        assert "what you commit" in joined, f"no commitment section; headings were {headings}"

    def test_the_offer_names_the_three_promised_benefits(self, text: str):
        """AC1: direct line to the maintainer, roadmap influence, public credit."""
        low = text.lower()
        for promise in ("direct line", "roadmap", "credit"):
            assert promise in low, f"the offer never mentions {promise!r}"

    def test_the_commitment_asks_for_a_paid_pilot_or_a_time_commitment(self, text: str):
        """AC1's sharpest clause — 'paid signal beats free'. A program that asks
        for nothing selects for people who will not show up."""
        low = text.lower()
        assert "paid pilot" in low
        assert "time commitment" in low

    def test_it_states_the_cohort_size_and_a_feedback_cadence(self, text: str):
        """AC2's target, and the cadence that makes the loop tight."""
        assert re.search(r"5\s*[-–—]\s*10 teams", text), "cohort size 5-10 is not stated"
        assert re.search(r"\bcadence\b", text, re.IGNORECASE)


class TestIntake:
    def test_the_intake_questions_cover_workflow_scale_and_engines(self, text: str):
        """AC2. These three decide whether a team is a fit at all."""
        low = text.lower()
        for topic in ("workflow", "scale", "engine"):
            assert topic in low, f"intake never asks about {topic!r}"

    def test_intake_reuses_the_618_signup_path(self, text: str):
        """AC3. A second, unwatched inbox is worse than no inbox."""
        assert "hello@codeframe.sh" in text
        assert "discussions" in text.lower()

    def test_it_does_not_invent_a_second_contact_address(self, text: str):
        """The only addresses this repo answers are the ones already published."""
        published = {"hello@codeframe.sh", "licensing@codeframe.sh", "security@codeframe.sh"}
        found = set(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text))

        assert not (found - published), f"unpublished contact address: {found - published}"


class TestActivation:
    def test_activation_is_tied_to_the_announcement(self, text: str):
        """AC4. The program goes live the week after the public announcement —
        a date would already be stale, the trigger will not be."""
        low = text.lower()
        assert "announcement" in low
        assert re.search(r"week after", low), "the activation trigger is not stated"


class TestItIsReachable:
    """A launch page nobody links to does not capture launch traffic."""

    @pytest.mark.parametrize("doc", ["README.md", "LICENSING.md"])
    def test_the_doc_is_linked_from(self, doc: str):
        assert "DESIGN_PARTNERS.md" in (REPO_ROOT / doc).read_text()
