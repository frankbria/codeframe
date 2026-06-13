"""`cf --version` / `cf -V` print the version and exit cleanly."""
import re

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version_flag_prints_version_and_exits(flag):
    result = runner.invoke(app, [flag])
    assert result.exit_code == 0
    assert "codeframe" in result.stdout
    # A semver-ish token must be present (e.g. 0.9.1 or 0.0.0+unknown).
    assert re.search(r"\d+\.\d+\.\d+", result.stdout)
