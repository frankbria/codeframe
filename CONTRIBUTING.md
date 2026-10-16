# Contributing to CodeFRAME

Thank you for your interest in contributing to CodeFRAME!

## Beta expectations

CodeFRAME is in **public beta**. The product vision — Think → Build → Prove →
Ship — is stable, but the surface area is still moving. Knowing what's settled
and what isn't will save you time before you open a PR.

**Stable enough to build on:**

- The **Golden Path CLI** (`cf init/prd/tasks/work/proof/pr`) and its core
  modules in `codeframe/core/`.
- The PROOF9 quality system and the agent/LLM adapter interfaces.

**Still in flux (expect change):**

- The **proof9 Claude Code plugin** (`proof9/`), the new front door to the
  proof ledger.
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

Add documentation when introducing a cross-cutting pattern or a data-model change.

## Credentials & Security

There is no server and no account system: CodeFRAME is a local CLI. Provider keys and
the GitHub token are stored by `cf auth setup` in the OS keyring, or in an encrypted file
fallback (`codeframe/core/credentials.py`); `cf auth list|validate|rotate|remove` manage
them. Never print a stored credential, and never write one into `.codeframe/` — that
directory lives inside a repository a user may commit or share.

Treat everything inside a workspace as untrusted input: a cloned repo can commit
`.codeframe/config.yaml`, which is why hooks need `cf hooks trust` and a non-loopback
`llm.base_url` needs `CODEFRAME_ALLOW_CONFIG_BASE_URL`. The "Environment Variables"
section of [`CLAUDE.md`](CLAUDE.md) documents each switch.

## Testing

- Write tests for new behaviour, before the code where you can
- Coverage is gated in CI at the floor in `.coveragerc` (currently 80%)
- Run the full check before submitting a PR:

  ```bash
  uv run pytest && uv run ruff check . && uv run mypy codeframe/
  ```

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
