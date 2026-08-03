"""FastAPI Status Server for CodeFRAME."""

# Standard library imports
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path

# Third-party imports
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Local imports - v2 only (no v1 persistence layer)
from codeframe.ui.routers import (
    # v2 routers only - delegate to codeframe.core modules
    batches_v2,
    blockers_v2,
    checkpoints_v2,
    costs_v2,
    diagnose_v2,
    discovery_v2,
    environment_v2,
    events_v2,
    gates_v2,
    git_v2,
    github_integrations_v2,
    interactive_sessions_v2,
    pr_v2,
    prd_v2,
    proof_v2,
    review_v2,
    schedule_v2,
    session_chat_ws,
    settings_v2,
    terminal_ws,
    streaming_v2,
    tasks_v2,
    templates_v2,
    workspace_v2,
)
from codeframe.auth import router as auth_router
from codeframe.auth.dependencies import require_auth, require_method_scope
from codeframe.platform_store.database import Database
from codeframe.lib.rate_limiter import (
    get_rate_limiter,
    rate_limit_exceeded_handler,
)
from codeframe.config.rate_limits import get_rate_limit_config

# ============================================================================
# Configuration and Setup
# ============================================================================


class DeploymentMode(str, Enum):
    """Deployment mode for CodeFRAME."""

    SELF_HOSTED = "self_hosted"
    HOSTED = "hosted"


def get_deployment_mode() -> DeploymentMode:
    """Get current deployment mode from environment.

    Returns:
        DeploymentMode.SELF_HOSTED or DeploymentMode.HOSTED
    """
    mode = os.getenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted").lower()

    if mode == "hosted":
        return DeploymentMode.HOSTED
    return DeploymentMode.SELF_HOSTED


def is_hosted_mode() -> bool:
    """Check if running in hosted SaaS mode.

    Returns:
        True if hosted mode, False if self-hosted
    """
    return get_deployment_mode() == DeploymentMode.HOSTED


# Logger setup
logger = logging.getLogger(__name__)


# ============================================================================
# Application Lifespan
# ============================================================================


# Note: Session cleanup removed - v1 persistence layer not used in v2
# If session management is needed, implement in v2 core modules


def _env_flag(name: str) -> bool:
    """Whether an opt-in env flag is set. Truthy: ``1``, ``true``, ``yes``, ``on``."""
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _allow_insecure_secret() -> bool:
    """Whether the local-dev escape hatch for the default JWT secret is set.

    Controlled by ``CODEFRAME_ALLOW_INSECURE_SECRET`` (default OFF). This hatch
    is for local development only and is **never** honored in hosted mode.
    """
    return _env_flag("CODEFRAME_ALLOW_INSECURE_SECRET")


def _validate_workspace_allowlist_config():
    """Refuse to serve with an unrestricted workspace allowlist (issue #896).

    ``enforce_workspace_allowlist`` is a no-op when ``WORKSPACE_ROOT`` is unset,
    so an exposed server handed every authenticated principal a shell anywhere
    on the host: ``POST /api/v2/sessions`` stores an arbitrary ``workspace_path``
    that ``terminal_ws`` later uses as a shell ``cwd``. The control defaulted to
    off and no deployment config set it, so the public instance ran wide open.

    In self-hosted mode the allowlist only matters where authentication is what
    stands between a caller and those routes: with auth disabled every caller is
    unrestricted already, and demanding a root would just break local dev. So
    the self-hosted gate is "auth enforced but no roots configured".

    Hosted/multi-tenant has no unrestricted configuration at all — the roots are
    what separate tenants. ``_validate_security_config`` already rejects
    hosted-with-auth-disabled, but this does not lean on that: a fail-closed
    property that depends on the order of two validators reopens the moment
    someone reorders them.

    Mirrors the ``CODEFRAME_ALLOW_INSECURE_SECRET`` hatch above: single-operator
    self-hosted can still opt out via ``CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES``
    — explicitly and loudly — but hosted never can.

    Raises:
        RuntimeError: If the allowlist is missing where it is required and no
            applicable escape hatch is set.
    """
    from codeframe.auth.dependencies import auth_required
    from codeframe.ui.dependencies import _allowed_workspace_roots

    hosted = get_deployment_mode() == DeploymentMode.HOSTED

    if _allowed_workspace_roots() or (not hosted and not auth_required()):
        return

    if not hosted and _env_flag("CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES"):
        logger.warning(
            "⚠️  SECURITY: WORKSPACE_ROOT is unset, so any authenticated user can "
            "open a session — and therefore a shell — in ANY directory on this "
            "host. Starting anyway because CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES "
            "is set. Use this for a single-operator LOCAL machine only; never "
            "expose this server."
        )
        return

    raise RuntimeError(
        "🚨 SECURITY: WORKSPACE_ROOT must list the permitted workspace roots in "
        + ("hosted mode" if hosted else "this configuration")
        + ". Without it, any authenticated user can start "
        "an interactive session — and a terminal shell — in any directory on this "
        "host. Set WORKSPACE_ROOT to one or more directories separated by "
        f"'{os.pathsep}' (e.g. WORKSPACE_ROOT=/srv/workspaces)"
        + (
            "."
            if hosted
            else ", or set CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES=1 for a "
            "single-operator local machine only."
        )
    )


