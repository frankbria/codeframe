# CodeFRAME Product Roadmap

**Updated**: 2026-10-16
**Vision**: *CodeFRAME is the project delivery system that turns ideas into verified, deployed code — AI agents write the code, CodeFRAME owns everything before and after.*

This is the **single source of truth** for CodeFRAME's product roadmap. All prior planning documents (V2_STRATEGIC_ROADMAP, FEATURE_ROADMAP, IMPLEMENTATION_ROADMAP, etc.) were retired and remain in git history.

The product is the **`cf` CLI** (Think → Build → Prove → Ship), the **`cf dashboard`** TUI, and the **proof9 Claude Code plugin** (`proof9/`), which is the front door to the proof ledger from inside a coding session. The web UI, the FastAPI server, the auth layer and the deploy stack were **removed in #1477**; the phases below that were web-only are kept for the record and marked as removed.

### Completed foundation (prior phases)
- **Phases 1–2.5**: CLI foundation, ReAct agent — complete. (The FastAPI server layer from Phase 2 was removed in #1477.)
- **Phase 3**: Web UI core screens — shipped, then removed in #1477.
- **Phase 4.A–4.D** (the earlier agent-adapter milestones — not the 4A/4B rows in the Summary table below): Agent adapter protocol (ClaudeCode/Codex/OpenCode/Kilocode), execution environment (worktree isolation), multi-provider LLM (OpenAI-compatible adapter) — all complete. E2B cloud execution is **not** complete: it is EXPERIMENTAL and gated behind `CODEFRAME_ENABLE_CLOUD_ENGINE` (#966)

---

## Current State

Per-phase status lives in the **Summary** table at the end of this document — the one place that says what shipped. Section headers carry no status markers, so they cannot drift from it.

The golden path works end-to-end from the CLI for a single developer on a single project, with no server. The proof ledger is reachable from Claude Code through the proof9 plugin (`/proof <what went wrong>`, `/proof ratchet`), which drives `cf proof … --json`.

---

## Phase 3.5 — Close the Interaction Gap

Milestones A (bidirectional agent chat, #500–509), B (run gates from the web UI, #566, #567, #574, #575) and C (glitch capture UI, #568, #569) were web UI features and were removed with it in #1477. What they exercised remains in core and the CLI: `cf proof run` records every run in the `proof_runs` ledger table with per-gate evidence (`cf proof show`), and `cf proof capture` (or `/proof` in the plugin) turns a glitch into a requirement.

---

## Phase 4 — Complete the SHIP Phase

### Milestone A: PROOF9 merge gate (#583, #731, #1247, #1254)

**Current state**: Shipped. `cf pr merge` refuses while open (non-waived) requirements exist unless `--override --reason "..."` is supplied, which is persisted to the `pr_merge_overrides` ledger table. The gate is scoped to the PR's changed files, including pre-rename paths, so a rename cannot escape its requirement (#1254); any failure to fetch the file list falls back to the workspace-global gate. `ProofRun.vacuous_pass` distinguishes "all gates passed" from "passed having executed nothing". It is computed as *passed with an empty tally* rather than by reading the config, so it also catches an `enabled_gates` list that excludes every obligation and a run whose gates were all UNVERIFIABLE; a warn-mode run that masked a real failure is deliberately not vacuous, since its gates ran.

The merge gate was **not** coupled to `vacuous_pass`. A vacuous run leaves its requirements OPEN — `mark_satisfied` never fires on an empty result — so the gate already blocks such a workspace via requirement status.

The web PR status panel (#583) and the server-side merge endpoint (#731) were removed in #1477; the gate itself lives in core and `cf pr merge`.

**Why it matters for the vision**: "Merge is gated on PROOF9 pass." That sentence is in the vision doc.

---

### Milestone B: Post-Merge Glitch Capture Loop

When a merged PR leads to a production glitch, the system should make it easy to feed that back into PROOF9 as a permanent requirement: a capture that starts from a merged PR carries that PR's scope (files changed), and the resulting requirement links back to the PR that produced the code it is guarding.

The original spec placed this on the web Review page; with the web UI removed (#1477) the surface is the CLI and the proof9 plugin.

**Why it matters for the vision**: "Quality compounding interest. Over time, the system becomes harder to break in the ways you have already been burned." Without connecting post-merge glitches back to the PROVE layer, each deployment is a one-shot with no learning.

---

## Phase 5 — Platform Completeness

Issues #554–#565 (2026-04-06) built these as web features; the web surfaces were removed in #1477. What remains is listed per item.

1. **Settings page** (#554–556) — removed. Credentials are managed with `cf auth setup|list|validate|rotate|remove`; PROOF9 defaults live in `.codeframe/proof_config.json` (`enabled_gates`, `strictness`), which `run_proof()` honors.
2. **Cost and token analytics** (#557–558) — the Costs page was removed. Token usage is still recorded per task in `token_usage` and reported by `cf stats`.
3. **Async notifications** (#559–560) — the browser notifications and in-app center were removed. The outbound webhook (`codeframe/notifications/webhook.py`) still fires on `batch.completed` and `blocker.created` (the `pr.merged` event came from the removed server) when `.codeframe/notifications_config.json` enables it.
4. **PRD stress-test web UI** (#561–562) — removed. `cf prd stress-test` runs the same `core/prd_stress_test.py`.
5. **GitHub Issues import** (#563–565) — the import flow was web-only and was removed. The core services (`core/github_issues_service.py`, `core/github_integration_config.py`) and auto-close of already-imported tasks on DONE remain; there is no CLI import command.

---

## What Is Explicitly Out of Scope

These are items that were considered and excluded because they do not serve the core vision at this stage.

**A web UI or hosted server**: removed in #1477. The CLI, the TUI and the proof9 plugin are the product.

**Fleet management / multi-repo coordination**: The vision explicitly says "It is not a fleet manager." CodeFRAME is for a single developer or small team on one project. Scaling to 30 agents across 10 repos is Gastown's domain.

**Multi-user workspaces and team permissions**: The vision says "solo developers and small teams." Collaboration features are not load-bearing until there is evidence of team adoption.

**Custom quality gate definitions**: PROOF9's 9 gates are well-defined and their configuration is a power-user concern that belongs in a config file.

**Deployment automation**: Post-merge deployment hooks are mentioned in the vision as part of SHIP, but CodeFRAME is not a CI/CD system. Deployment is what happens after CodeFRAME's artifacts are consumed by GitHub Actions or another pipeline. Focus on producing the right artifacts (verified PRs with proof reports), not on owning deployment.

**Competitor / agent benchmarking**: Comparing Claude Code vs Codex results for the same task is interesting but not on the critical path for the vision. Instrument cost and quality data first; analysis tooling comes later when there is data to analyze.

---

## Summary

| Phase | Focus | Status | Issues |
|---|---|---|---|
| 3.5A | Bidirectional agent chat | 🗑️ Removed (web UI, #1477) | #500–509 |
| 3.5B | Run gates from the web UI | 🗑️ Removed (web UI, #1477); `cf proof run` records runs + evidence | #566, #567, #574, #575 |
| 3.5C | Glitch capture UI | 🗑️ Removed (web UI, #1477); `cf proof capture` and the proof9 plugin's `/proof` capture | #568, #569 |
| 4A | PROOF9 merge gate | ✅ Complete (`cf pr merge` gate with audited override #731; per-PR scope + `vacuous_pass` #1247, #1254). The web PR status panel and merge endpoint were removed in #1477 | #571, #731, #1247, #1254 |
| 4B | Post-merge glitch capture loop | ❌ Not started | — |
| 5.1 | Settings page | 🗑️ Removed (web UI, #1477); `cf auth`, `.codeframe/proof_config.json` | #554–556 |
| 5.2 | Cost analytics | 🗑️ Web page removed (#1477); `cf stats` | #557–558 |
| 5.3 | Async notifications | 🗑️ Browser/in-app removed (#1477); outbound webhook remains | #559–560 |
| 5.4 | PRD stress-test web UI | 🗑️ Removed (web UI, #1477); `cf prd stress-test` | #561–562 |
| 5.5 | GitHub Issues import | 🗑️ Removed (web-only flow, #1477); core services remain | #563–565 |
| — | Web UI, FastAPI server, auth layer, deploy stack | 🗑️ Removed | #1477 |

**Current focus**: Phase 4B — post-merge glitch capture loop, on the CLI and the proof9 plugin. Phase 4A is complete: open (non-waived) requirements block `cf pr merge` unless an explicit override + reason is supplied, persisted as an audit record, and the gate is scoped to the PR's changed files.
