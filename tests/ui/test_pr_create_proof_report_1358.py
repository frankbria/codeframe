"""Create PR from the web UI attaches the PROOF9 report, like `cf pr create` (#1358).

The CLI appends `core.proof.report.pr_proof_report` to the PR body since
#1273; `POST /api/v2/pr` sent only what the user typed, so a reviewer on
GitHub never saw the proof status of a PR opened from the review page.
"""

from unittest.mock import patch

import pytest

from tests.ui.test_pr_create_payload_1272 import _github
from tests.ui import test_pr_create_payload_1272 as _base

pytestmark = pytest.mark.v2

client = _base.client


def _sent_body(client, payload):
    gh = _github()
    with patch("codeframe.ui.routers.pr_v2._get_github_client", return_value=gh):
        resp = client.post("/api/v2/pr", json=payload)
    assert resp.status_code == 201, resp.text
    return gh.create_pull_request.await_args.kwargs["body"]


def test_the_report_is_appended_by_default(client):
    body = _sent_body(client, {"branch": "feature/x", "title": "T", "body": "What changed."})
    assert body.startswith("What changed.\n\n## PROOF9"), body
    assert "No proof requirements" in body  # this workspace has none


def test_an_empty_body_is_just_the_report(client):
    body = _sent_body(client, {"branch": "feature/x", "title": "T", "body": ""})
    assert body.startswith("## PROOF9"), body


def test_it_can_be_turned_off(client):
    body = _sent_body(client, {"branch": "feature/x", "title": "T", "body": "B", "proof_report": False})
    assert body == "B"


def test_a_report_that_fails_never_blocks_the_pr(client):
    with patch("codeframe.core.proof.report.pr_proof_report", side_effect=RuntimeError("ledger gone")):
        body = _sent_body(client, {"branch": "feature/x", "title": "T", "body": "B"})
    assert body == "B"
