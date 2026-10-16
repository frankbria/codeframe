"""#1471 — the proof9 plugin's distribution and its CI gate.

The plugin ships from this repository's marketplace file, and CI validates,
tests and type-checks it on every PR. The type-check needs the plugin API's
declarations, which only a running Claude Code session writes, so they are
vendored under tools/proof9-types/ (outside the plugin, so installs do not ship
them) and CI installs exactly the Claude Code version that wrote them.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
TYPES = ROOT / "tools" / "proof9-types"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def _steps_text(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


def test_the_marketplace_lists_proof9_from_its_folder():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    [entry] = [p for p in market["plugins"] if p["name"] == "proof9"]
    assert entry["source"] == "./proof9"
    assert json.loads((ROOT / "proof9" / ".claude-plugin" / "plugin.json").read_text())["name"] == "proof9"


def test_the_readme_has_the_install_line():
    assert "/plugin install proof9 --marketplace frankbria/codeframe" in (ROOT / "README.md").read_text()


def test_the_plugin_states_the_cli_version_it_needs():
    register = (ROOT / "proof9" / "hooks" / "register.tsx").read_text()
    major, minor, patch = re.search(r"MIN_VERSION = \[(\d+), (\d+), (\d+)\]", register).groups()
    needed = f"{major}.{minor}.{patch}"
    assert f"version {needed} or later" in (ROOT / "proof9" / "README.md").read_text()
    assert f"codeframe-ai {needed}" in (ROOT / "README.md").read_text()


def test_ci_validates_tests_and_type_checks_the_plugin():
    job = _jobs()["proof9-plugin"]
    run = _steps_text(job)
    assert "claude plugin validate ./proof9" in run
    assert "claude plugin test ./proof9" in run
    assert "tsc -p tools/proof9-types/tsconfig.json" in run


def test_ci_installs_the_claude_code_that_wrote_the_vendored_types():
    """Different versions describe different APIs: a drift would type-check the
    plugin against one and run its tests on another."""
    header = (TYPES / "claude-code.d.ts").read_text().splitlines()[0]
    written_by = re.fullmatch(r"// Written by Claude Code (\S+)\.", header).group(1)
    assert f"@anthropic-ai/claude-code@{written_by}" in _steps_text(_jobs()["proof9-plugin"])


def test_the_type_check_covers_hooks_tests_and_state_contract():
    include = json.loads((TYPES / "tsconfig.json").read_text())["include"]
    assert set(include) >= {"claude-code.d.ts", "../../proof9/hooks", "../../proof9/tests", "../../proof9/types"}


def test_the_plugin_job_gates_the_summary():
    summary = _jobs()["test-summary"]
    assert "proof9-plugin" in summary["needs"]
    assert "needs.proof9-plugin.result" in _steps_text(summary)


def test_installs_do_not_ship_the_vendored_types():
    assert not list((ROOT / "proof9").rglob("claude-code.d.ts"))
