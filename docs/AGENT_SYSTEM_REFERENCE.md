# Agent System Reference

Detailed reference for CodeFRAME's agent system. Loaded on-demand — not required for every task.

---

## Component Table

| Component | File | Purpose |
|-----------|------|---------|
| **ReactAgent** | `core/react_agent.py` | Default engine: observe-think-act loop with tool use |
| **Tools** | `core/tools.py` | 7 agent tools: read/edit/create file, run command/tests, search, list |
| **Editor** | `core/editor.py` | Search-replace editor with 4-level fuzzy matching |
| **Stall Detector** | `core/stall_detector.py` | Synchronous stall check + StallAction enum + StallDetectedError |
| **Stall Monitor** | `core/stall_monitor.py` | Thread-based watchdog with callback (integrated into ReactAgent) |
| LLM Adapter | `adapters/llm/base.py` | Protocol, ModelSelector, Purpose enum |
| Anthropic Provider | `adapters/llm/anthropic.py` | Claude integration with streaming |
| Mock Provider | `adapters/llm/mock.py` | Testing with call tracking |
| Context Loader | `core/context.py` | Codebase scanning, relevance scoring |
| Planner | `core/planner.py` | Task → ImplementationPlan via LLM (plan engine) |
| Executor | `core/executor.py` | File ops, shell commands, rollback (plan engine) |
| Agent (legacy) | `core/agent.py` | Plan-based orchestration (--engine plan) |
| Runtime | `core/runtime.py` | Run lifecycle, engine selection, agent invocation |
| Conductor | `core/conductor.py` | Batch orchestration, worker pool |
| Dependency Graph | `core/dependency_graph.py` | DAG operations, topological sort |
| Dependency Analyzer | `core/dependency_analyzer.py` | LLM-based dependency inference |
| Environment Validator | `core/environment.py` | Tool detection and validation |
| Installer | `core/installer.py` | Cross-platform tool installation |
| Diagnostics | `core/diagnostics.py` | Failed task analysis |
| Diagnostic Agent | `core/diagnostic_agent.py` | AI-powered task diagnosis |
| Credentials | `core/credentials.py` | API key and credential management |
| Event Publisher | `core/streaming.py` | Real-time SSE event distribution |
| API Key Service | `auth/api_key_service.py` | API key CRUD and validation |
| Rate Limiter | `lib/rate_limiter.py` | Per-endpoint rate limiting |

---

## Model Selection Strategy

Task-based heuristic via `Purpose` enum (`adapters/llm/base.py`, each overridable
with `CODEFRAME_<PURPOSE>_MODEL`):
- **PLANNING / EXECUTION / CORRECTION / SUPERVISION** → `claude-sonnet-4-5`
- **GENERATION** → `claude-haiku-4-5` (fast/cheap)

