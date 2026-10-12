# Architecture

*Last Updated: 2026-10-11*

## Layers

```
 cf / codeframe CLI (codeframe/cli/)         web-ui (Next.js, web-ui/src/)
        │  direct calls, no server                 │ REST + SSE + WebSocket
        ▼                                          ▼
 ┌──────────────────────────────┐   ┌──────────────────────────────────────┐
 │ codeframe/core/  (HEADLESS)  │◄──│ codeframe/ui/  FastAPI (thin adapter) │
 │ domain + orchestration       │   │ server.py + routers/*_v2.py           │
 └──────────────┬───────────────┘   └───────────────┬──────────────────────┘
                │                                   │ auth: codeframe/auth/
                ▼                                   ▼
 adapters: codeframe/adapters/llm (anthropic, openai, mock), core/adapters
 (claude_code, codex, opencode, kilocode, builtin), adapters/e2b (gated)
                │
                ▼
 .codeframe/state.db (per workspace)   platform.db (control plane: codeframe/platform_store/)
```

Non-negotiable rules (from `CLAUDE.md`):
1. `codeframe/core/**` imports no FastAPI, HTTP or UI modules.
2. Golden Path CLI commands work with **no server running**; the server wraps core.
3. `agent.py` manages `AgentState`; `runtime.py` owns every `TaskStatus` transition.
4. Every commit stays runnable (`codeframe --help` works).

## Key flows

| Flow | Path |
|------|------|
| **THINK: PRD discovery** | `cf prd generate` (`cli/app.py:prd_generate`) or `POST /api/v2/discovery/*` (`ui/routers/discovery_v2.py`) → `core/prd_discovery.py:PrdDiscoverySession` (LLM Q&A with stop rules: cap, plateau, duplicate guard) → `core/prd.py` stores the PRD |
| **THINK: stress test** | `cf prd stress-test` / SSE `GET /api/v2/prd/stress-test` → `core/prd_stress_test.py` |
| **THINK: tasks** | `cf tasks generate` → `core/planner.py` + `core/tasks.py`; dependencies in `core/dependency_graph.py` |
| **BUILD: single task** | `cf work start <id> --execute` → `core/runtime.py` (run lifecycle, engine selection via `core/engine_registry.py`) → `core/react_agent.py` (default) or an external adapter in `core/adapters/` → `core/gates.py` verification + self-correction (`core/fix_tracker.py`, `core/quick_fixes.py`) |
| **BUILD: batch** | `cf work batch run` → `core/conductor.py` worker pool, serial/parallel/auto |
| **PROVE** | `cf proof run` / `ui/routers/proof_v2.py` → `core/proof/runner.py` over `ledger.py` requirements, `scope.py` intersection, `evidence.py` |
| **SHIP** | `cf pr create/merge` (`cli/pr_commands.py`) / `ui/routers/pr_v2.py` → GitHub via `git/github_integration.py`; merge blocked by PROOF9 gate (`core/proof/ledger.py:list_blocking_requirements`) |
| **GitHub issues import** | `ui/routers/github_integrations_v2.py` → `core/github_connect_service.py`, `core/github_issues_service.py`, `core/github_integration_config.py` |

## Cross-cutting

- **LLM access**: always `core/llm_resolution.py` (`resolve_llm_settings`, `create_provider`,
  `resolve_api_key`); usage is recorded by `core/usage_recording.py` into `token_usage`.
- **Events**: append-only event log in `core/events.py` (`emit_for_workspace`); streamed by
  `core/streaming.py` and `ui/routers/events_v2.py`.
- **Auth**: `codeframe/auth/` (JWT + API keys, scopes, single-use stream tickets); every v2 router
  is mounted with `require_auth` in `ui/server.py`.
- **Isolation**: git worktrees (`core/worktrees.py`, `core/sandbox/worktree.py`); delegated agents
  get a sandboxed env/HOME (`core/agent_env.py`).
- **Spend limits**: `core/spend_limit.py`, `core/cost_tracker.py`.
