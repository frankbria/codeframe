"""#1169 — the CI guard that resolves the *ranges*, not the lock.

`uv.lock` is what CI, `uv sync` and every contributor resolve. `uv tool install
codeframe-ai` gets none of it: pip/uv resolve the ranges in `pyproject.toml`
from scratch against whatever is on PyPI today. Those two resolutions drift
apart silently, and twice that drift shipped a dead-on-arrival release while
every gate was green (#1112, #1168).

`.github/workflows/unlocked-resolution.yml` closes the gap. These assertions
pin the properties that make it worth having — delete any one of them and the
job goes back to testing the lockfile, or stops blocking a release.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
UNLOCKED = WORKFLOWS / "unlocked-resolution.yml"
RELEASE = WORKFLOWS / "release.yml"


def _load(path: Path) -> dict:
    # PyYAML parses the bare `on:` key as the boolean True.
    return yaml.safe_load(path.read_text())


def _steps(workflow: dict) -> list[dict]:
    return [s for job in workflow["jobs"].values() for s in job.get("steps", [])]


def test_it_runs_on_a_schedule():
    """This class of break arrives from upstream, not from a commit of ours."""
    triggers = _load(UNLOCKED)[True]
    assert "schedule" in triggers, (
        "without a schedule the job only ever sees the resolution as of the last "
        "push, which is exactly the blind spot that shipped 0.9.2"
    )


def test_it_never_installs_from_the_lockfile():
    """`uv sync`/`uv run` resolve uv.lock — the resolution this job must NOT test."""
    runs = " ".join(s.get("run", "") for s in _steps(_load(UNLOCKED)))
    for locked in ("uv sync", "uv run", "uv lock"):
        assert locked not in runs, f"{locked!r} reads uv.lock; this job must resolve the ranges"
    assert "uv pip install" in runs


def test_it_exercises_the_sdk_signature_guards_against_the_resolved_env():
    """Installing is not enough — 0.9.2 installed fine and TypeError'd on first call."""
    runs = " ".join(s.get("run", "") for s in _steps(_load(UNLOCKED)))
    assert "test_sdk_kwargs_guard_614.py" in runs
    assert "test_model_defaults_guard_1112.py" in runs


def test_the_release_is_gated_on_it():
    release = _load(RELEASE)
    gate = next(
        (
            name
            for name, job in release["jobs"].items()
            if "unlocked-resolution.yml" in str(job.get("uses", ""))
        ),
        None,
    )
    assert gate, "release.yml does not call the unlocked-resolution workflow"
    assert gate in release["jobs"]["build"]["needs"], (
        f"release job 'build' does not need {gate!r}, so a tag can publish a "
        "release whose unlocked resolution was never checked"
    )
