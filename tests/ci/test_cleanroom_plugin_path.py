"""The cold-start harness checks the proof9 plugin a stranger actually receives.

scripts/quickstart-cleanroom/ installs proof9 from the published marketplace and
runs its own tests from the installed copy. That only means something if it is
the published copy, and if the harness runs the same Claude Code that CI tests
the plugin against; otherwise the two disagree about which runtime the plugin
was checked on.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "quickstart-cleanroom"


def test_cleanroom_pins_the_claude_code_ci_tests_the_plugin_against():
    workflows = "\n".join(p.read_text() for p in (ROOT / ".github" / "workflows").glob("*.yml"))
    ci = set(re.findall(r"@anthropic-ai/claude-code@([0-9][0-9.]*)", workflows))
    assert len(ci) == 1, f"CI should pin exactly one Claude Code version, found {sorted(ci)}"

    dockerfile = (HARNESS / "Dockerfile").read_text()
    pinned = re.search(r"^ARG CLAUDE_CODE_VERSION=([0-9][0-9.]*)$", dockerfile, re.MULTILINE)
    assert pinned, "the cleanroom Dockerfile no longer pins CLAUDE_CODE_VERSION"
    assert pinned.group(1) == next(iter(ci)), (
        f"cleanroom runs Claude Code {pinned.group(1)} but CI tests the plugin on "
        f"{next(iter(ci))}"
    )


def test_cleanroom_installs_the_published_plugin_not_this_checkout():
    script = (HARNESS / "walkthrough.sh").read_text()
    assert "claude plugin install proof9 --marketplace frankbria/codeframe" in script, (
        "the harness must install proof9 the way the README tells a visitor to"
    )
    for check in ("plugin-validate", "plugin-test"):
        assert f'step "{check}"' in script, f"the harness no longer runs {check} on the installed copy"
    assert "@anthropic-ai/claude-code" not in script and "proof9/" not in script, (
        "the walkthrough must not install the plugin from a local path"
    )
