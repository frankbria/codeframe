"""#1465: the static codeframe.sh page under site/.

Pins what the issue's acceptance criteria require and what could silently drift:
the limitations text must match the README word for word (a release bump changes
the README's version string, and the page has to follow), the page loads no
script, form or third-party resource, every local asset it references ships
inside site/ (so the directory deploys as-is), and the social card is 1200x630
at an absolute URL.
"""

import html
import re
import struct
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
PAGE = (SITE / "index.html").read_text(encoding="utf-8")


def _words(text: str) -> str:
    return " ".join(text.split())


def _readme_limitations() -> str:
    lines = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    start = lines.index("> [!NOTE]") + 1
    block = []
    for line in lines[start:]:
        if not line.startswith(">"):
            break
        block.append(line[1:].strip())
    md = " ".join(block)
    md = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)  # [text](url) -> text
    return _words(md.replace("**", "").replace("`", ""))


def _page_limitations() -> str:
    m = re.search(r'<blockquote id="limitations">(.*?)</blockquote>', PAGE, re.S)
    assert m, "limitations blockquote missing"
    return _words(html.unescape(re.sub(r"<[^>]+>", "", m.group(1))))


def test_limitations_match_readme_verbatim():
    readme = _readme_limitations()
    assert readme.startswith("CodeFRAME is in public beta")
    assert _page_limitations() == readme


def test_no_script_form_or_third_party_resource():
    lowered = PAGE.lower()
    assert "<script" not in lowered
    assert "<form" not in lowered
    assert "<iframe" not in lowered
    # Only navigation links may leave the page; nothing it loads may.
    loaded = re.findall(r'(?:src|srcset)="([^"]+)"', PAGE)
    loaded += re.findall(r'<link[^>]+href="([^"]+)"', PAGE)
    external = [u for u in loaded if "://" in u and not u.startswith("https://codeframe.sh/")]
    assert external == []


def test_local_assets_ship_inside_site():
    refs = re.findall(r'(?:src|srcset)="([^"]+)"', PAGE)
    # Icons too: a missing favicon fails silently in the browser (#1476).
    refs += re.findall(r'<link rel="(?:icon|apple-touch-icon)"[^>]+href="([^"]+)"', PAGE)
    assert refs, "page references no assets"
    for ref in refs:
        assert "://" not in ref and not ref.startswith(("/", "..")), ref
        assert (SITE / ref).is_file(), f"site/{ref} missing"


def test_social_card_is_absolute_and_1200x630():
    for prop in ('property="og:image"', 'name="twitter:image"'):
        m = re.search(rf'<meta {prop} content="([^"]+)"', PAGE)
        assert m, prop
        assert m.group(1) == "https://codeframe.sh/og-image.png"
    png = (SITE / "og-image.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (1200, 630)
