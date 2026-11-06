"""The published sample evidence report is what the shop fixture run produces.

`scripts/demo/build-sample-report.sh` runs real `cf` and real pytest in a copy
of examples/shop-fixture, so this lives in tests/core with the other real-pytest
proof tests (see test_proof_ratchet_1467.py for why not tests/cli).
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.v2, pytest.mark.timeout(300)]

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "scripts" / "demo" / "build-sample-report.sh"
PUBLISHED = REPO / "site" / "sample-evidence-report.html"

# What legitimately differs between two runs: clocks, run IDs, durations, the
# checksums of evidence that embeds timings, and the release being run.
_VOLATILE = [
    (re.compile(r"\d{4}-\d{2}-\d{2}(T[\d:.]+\+00:00)?"), "<date>"),
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "<run>"),
    (re.compile(r"[0-9a-f]{64}"), "<checksum>"),
    (re.compile(r"\d+ ms"), "<duration>"),
    (re.compile(r"codeframe-ai [^<]+"), "codeframe-ai <version>"),
]


def _stable(html: str) -> str:
    for pattern, placeholder in _VOLATILE:
        html = pattern.sub(placeholder, html)
    return html


def _requirement(html: str, title: str) -> str:
    """The report section of the requirement with this title."""
    return next(section for section in html.split("<h3>") if title in section)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> str:
    tmp_path = tmp_path_factory.mktemp("demo")
    # This interpreter's bin first, so `cf` is the code under test.
    env = {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "VIRTUAL_ENV": sys.prefix,
        "TMPDIR": str(tmp_path),
    }
    result = subprocess.run(
        ["bash", str(BUILD), str(tmp_path)], env=env, capture_output=True, text=True, timeout=280,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    return (tmp_path / "sample-evidence-report.html").read_text(encoding="utf-8")


def test_published_report_matches_a_fresh_fixture_run(built):
    # On failure: `uv run scripts/demo/build-sample-report.sh` and commit site/.
    assert _stable(PUBLISHED.read_text(encoding="utf-8")) == _stable(built)


def test_report_shows_the_refused_flat_shipping_commit(built):
    free_shipping = _requirement(built, "Orders over $50 were charged shipping")
    assert 'class="tag open">OPEN' in free_shipping
    assert "unit: failed" in free_shipping
    assert 'class="tag fail">FAILED' in built.split("<h2>Run history</h2>")[1]


def test_report_shows_the_waiver_as_self_asserted(built):
    gift_cards = _requirement(built, "Gift cards must not be taxed")
    assert 'class="tag waived">WAIVED' in gift_cards
    assert "Gift cards launch after pilot" in gift_cards
    assert "approved by shop-demo (the OS user who ran <code>cf proof waive</code>: self-asserted" in gift_cards
    assert " · expires " in gift_cards
