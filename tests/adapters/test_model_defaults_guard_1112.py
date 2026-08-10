"""#1112 — the release guard that stops a dated model ID rotting out of a published wheel.

0.9.1 shipped `claude-3-5-haiku-20241022` and friends. Those IDs were valid the
day they were written and 404 today, so every LLM command in the published
artifact was dead on arrival. Dated IDs get retired; the undated aliases do not.
This pins that rule so it cannot recur silently.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_model_defaults import (
    DATED_MODEL_RE,
    check_call_sites,
    check_defaults_are_aliases,
    check_defaults_resolve,
)

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dated_ids_are_recognised_and_aliases_are_not():
    assert DATED_MODEL_RE.search("claude-3-5-haiku-20241022")
    assert DATED_MODEL_RE.search("claude-haiku-4-5-20251001")
    assert not DATED_MODEL_RE.search("claude-haiku-4-5")
    assert not DATED_MODEL_RE.search("claude-sonnet-4-5")


def test_every_default_model_is_a_dateless_alias():
    assert check_defaults_are_aliases() == []


def test_no_live_call_site_hardcodes_a_dated_model_id():
    assert check_call_sites(REPO_ROOT) == []


def test_require_live_without_a_key_is_a_failure(monkeypatch):
    """An unconfigured release secret must fail loudly, not skip the live check."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_GUARD_REQUIRE_LIVE", "1")
    violations = check_defaults_resolve()
    assert len(violations) == 1
    assert "ANTHROPIC_API_KEY" in violations[0]


def test_no_key_and_no_require_live_skips_quietly(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_GUARD_REQUIRE_LIVE", raising=False)
    assert check_defaults_resolve() == []


def test_script_exits_zero_offline():
    """The release workflow runs this as a build step, so its exit code matters."""
    # Drop the key so this stays offline even on a machine (or CI runner) that
    # has one — the live half is the release job's business, not this test's.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_model_defaults"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
