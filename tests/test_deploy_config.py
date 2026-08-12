"""Deploy configuration smoke checks (#727 / P0.16, rewritten for #1121).

Originally these guarded the PM2 shape: a missing ecosystem.production.config.js
and a wrong uv PATH aborted a fresh production host under `set -e`. #1121
replaced build-on-server with pre-built images, so the same invariants are now
asserted against the compose stack — the app must bind loopback only, the deploy
must not build anything on the box, and state must live on volumes rather than
inside an image that a pull replaces.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO = Path(__file__).resolve().parents[1]
DEPLOY_YML = REPO / ".github" / "workflows" / "deploy.yml"
COMPOSE = REPO / "docker-compose.yml"
COMPOSE_STAGING = REPO / "docker-compose.staging.yml"
COMPOSE_PRODUCTION = REPO / "docker-compose.production.yml"
BACKEND_DOCKERFILE = REPO / "Dockerfile"
FRONTEND_DOCKERFILE = REPO / "web-ui" / "Dockerfile"
CADDYFILE = REPO / "deploy" / "Caddyfile.example"
STAGING_ENV = REPO / ".env.staging.example"
PROD_ENV = REPO / ".env.production.example"


def _compose(*paths) -> dict:
    """Parsed compose, so assertions are about structure rather than substrings."""
    import yaml

    merged: dict = {}
    for path in paths:
        data = yaml.safe_load(path.read_text()) or {}
        for name, service in (data.get("services") or {}).items():
            merged.setdefault(name, {}).update(service)
    return merged


def test_the_compose_stack_exists():
    for path in (COMPOSE, COMPOSE_STAGING, COMPOSE_PRODUCTION):
        assert path.is_file(), f"{path.name} is missing — deploy.yml runs it"


def test_both_environments_are_migrated():
    """AC: no half-migrated environment. Production has never been deployed,
    which is exactly how it would get left behind."""
    text = DEPLOY_YML.read_text()

    assert "docker-compose.staging.yml" in text
    assert "docker-compose.production.yml" in text


def test_the_dockerfiles_exist():
    assert BACKEND_DOCKERFILE.is_file()
    assert FRONTEND_DOCKERFILE.is_file()


def _deploy_commands() -> str:
    """Every `run:` line in the DEPLOY jobs, comments stripped.

    Parsed and de-commented rather than grepped over the raw file: the workflow
    explains WHY it no longer runs `uv sync`, and a substring check reports that
    prose as a violation. My first version did exactly that — the same
    classifier mistake as #1113/#1116/#1064.
    """
    import yaml

    workflow = yaml.safe_load(DEPLOY_YML.read_text())
    lines = []
    for name, job in workflow["jobs"].items():
        if not name.startswith("deploy-"):
            continue  # the build jobs are SUPPOSED to build
        for step in job.get("steps", []):
            for line in step.get("run", "").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    lines.append(stripped)
    return "\n".join(lines)


def test_the_deploy_builds_nothing_on_the_server():
    """AC: no pm2, no uv sync, no npm run build over SSH.

    This is the whole point of #1121 — a build that happens on the box can fail
    halfway and leave new code beside a dead process, with no previous image to
    restart.
    """
    commands = _deploy_commands()

    for forbidden in ("pm2 ", "uv sync", "uv venv", "npm run build", "npm ci"):
        assert forbidden not in commands, (
            f"a deploy job still runs `{forbidden.strip()}` — the server must "
            "pull a pre-built image, not build one"
        )


def test_the_deploy_pulls_an_image_addressed_by_commit():
    """A moving tag would make a deploy unreproducible and a rollback guesswork."""
    commands = _deploy_commands()

    assert "IMAGE_TAG=" in commands and "github.sha" in commands, (
        "the deploy must pin the image to the commit it was built from"
    )
    # The command is $COMPOSE pull, where COMPOSE holds the -f flags — so
    # match case-insensitively rather than on the literal lowercase form.
    assert "compose pull" in commands.lower()


def test_the_deploy_never_issues_a_host_wide_docker_command():
    """The shared-VPS invariant from #912, carried over.

    `pm2 delete all` once stopped every unrelated app on this box. The compose
    equivalents are just as blunt: `docker system prune`, `docker stop $(docker
    ps -q)`, `docker compose down` without a project scope. Compose commands
    here must always name the project's own files.
    """
    commands = _deploy_commands()

    for forbidden in ("docker system prune", "docker container prune", "docker stop $(", "docker rm -f $("):
        assert forbidden not in commands, (
            f"`{forbidden}` would hit unrelated apps on the shared VPS (#912)"
        )


def test_state_lives_on_volumes_not_in_the_image():
    """AC: the SQLite DB and WORKSPACE_ROOT survive a deploy. Anything written
    inside the image is gone the moment a new tag is pulled."""
    services = _compose(COMPOSE)
    volumes = services["backend"]["volumes"]
    joined = " ".join(volumes)

    assert "/data" in joined
    assert "/workspaces" in joined

    env = services["backend"]["environment"]
    assert env["DATABASE_PATH"].startswith("/data/")
    assert env["WORKSPACE_ROOT"] == "/workspaces"


def test_the_backend_image_carries_git():
    """core/workspace and the sandbox create repos and worktrees. A slim base
    without git turns that into a runtime failure nothing here would catch."""
    assert "git" in BACKEND_DOCKERFILE.read_text()


def test_the_dependency_install_is_frozen():
    """An image resolved from a drifted lock is not what CI tested."""
    assert "--frozen" in BACKEND_DOCKERFILE.read_text()
    assert "npm ci" in FRONTEND_DOCKERFILE.read_text()


# ---------------------------------------------------------------------------
# TLS reverse proxy (#747 / P1.20): app processes bind loopback; a
# TLS-terminating proxy is the sole public listener; documented origins are
# https/wss. Under compose the binding that matters is the PUBLISHED port —
# 0.0.0.0 inside a container is fine and normal, publishing on 0.0.0.0 is not.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override", [COMPOSE_STAGING, COMPOSE_PRODUCTION], ids=["staging", "production"]
)
@pytest.mark.parametrize("service", ["backend", "frontend"])
def test_published_ports_are_loopback_only(override, service):
    services = _compose(COMPOSE, override)

    for mapping in services[service]["ports"]:
        assert str(mapping).startswith("127.0.0.1:"), (
            f"{override.name}:{service} publishes {mapping} — a non-loopback "
            "binding exposes the app directly and bypasses the TLS proxy (#747)"
        )


@pytest.mark.parametrize("service", ["backend", "frontend"])
def test_each_service_has_a_healthcheck(service):
    """`up -d` returning is not the same as the app serving. Without these the
    deploy reports success the instant the container starts."""
    assert "healthcheck" in _compose(COMPOSE)[service]


def test_the_frontend_waits_for_a_healthy_backend():
    depends = _compose(COMPOSE)["frontend"]["depends_on"]
    assert depends["backend"]["condition"] == "service_healthy"


def test_env_examples_bind_backend_loopback():
    """HOST in the deploy env templates must pin the backend to loopback."""
    for env in (STAGING_ENV, PROD_ENV):
        text = env.read_text()
        assert re.search(r"^HOST=127\.0\.0\.1$", text, re.MULTILINE), (
            f"{env.name}: HOST must be 127.0.0.1 (backend behind the proxy)"
        )
        assert "HOST=0.0.0.0" not in text, f"{env.name}: HOST must not be 0.0.0.0"


# --- Workspace allowlist must reach the deployed host (#896 / P0.2) ---------
#
# WORKSPACE_ROOT gates which directories an authenticated user can open an
# interactive session — and therefore a terminal shell — in. It defaulted to
# "no allowlist", and none of the three deployment configs set it, so the
# public instance ran wide open. Startup now refuses to serve in that state,
# which turns a silent security hole into a loud boot failure — so the deploy
# configs have to actually supply the value.


@pytest.mark.parametrize("env", [STAGING_ENV, PROD_ENV], ids=["staging", "prod"])
def test_env_examples_set_workspace_allowlist(env):
    text = env.read_text()
    root = re.search(r"^WORKSPACE_ROOT=(\S+)$", text, re.MULTILINE)
    assert root, f"{env.name}: WORKSPACE_ROOT must be set (#896)"
    assert root.group(1).startswith("/"), (
        f"{env.name}: WORKSPACE_ROOT must be absolute, got {root.group(1)!r}"
    )
    assert re.search(r"^CODEFRAME_DEPLOYMENT_MODE=self_hosted$", text, re.MULTILINE), (
        f"{env.name}: CODEFRAME_DEPLOYMENT_MODE must be explicit, not inherited"
    )


def test_deploy_workflow_writes_workspace_allowlist():
    """Both env write-outs (staging + production) must emit the two variables.

    WORKSPACE_ROOT is host-specific so it interpolates a shell variable;
    CODEFRAME_DEPLOYMENT_MODE is a deliberate constant, not an operator knob.
    """
    text = DEPLOY_YML.read_text()
    for emitted in ('"WORKSPACE_ROOT=${WORKSPACE_ROOT}"',
                    '"CODEFRAME_DEPLOYMENT_MODE=self_hosted"'):
        assert text.count(emitted) == 2, (
            f"deploy.yml must emit {emitted} in both the staging and production "
            f"env files (#896)"
        )


def test_deploy_workflow_defaults_workspace_root():
    """The value must not depend on a GitHub secret nobody has set yet.

    A hard requirement on a new secret would break the deploy on the very first
    run after this change — and the failure mode (startup refusing to serve) is
    indistinguishable from the bug being fixed.
    """
    text = DEPLOY_YML.read_text()
    assert text.count("WORKSPACE_ROOT:-") == 2, (
        "deploy.yml must default WORKSPACE_ROOT when the secret is unset"
    )


def test_env_examples_document_tls_origins():
    """Public-facing origins in the deploy templates must be https/wss, not
    plaintext http/ws (the whole point of #747)."""
    for env in (STAGING_ENV, PROD_ENV):
        text = env.read_text()
        for line in text.splitlines():
            if line.startswith("NEXT_PUBLIC_API_URL="):
                assert line.split("=", 1)[1].startswith("https://"), f"{env.name}: {line}"
            if line.startswith("NEXT_PUBLIC_WS_URL="):
                assert line.split("=", 1)[1].startswith("wss://"), f"{env.name}: {line}"


def test_caddyfile_example_exists_and_proxies_both_services():
    """A reverse-proxy config must ship and route to both loopback services."""
    assert CADDYFILE.is_file(), "deploy/Caddyfile.example must exist"
    text = CADDYFILE.read_text()
    assert "reverse_proxy" in text
    assert "127.0.0.1:14200" in text, "Caddyfile must proxy the backend"
    assert "127.0.0.1:14100" in text, "Caddyfile must proxy the frontend"
    # Backend paths (API/auth/websockets) must be routed to the backend.
    assert "/api/*" in text and "/auth/*" in text and "/ws/*" in text


@pytest.mark.skipif(shutil.which("caddy") is None, reason="caddy not available")
def test_caddyfile_example_is_valid():
    """If caddy is installed, the shipped config must pass `caddy validate`."""
    result = subprocess.run(
        ["caddy", "validate", "--config", str(CADDYFILE), "--adapter", "caddyfile"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_remote_setup_installs_proxy_and_binds_loopback_firewall():
    """Provisioning must install the proxy and stop exposing the app ports
    directly (only 80/443 should be public)."""
    text = (REPO / "scripts" / "remote-setup.sh").read_text()
    assert "caddy" in text.lower(), "remote-setup.sh must provision the reverse proxy"
    assert "for port in 80 443" in text, "remote-setup.sh firewall must allow HTTP/HTTPS (80/443)"
    # The raw app ports must no longer be opened to the world.
    assert "ufw allow 14100/tcp" not in text
    assert "ufw allow 14200/tcp" not in text


# --- .env ignore rules (#895 / P0.1) ----------------------------------------
#
# deploy.yml writes a real .env.production (ANTHROPIC_API_KEY + AUTH_SECRET)
# into the production git checkout. The ignore list used to enumerate
# .env/.env.local/.env.staging, so .env.production — and every future variant —
# defaulted to committable. These guard the pattern-plus-negation that replaced
# the enumeration.

# Templates that must stay committed (they carry no real values).
ENV_EXAMPLES = (
    ".env.example",
    ".env.production.example",
    ".env.staging.example",
    "web-ui/.env.example",
)

# Files that may hold live secrets and must never be committable. The last one
# does not exist today on purpose: the rule has to fail closed for variants
# nobody has thought of yet.
REAL_ENV_FILES = (
    ".env",
    ".env.local",
    ".env.staging",
    ".env.production",
    ".env.hosted",
)

# These guards are necessarily CI/checkout-only: gitignore behaviour cannot be
# tested without git. They do not run against an unpacked sdist.
requires_git_checkout = pytest.mark.skipif(
    shutil.which("git") is None or not (REPO / ".git").exists(),
    reason="needs a git checkout (not available in an unpacked sdist)",
)


def _is_ignored(path: str) -> bool:
    """Ask git whether `path` is excluded, rather than re-implementing
    .gitignore matching here.

    `--no-index` makes this a pure test of the ignore rules: without it git
    short-circuits and reports any *tracked* file as not-ignored, which would
    make the ENV_EXAMPLES assertions pass even if the `!` negation were broken.
    """
    return (
        subprocess.run(
            ["git", "check-ignore", "-q", "--no-index", "--", path],
            cwd=str(REPO),
            capture_output=True,
        ).returncode
        == 0
    )


@requires_git_checkout
@pytest.mark.parametrize("name", REAL_ENV_FILES)
def test_real_env_files_are_gitignored(name):
    """Any file that can hold live credentials must be unstageable."""
    assert _is_ignored(name), (
        f"{name} is not gitignored — `git add -A` would publish live secrets "
        f"to a public repo. Expected `.env*` to match it."
    )


@requires_git_checkout
@pytest.mark.parametrize("name", ENV_EXAMPLES)
def test_env_examples_are_not_gitignored(name):
    """The `.env*` rule must be narrowed by `!.env*.example` so the templates
    stay committable — otherwise operators lose the files they copy from."""
    assert not _is_ignored(name), (
        f"{name} is gitignored — the `!.env*.example` negation is missing or "
        f"ordered before the `.env*` rule that it must override."
    )


@requires_git_checkout
@pytest.mark.parametrize("name", REAL_ENV_FILES)
def test_real_env_files_are_not_tracked(name):
    """.gitignore only governs *untracked* paths — a file already in the index
    stays committable no matter what the rules say. Guard against a real env
    file being force-added (`git add -f`) and quietly reopening the hole."""
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", name],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert tracked.returncode != 0, (
        f"{name} is TRACKED — it will be committed on every change regardless "
        f"of .gitignore. Remove it from the index: git rm --cached {name}"
    )


@requires_git_checkout
@pytest.mark.parametrize("name", ENV_EXAMPLES)
def test_env_examples_are_still_tracked(name):
    """Belt-and-braces: the templates are actually in the index."""
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", name],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert tracked.returncode == 0, f"{name} is no longer tracked: {tracked.stderr.strip()}"
