# CodeFRAME Product Roadmap

**Updated**: 2026-04-06
**Vision**: *CodeFRAME is the project delivery system that turns ideas into verified, deployed code — AI agents write the code, CodeFRAME owns everything before and after.*

This is the **single source of truth** for CodeFRAME's product roadmap. All prior planning documents (V2_STRATEGIC_ROADMAP, FEATURE_ROADMAP, IMPLEMENTATION_ROADMAP, etc.) are archived in `docs/archive/`.

This document focuses on gaps in the web product that block the end-to-end vision. It is not a comprehensive feature list. Items included here were selected because they are load-bearing for the Think → Build → Prove → Ship pipeline or because their absence creates a significant hole in the user experience.

### Completed foundation (prior phases)
- **Phases 1–2.5**: CLI foundation, FastAPI server layer, ReAct agent — all complete
- **Phase 3**: Web UI core screens — PRD editor, task board, execution monitor, blocker resolution, diff reviewer, PROOF9 requirements table, interactive agent sessions (`/sessions`) — all complete
- **Phase 4.A–4.D**: Agent adapter protocol (ClaudeCode/Codex/OpenCode/Kilocode), execution environment (worktree isolation, E2B cloud), multi-provider LLM (OpenAI-compatible adapter) — all complete

---

## Current State (verified 2026-04-06)

The golden path works end-to-end in the browser for a single developer on a single project. All core screens exist. What is missing is not *breadth* — it is *depth* in the places the vision depends on most.

---

## Phase 3.5 — Close the Interaction Gap ✅ PARTIAL (A+B complete, C pending)

**The issue**: The web UI is read-heavy. Users watch agents run, view requirements, inspect diffs. But they cannot run quality gates from the browser or capture a glitch and watch it become a permanent proof obligation.

### Milestone A: Bidirectional Agent Chat ✅ COMPLETE (#500–509)

Fully shipped: `/sessions` page, `/sessions/[id]` detail with `SplitPane`, `AgentChatPanel`, `AgentTerminal`, `useAgentChat` WebSocket hook, `session_chat_ws.py` router, `terminal_ws.py` router, `session_manager.py` core module, `interactive_sessions_v2.py` REST API.

---

### Milestone B: Run Quality Gates from the Web UI ✅ COMPLETE (#566, #567, #574, #575)

Fully shipped: `[Run Gates]` button on the PROOF9 page, live gate progress view (pending → running → passed/failed), per-gate evidence display (`GateEvidencePanel`), and run history panel (`RunHistoryPanel`) showing the last 5 gate runs. Backend endpoints `GET /api/v2/proof/runs` and `GET /api/v2/proof/runs/{run_id}/evidence` added. Core: `proof_runs` table in `ledger.py`, `ProofRun` dataclass in `models.py`, `runner.py` populates runs on every execution.

---

### Milestone C: Glitch Capture UI ✅ COMPLETE (#568, #569)

Fully shipped: `CaptureGlitchModal` form reachable from the PROOF9 page header and the sidebar "Capture Glitch" button. Form collects description (markdown), source (production/QA/dogfooding/monitoring), scope (files/routes/components, stored as `ScopeOut` on the backend and `ProofScope` in the frontend types), gate obligations (multi-select), severity, and optional expiry. On submit, creates a new REQ in the requirements ledger immediately.

REQ detail view (`/proof/[req_id]`): markdown-rendered description, scope metadata display, obligations table with a `Latest Run` column showing pass/fail per gate from the most recent run, sortable/filterable evidence history, and a "Capture Glitch" empty-state CTA when no evidence exists yet.

---

## Phase 4 — Complete the SHIP Phase ❌ NOT STARTED

**The issue**: The Review page creates a PR. After that, the user has no feedback from CodeFRAME. They must go to GitHub to check CI, check reviews, and merge. The SHIP phase currently ends at PR creation.

### Milestone A: PR Status Tracking ❌ NOT STARTED

After a PR is created from the Review page, show its live status in the web UI.

**What to build**:

