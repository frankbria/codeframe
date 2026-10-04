"""Helper images that touch the production volume are pinned by digest (#1390).

`deploy/backup-db.sh` and the PM2 migration in `deploy.yml` run a Docker Hub
image with the data volume mounted read-write. A mutable tag means a retagged
or compromised image runs against the database (password hashes, tokens).
Dependabot's docker ecosystem does not read shell scripts or workflow steps,
so nothing else would notice a tag here.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
FILES = [*sorted((ROOT / "deploy").glob("*.sh")), ROOT / "deploy" / "README.md",
         ROOT / ".github" / "workflows" / "deploy.yml"]
# Public base images, as `name:tag`. Our own images come from compose, by tag
# CI just built, and are not what this guards.
# An optional registry prefix, so docker.io/library/alpine:x cannot slip by.
IMAGE = re.compile(
    r"(?<![\w/.])((?:docker\.io/)?(?:library/)?(?:python|alpine|busybox|debian|ubuntu|node):[\w.-]+)"
    r"(@sha256:[0-9a-f]{64})?"
)


def _refs(text):
    """Image references that would be *run*: not a tag named in prose
    (`inline code`) or looked up by the refresh recipe (pull + inspect)."""
    for line in text.splitlines():
        if "docker inspect" in line:
            continue
        for m in IMAGE.finditer(line):
            if line[m.start() - 1 : m.start()] == "`" and line[m.end() : m.end() + 1] == "`":
                continue
            yield m


def test_every_helper_image_is_pinned_by_digest():
    unpinned = [
        f"{path.relative_to(ROOT)}: {m.group(1)}"
        for path in FILES
        for m in _refs(path.read_text())
        if not m.group(2)
    ]
    assert not unpinned, unpinned


def test_the_guard_sees_the_images_it_protects():
    """A guard that matches nothing passes forever."""
    found = {m.group(1) for path in FILES for m in _refs(path.read_text())}
    assert {"python:3.12-alpine", "alpine:3.22"} <= found, found


def test_a_registry_qualified_spelling_is_caught_too():
    assert [m.group(1) for m in _refs("  docker.io/library/alpine:3.22 sh -c 'x'")] == [
        "docker.io/library/alpine:3.22"
    ]
