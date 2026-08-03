# Contributing to CodeFRAME

Thank you for your interest in contributing to CodeFRAME!

## Beta expectations

CodeFRAME is in **public beta**. The product vision — Think → Build → Prove →
Ship — is stable, but the surface area is still moving. Knowing what's settled
and what isn't will save you time before you open a PR.

**Stable enough to build on:**

- The **Golden Path CLI** (`cf init/prd/tasks/work/proof/pr`) and its core
  modules in `codeframe/core/`.
- The **v2 REST API** and its authentication model.
- The PROOF9 quality system and the agent/LLM adapter interfaces.

**Still in flux (expect change):**

- **Web UI** surfaces and components — pages are actively being added and
  reworked; coordinate before large UI changes.
- Anything behind a phase that is "in progress" in
  [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md).
- Database schemas and on-disk `.codeframe/` formats may change between betas.

**How to propose a change:** open a thread in
[**Discussions → Ideas**](https://github.com/frankbria/codeframe/discussions/categories/ideas)
*before* writing code for anything non-trivial. During the beta, feature
requests are routed to Discussions (not the issue tracker) so we can shape them
together; the issue tracker is reserved for confirmed bugs and accepted work.
Bug reports go through the [bug report
template](https://github.com/frankbria/codeframe/issues/new/choose). Security
issues follow [SECURITY.md](SECURITY.md) — never a public issue or PR.

Every change must support the Think → Build → Prove → Ship pipeline. If it
doesn't, it likely won't be merged regardless of quality — see
[`CLAUDE.md`](CLAUDE.md) and [`docs/VISION.md`](docs/VISION.md).

## Development Setup

```bash
# Clone repository
git clone https://github.com/frankbria/codeframe.git
cd codeframe

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install development dependencies
uv sync

# Set up environment variables
export ANTHROPIC_API_KEY="your-api-key-here"

# Set up frontend (if working on UI)
cd web-ui
npm install
cd ..

# Run tests
uv run pytest

# Format code
uv run ruff format codeframe tests
uv run ruff check codeframe tests
```

## Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for public APIs
- Maximum line length: 100 characters

## Architecture Documentation

Before contributing, read the documents that actually govern the codebase:

- [`CLAUDE.md`](CLAUDE.md) — the non-negotiable architecture rules (core is headless, the
  CLI never requires a server, agent state transitions flow through the runtime)
- [`docs/GOLDEN_PATH.md`](docs/GOLDEN_PATH.md) — the CLI-first workflow contract
- [`docs/CLI_WIREFRAME.md`](docs/CLI_WIREFRAME.md) — command → module mapping
- [`docs/AGENT_SYSTEM_REFERENCE.md`](docs/AGENT_SYSTEM_REFERENCE.md) — components and execution flows
- [`docs/PHASE_2_DEVELOPER_GUIDE.md`](docs/PHASE_2_DEVELOPER_GUIDE.md) — the server layer and v2 router patterns
- [`docs/PHASE_3_UI_ARCHITECTURE.md`](docs/PHASE_3_UI_ARCHITECTURE.md) — the Next.js web UI

Add documentation when introducing a cross-cutting pattern or a data-model change.

## Authentication & Security

Auth is enforced centrally, not per handler. `codeframe/ui/server.py` mounts every v2
router with a router-level dependency:

```python
_AUTH = [Depends(require_method_scope)]
app.include_router(tasks_v2.router, dependencies=_AUTH)   # /api/v2/tasks
```

So **a new router is protected by mounting it that way, and by nothing else.** A router
added without `dependencies=_AUTH` is publicly reachable.
A companion suite enumerates `app.routes` and fails when any `/api/v2` route is missing
the dependency, so that mistake cannot reach `main`.

### What a caller must present

`require_auth` accepts either a JWT `Authorization: Bearer <token>` or an `X-API-Key`
header, and resolves both to a principal dict. Enforcement is gated by
`CODEFRAME_AUTH_REQUIRED`, read **at request time**, default **on**; set it to `false`
for local development. With auth disabled the dependency yields a synthetic principal
carrying every scope — the single-operator local opt-out.

Streams never carry a JWT in the URL. `POST /auth/stream-ticket` mints a 60-second
single-use ticket, redeemed as `?ticket=` on the two SSE routes and the two WebSocket
routes only.

### Scopes

A JWT principal's scopes come from its user row: `read` and `write` always, plus `admin`
only when `is_superuser`. Use `require_scope(SCOPE_ADMIN)` for anything that stores a
credential or merges a PR:

```python
@router.post("/{pr_number}/merge")
async def merge_pull_request(
    request: Request,
    pr_number: int,
    workspace: Workspace = Depends(get_v2_workspace),
    auth: dict = Depends(require_auth),
    _: None = Depends(require_scope(SCOPE_ADMIN)),
) -> MergeResponse:
    ...
```

### Tenancy

Handlers do not hand-roll ownership checks. `get_v2_workspace` resolves the caller's
workspace and enforces the `WORKSPACE_ROOT` allowlist, returning 403 for a path outside
it; in hosted mode each user is further confined to `<root>/<user_id>`. Take the
workspace from that dependency rather than from a client-supplied path.

### Writing tests for a protected endpoint

`tests/conftest.py` sets `CODEFRAME_AUTH_REQUIRED=false` for the suite, so most tests
need nothing. Tests that exercise auth opt back in explicitly — see
`tests/ui/test_v2_auth_enforcement.py` for the app fixture, and its companion for a real
register → login → authorized-request round-trip.

**See also**: the "Environment Variables" section of [`CLAUDE.md`](CLAUDE.md) documents
every auth-related switch (`CODEFRAME_AUTH_REQUIRED`, `AUTH_SECRET`,
`CODEFRAME_BOOTSTRAP_TOKEN`, `WORKSPACE_ROOT`, `JWT_LIFETIME_SECONDS`) and what happens
when each is unset.

## Testing

- Write tests for new behaviour, before the code where you can
- Coverage is gated in CI at the floor in `.coveragerc` (currently 80%)
- Run the full check before submitting a PR:

  ```bash
  uv run pytest && uv run ruff check . && uv run mypy codeframe/
  cd web-ui && npm test && npm run build
  ```

- Include an auth test for a protected endpoint
- Real-LLM lifecycle tests are opt-in and cost money: `scripts/lifecycle --mode cli`

See [`TESTING.md`](TESTING.md) for how the suites are laid out and which markers exist.

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear commit messages
3. Add tests for new functionality
4. Update documentation if needed
5. Run tests and linting
6. Submit PR with description of changes

## Adding an LLM Provider

Implement [`codeframe/adapters/llm/base.py`](codeframe/adapters/llm/base.py)'s
`LLMProvider`, alongside the existing `anthropic.py`, `openai.py` and `mock.py`, then
register it in the resolution chain (`codeframe/core/llm_resolution.py`). Any
OpenAI-compatible endpoint already works without new code — use
`--llm-provider openai --llm-model <name>` with `OPENAI_BASE_URL`.

## Adding a Coding-Agent Adapter

Implement [`codeframe/core/adapters/agent_adapter.py`](codeframe/core/adapters/agent_adapter.py)'s
interface, alongside `claude_code.py`, `codex.py`, `opencode.py` and `kilocode.py`. Declare
the credentials your CLI needs (`credential_env_vars`) and its login directory
(`home_passthrough`): delegated agents run with a sandboxed `$HOME` by default, so a CLI
that keeps state elsewhere will not find it.

## Questions?

Ask in [Discussions → Q&A](https://github.com/frankbria/codeframe/discussions/categories/q-a).
For licensing or commercial questions, see [LICENSING.md](LICENSING.md).