- A **PR Status panel** on the Review page (and optionally on the task detail modal) that polls GitHub for:
  - CI check status (pending / passing / failing), with per-check breakdown
  - Review status (approved / changes requested / pending)
  - Merge state (open / merged / closed)
- Polling interval: 30 seconds when the Review page is active
- Visual indicators matching the existing state badge patterns
- A **[Merge]** button that becomes active only when:
  1. All CI checks pass, and
  2. PROOF9 has no open (non-waived) requirements for the changed scope
- If PROOF9 has open requirements: show a gating message listing which requirements are blocking merge and linking to the PROOF9 page

**Why it matters for the vision**: "Merge is gated on PROOF9 pass." That sentence is in the vision doc. Without CI tracking and a merge gate in the UI, this is a CLI-only guarantee. The SHIP phase is only complete when the user can go from "PR opened" to "merged" without leaving CodeFRAME.

---

### Milestone B: Post-Merge Glitch Capture Loop ❌ NOT STARTED

When a merged PR leads to a production glitch, the system should make it easy to feed that back into PROOF9 as a permanent requirement.

**What to build**:

- A **PR history view** on the Review page (or a dedicated `/shipped` page) listing recently merged PRs with their proof reports at time of merge
- A **"Report Glitch"** action on each merged PR that pre-populates the Glitch Capture form (Milestone C above) with the PR's scope (files changed, routes affected)
- A link from each glitch REQ back to the PR that produced the code it is guarding

**Why it matters for the vision**: "Quality compounding interest. Over time, the system becomes harder to break in the ways you have already been burned." This feedback loop is described as central to the system. Without connecting post-merge glitches back to the PROVE layer, each deployment is a one-shot with no learning.

---

## Phase 5 — Platform Completeness ❌ NOT STARTED

Issues created: #554–#565 (2026-04-06)

These items are not part of a specific pipeline stage but are prerequisites for real-world adoption. They are ordered by the degree to which their absence blocks a new user from completing the pipeline.

### 1. Settings Page

**Current state**: API keys, model selection, quality gate thresholds, and agent preferences are configured via environment variables or CLI config. There is no web UI for any of this.

**What to build**:

