# Testing CodeFRAME

> This file used to be a ~400-line Sprint-1 manual checklist that imported modules
> which no longer exist (`codeframe.agents.providers.anthropic_provider`,
> `codeframe.providers.base`) and told you to start the server with a command that
> was renamed several releases ago. It has been replaced with what the suite
> actually is today (#950). Sprint history is in git history.

## The one command

```bash
uv run pytest && uv run ruff check . && uv run mypy codeframe/
```

That is the same gate [CI](.github/workflows/test.yml) runs. If it passes locally it should pass on a PR.

## What a bare `uv run pytest` runs

Everything under `tests/` **except** the two markers that cost real money:

```ini
# pytest.ini
addopts = ... -m "not e2e_llm and not lifecycle"
```

A `-m` on the command line **replaces** that one rather than combining with it — so
`uv run pytest -m integration` also re-enables the paid tests. Add
`and not e2e_llm and not lifecycle` when you narrow by marker.

## Layout

| Directory | What lives there |
|---|---|
| `tests/core/` | Headless domain + orchestration (`tasks`, `conductor`, `prd`, `proof`, `git`, …) |
| `tests/cli/` | Typer commands, via `CliRunner` — in-process |
| `tests/adapters/` | LLM providers and the E2B sandbox |
| `tests/integration/` | Cross-module flows |
| `tests/agents/` | Dependency resolution |
| `tests/e2e/` | CLI end-to-end (`tests/e2e/cli`) |
| `tests/lifecycle/` | Full Think → Build → Prove loop against a real LLM |

## Markers

Registered in `pytest.ini`. The ones that change what runs:

| Marker | Effect |
|---|---|
| `e2e_llm` | **Deselected by default.** Real Anthropic calls, and the fixtures `rmtree` `.codeframe/` inside an external project. Opt in with `-m e2e_llm`. |
| `lifecycle` | **Deselected by default.** Real Anthropic calls, 10–30 minutes. Run via `scripts/lifecycle`, never directly. |
| `slow`, `integration`, `edge_case` | Selection conveniences; all run by default. |
| `v2` | Registered for back-compat and ad-hoc selection. **Not** a CI gate — anything non-e2e and non-lifecycle runs by default (#669). |

## Coverage

Gated, not decorative. [`.coveragerc`](.coveragerc) sets `fail_under = 80`, which `pytest --cov`
enforces on the CI gate and which the README badge mirrors.

```bash
uv run pytest --cov=codeframe --cov-report=term
```

Note that `fail_under` applies to **any** run that asks for coverage, so measuring a
subset (`pytest tests/core --cov=codeframe`) exits 1 on the threshold. That is stock
`pytest-cov` behaviour, not a misconfiguration.

## Real-LLM lifecycle tests

These cost money and are not part of any automated gate. Run the CLI mode locally
before opening a PR that touches the execution path:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
scripts/lifecycle --mode cli            # ~$0.50–1.00 with the default haiku model
scripts/lifecycle --mode cli --dry-run  # show what would run, spend nothing
```

## Writing tests

- **No mocking at integration boundaries.** Use a real SQLite workspace, a real git
  repository, the real core modules. Substitute only what would spend money, spawn an
  agent, or reach the network — and say so in a comment.
- **Assert outcomes, not exit codes.** A `0` from `cf commit create` means little;
  reading the commit back out of `git log` means something.
- **Give a destructive path a negative case too.** "Exits 1" and "did not corrupt
  anything" are different claims.

## Demoing against a sample project

When verifying agent behaviour end to end against something like `cf-test/`, you are
**observing the agent's work, not doing it**. Do not fix its errors or write code on its
behalf — that is the data. Report what worked, what failed, and the final state against
the acceptance criteria.