def _validate_security_config():
    """Validate security configuration at startup.

    Refuses to start whenever the JWT secret is still the publicly-known default
    AND auth would actually be enforced — otherwise anyone can forge a valid JWT
    and bypass auth on every v2/WS/SSE route (issue #643). A local-dev escape
    hatch (``CODEFRAME_ALLOW_INSECURE_SECRET``) is honored only in self-hosted
    mode; hosted mode always fails on the default secret.

    Raises:
        RuntimeError: If auth is enabled (or hosted mode) while the default
            secret is in use and no escape hatch applies, or if hosted mode is
            requested with authentication disabled.
    """
    from codeframe.auth.manager import SECRET, DEFAULT_SECRET
    from codeframe.auth.dependencies import auth_required

    deployment_mode = get_deployment_mode()

    # Hosted/production mode checks must run regardless of whether the secret is
    # custom, because hosted mode must never run with auth disabled.
    if deployment_mode == DeploymentMode.HOSTED:
        # Never tolerate the default secret. The dev escape hatch is
        # intentionally NOT honored here.
        if SECRET == DEFAULT_SECRET:
            raise RuntimeError(
                "🚨 SECURITY: AUTH_SECRET must be set in hosted/production mode. "
                "Using the default secret compromises all JWT tokens. "
                "Set the AUTH_SECRET environment variable to a secure random value "
                "(e.g. `openssl rand -hex 32`)."
            )
        if not auth_required():
            raise RuntimeError(
                "Hosted mode requires authentication. "
                "Set CODEFRAME_AUTH_REQUIRED=true (or equivalent) and configure a secure AUTH_SECRET."
            )
        # Hosted mode with a real secret and auth enabled is safe to start.
        return

    if SECRET != DEFAULT_SECRET:
        logger.info("🔐 AUTH_SECRET configured (custom secret in use)")
        return

    # Self-hosted with auth enabled: forging a JWT is trivial with the known
    # default secret, so refuse to start unless the operator has explicitly
    # opted into the insecure local-dev escape hatch.
    if auth_required():
        if _allow_insecure_secret():
            logger.warning(
                "⚠️  SECURITY: starting with the default AUTH_SECRET because "
                "CODEFRAME_ALLOW_INSECURE_SECRET is set. JWTs can be forged — "
                "use this for LOCAL DEVELOPMENT ONLY, never expose this server."
            )
            return
        raise RuntimeError(
            "🚨 SECURITY: AUTH_SECRET must be set when authentication is enabled. "
            "The default secret lets anyone forge a valid JWT and bypass auth. "
            "Set AUTH_SECRET to a secure random value (e.g. `openssl rand -hex 32`), "
            "or set CODEFRAME_ALLOW_INSECURE_SECRET=1 for local development only."
        )

    # Auth disabled: the secret is not used to enforce access, so a default is
    # acceptable — but still warn so it isn't shipped into an exposed server.
    logger.warning(
        "⚠️  Running with default AUTH_SECRET - acceptable for self-hosted "
        "development only (auth is disabled)"
    )