- **Agent settings**: default model per agent type (Claude, Codex, OpenCode), max turns, max cost per task
- **API keys**: input and verify `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, GitHub token — stored encrypted, never returned in plaintext
- **PROOF9 defaults**: which gates are enabled by default for new projects, strictness level (fail on any open REQ vs. warn only)
- **Workspace configuration**: workspace root path, default branch, auto-detection overrides

Without a settings page, a new user who cannot find the env vars cannot use the product. This is an onboarding blocker.

---

### 2. Cost and Token Analytics

**Current state**: Token usage is recorded in the DB (`token_usage` table) per task. It is not surfaced anywhere in the web UI.

**What to build**:

- A **Costs page** (or section within Settings) showing:
  - Total spend for the current workspace, last 7 / 30 / 90 days
  - Cost breakdown by task (top 10 most expensive)
  - Cost breakdown by agent type (Claude Code vs Codex vs ReAct)
  - Input vs output token split
  - Average cost per task
- Cost column on the task board cards (already supported in the data model, just not displayed)

**Why it matters for the vision**: CodeFRAME runs paid AI APIs. Users need to know what they are spending and which tasks are costing the most. This is also the data that informs prompt template improvements and agent selection decisions.

---

### 3. Async Notifications

**Current state**: Batch executions can run for hours. The user has no notification when a batch completes, a blocker is created, or a gate run fails.

**What to build**:

- **Browser notifications** (Web Notifications API): opt-in, triggered on batch completion, blocker creation, and gate run failure — follow the existing WebSocket event stream for triggers
- **In-app notification center**: a bell icon in the sidebar with a history of recent notifications, clearable
- **Optional webhook**: a single URL the user can configure to receive JSON payloads on key events (batch done, blocker created, PR merged) — supports Slack, Discord, or any HTTP endpoint

The webhook is optional and last priority. Browser notifications and the in-app center are sufficient for the core use case.

---

### 4. PRD Stress-Test Web UI

**Current state**: The CLI has `cf prd stress-test` for recursive decomposition — it takes the PRD and surfaces ambiguities the agent cannot resolve without human input. This is described in the vision as a core part of the THINK phase. The web UI has no equivalent; users who work exclusively in the browser never see this step.

**What to build**:

- A **[Stress Test]** button on the PRD page that triggers the stress-test process
- A **results view** showing the decomposition tree with ambiguities surfaced as questions, styled similarly to the existing Discovery transcript
- Each ambiguity has an inline answer field — the user's answers are fed back to refine the PRD
- On completion: the refined PRD is saved and the user can proceed to task generation

**Why it matters for the vision**: "Gaps discovered at planning time, not execution time." The stress-test is the mechanism that makes requirements specific enough for agents to execute correctly. Without it in the web UI, the web-first user skips the most valuable part of the THINK phase.

---

### 5. External Issue Import (GitHub Issues → Tasks)

**Current state**: The THINK phase starts from "I have an idea" (PRD generation). The vision acknowledges that some users start from an existing issue tracker: "If you already have issues in a tracker, CodeFRAME can potentially consume them (future integration)."

**What to build**:

- A **GitHub Issues import** flow on the Tasks page: connect a GitHub repo, browse open issues, select one or more, and import them as CodeFRAME tasks with their title, description, and labels mapped to task fields
- Imported tasks link back to the original GitHub issue (external ID stored)
- On task completion, optionally close the corresponding GitHub issue

Keep scope narrow: GitHub only, import-only (no two-way sync), no Linear or Jira in v1 of this feature.

**Why it matters for the vision**: Many developers already have issue trackers. Requiring them to re-enter every issue into a PRD is a barrier to adoption. Import is the bridge between "I have a backlog" and "I want CodeFRAME to work through it."

---

## What Is Explicitly Out of Scope

These are items that were considered and excluded because they do not serve the core vision at this stage.

**Fleet management / multi-repo coordination**: The vision explicitly says "It is not a fleet manager." CodeFRAME is for a single developer or small team on one project. Scaling to 30 agents across 10 repos is Gastown's domain.

**Multi-user workspaces and team permissions**: The vision says "solo developers and small teams." JWT auth supports multiple users, but role-based workspace access control is not load-bearing until there is evidence of team adoption. Shipping collaboration features before single-user quality is right would be premature.

**Custom quality gate definitions via UI**: PROOF9's 9 gates are well-defined and their configuration is a power-user concern that belongs in a config file, not a UI form. This can be revisited when the gate run UI (Phase 3.5 Milestone B) is validated.

**Deployment automation**: Post-merge deployment hooks are mentioned in the vision as part of SHIP, but CodeFRAME is not a CI/CD system. Deployment is what happens after CodeFRAME's artifacts are consumed by GitHub Actions or another pipeline. Focus on producing the right artifacts (verified PRs with proof reports), not on owning deployment.

**Competitor / agent benchmarking**: Comparing Claude Code vs Codex results for the same task is interesting but not on the critical path for the vision. Instrument cost and quality data first; analysis tooling comes later when there is data to analyze.

---

## Summary

| Phase | Focus | Status | Issues |
|---|---|---|---|
| 3.5A | Bidirectional agent chat | ✅ Complete | #500–509 |
| 3.5B | Run gates from the web UI | ✅ Complete | #566, #567, #574, #575 |
| 3.5C | Glitch capture UI | ✅ Complete | #568, #569 |
| 4A | PR status + PROOF9 merge gate | ❌ Not started | — |
| 4B | Post-merge glitch capture loop | ❌ Not started | — |
| 5.1 | Settings page | ❌ Not started | #554–556 |
| 5.2 | Cost analytics | ❌ Not started | #557–558 |
| 5.3 | Async notifications | ❌ Not started | #559–560 |
| 5.4 | PRD stress-test web UI | ❌ Not started | #561–562 |
| 5.5 | GitHub Issues import | ❌ Not started | #563–565 |

**Current focus**: Phase 4A — PR status tracking + PROOF9 merge gate.

The ordering within Phase 5 is by onboarding impact. Settings (5.1) and cost (5.2) block new users earliest.
