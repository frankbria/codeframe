"""One tech-stack detector for every surface (#1381).

`cf init --detect` and the web UI (workspace init, the Settings auto-detect
toggle) each had their own detector, and they disagreed: the router's decided
"uv" with ``"uv" in content``, so any pyproject that mentioned uvicorn was
reported as "Python with uv". The agent reads this text, so the same repo got a
different description depending on where it was detected.
"""

import pytest

from codeframe.core.tech_stack import detect_tech_stack

pytestmark = pytest.mark.v2

UVICORN_ONLY = """\
[project]
name = "svc"
dependencies = ["uvicorn>=0.30", "starlette"]
"""


def test_a_pyproject_that_only_mentions_uvicorn_is_not_uv(tmp_path):
    (tmp_path / "pyproject.toml").write_text(UVICORN_ONLY, encoding="utf-8")

    assert detect_tech_stack(tmp_path) == "Python with pip"


def test_uv_is_still_detected_from_its_lockfile(tmp_path):
    (tmp_path / "pyproject.toml").write_text(UVICORN_ONLY, encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    assert detect_tech_stack(tmp_path) == "Python with uv"



@pytest.mark.parametrize(
    "package_json",
    ["[]", "null", '"x"', '{"dependencies": ["react"]}', '{"devDependencies": null}'],
)
def test_a_package_json_that_is_not_an_object_does_not_crash(tmp_path, package_json):
    """The web UI's old detector never parsed package.json; the shared one
    does, and must not turn valid-but-odd JSON into a 500 (GLM review)."""
    (tmp_path / "package.json").write_text(package_json, encoding="utf-8")

    assert detect_tech_stack(tmp_path) == "JavaScript with npm"
