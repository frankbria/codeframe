"""The codeframe.sh pricing page and the docs that point at it.

Decision of 2026-11-03: CodeFRAME is free and open source, and enterprise use is
by contact. No published prices, no tiers, no seat count. This pins the page to
that decision and holds it to the same static-page rules as index.html
(tests/ci/test_site_1465.py): no script or form, nothing loaded from elsewhere,
every local asset shipped inside site/. It also keeps the "hosted offering and
commercial support are planned" promise from coming back to the docs.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
PAGE = (SITE / "pricing.html").read_text(encoding="utf-8")


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", "", html, flags=re.S)).split())


def test_index_links_to_pricing():
    assert 'href="pricing.html"' in (SITE / "index.html").read_text(encoding="utf-8")


def test_says_free_and_gives_the_contact_address():
    text = _text(PAGE)
    assert "CodeFRAME is free" in text
    assert "Apache-2.0" in text
    assert 'href="mailto:hello@codeframe.sh"' in PAGE


def test_publishes_no_price_or_tier():
    """A currency amount or a per-seat line would contradict the decision."""
    text = _text(PAGE)
    assert not re.search(r"[$€£]\s*\d|\d\s*(?:USD|EUR)\b", text), "a price is published"
    assert not re.search(r"per (?:seat|user|month)|/mo\b|most popular", text, re.I)


def test_no_script_form_or_third_party_resource():
    lowered = PAGE.lower()
    assert "<script" not in lowered
    assert "<form" not in lowered
    assert "<iframe" not in lowered
    loaded = re.findall(r'(?:src|srcset)="([^"]+)"', PAGE)
    loaded += re.findall(r'<link[^>]+href="([^"]+)"', PAGE)
    external = [u for u in loaded if "://" in u and not u.startswith("https://codeframe.sh/")]
    assert external == []


def test_local_assets_ship_inside_site():
    refs = re.findall(r'(?:src|srcset)="([^"]+)"', PAGE)
    for tag in re.findall(r"<link\b[^>]*>", PAGE):
        if re.search(r'rel="(?:icon|apple-touch-icon)"', tag):
            refs += re.findall(r'href="([^"]+)"', tag)
    assert refs, "page references no assets"
    for ref in refs:
        assert "://" not in ref and not ref.startswith(("/", "..")), ref
        assert (SITE / ref).is_file(), f"site/{ref} missing"


@pytest.mark.parametrize("doc", ["README.md", "LICENSING.md", "DESIGN_PARTNERS.md"])
def test_docs_no_longer_promise_a_planned_paid_offering(doc: str):
    text = " ".join((ROOT / doc).read_text(encoding="utf-8").split()).lower()
    assert "hosted offering and commercial support" not in text
    assert "when pricing lands" not in text and "general pricing lands" not in text
