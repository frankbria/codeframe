# Testing CodeFRAME

> This file used to be a ~400-line Sprint-1 manual checklist that imported modules
> which no longer exist (`codeframe.agents.providers.anthropic_provider`,
> `codeframe.providers.base`) and told you to start the server with a command that
> was renamed several releases ago. It has been replaced with what the suite
> actually is today (#950). Sprint history lives in [`legacydocs/SPRINTS.md`](legacydocs/SPRINTS.md).

## The one command

```bash
uv run pytest && uv run ruff check . && uv run mypy codeframe/
cd web-ui && npm test && npm run build
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
| `tests/ui/` | FastAPI router tests, via `TestClient` over a fresh app |
| `tests/cli/` | Typer commands, via `CliRunner` — in-process, no server |
| `tests/adapters/` | LLM providers and the E2B sandbox |
| `tests/unit/` | Narrow units that fit none of the above (e.g. the GitHub client) |
| `tests/integration/` | Cross-module flows |
| `tests/agents/` | Dependency resolution |
| `tests/e2e/` | CLI end-to-end (`tests/e2e/cli`) and Playwright browser (`tests/e2e/*.spec.ts`) |
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

`--mode api` and `--mode web` **exit 3**: they are not implemented (#1068). They used
to collect only skipped stubs and exit 0, which read as a pass.

## Browser E2E

[`tests/e2e/playwright.config.ts`](tests/e2e/playwright.config.ts) starts both servers itself (`uv uvicorn` for the
backend, `next build && next start` for the frontend) and `global-setup.ts` seeds a
workspace and a login user. You do not start anything by hand.

```bash
cd tests/e2e && npx playwright test
```

## Web UI

```bash
cd web-ui
npm test              # Jest
npm run lint          # eslint --max-warnings 0
npm run build         # must succeed; the frontend-tests CI job enforces it
```

## Writing tests

- **No mocking at integration boundaries.** Use a real SQLite workspace, a real git
  repository, the real core modules. Substitute only what would spend money, spawn an
  agent, or reach the network — and say so in a comment.
- **Assert outcomes, not status codes.** A `201` from the commit endpoint means little;
  reading the commit back out of `git log` means something.
- **Give a destructive path a negative case too.** "Returns 400" and "did not corrupt
  anything" are different claims.
- **A new `/api/v2` router is protected by how it is mounted**, and by nothing else.
  [`tests/ui/test_v2_auth_enforcement.py`](tests/ui/test_v2_auth_enforcement.py) asserts
  the 401 responses, and a companion suite enumerates `app.routes` so a router mounted
  without the auth dependency fails rather than shipping.
- Tests run with `CODEFRAME_AUTH_REQUIRED=false` (set in [`tests/conftest.py`](tests/conftest.py)); opt back
  in explicitly when auth is what you are testing.

## Demoing against a sample project

When verifying agent behaviour end to end against something like `cf-test/`, you are
**observing the agent's work, not doing it**. Do not fix its errors or write code on its
behalf — that is the data. Report what worked, what failed, and the final state against
the acceptance criteria.
