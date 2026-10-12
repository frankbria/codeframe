"""#1447 — the nightly cross-browser E2E sweep failed every night on Firefox.

Two defects, found together:

1. The full sweep runs every spec in three browsers against ONE backend. By the
   time Firefox reached `/tasks`, the 100/minute API limit was spent and the page
   rendered its "Too many requests" error card instead of the board. The PR-gated
   smoke runs one browser and never got that far. The Playwright backend is a
   test-only server, so it now starts with `RATE_LIMIT_ENABLED=false`.

2. That error card failed axe's color-contrast rule, a real defect the rate limit
   merely exposed: `text-destructive` on its own `bg-destructive/10` tint measured
   4.13:1, and `text-muted-foreground` on the same tint 4.48:1 (WCAG AA is 4.5:1).
   The tint appears on 17 surfaces, so the fix is in the light-theme tokens.
   With rate limiting off the E2E suite no longer renders the card, so this file
   computes the contrast directly from `globals.css`.
"""

import colorsys
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
GLOBALS_CSS = ROOT / "web-ui" / "src" / "app" / "globals.css"
PLAYWRIGHT_CONFIG = ROOT / "tests" / "e2e" / "playwright.config.ts"
AA = 4.5


def _light_tokens() -> dict[str, tuple[float, float, float]]:
    """HSL tokens from the first (light-theme) block of globals.css, as RGB."""
    css = GLOBALS_CSS.read_text()
    block = css[css.index("{") : css.index("}")]
    tokens = {}
    for name, h, s, lightness in re.findall(
        r"--([\w-]+):\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%", block
    ):
        tokens[name] = colorsys.hls_to_rgb(
            float(h) / 360, float(lightness) / 100, float(s) / 100
        )
    return tokens


def _luminance(rgb) -> float:
    def channel(x: float) -> float:
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = map(channel, rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _tint(color, background, alpha: float = 0.10):
    return tuple(alpha * c + (1 - alpha) * g for c, g in zip(color, background))


@pytest.mark.parametrize("foreground", ["destructive", "muted-foreground"])
def test_text_on_the_destructive_tint_meets_wcag_aa(foreground: str):
    tokens = _light_tokens()
    tint = _tint(tokens["destructive"], tokens["background"])
    ratio = _contrast(tokens[foreground], tint)
    assert ratio >= AA, (
        f"text-{foreground} on bg-destructive/10 is {ratio:.2f}:1, below {AA}:1 — "
        "every error card fails axe color-contrast (#1447)"
    )


def test_white_text_on_destructive_buttons_still_meets_wcag_aa():
    tokens = _light_tokens()
    ratio = _contrast(tokens["destructive-foreground"], tokens["destructive"])
    assert ratio >= AA, f"destructive buttons are {ratio:.2f}:1"


def test_the_e2e_backend_runs_without_rate_limiting():
    config = PLAYWRIGHT_CONFIG.read_text()
    backend = next(line for line in config.splitlines() if "uvicorn codeframe.ui.server:app" in line)
    assert "RATE_LIMIT_ENABLED=false" in backend, (
        "the Playwright backend keeps the 100/minute limit, so the three-browser "
        "nightly sweep exhausts it and Firefox gets 429 pages (#1447)"
    )
