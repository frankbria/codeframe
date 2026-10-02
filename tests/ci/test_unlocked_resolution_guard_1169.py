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
    # `needs:` is a string when there is one dependency and a list when there are
    # several. Normalise, so this stays a membership check and never degrades
    # into a substring match against a similarly-named job.
    needs = release["jobs"]["build"]["needs"]
    needs = [needs] if isinstance(needs, str) else needs
    assert gate in needs, (
        f"release job 'build' does not need {gate!r}, so a tag can publish a "
        "release whose unlocked resolution was never checked"
    )


def test_it_runs_the_cli_suite_and_the_mock_lifecycle_against_the_resolved_env():
    """#1268: typer 0.27 broke `cf proof capture` while `cf --help` still ran."""
    runs = " ".join(s.get("run", "") for s in _steps(_load(UNLOCKED)))
    for target in (
        "tests/cli",
        "tests/core/test_tui_dashboard.py",
        "tests/core/test_cli_validators.py",
        "tests/lifecycle/test_api_lifecycle.py",
        "tests/adapters/test_request_shape_1267.py",  # wire-level OpenAIProvider
    ):
        assert target in runs, f"{target} is not run against the unlocked resolution"


def test_it_uses_the_unlocked_interpreter_by_absolute_path():
    """An activated venv can fall back to another interpreter on PATH."""
    runs = [s.get("run", "") for s in _steps(_load(UNLOCKED))]
    pytest_runs = [r for r in runs if "-m pytest" in r]
    assert pytest_runs and all(
        '"$RUNNER_TEMP/unlocked/bin/python" -m pytest' in r for r in pytest_runs
    )
    assert not any("activate" in r for r in runs)


@pytest.mark.parametrize("package", ["anthropic", "openai", "typer", "click", "pytest"])
def test_sdks_the_cli_calls_into_have_a_ceiling(package):
    """The #1168 lesson: a floor-only pin is a latent dead-on-arrival release."""
    import tomllib

    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    pyproject = tomllib.loads((WORKFLOWS.parents[1] / "pyproject.toml").read_text())
    reqs = {
        canonicalize_name(r.name): r
        for r in map(Requirement, pyproject["project"]["dependencies"])
    }
    req = reqs.get(canonicalize_name(package))
    assert req is not None, f"{package} is not a runtime dependency"
    assert any(s.operator in ("<", "<=", "~=", "==") for s in req.specifier), (
        f"{req} has no upper bound"
    )