def _worker_count_from_env() -> int:
    """Worker count from ``WEB_CONCURRENCY`` / ``UVICORN_WORKERS`` env vars.

    Returns the largest valid value found, or ``1`` when neither is set or
    parseable. ``WEB_CONCURRENCY`` is honored by both uvicorn and gunicorn;
    ``UVICORN_WORKERS`` is uvicorn's env-var form of ``--workers``.
    """
    count = 1
    for var in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = os.getenv(var)
        if not raw or not raw.strip():
            continue
        try:
            value = int(raw.strip())
        except ValueError:
            continue
        if value > count:
            count = value
    return count


def _parse_worker_count_from_argv(argv: list[str]) -> int | None:
    """Parse a uvicorn/gunicorn worker count from a command-line argv list.

    Recognizes ``--workers N``, ``--workers=N``, ``-w N`` and ``-w=N``. Returns
    the positive integer worker count, or ``None`` when no parseable, positive
    worker flag is present.
    """
    for i, token in enumerate(argv):
        value: str | None = None
        if token in ("--workers", "-w"):
            value = argv[i + 1] if i + 1 < len(argv) else None
        elif token.startswith("--workers="):
            value = token[len("--workers="):]
        elif token.startswith("-w="):
            value = token[len("-w="):]
        if value is None:
            continue
        try:
            count = int(value.strip())
        except (ValueError, AttributeError):
            continue
        if count > 0:
            return count
    return None


def _is_asgi_server_cmdline(argv: list[str]) -> bool:
    """True when ``argv`` looks like a uvicorn/gunicorn server invocation.

    Matches ``uvicorn``, ``python -m uvicorn``, an absolute ``uvicorn`` path, and
    ``gunicorn`` (incl. ``-k uvicorn.workers.UvicornWorker``). Used to avoid
    reading a ``--workers`` flag off an unrelated ancestor (a wrapper, supervisor,
    or test runner) and mistaking it for the server's worker count.

    This is a loose substring match on any token, so a path that merely contains
    ``uvicorn``/``gunicorn`` would also match. That's acceptable for an
    advisory-only warning: a false positive only emits an unnecessary WARNING, it
    never breaks startup.
    """
    return any(("uvicorn" in token or "gunicorn" in token) for token in argv)


