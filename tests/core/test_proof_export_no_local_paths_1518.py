"""#1518 — an evidence report is shared, so it names no local path."""

import json
import subprocess

import pytest

from codeframe.core.proof.export import export_document, render_html
from tests.core.test_proof_export_1472 import ws  # noqa: F401 — the fixture

pytestmark = pytest.mark.v2


def test_without_a_remote_the_repository_is_the_folder_name(ws):  # noqa: F811
    workspace, path = ws
    doc = export_document(workspace)
    assert doc["provenance"]["repository"] == path.name


def test_with_a_remote_the_repository_is_its_url_without_credentials(ws):  # noqa: F811
    workspace, path = ws
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "https://bob:s3cret@github.com/acme/shop.git"],
        check=True,
    )
    assert export_document(workspace)["provenance"]["repository"] == "https://github.com/acme/shop.git"


def test_no_absolute_path_reaches_the_json_or_the_html(ws):  # noqa: F811
    workspace, path = ws
    doc = export_document(workspace)
    paths = [ev["artifact_path"] for r in doc["requirements"] for ev in r["evidence"]]
    assert paths and all(p.startswith(".codeframe/") for p in paths), paths
    for text in (json.dumps(doc), render_html(doc)):
        assert str(path) not in text
