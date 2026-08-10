"""#1077 — GET /api/v2/review/patch 500'd on a diff containing a non-UTF-8 byte.

`core/git.get_patch` goes through GitPython, which decodes with
``surrogateescape``. That is lossless in Python, but a lone surrogate cannot be
serialised into JSON — so the response raised and FastAPI answered 500. The
`Export Patch` button on `/review` was simply dead for any repository with one
Latin-1 comment or a stray byte from a bad merge.

A patch is a file that gets fed back to ``git apply``, so it has to be
byte-faithful end to end. The endpoint now returns the raw bytes as
application/octet-stream.
"""

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import git
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _init_repo(path, final: bytes):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    target = path / "notes.txt"
    target.write_bytes(b"original\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=path, check=True)
    target.write_bytes(final)
    return path


@pytest.fixture
def latin1_repo(tmp_path):
    """A tracked file edited to contain a byte that is not valid UTF-8."""
    return _init_repo(tmp_path, b"caf\xe9 latin-1\n")


@pytest.fixture
def ascii_repo(tmp_path):
    return _init_repo(tmp_path, b"plain ascii change\n")


def _client(repo):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import review_v2

    workspace = create_or_load_workspace(repo)
    app = FastAPI()
    app.include_router(review_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    return TestClient(app), workspace


class TestTheEndpointNoLongerCrashes:
    def test_a_non_utf8_diff_is_200(self, latin1_repo):
        """AC: 200 for a diff containing a non-UTF-8 byte."""
        client, _ = _client(latin1_repo)
        res = client.get("/api/v2/review/patch")
        assert res.status_code == 200, res.text

    def test_the_raw_byte_survives_the_response(self, latin1_repo):
        client, _ = _client(latin1_repo)
        res = client.get("/api/v2/review/patch")
        assert b"\xe9" in res.content
        # Not the UTF-8 re-encoding of U+00E9, which is what a JSON round-trip
        # or a str->bytes step would have produced.
        assert b"\xc3\xa9" not in res.content

    def test_the_filename_moved_to_content_disposition(self, latin1_repo):
        client, _ = _client(latin1_repo)
        res = client.get("/api/v2/review/patch")
        assert "attachment" in res.headers["content-disposition"]
        assert ".patch" in res.headers["content-disposition"]


class TestItIsByteIdenticalToGit:
    """AC: byte-identical to `git diff --patch --full-index`."""

    @pytest.mark.parametrize("fixture", ["latin1_repo", "ascii_repo"])
    def test_the_response_matches_git(self, fixture, request):
        repo = request.getfixturevalue(fixture)
        client, _ = _client(repo)

        expected = subprocess.run(
            ["git", "diff", "--patch", "--full-index"],
            cwd=repo,
            capture_output=True,
        ).stdout

        assert client.get("/api/v2/review/patch").content == expected

    @pytest.mark.parametrize("fixture", ["latin1_repo", "ascii_repo"])
    def test_core_get_patch_bytes_matches_git(self, fixture, request):
        repo = request.getfixturevalue(fixture)
        workspace = create_or_load_workspace(repo)

        expected = subprocess.run(
            ["git", "diff", "--patch", "--full-index"],
            cwd=repo,
            capture_output=True,
        ).stdout

        assert git.get_patch_bytes(workspace) == expected


class TestTheExportedPatchApplies:
    """AC: assert by applying it back with `git apply` and comparing bytes.

    The shape used by tests/core/test_locale_decoding_1029.py — a patch that
    cannot be applied is not a patch, however well-formed it looks.
    """

    @pytest.mark.parametrize(
        "fixture,final",
        [("latin1_repo", b"caf\xe9 latin-1\n"), ("ascii_repo", b"plain ascii change\n")],
    )
    def test_git_apply_reproduces_the_original_bytes(
        self, fixture, final, request, tmp_path
    ):
        repo = request.getfixturevalue(fixture)
        client, _ = _client(repo)
        patch_bytes = client.get("/api/v2/review/patch").content

        # A clean clone at the base commit, then apply the exported patch.
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(repo), str(clone)], check=True, capture_output=True
        )
        patch_file = tmp_path / "exported.patch"
        patch_file.write_bytes(patch_bytes)

        applied = subprocess.run(
            ["git", "apply", str(patch_file)], cwd=clone, capture_output=True
        )
        assert applied.returncode == 0, applied.stderr

        assert (clone / "notes.txt").read_bytes() == final


class TestAnAsciiDiffIsUnchanged:
    """AC: a plain ASCII diff still exports unchanged."""

    def test_it_still_contains_the_change(self, ascii_repo):
        client, _ = _client(ascii_repo)
        body = client.get("/api/v2/review/patch").content
        assert b"plain ascii change" in body
        assert b"diff --git" in body
