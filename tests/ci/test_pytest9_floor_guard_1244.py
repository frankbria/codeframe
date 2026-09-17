"""#1244 — pytest must resolve at or above 9.0.3 (GHSA-6w46-j5rx-g56g).

pytest < 9.0.3 has a tmpdir-handling advisory, and pytest is a *runtime*
dependency here (`cf` shells out to it for the PROOF9 test gate and the
generated stubs import it), so the floor lives in two places in pyproject.toml.
Both floors and the installed runner are pinned here so a stray `>=8` cannot
creep back through either list.
"""

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

pytestmark = pytest.mark.v2

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
FLOOR = Version("9.0.3")


def _pytest_requirements() -> dict[str, Requirement]:
    data = tomllib.loads(PYPROJECT.read_text())
    lists = {
        "runtime": data["project"]["dependencies"],
        "dev": data["project"]["optional-dependencies"]["dev"],
    }
    found = {}
    for name, deps in lists.items():
        reqs = [Requirement(d) for d in deps]
        found[name] = next(r for r in reqs if r.name == "pytest")
    return found


def test_installed_pytest_is_patched():
    assert Version(pytest.__version__) >= FLOOR


@pytest.mark.parametrize("dep_list", ["runtime", "dev"])
def test_pyproject_pytest_floor_is_patched_and_capped(dep_list):
    spec = _pytest_requirements()[dep_list].specifier
    assert not spec.contains("9.0.2"), f"{dep_list}: floor must exclude < 9.0.3"
    assert spec.contains("9.0.3"), f"{dep_list}: 9.0.3 must satisfy the range"
    # #1168/#1170: floor-only pins on something we depend on are latent DOA releases.
    assert not spec.contains("10.0.0"), f"{dep_list}: cap the major"
