"""Bundled-ruff edge cases left by #1307 (#1308).

1. When the project has no ruff, CodeFRAME's own copy lints it, against the
   project's config. A config written for a newer ruff makes that older copy
   die with "unknown field", and the gate reported FAILED on clean code. That
   is version skew in *our* tool, not a defect in theirs: SKIPPED, explained.
   The project's own ruff failing on its own config stays FAILED (#1307).
2. Per-edit lint forced ``--output-format=concise``, which ruff < 0.3 rejects,
   so every edit in a project pinning old ruff failed with a usage error.
"""

from __future__ import annotations

import sys

import pytest

from codeframe.core import gates as core_gates
from codeframe.core.gates import LINTER_REGISTRY, GateStatus
from tests.core import test_gates_bundled_tool_1262 as _bundled

pytestmark = pytest.mark.v2

# The README-install PATH fixtures from #1262, shared rather than copied.
readme_install_path = _bundled.readme_install_path
repo = _bundled.repo

NEWER_CONFIGS = {
    "unknown-field": "[lint]\nfuture-option-xyz = true\n",
    "unknown-rule": '[lint]\nselect = ["ZZZ999"]\n',
    "unknown-variant": 'target-version = "py399"\n',
}


@pytest.mark.parametrize("config", NEWER_CONFIGS.values(), ids=NEWER_CONFIGS.keys())
def test_bundled_ruff_that_cannot_read_a_newer_config_skips(readme_install_path, repo, config):
    (repo / "ruff.toml").write_text(config)

    check = core_gates._run_ruff(repo)

    assert check.status == GateStatus.SKIPPED, check.output
    assert "newer ruff" in check.output, check.output


def test_the_projects_own_ruff_failing_on_its_config_still_fails(readme_install_path, repo, monkeypatch):
    """Only CodeFRAME's copy gets the benefit of the doubt: the project's own
    ruff rejecting its own config is a real, fixable failure."""
    (repo / "ruff.toml").write_text(NEWER_CONFIGS["unknown-field"])
    monkeypatch.setattr(core_gates, "_tool_prefix", lambda *a, **k: [sys.executable, "-m", "ruff"])

    check = core_gates._run_ruff(repo)

    assert check.status == GateStatus.FAILED, check.output


def test_per_edit_lint_with_bundled_ruff_and_a_newer_config_skips(readme_install_path, repo):
    (repo / "ruff.toml").write_text(NEWER_CONFIGS["unknown-field"])

    check = core_gates.run_lint_on_file(repo / "app.py", repo)

    assert check.status == GateStatus.SKIPPED, check.output


def test_per_edit_lint_does_not_force_an_output_format():
    (ruff,) = [c for c in LINTER_REGISTRY if c.name == "ruff"]
    assert not any(part.startswith("--output-format") for part in ruff.cmd), ruff.cmd


def test_per_edit_lint_still_parses_errors_in_the_default_format(readme_install_path, repo):
    (repo / "app.py").write_text("import os\n")

    check = core_gates.run_lint_on_file(repo / "app.py", repo)

    assert check.status == GateStatus.FAILED, check.output
    assert any(e.get("code") == "F401" for e in check.detailed_errors), check.output
    assert "F401" in check.output  # what the agent reads


def test_the_agent_sees_every_finding_not_the_first_few(readme_install_path, repo):
    """Without --output-format=concise, ruff's full format spends ~7 lines a
    finding, and the agent's tool result is capped at 2000 chars: only the
    first handful of 15 findings reached it (GLM review). The agent now gets
    one line per parsed finding."""
    from codeframe.adapters.llm.mock import MockProvider
    from codeframe.core.react_agent import ReactAgent
    from codeframe.core.workspace import create_or_load_workspace

    (repo / "app.py").write_text("".join(f"import mod{i}\n" for i in range(15)))
    agent = ReactAgent(workspace=create_or_load_workspace(repo), llm_provider=MockProvider())

    feedback = agent._run_lint_on_file("app.py")

    assert feedback.count("F401") == 15, feedback


def test_autofix_with_bundled_ruff_and_a_newer_config_skips(readme_install_path, repo):
    (repo / "ruff.toml").write_text(NEWER_CONFIGS["unknown-field"])

    check = core_gates.run_autofix_on_file(repo / "app.py", repo)

    assert check.status == GateStatus.SKIPPED, check.output
