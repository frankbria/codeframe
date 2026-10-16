# Modules

*Last Updated: 2026-10-11*

## `codeframe/core/` by concern

| Concern | Modules |
|---------|---------|
| Workspace & state | `workspace.py` (`.codeframe/state.db`, schema), `atomic_io.py`, `path_safety.py`, `config.py` (`.codeframe/config.yaml` → `EnvironmentConfig`), `config_watcher.py` |
| THINK | `prd.py`, `prd_discovery.py` (Socratic discovery + stop rules), `prd_stress_test.py`, `planner.py`, `tasks.py`, `task_tree.py`, `dependency_graph.py`, `dependency_analyzer.py`, `tech_stack.py`, `templates.py` |
| BUILD engines | `runtime.py` (run lifecycle, `TaskStatus`), `engine_registry.py`, `react_agent.py` + `tools.py` + `editor.py` (default ReAct engine), `agent.py` + `executor.py` (legacy plan engine), `adapters/*` (external agents), `agent_env.py` (sandboxed env/HOME), `context.py`, `context_packager.py` |
| Orchestration | `conductor.py` (batches), `run_control.py`, `schedule.py`, `stall_detector.py`, `stall_monitor.py`, `reconciliation.py`, `replay.py`, `worktrees.py`, `sandbox/` |
| Verification | `gates.py`, `fix_tracker.py`, `quick_fixes.py`, `review.py`, `diagnostics.py`, `diagnostic_agent.py`, `proof/` (PROOF9) |
| Blockers & events | `blockers.py`, `blocker_detection.py`, `events.py`, `streaming.py`, `progress.py`, `state_machine.py`, `checkpoints.py`, `artifacts.py` |
| LLM & cost | `llm_resolution.py`, `llm_json.py`, `usage_recording.py`, `cost_tracker.py`, `spend_limit.py`, `models.py` (incl. `CallType`: add every new `call_type` here) |
| GitHub | `git.py`, `github_connect_service.py`, `github_issues_service.py`, `github_integration_config.py` |
| Security & trust | `credentials.py` (keyring + encrypted file store), `hook_trust.py`, `hooks.py`, `dangerous_commands.py`, `claude_code_guard.py`, `env_provenance.py` |
| Environment | `environment.py`, `installer.py`, `agents_config.py` |
| Telemetry | `telemetry.py`, `engine_stats.py`, `notifications_config.py` |

## Outside core

| Package | Purpose |
|---------|---------|
| `adapters/llm/` | `LLMProvider` base + Anthropic / OpenAI-compatible / Mock providers |
| `platform_store/` | `repositories/token_repository.py` — per-workspace `TokenRepository` |
| `planning/` | `prd_templates.py` (PRD templates), `task_templates.py`, `task_scheduler.py` |
| `notifications/webhook.py` | Outbound webhook with DNS-pinned SSRF guard |
| `lib/` | `metrics_tracker.py` |
| `tui/` | Textual dashboard (`cf dashboard`) |
