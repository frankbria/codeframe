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

Task-based heuristic via `Purpose` enum:
- **PLANNING** → claude-sonnet-4-20250514 (complex reasoning)
- **EXECUTION** → claude-sonnet-4-20250514 (balanced)
- **GENERATION** → claude-haiku-4-20250514 (fast/cheap)

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

16 v2 router modules: `blockers_v2`, `prd_v2`, `tasks_v2`, `workspace_v2`, `batches_v2`, `streaming_v2`, `api_key_v2`, `discovery_v2`, `checkpoints_v2`, `schedule_v2`, `templates_v2`, `git_v2`, `review_v2`, `pr_v2`, `environment_v2`, `proof_v2`.

See `docs/PHASE_2_DEVELOPER_GUIDE.md` for full router details.