def _read_proc_cmdline(pid: int) -> list[str] | None:
    """Read ``/proc/<pid>/cmdline`` as an argv list, or ``None`` if unavailable.

    Linux-only; returns ``None`` on any error (missing /proc, permission, race).
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if not raw:
        return None
    # /proc cmdline is NUL-separated and usually NUL-terminated.
    return [part.decode("utf-8", "replace") for part in raw.split(b"\x00") if part]


def _read_proc_ppid(pid: int) -> int | None:
    """Read the parent PID from ``/proc/<pid>/status``, or ``None`` on error."""
    try:
        with open(f"/proc/{pid}/status", "r", encoding="ascii") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _iter_ancestor_cmdlines(max_depth: int = 8) -> list[list[str]]:
    """Best-effort: this process's cmdline plus those of its ancestors.

    Walks up the process tree via ``/proc`` (Linux only). Returns ``[]`` on
    non-Linux platforms or when nothing is readable. Never raises.
    """
    cmdlines: list[list[str]] = []
    try:
        pid: int | None = os.getpid()
    except OSError:
        return cmdlines
    seen: set[int] = set()
    for _ in range(max_depth):
        if pid is None or pid <= 0 or pid in seen:
            break
        seen.add(pid)
        cmdline = _read_proc_cmdline(pid)
        if cmdline:
            cmdlines.append(cmdline)
        pid = _read_proc_ppid(pid)
    return cmdlines


def _detect_workers_from_process_tree() -> int | None:
    """Best-effort worker count from a ``--workers N`` flag on an ancestor.

    Worker subprocesses are spawned, so their own ``sys.argv`` does not carry
    ``--workers`` — the original flag lives on the supervisor (parent) process.
    Returns ``None`` when nothing is found or detection isn't possible. Never
    raises.
    """
    try:
        for argv in _iter_ancestor_cmdlines():
            if not _is_asgi_server_cmdline(argv):
                continue
            count = _parse_worker_count_from_argv(argv)
            if count is not None:
                return count
    except Exception:  # best-effort signal; never break startup
        return None
    return None


def _detect_worker_count() -> int:
    """Best-effort detection of the configured uvicorn/gunicorn worker count.

    Combines two signals and returns the largest:

    - ``WEB_CONCURRENCY`` / ``UVICORN_WORKERS`` env vars (set by most production
      process managers), and
    - a ``--workers N`` flag on an ancestor process command line, which covers a
      bare ``uvicorn ... --workers N`` invocation that sets no env var (Linux
      only, via ``/proc``).

    This is a best-effort signal for the startup warning below; detection
    failure degrades silently to the env-var result (never raises).
    """
    count = _worker_count_from_env()
    try:
        from_tree = _detect_workers_from_process_tree()
    except Exception:
        from_tree = None
    if from_tree is not None and from_tree > count:
        count = from_tree
    return count


def _per_worker_rate_limit_warning(
    *, enabled: bool, storage: str, worker_count: int
) -> str | None:
    """Return a startup warning when in-memory rate limiting is per-worker.

    With in-memory storage each worker process keeps its own rate-limit
    counters, so the effective limit multiplies by the worker count — silently
    weakening brute-force protection on the auth endpoints (issue #678). Returns
    ``None`` when the configuration is safe (rate limiting disabled,
    redis-backed, or a single worker).
    """
    if not enabled or storage != "memory" or worker_count <= 1:
        return None
    return (
        f"⚠️  Rate limiting uses in-memory storage with {worker_count} workers: "
        f"counters are per-worker, so limits (including auth brute-force "
        f"protection) are effectively multiplied by ~{worker_count}x. "
        f"Set RATE_LIMIT_STORAGE=redis (with REDIS_URL) for shared, "
        f"cross-worker rate limiting."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Load environment variables from .env file
    from codeframe.core.config import load_environment
    load_environment()

    # The auth manager captured SECRET at import time, before .env was loaded
    # (the app module is imported by uvicorn before this lifespan runs). Refresh
    # it from the now-loaded environment so a `.env`-only AUTH_SECRET is honored
    # by signing, verification, and the WS decoders — and so the guard below
    # validates the real configured secret, not a stale default (issue #643).
    from codeframe.auth.manager import refresh_secret
    refresh_secret()

    # Validate security configuration before starting
    _validate_security_config()

    _validate_workspace_allowlist_config()

    # Initialize global persistent DB (used by interactive_sessions and auth)
    db_path = os.environ.get(
        "DATABASE_PATH",
        str(Path.cwd() / ".codeframe" / "state.db"),
    )
    db = Database(db_path)
    db.initialize()
    app.state.db = db

    # Log the effective auth mode (#336: env-gated, secure by default)
    from codeframe.auth.dependencies import auth_required

    if auth_required():
        logger.info("🔒 Authentication: ENABLED (default; set CODEFRAME_AUTH_REQUIRED=false to disable locally)")
    else:
        logger.warning("🔓 Authentication: DISABLED via CODEFRAME_AUTH_REQUIRED — do not expose this server publicly")

    # Initialize rate limiting
    rate_limit_config = get_rate_limit_config()
    if rate_limit_config.enabled:
        limiter = get_rate_limiter()
        if limiter:
            app.state.limiter = limiter
            logger.info(
                f"🚦 Rate limiting: ENABLED "
                f"(storage={rate_limit_config.storage}, "
                f"standard={rate_limit_config.standard_limit})"
            )
        # Warn when in-memory counters are split across multiple workers, which
        # multiplies the effective limit and weakens auth brute-force protection
        # (issue #678). Silent for single-worker and Redis-backed deployments.
        per_worker_warning = _per_worker_rate_limit_warning(
            enabled=rate_limit_config.enabled,
            storage=rate_limit_config.storage,
            worker_count=_detect_worker_count(),
        )
        if per_worker_warning:
            logger.warning(per_worker_warning)
    else:
        logger.info("🚦 Rate limiting: DISABLED")

    yield

    # Shutdown: nothing to clean up (v2 uses per-workspace databases managed by core)


# ============================================================================
# OpenAPI Tags and Metadata
# ============================================================================

# Tags must stay in sync with the tags of the routers actually mounted below —
# tests/ui/test_openapi_docs_accuracy.py asserts the two sets are equal (#951).
# The two WebSocket routes carry no OpenAPI tag (WebSockets are not part of the
# OpenAPI schema); they are documented in OPENAPI_DESCRIPTION instead.
OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "Health check endpoints - verify API availability and get deployment information.",
    },
    {
        "name": "auth",
        "description": "Authentication - bootstrap registration, login, and short-lived stream tickets for SSE/WebSocket connections.",
    },
    {
        "name": "users",
        "description": "The authenticated user's own account - read and update the current user record.",
    },
    {
        "name": "api-keys",
        "description": "API key management - create, list, and revoke long-lived `X-API-Key` credentials.",
    },
    {
        "name": "workspaces-v2",
        "description": "Workspace lifecycle - initialize a workspace on a repository path, read its status, and manage its configuration.",
    },
    {
        "name": "prd-v2",
        "description": "PRD management - read and version the product requirements document, and run the streaming stress-test that surfaces and resolves ambiguities.",
    },
    {
        "name": "discovery-v2",
        "description": "Discovery phase - interactive PRD discovery sessions that turn a codebase and a conversation into a PRD.",
    },
    {
        "name": "tasks-v2",
        "description": "Task management and execution - list, create, and update tasks, start work on one, and stream its execution events (SSE).",
    },
    {
        "name": "batches-v2",
        "description": "Batch orchestration - run many tasks serially or in parallel, and monitor, cancel, or resume a batch.",
    },
    {
        "name": "diagnose-v2",
        "description": "Task diagnostics - explain why a task stalled, failed, or is blocked.",
    },
    {
        "name": "blockers-v2",
        "description": "Human-in-the-loop blockers - list, view, and answer the questions an agent raised before it can continue.",
    },
    {
        "name": "sessions-v2",
        "description": "Interactive agent sessions - create a session, replay its message history, and manage its lifecycle. Live chat and terminal I/O run over the WebSocket routes described above.",
    },
    {
        "name": "events",
        "description": "Append-only event log - query the durable record of what the orchestrator and its agents did.",
    },
    {
        "name": "proof-v2",
        "description": "PROOF9 quality system - capture requirements from glitches, run proof obligations, manage waivers, and query evidence.",
    },
    {
        "name": "gates-v2",
        "description": "Verification gates - run the test, lint, type-check and coverage gates and read their results.",
    },
    {
        "name": "review-v2",
        "description": "Code review - inspect the working diff and export it as a patch.",
    },
    {
        "name": "git-v2",
        "description": "Git operations - status, diff, branch, and commit against the workspace repository.",
    },
    {
        "name": "pr-v2",
        "description": "GitHub pull requests - create a PR, read its status and checks, and merge it through the PROOF9 merge gate.",
    },
    {
        "name": "checkpoints-v2",
        "description": "Workspace checkpoints - snapshot workspace state and restore a previous snapshot.",
    },
    {
        "name": "schedule-v2",
        "description": "Task scheduling - schedule predictions, bottlenecks, and critical-path analysis over the task graph.",
    },
    {
        "name": "templates-v2",
        "description": "Project and task templates - list, view, and apply reusable templates.",
    },
    {
        "name": "environment-v2",
        "description": "Environment management - check the toolchain a workspace needs, install what is missing, and run diagnostics.",
    },
    {
        "name": "metrics",
        "description": "Cost and token metrics - spend summaries and per-task / per-agent token breakdowns.",
    },
    {
        "name": "settings",
        "description": "Server and workspace settings - agent defaults, provider API keys, PROOF9 defaults, and outbound notification webhooks.",
    },
    {
        "name": "integrations",
        "description": "External service integrations - connect a GitHub repository via Personal Access Token, then browse and import its issues as tasks.",
    },
]

OPENAPI_DESCRIPTION = """
# CodeFRAME API

**CodeFRAME** is a project delivery system for AI-assisted software work: Think → Build →
Prove → Ship. It owns the edges of the pipeline — requirements, task decomposition,
verification gates, and shipping — and delegates the code writing to frontier coding
agents. This API is the HTTP surface over that system; the `cf` CLI drives the same core
without a server.

## Overview

The CodeFRAME API enables you to:

- **Set up a workspace** - Initialize CodeFRAME on a repository path and manage its configuration
- **Think** - Author and version a PRD, stress-test it for ambiguities, and generate tasks from it
- **Build** - Start work on a task or a batch of tasks, follow execution events in real time, and answer blockers
- **Prove** - Run verification gates and the PROOF9 evidence system over the result
- **Ship** - Review the diff, open a pull request, and merge it through the PROOF9 merge gate

## Authentication

All `/api/v2/*` endpoints require authentication by default (disable for local
development with `CODEFRAME_AUTH_REQUIRED=false`). Public: `/`, `/health`, the docs, and
the `/auth/*` login and bootstrap-registration endpoints. Two authentication methods:

1. **API Key** - Include an `X-API-Key` header with your API key
2. **Session Token** - Use the JWT from the login endpoint in an `Authorization: Bearer <token>` header

Scopes are derived from the account: every principal has `read` and `write`; `admin` is
granted only to a superuser. Safe methods require `read`, mutating methods require
`write`, and a few routes (credential storage, PR merge) require `admin`.

### Streaming connections

Browser `EventSource` and `WebSocket` clients cannot send an `Authorization` header, so
streams authenticate with a **single-use ticket** instead — never with a JWT in the URL.
Call `POST /auth/stream-ticket` (write scope) to mint a ticket, then append it as
`?ticket=<value>` when opening the connection. A ticket is valid for 60 seconds and is
consumed on first use, so fetch a fresh one for every connection and every reconnect.

Tickets are accepted **only** on these routes:

| Route | Kind |
|---|---|
| `GET /api/v2/tasks/{task_id}/stream` | SSE |
| `GET /api/v2/tasks/{task_id}/output` | SSE |
| `GET /api/v2/prd/stress-test` | SSE |
| `WS /ws/sessions/{session_id}/chat` | WebSocket |
| `WS /ws/sessions/{session_id}/terminal` | WebSocket |

The two WebSocket routes do not appear in this schema — OpenAPI does not describe
WebSockets. `chat` streams agent output as `text_delta`, `tool_use_start`, `tool_result`,
`thinking`, `cost_update`, `done` and `error` messages; `terminal` forwards raw bytes to
and from a shell in the session workspace.

## Rate Limiting

The API rate-limits by client, with a lower limit on AI endpoints (agent start, LLM
calls) than on ordinary reads. Exceeding a limit returns `429` with a `Retry-After`
header (seconds) and an `X-RateLimit-Limit` header describing the limit that was hit.
Successful responses do not carry rate-limit headers.

## Error Responses

All errors follow a consistent format:
```json
{
    "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `400` - Bad Request (validation error)
- `401` - Unauthorized (authentication required)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found (resource doesn't exist)
- `409` - Conflict (duplicate resource or state conflict)
- `422` - Unprocessable Entity (Pydantic validation failure)
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error
"""


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="CodeFRAME API",
    description=OPENAPI_DESCRIPTION,
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "CodeFRAME Support",
        "url": "https://github.com/frankbria/codeframe",
    },
    license_info={
        "name": "AGPL-3.0-or-later",
        "identifier": "AGPL-3.0-or-later",
    },
)


# ============================================================================
# Rate Limiting Setup
# ============================================================================

# Add rate limiting exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


from fastapi.responses import JSONResponse  # noqa: E402

from codeframe.core.llm_resolution import UntrustedBaseURLError  # noqa: E402
from codeframe.ui.response_models import ErrorCodes, api_error  # noqa: E402


@app.exception_handler(UntrustedBaseURLError)
async def untrusted_base_url_handler(request, exc: UntrustedBaseURLError):
    """A repo-supplied ``llm.base_url`` was refused (#903).

    A deliberate refusal, so it answers 400 with the reason rather than a 500
    with a stack trace — the operator needs to see which endpoint was blocked
    and how to allow it.
    """
    return JSONResponse(
        status_code=400,
        content=api_error(
            "Untrusted LLM endpoint in workspace config",
            ErrorCodes.INVALID_REQUEST,
            str(exc),
        ),
    )

# Add rate limiting middleware if enabled
# Initialize limiter immediately so it's available before lifespan runs
rate_limit_config = get_rate_limit_config()
if rate_limit_config.enabled:
    limiter = get_rate_limiter()
    if limiter:
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)


# ============================================================================
# CORS Middleware
# ============================================================================

# CORS configuration from environment variables
# Get CORS_ALLOWED_ORIGINS from env (comma-separated list)
cors_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")

# Parse comma-separated origins
if cors_origins_env:
    allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
elif os.environ.get("CODEFRAME_DEPLOYMENT_MODE", "self_hosted").strip().lower() == "hosted":
    # Fail closed (#934). The localhost fallback below is paired with
    # allow_credentials=True, so on a multi-tenant deployment an unset
    # CORS_ALLOWED_ORIGINS would let a page served from any localhost origin —
    # including one an attacker persuades a logged-in operator to open — make
    # credentialed cross-origin calls. A hosted deploy that has not declared its
    # origins gets none, not convenient ones.
    allowed_origins = []
    logger.error(
        "CORS_ALLOWED_ORIGINS is unset in hosted mode — refusing all cross-origin "
        "requests. Set it to your public origin(s)."
    )
else:
    # Self-hosted/local default: the dev servers, on the same machine as the API.
    allowed_origins = [
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:3001",  # Next.js E2E test server
        "http://localhost:5173",  # Vite dev server
    ]

logger.info("CORS allowed origins: %s (from env: %r)", allowed_origins, cors_origins_env)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Check Endpoints
# ============================================================================


@app.get(
    "/",
    summary="Basic health check",
    description="Simple health check endpoint that returns online status. Use /health for detailed information.",
    tags=["health"],
)
async def root():
    """Health check endpoint."""
    return {"status": "online", "service": "CodeFRAME API"}


@app.get(
    "/health",
    summary="Detailed health check",
    description="Returns comprehensive health information including version, git commit, deployment time, "
                "and database connection status. Useful for monitoring and debugging.",
    tags=["health"],
)
async def health_check():
    """Detailed health check with deployment info.

    Returns:
        - status: Service health status
        - version: API version from FastAPI app
        - commit: Git commit hash (short)
        - deployed_at: Server startup timestamp
        - database: Database connection status
    """
    # Get git commit hash
    try:
        git_commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parent.parent.parent,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        git_commit = "unknown"

    return {
        "status": "healthy",
        "service": "CodeFRAME Status Server",
        "version": app.version,
        "commit": git_commit,
        "deployed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


# ============================================================================
# Test-Only Endpoints (for WebSocket integration tests)
# ============================================================================
#
# Gated behind CODEFRAME_ENABLE_TEST_ENDPOINTS (#753): /test/broadcast lets any
# *authenticated* principal push arbitrary JSON to every WebSocket subscriber,
# so it must never be reachable in production. Registered only when the flag is
# set; integration tests set it explicitly. The flag is read once at import
# time, so the route is genuinely absent (not in OpenAPI, 404 on request) when
# unset, rather than gated inside the handler.
if os.getenv("CODEFRAME_ENABLE_TEST_ENDPOINTS"):

    @app.post("/test/broadcast", dependencies=[Depends(require_auth)])
    async def test_broadcast(message: dict, project_id: int = None):
        """Trigger a WebSocket broadcast for testing purposes.

        This endpoint is only intended for use in integration tests to trigger
        broadcasts from the server subprocess. In production, broadcasts are
        triggered by actual server-side events.

        Args:
            message: The message dict to broadcast
            project_id: Optional project ID for filtered broadcasts

        Returns:
            Success confirmation
        """
        from codeframe.ui.shared import manager

        await manager.broadcast(message, project_id=project_id)
        return {"status": "broadcast_sent", "project_id": project_id}


# ============================================================================
# Router Mounting (v2 only)
# ============================================================================

# Authentication router
app.include_router(auth_router.router)

# v2 API routers - all delegate to codeframe.core modules
#
# Auth enforcement (issue #336): every v2 REST router is mounted with a
# blanket scope-aware auth dependency. ``require_method_scope`` first resolves
# ``require_auth`` (honoring CODEFRAME_AUTH_REQUIRED — disabled returns a
# synthetic all-scopes principal, so local/dev/tests are unchanged), then
# enforces scope by HTTP method (#717): safe methods need ``read``, mutating
# methods need ``write``. Admin-only routes (credential storage, PR merge) add
# their own ``Depends(require_scope("admin"))``. The two WebSocket routers
# (session_chat_ws, terminal_ws) are intentionally excluded — they perform
# their own single-use ?ticket= auth (#745). The auth_router stays public.
_AUTH = [Depends(require_method_scope)]
app.include_router(batches_v2.router, dependencies=_AUTH)       # /api/v2/batches
app.include_router(blockers_v2.router, dependencies=_AUTH)      # /api/v2/blockers
app.include_router(checkpoints_v2.router, dependencies=_AUTH)   # /api/v2/checkpoints
app.include_router(costs_v2.router, dependencies=_AUTH)         # /api/v2/costs
app.include_router(diagnose_v2.router, dependencies=_AUTH)      # /api/v2/tasks/{id}/diagnose
app.include_router(discovery_v2.router, dependencies=_AUTH)     # /api/v2/discovery
app.include_router(environment_v2.router, dependencies=_AUTH)   # /api/v2/env
app.include_router(events_v2.router, dependencies=_AUTH)        # /api/v2/events
app.include_router(gates_v2.router, dependencies=_AUTH)         # /api/v2/gates
app.include_router(git_v2.router, dependencies=_AUTH)           # /api/v2/git
app.include_router(github_integrations_v2.router, dependencies=_AUTH)  # /api/v2/integrations/github
app.include_router(interactive_sessions_v2.router, dependencies=_AUTH)  # /api/v2/sessions
app.include_router(session_chat_ws.router)          # /ws/sessions/{id}/chat (WS: own auth)
app.include_router(terminal_ws.router)              # /ws/sessions/{id}/terminal (WS: own auth)
app.include_router(pr_v2.router, dependencies=_AUTH)            # /api/v2/pr
app.include_router(prd_v2.router, dependencies=_AUTH)           # /api/v2/prd
app.include_router(proof_v2.router, dependencies=_AUTH)         # /api/v2/proof
app.include_router(review_v2.router, dependencies=_AUTH)        # /api/v2/review
app.include_router(schedule_v2.router, dependencies=_AUTH)      # /api/v2/schedule
app.include_router(settings_v2.router, dependencies=_AUTH)      # /api/v2/settings
app.include_router(streaming_v2.router, dependencies=_AUTH)     # /api/v2/tasks/{id}/stream (SSE)
app.include_router(tasks_v2.router, dependencies=_AUTH)         # /api/v2/tasks
app.include_router(templates_v2.router, dependencies=_AUTH)     # /api/v2/templates
app.include_router(workspace_v2.router, dependencies=_AUTH)     # /api/v2/workspaces


# ============================================================================
# Server Startup
# ============================================================================


def run_server(host: str = "127.0.0.1", port: int = 8080):
    """Run the Status Server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="CodeFRAME Status Server")
    parser.add_argument(
        "--host",
        type=str,
        # Loopback by default (#935): this process exposes SQLite state,
        # workspace file access and agent execution. Set HOST=0.0.0.0 to expose it.
        default=os.environ.get("HOST", "127.0.0.1"),
        help="Host to bind to (default: 0.0.0.0 or HOST env var)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8080"))),
        help="Port to bind to (default: 8080 or BACKEND_PORT/PORT env var)",
    )

    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
