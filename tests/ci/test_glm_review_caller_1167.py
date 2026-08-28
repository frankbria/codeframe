"""#1167 — the GLM Review caller grants only what the reviewer needs.

The old pin (`b877d15`) declared `issues: write` and `id-token: write` on its
job, and GitHub fails a run when a caller grants less than the called job
requests — so this repo had to grant both. Upstream dropped them after verifying
the reviewer never mints an OIDC token, and that a comment on a PR is authorised
by `pull-requests` even though it posts through the shared
`/issues/{n}/comments` endpoint.

Re-adding either here would be a silent privilege regression: the workflow would
still pass, because over-granting is legal. This is the only thing that would
notice.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

CALLER = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "glm-review.yml"


def _review_job() -> dict:
    return yaml.safe_load(CALLER.read_text())["jobs"]["review"]


def test_it_grants_only_read_contents_and_pull_request_writes():
    assert _review_job()["permissions"] == {"contents": "read", "pull-requests": "write"}


def test_the_reusable_workflow_is_pinned_to_a_full_sha():
    """A moving `@main` would reintroduce the grants without a diff to review."""
    ref = _review_job()["uses"].split("@", 1)[1]
    assert len(ref) == 40 and all(
        c in "0123456789abcdef" for c in ref
    ), f"glm-review is pinned to {ref!r}; pin a full commit SHA"
