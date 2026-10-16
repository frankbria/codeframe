# Patterns

*Last Updated: 2026-10-11*

## Recurring design patterns

- **Core function + thin wrappers.** Core exposes plain functions or session classes; the CLI
  command (and the TUI) call it (e.g. `core/prd_discovery.py:process_discovery_answer`).
- **Engine registry.** `core/engine_registry.py` maps `--engine` names to the ReAct engine or
  external adapters (`core/adapters/*`); `resolve_engine` refuses gated engines (e2b).
- **Fail closed.** Security and merge gates default to blocking on any error (PROOF9 merge gate,
  hook trust, webhook SSRF guard). Watch out: a bare `except Exception` downstream
  will also swallow a test's in-band assertion.
- **Persist-first, re-check after LLM calls.** Long LLM calls can race a reset; writes after them
  use `require_active=True` (`prd_discovery._save_session`).

## Error handling

- Core raises typed exceptions (e.g. `DiscoveryError`, `NoApiKeyError`, `IncompleteSessionError`);
  the CLI maps them to messages and exit codes.
- CLI prints errors through `codeframe.cli.helpers.print_error` (Rich-escaped). Never interpolate
  user text into Rich markup unescaped (`tests/cli/test_rich_hostile_data_1054.py` enforces this).

## Configuration & secrets

- Precedence for LLM: CLI flag > env > `.codeframe/config.yaml` > default (anthropic). Resolve only via
  `core/llm_resolution.py`.
- `.codeframe/config.yaml` is untrusted (a cloned repo can commit it): unknown keys are dropped with a
  warning (`core/config.py:_build_config`), and repo-supplied `llm.base_url` and hooks need opt-in.
- Secrets: `core/credentials.py` (OS keyring, time-boxed; encrypted file fallback keyed by
  `CODEFRAME_CREDENTIAL_SECRET`). Env vars are documented in `CLAUDE.md` → Environment Variables.

## Testing

- `tests/<area>/`; new v2 tests carry `pytestmark = pytest.mark.v2`. Markers are strict (`pytest.ini`);
  real-LLM markers (`lifecycle`, `e2e_llm`) are deselected by default.
- Fakes over live services: provider fakes route on prompt text (see
  `tests/core/test_prd_discovery_bounded_1443.py`), `CODEFRAME_LLM_PROVIDER=mock` for agent runs.
- Guard tests pin invariants: SDK kwargs (`tests/adapters/test_sdk_kwargs_guard_614.py`), workflow
  and docs guards (`tests/ci/`), `CallType` coverage, Rich escaping.
- CLI end-to-end in `tests/e2e/cli/`.
