"""#1473 — the first-run messages name the two ways forward in plain words.

A new user's first `cf proof run` or `cf proof status` meets an empty ledger.
The message has to say what to do next without assuming they know the
pipeline: record a bug (`cf proof capture`) or lock in the tests that pass
today (`cf proof ratchet`), each with what it does.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.mark.parametrize("command", ["run", "status"])
def test_the_empty_ledger_names_both_ways_forward_and_what_each_does(tmp_path: Path, command):
    create_or_load_workspace(tmp_path)
    out = " ".join(runner.invoke(app, ["proof", command, "-w", str(tmp_path)]).output.split())
    assert "cf proof capture" in out
    assert "cf proof ratchet" in out
    assert "record a bug" in out
    assert "tests that pass today" in out