**Request shape follows the model (#1267).** Opus 4.7+, Opus 5/5.5, Sonnet 5/5.5
and Fable reject `temperature` and a fixed `thinking.budget_tokens` with a 400, so
the Anthropic adapter sends them only to an allowlist of families that take them
(Claude 3, Claude 4 up to 4.6) and asks everything else for adaptive thinking. On
OpenAI itself the adapter sends `max_completion_tokens`, and drops `temperature`
for reasoning models (o-series, gpt-5); ollama/vllm/compatible keep `max_tokens`.
Wire tests: `tests/adapters/test_request_shape_1267.py`.

### Plan: moving the defaults off Sonnet 4.5

`claude-sonnet-4-5` reaches end-of-life on **2026-11-30** (listed in
`anthropic` 1.11's `DEPRECATED_MODELS`); Haiku 4.5 has no announced date yet.
The request-shape fix above is the prerequisite — it lets any current model run.

1. **Ship the request-shape fix** (#1267) in a release, so a user who overrides
   `CODEFRAME_*_MODEL` to a current model already works.
2. **By 2026-10-31, move the Sonnet-tier defaults** (planning, execution,
   correction, supervision) to `claude-sonnet-5-5` in one PR: update
   `base.py` and `tests/adapters/test_model_defaults_guard_1112.py`.
   Before merging, run `scripts/lifecycle --mode cli` against the new default
   and compare cost and gate pass rate with Sonnet 4.5 — it runs adaptive
   thinking by default, so spend per task can move in either direction. Sonnet
   5.5 is cheaper per token ($2/$10 vs $3/$15).
3. **Cut a release** carrying the new defaults at least two weeks before
   2026-11-30, then run the cold-start check (`scripts/quickstart-cleanroom`)
   against the published package — #1112 shipped retired IDs exactly this way.
4. **Haiku 4.5** stays the generation default until a retirement date is
   announced; the Unlocked Resolution workflow surfaces the SDK's deprecation
   notice when it appears (#1340).

Future: `cf tasks set provider <id> <provider>` for per-task override.

---

## Engine Execution Flows

See `docs/REACT_AGENT_ARCHITECTURE.md` for the deep-dive. Summary:

**ReAct (default):** `runtime.start_task_run()` → `ReactAgent.run()` → tool-use loop (stall check → LLM tool call → observe → record → verify) → final verification with self-correction (up to 5 retries) → status update (DONE/BLOCKED/FAILED).

**Plan (legacy, `--engine plan`):** `runtime.start_task_run()` → `agent.run()` → LLM creates plan → execute steps → incremental ruff → final verification with self-correction (up to 3 retries) → status update.

---

## Self-Correction System

### Components
- **Fix Attempt Tracker** (`core/fix_tracker.py`) — prevents repeating failed fixes; normalizes errors, tracks (error_signature, fix_description) pairs, detects escalation patterns
- **Pattern-Based Quick Fixes** (`core/quick_fixes.py`) — fixes common errors without LLM:
  - `ModuleNotFoundError` → auto-install package
  - `ImportError` → add missing import
  - `NameError` → add common imports (Optional, dataclass, Path, etc.)
  - `SyntaxError` → fix missing colons, f-string prefixes
  - `IndentationError` → normalize mixed tabs/spaces
- **Escalation to Blocker** — triggered after 3 same-error failures, 3 same-file failures, or 5 total failures

### Flow
```
Error occurs
    │
    ├── Try ruff --fix (auto-lint)
    ├── Try pattern-based quick fix (no LLM) → record outcome
    ├── Check escalation threshold → create blocker if exceeded
    └── Use LLM to generate fix plan (with already-tried fixes excluded)
        └── Execute + re-verify
```

### Key Methods (in `core/agent.py` / `core/react_agent.py`)
- `_run_final_verification()` — while loop re-running gates after self-correction
- `_attempt_verification_fix()` — orchestrates quick fixes, escalation check, LLM fixes
- `_create_escalation_blocker()` — creates detailed blocker with context
- `_verbose_print()` — conditional stdout for observability

---

## Stall Detection

- `StallMonitor` (`core/stall_monitor.py`) — thread-based watchdog, polls every 5s
- `StallDetector` (`core/stall_detector.py`) — synchronous time-tracking primitive
- `StallAction` enum — RETRY, BLOCKER, FAIL
- `StallDetectedError` — exception for RETRY path

Recovery:
- **BLOCKER** (default): creates informative blocker, task → BLOCKED
- **RETRY**: raises `StallDetectedError`, runtime retries once with fresh agent
- **FAIL**: task transitions directly to FAILED

Config: `agent_budget.stall_timeout_s` in `.codeframe/config.yaml` (0 = disabled)

---

## Server Architecture (Phase 2)

Pattern: Thin adapter over core — server routes delegate to `core.*` modules.

```
CLI (typer) ─┬── core.* ─── adapters.*
             │
Server (fastapi) ─┘
```

The 21 v2 REST router modules are: `batches_v2`, `blockers_v2`, `checkpoints_v2`, `costs_v2`, `diagnose_v2`, `discovery_v2`, `environment_v2`, `events_v2`, `gates_v2`, `git_v2`, `github_integrations_v2`, `interactive_sessions_v2`, `pr_v2`, `prd_v2`, `proof_v2`, `review_v2`, `schedule_v2`, `settings_v2`, `tasks_v2`, `templates_v2`, `workspace_v2` — plus the two WebSocket routers `session_chat_ws` and `terminal_ws`. (The API-key routes live in `codeframe/auth/api_key_router.py`, not under `routers/`.)

See `docs/PHASE_2_DEVELOPER_GUIDE.md` for full router details.
