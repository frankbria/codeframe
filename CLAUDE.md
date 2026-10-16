# CodeFRAME Development Guidelines

Last updated: 2026-10-16

## Product Vision

CodeFrame is a **project delivery system**: Think → Build → Prove → Ship.

It owns the **edges** of the AI coding pipeline — everything BEFORE code gets written (PRD, specification, task decomposition) and everything AFTER (verification gates, quality memory, deployment). The actual code writing is delegated to frontier coding agents (Claude Code, Codex, OpenCode).

**CodeFrame does not compete with coding agents. It orchestrates them.**

```
THINK:  cf prd generate → cf prd stress-test → cf tasks generate
BUILD:  cf work start <task> --engine claude-code  (or codex, opencode, built-in)
PROVE:  cf proof run  (9-gate evidence-based quality system)
SHIP:   cf pr create → cf pr merge <number>
LOOP:   Glitch → cf proof capture → New REQ → Enforced forever
```

**Status: CLI ✅ | ReAct agent ✅ | Agent adapters ✅ | Multi-provider LLM ✅ | proof9 plugin ✅ | Web UI + server removed (#1477) | Next: Phase 4B** — See `docs/PRODUCT_ROADMAP.md`.

If you are an agent working in this repo: **do not improvise architecture**. Follow the documents listed below.

---

## Primary Contract (MUST FOLLOW)

1) **Golden Path**: `docs/GOLDEN_PATH.md` — the only workflow we build until it works end-to-end
2) **Command Tree + Module Mapping**: `docs/CLI_WIREFRAME.md` — CLI commands → core modules
3) **Product Roadmap**: `docs/PRODUCT_ROADMAP.md` — current phase plan and status
4) **Vision**: `docs/VISION.md` — north star for all decisions
5) **Agent System Reference**: `docs/AGENT_SYSTEM_REFERENCE.md` — agent components, execution flows

**Rule 0:** If a change does not directly support the Think → Build → Prove → Ship pipeline, do not implement it.

### Current Focus: Phase 4B

**The web UI, the FastAPI server, the auth layer and the deploy stack were removed (#1477).** The product is the `cf` CLI, the `cf dashboard` TUI and the proof9 Claude Code plugin (`proof9/`), which drives `cf proof … --json` and is the front door for the proof ledger. Phases 3.5, 5.1–5.5 shipped web features; their web surfaces went with #1477. What remains in core:

- **GitHub Issues (#563–565)**: `core/github_connect_service.py`, `core/github_issues_service.py` (`list_issues`, `get_issue`, `close_issue`) and `core/github_integration_config.py` remain; there is no CLI import command. Three #956 invariants hold in `list_issues`: the cache key is a **tuple** `(repo, page, per_page, search, label, user_id)` — never a `|`-joined string, which let a `|` in the search text collide with the label field; free-text search is quoted **per word** by `_sanitize_search` so it cannot inject `repo:`/`is:` qualifiers and escape the connected repo — and **every other user field that lands in `q` needs the same treatment**: the `label` qualifier shipped without it and reopened the hole (#1275; `"` is now stripped from it too); and a 403/429 that is really throttling (`Retry-After` / `X-RateLimit-Remaining: 0` / a body message naming the limit) raises `RateLimitedError` instead of being misreported as a missing `issues:read` scope. **Auto-close**: marking an opted-in imported task DONE closes the linked issue — fired from core `tasks.update_status`, targeting the task's *source* repo parsed from `external_url`, off the caller's path (non-daemon thread in CLI). The PAT comes from `github_integration_config.resolve_background_pat` (#900, #1283).
- **Cost tracking (#557–558)**: token usage is recorded per task in `token_usage` and reported by `cf stats`. A v2 data-loss bug where `react_agent` int-cast UUID task IDs and stored NULL was fixed; a second instance of the same class was fixed later: `CallType` had no `verification_fix` member, so `TokenUsage` rejected every self-correction retry's record and `_persist_token_usage` dropped it with only a WARNING (#712). **Any new `call_type` literal must be added to `CallType` in `core/models.py`** — `tests/core/test_react_agent_tokens.py::TestEveryEmittedCallTypeIsValid` enforces this.
- **Outbound webhook (#560)**: `codeframe/notifications/webhook.py` (`WebhookNotificationService`), configured by `.codeframe/notifications_config.json`, dispatched fire-and-forget (5s timeout) from `core/conductor.py` on `BATCH_COMPLETED` only and from `core/blockers.py:create()` after `BLOCKER_CREATED`. Failures are logged but never break the triggering operation.
- **PROOF9 config (#556)**: `run_proof()` honors `enabled_gates` filtering and `strictness` (`strict` vs `warn`) from `.codeframe/proof_config.json`. The 9-gate canonical order and the filename live in `codeframe/core/proof/models.py`.
- **PRD stress-test (#561–562)**: `cf prd stress-test` runs `core/prd_stress_test.py`; ambiguities carry `Ambiguity.severity` (`"blocking"`/`"warning"`), and `resolve_ambiguities_into_prd` + `prd.create_new_version` fold answers into a new PRD version.

**PROOF9 merge gate is enforced (#731)** — `cf pr merge` blocks while open (non-waived) requirements exist on the cwd workspace (`--override --reason "..."` to bypass; no workspace in cwd → no gate). The override is persisted to the `pr_merge_overrides` ledger table (actor, reason, bypassed requirements, timestamp). The #1247 follow-ups are **shipped**, and they changed three things worth knowing:

**The gate is scoped to the PR's changed files.** `list_blocking_requirements(workspace, changed_scope=None)` filters through `scope.intersects` — the same predicate `run_proof` has used since #922, not a second merge-specific rule. `changed_scope=None` means match-everything, so an omitted argument can never loosen the gate, and every failure path (outage, rate limit, missing credential, empty file list) falls back to it. The file list is fetched **only when something would otherwise block**, so a clean merge does not depend on a GitHub call. `_resolve_pr_scope` in `codeframe/cli/pr_commands.py` (#1254) fetches the PR's files and returns `None` on any failure. It asks for `include_previous=True`: GitHub reports a rename under its new path only, and without the old one a rename escaped the requirement scoped to it (a P1 found in review — **fail-closed defends against failures, not against correct-looking but incomplete input**). It resolves credentials through the headless `resolve_github_credentials`, not `_get_github_config`: that one prints and raises `typer.Exit`, so a merge about to be refused on requirements would have reported a credential problem instead.

**Three more fail-opens closed in #1276.** A WAIVED requirement whose waiver expired blocks; the check is read-only, and reverting the status stays `cf proof`'s job. `get_pr_files(require_complete=True)` raises `IncompletePRFilesError` at GitHub's 3000-file cap, or when the count disagrees with the PR's `changed_files`; the gate then falls back to `None`. Legacy absolute `scope.files` from 0.9.3 are rewritten once per process by `ledger._normalize_absolute_scope_files`. It uses `scope._is_absolute_path` and `_relativize` on **one entry at a time**, never `build_scope_from_capture`, which splits on commas.

The mutation check that shipped #1254 found the rename case was pinned by a test that *passed with the defect present*: its mock asserted `include_previous` in-band, and the `AssertionError` was swallowed by the gate's own fail-closed `except Exception`, which blocks the merge anyway. The rename test now makes the mock **behave** like GitHub (post-rename path only when not asked for previous) and asserts on the outcome. **A fail-closed handler will absorb an in-band test assertion and turn a red test green** — assert on behaviour, not on the mock's own arguments, anywhere a bare `except Exception` sits downstream.

The cross-family review of the same change found the matching fail-*open*: `build_scope_from_capture` stores a `--where` string verbatim, so a requirement captured as `./x.py` never matched anything and dropped out of every scoped run. Workspace-global scope hid it (the gate blocked regardless); scoping the CLI made it a silent merge. `scope._files_intersect` now normalizes both sides through `posixpath.normpath`, which fixes the gate and `run_proof` at once. A second review pass found the same fail-open in another spelling: the first fix collapsed root-equivalent paths (`./`, `src/..`) to `""` and *skipped* them, so a requirement scoped to the repo root matched nothing at all. `_normalize` now returns `"."` for the root and `_files_intersect` treats it as covering every file. **A normalizer that maps a meaningful value onto its own "nothing here" sentinel re-creates the bug it was written to fix.** #1258 then made the *classifier* workspace-aware, which is the layer that actually has a root: `build_scope_from_capture(where, workspace=..., on_warning=...)`. An absolute path inside the workspace is relativized into `files`; one that cannot equal a repo-relative path (`C:/…`, `~/…`, `file://…`, a leading `\`, or anything absolute with a space or `+` that the route regex rejects) goes to `tags`, which is uncomparable and therefore **fails closed**, with a warning naming it. It is deliberately **not** rejected: `/login` is a legitimate route that is also "outside the workspace", so refusing those would break route capture.

Two traps that change live in that function. **An inside-workspace path only beats route classification when it has a file extension or exists on disk** — a repo at `/app` (an ordinary container layout) makes `/app/settings` syntactically inside the workspace, and treating it as a file turned a route that matched everything into a file scope matching nothing. And **the route regex `^/[\w/\-.*]+$` runs before the file branches and admits dots**, so a plain POSIX absolute path was always classified as a *route* — it matched everything via #922, which is why this bug read as harmless for so long. #1258 was filed claiming the opposite; verify a scope claim by running `build_scope_from_capture`, not by reading the branch order.

A third trap, found over three review rounds: **a captured path that passes through a symlink stores every link it traverses plus the final target** (`_traversed_paths`, a `realpath` that keeps a record). git stores a symlink as a blob at its own path and never descends into a symlinked directory, so retargeting a link is reported under the *link's* path while an edit to its target is reported under the *target's* — any single spelling lets one of those changes escape the scope. That covers a file link (`link.py`, `real.py`), a mid-path directory link (`linkdir`, `realdir/x.py`) and every link in a chain; a loop fails closed at the kernel's 40-hop ELOOP limit. Each round had found one more shape, so this is the general rule — if another topology turns up, fail closed on any traversed link rather than adding a spelling. Keep `ValueError` in `_relativize`'s `except`: path operations raise it for an embedded NUL, and a `--where` must never crash capture.

**`ProofRun.vacuous_pass`** distinguishes a pass from a pass that verified nothing, computed as *passed with an empty tally* rather than by reading the config — so it also catches an `enabled_gates` list that excludes every obligation, and an all-UNVERIFIABLE run. A warn-mode run that masked a real failure is **not** vacuous (its gates ran), and a workspace with no requirements is not either (an empty ledger makes no false claim). The merge gate is deliberately **not** coupled to it: a vacuous run leaves requirements OPEN, so the gate already blocks them via requirement status. The ledger column is added by lazy `ALTER TABLE` mirroring #728 — and it **borrows the connection `_ensure_tables` already holds**, because `tests/core/test_tui_dashboard.py` pins a cold dashboard load at 3 connections and the TUI refreshes every 2s.

**`cf proof ratchet` (#1467)** fills an empty ledger from the tests that already pass. It runs the project's pytest suite **once** (sandboxed via `build_agent_env`, JUnit `junit_family=xunit1` so each case carries its file, `--cov=. --cov-context=test` when pytest-cov is present) and creates one OPEN requirement per passing test: `source=ratchet`, one `UNIT` obligation, one `must_pass` rule naming the test **by function name**, because that is how the runner enforces a rule (#1401). A name is locked only when `gates.cases_verdict` — the runner's own verdict, shared — passes across **every** case of that name in the suite, so `--path` filters which names are locked *after* a full run rather than narrowing what pytest runs (narrowing locked a name that also fails elsewhere, and let a `../` glob reach another repo). Scope is the files each test's coverage context touched, read straight from coverage's SQLite data with paths joined to the repo (`relative_files = True` stores them relative); no per-test data → `["."]` plus a warning, never a guess. Reruns dedupe on test name across every ratchet requirement; `Source.RATCHET` is reserved (capture raises). Exit 2 = nothing to lock, 1 = suite could not run — never a "locked in 0" success, and no `.codeframe/` is created unless something is locked. Once satisfied, a locked test is re-checked by a plain `cf proof run` whenever the diff touches its scope (#1484: a scoped run loads SATISFIED alongside OPEN when there is a diff and filters both through `intersects`; a clean tree re-checks nothing satisfied, and a failed scope detection re-checks everything), and always by `--full`. Its tests live in `tests/core/`, not `tests/cli/`: they spawn real pytest in fixture repos, which the Unlocked Resolution job's throwaway env cannot reach.

Phase 4A is ✅ Complete in the roadmap's Summary table, which is the single status authority (#1246).

Next, in order:
- **4B**: Post-merge glitch capture loop

See `docs/PRODUCT_ROADMAP.md` for full specs and issue links.

---

## Architecture Rules (non-negotiable)

### 1) Core must be headless
`codeframe/core/**` must NOT import FastAPI, WebSocket frameworks, HTTP request/response objects, or UI modules.

Core is allowed to: read/write durable state (SQLite/filesystem), run orchestration/worker loops, emit events to an append-only event log, call adapters via interfaces (LLM, git, fs).

### 2) CLI must not require a server
Golden Path commands work from the CLI alone. There is no server (removed in #1477); do not add one to support a CLI command.

### 3) Agent state transitions flow through runtime
- Agent (`agent.py`) manages its own `AgentState` (IDLE, PLANNING, EXECUTING, BLOCKED, COMPLETED, FAILED)
- Runtime (`runtime.py`) handles all `TaskStatus` transitions (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED)
- Agent does **NOT** call `tasks.update_status()` — runtime does this based on agent state

This separation prevents duplicate state transitions (e.g., DONE→DONE errors).

### 4) Keep commits runnable
At all times: `codeframe --help` works, Golden Path stubs can run, no breaking renames/moves.

---

## Current State

### v2 Architecture
- **Core-first**: Domain logic lives in `codeframe/core/` (headless)
- **CLI-first**: the Golden Path is the `cf` CLI; `cf dashboard` is a Textual TUI over the same core
- **Adapters**: LLM providers in `codeframe/adapters/llm/`
- **proof9 plugin**: `proof9/` is a Claude Code plugin that drives `cf proof … --json` by argv

### What's implemented
Full feature list in `docs/PRODUCT_ROADMAP.md`. Key capabilities: ReAct agent execution, batch execution (serial/parallel/auto), task dependencies, stall detection, self-correction, GitHub PR workflow, run output streaming (`cf work follow`), multi-provider LLM (Anthropic/OpenAI-compatible), agent adapters (ClaudeCode/Codex/OpenCode/Kilocode), worktree isolation, PROOF9 quality system (gate runs, per-gate evidence, run history, `cf proof ratchet`, `cf proof export`), the proof9 Claude Code plugin, and the `cf dashboard` TUI. E2B cloud execution exists but is EXPERIMENTAL and gated — see `CODEFRAME_ENABLE_CLOUD_ENGINE` below.

---

## Repository Structure

```
codeframe/
├── core/           # Headless domain + orchestration (NO FastAPI imports)
│   ├── react_agent.py, tools.py, editor.py   # ReAct engine (default)
│   ├── agent.py, planner.py, executor.py     # Plan engine (legacy --engine plan)
│   ├── runtime.py                            # Run lifecycle, engine selection
│   ├── conductor.py                          # Batch orchestration + worker pool
│   ├── dependency_graph.py, dependency_analyzer.py
│   ├── gates.py, fix_tracker.py, quick_fixes.py  # Verification + self-correction
│   ├── stall_detector.py, stall_monitor.py   # Stall detection
│   ├── tasks.py, blockers.py, prd.py, workspace.py
│   ├── context.py, state_machine.py, events.py, streaming.py
│   ├── environment.py, installer.py, diagnostics.py, diagnostic_agent.py
│   ├── credentials.py, agents_config.py
│   └── sandbox/context.py, sandbox/worktree.py   # Isolation abstractions
├── adapters/
│   ├── llm/base.py, llm/anthropic.py, llm/openai.py, llm/mock.py
│   └── e2b/        # Cloud sandbox (optional: pip install codeframe[cloud])
├── cli/app.py      # Typer CLI entry + subcommands
├── tui/            # `cf dashboard` (Textual)
├── notifications/  # Outbound webhook (WebhookNotificationService)
├── lib/            # metrics_tracker.py
└── platform_store/ # Per-workspace TokenRepository (token usage)

proof9/             # Claude Code plugin: /proof capture + ratchet via cf proof --json
tests/
├── core/           # Core module tests (auto-marked v2)
├── adapters/       # LLM + E2B adapter tests
├── agents/         # dependency_resolver tests
├── integration/    # Cross-module integration tests
├── cli/            # Typer command tests
├── ci/             # Workflow + doc guards
└── lifecycle/      # End-to-end CLI lifecycle test (real LLM)
```

---

## Commands

### Python / CLI
```bash
uv run pytest                            # All tests
uv run pytest tests/ --ignore=tests/e2e -m "not lifecycle"  # The CI gate (every non-e2e, non-real-LLM test)
                                         # ~6.5 min locally. If it is much slower on your
                                         # machine, see "Suite speed" below.
uv run pytest tests/core/                # Core module tests
scripts/lifecycle --mode cli             # Lifecycle test (run locally before a PR)
                                         # real LLM calls, needs a key, costs money
uv run ruff check .

scripts/quickstart-cleanroom/run.sh      # Cold-start check — RUN BEFORE EVERY RELEASE
                                         # Installs the PUBLISHED package on a clean
                                         # container and follows the README. Needs a
                                         # real key and ~10 min. Add `--source <dir>`
                                         # to check an unreleased fix instead.
```

#### The cold-start check is not optional (#1112, #1168)

Nothing else here installs what a user installs. `uv.lock` is what CI, `uv sync`
and every developer machine resolve; `uv tool install codeframe-ai` resolves the
**ranges** in `pyproject.toml` against live PyPI instead. Those two drift apart
silently, and twice now a release has been dead on arrival on the one install
path the README documents while every gate was green:

- **#1112** — 0.9.1 shipped retired model IDs; every AI command 404'd.
- **#1168** — 0.9.2 pinned `anthropic>=0.18.0` with no ceiling, so a fresh
  install resolved `anthropic` 1.0.0, which removed `temperature` from
  `Messages.create()`; every AI command raised `TypeError`.

So: **a floor-only pin on an SDK is a latent DOA release.** Cap the major on
anything whose call signature we depend on, and remember the lockfile hides it.
The adapter now runs on `anthropic` 1.x and the pin is `>=1.0,<2` (#1170) — the
*ceiling* is the lesson, not the version, so do not make it floor-only again.
`tests/adapters/test_sdk_kwargs_guard_614.py` catches the drift once it reaches
the lock. Before that, the **Unlocked Resolution** workflow
(`.github/workflows/unlocked-resolution.yml`, #1169) catches it: it resolves the
`pyproject.toml` ranges with no lockfile against live PyPI, installs into a
throwaway env, and runs `cf --help` plus both SDK guards against *that* env. It
runs daily on a schedule — this break arrives from upstream, so it can appear on
a day nobody pushed — on PRs touching `pyproject.toml` or the guards, and as a
required gate on `release.yml`. A red *scheduled* run opens or updates an issue
via `scheduled-failure-issue.yml` (#1239, #1242), like the other two daily
checks. `tests/ci/test_unlocked_resolution_guard_1169.py`
pins those properties.

#1170 moved where the risk lives, so the #614 guard now carries two halves. The
signature check stayed, but it got weaker: `temperature` was a real bet on the
signature, while `extra_body` — where `temperature` travels on 1.x — is generic
SDK plumbing that will never vanish. The second half is a wire-level test that
drives the installed client through a mock transport and decodes the request
body, so it fails if `extra_body` ever stops being merged into the request. It
lives in that same file deliberately: this file and
`test_model_defaults_guard_1112.py` are what Unlocked Resolution runs, and a
guard that the unlocked job cannot see is not guarding the install path.

That job needs no API key and takes seconds, so it is not a replacement for the
cold-start harness: it checks the *resolution*, the harness checks the
*published package* on a clean container. Both still matter.

#### Suite speed (#979)

The suite used to be fsync-bound: `_init_database` builds ~18 tables plus
indexes and switches to WAL, and that cost **~1273 ms per test** on a real
filesystem versus 2.7 ms on tmpfs. It ran once per test, which was most of the
wall clock — measured at ~910 s, and reportedly ~4 h on a slower WSL2 disk.

`tests/conftest.py` now builds that schema **once per session** and copies the
file (0.1 ms) into place per test. `_init_database` output is byte-identical
across builds, so the copy is exactly equivalent; the template is produced by
calling the real function, so a schema change or `SCHEMA_VERSION` bump cannot
leave it stale. Full suite: **~910 s → ~378 s**, same results, and CI benefits
too. `tests/core/test_workspace_db_template_979.py` pins the equivalence.

If your machine is still I/O-bound, put pytest's temp dirs on tmpfs:

```bash
mkdir -p /dev/shm/pytest-cf
uv run pytest tests/ --ignore=tests/e2e -m "not lifecycle" --basetemp=/dev/shm/pytest-cf
```

Opt-in on purpose — a real filesystem is what CI runs, and is the more faithful
environment. `/dev/shm` is RAM-backed (the run must fit) and Linux-only. It
composes with the ambient-workspace guard: `pytest_configure` registers
`--basetemp` as an isolated root. With the template fix this now buys nothing
here (378 s on disk vs 428 s on tmpfs before the fix); it is the lever only
for disks where the gap is still large.

### Golden Path CLI
```bash
# Workspace
cf init <repo> [--detect | --tech-stack "..." | --tech-stack-interactive]
cf status

# PRD
cf prd add <file.md>
cf prd show
cf prd stress-test [--llm-provider openai --llm-model gpt-4o]

# Tasks
cf tasks generate [--llm-provider openai --llm-model gpt-4o]
cf tasks list [--status READY]
cf tasks show <id>

# Work — single task
cf work start <task-id> [--execute] [--engine react|plan] [--verbose] [--dry-run]
cf work start <task-id> --execute --stall-timeout 120 --stall-action retry|blocker|fail
cf work start <task-id> --execute --llm-provider openai --llm-model gpt-4o
cf work stop <task-id>
cf work resume <task-id>
cf work follow <task-id> [--tail 50]
cf work diagnose <task-id>

# Work — batch
cf work batch run [<id>...] [--all-ready] [--engine react|plan]
cf work batch run --strategy serial|parallel|auto [--max-parallel 4] [--retry 3]
cf work batch run --all-ready --llm-provider openai --llm-model qwen2.5-coder:7b
cf work batch status [batch_id]          # batch_id optional here
cf work batch stop|resume|follow <batch_id>   # ...and required here

# Blockers
cf blocker list
cf blocker show <id>
cf blocker answer <id> "answer"

# Proof
cf proof capture | ratchet [--dry-run] [--path GLOB] | run [--full] | list | show | status | waive
cf proof export --format html|json|pdf [--output PATH]   # evidence report (#1472)

# Quality / State
cf review && cf patch export && cf commit create -m "feat: ..."
cf checkpoint create|list|restore
cf summary

# Environment
cf env check|doctor|install-missing|auto-install

# GitHub PR
cf pr create|list|get|status|merge|close

# Telemetry (machine-wide, opt-in)
cf config telemetry on|off|status
```

---

## What NOT to do

- Don't add a server, HTTP endpoints or a web UI back to support a CLI workflow (removed in #1477)
- Don't implement UI concepts (tabs, panels, progress bars) inside `codeframe/core/`
- Don't "clean up the repo" as a goal — only refactor to enable the pipeline
- Don't update task status from `agent.py` — let `runtime.py` handle transitions
- **Don't write to `discovery_sessions` without honouring the single-active-session
  index** (#1042). A workspace holds at most one row with
  `state != 'completed' AND COALESCE(is_complete, 0) = 0`, enforced by
  `idx_discovery_sessions_one_active`. So: create the row only via
  `_claim_session` (a plain INSERT, whose UNIQUE violation means "already
  active"), and update it only via `_save_session`. Any write that follows an
  LLM call must pass `require_active=True` — `/reset` can land during that call,
  and an unconditional write resurrects the session the user just abandoned.
  `submit_answer` and `pause_discovery` learned this the hard way.
- **Don't render user text through Rich without escaping it**, and don't write
  a new `except Exception as e: console.print(f"...{e}")` — use
  `codeframe.cli.helpers.print_error`, which escapes once (#1054). An exception
  message quotes user input, so rendering it raw made the handler itself raise
  `MarkupError` and turned a caught error into an uncaught crash. The guard is
  `tests/cli/test_rich_hostile_data_1054.py`: it seeds hostile markup into every
  user-supplied field and *runs the commands*, because the field-name scanner it
  replaced was too narrow four times in one review cycle — a local bound one
  statement earlier carries no field name at all. Every registered command must
  appear in its `RUN` or `EXEMPT` table; a new command fails CI until classified.
  The `EXEMPT` commands it cannot run are covered statically by
  `tests/cli/test_typer_arg_markup_1206.py`: a Typer command's `str`-annotated
  parameters are user input by definition, and any `console.print` / `.write` /
  `.add_row` in that command that interpolates one without `escape()` fails CI.
  Wrap the argument (`escape(str(x))` if it is Optional); do not add to `ALLOWED`.
- **Don't leave a CI gate disabled when its feature area becomes active.** Re-enable `DISABLED:` / `# COMMENTED OUT:` jobs before the first PR in that area.
- **A CI run that fails with ZERO jobs and no logs means the workflow file will not compile** (#1122). `gh run view --log-failed` returns `log not found`, the jobs API is empty, and the run ignores its own trigger filters — so it looks like an unrelated trigger bug rather than an outage. YAML validity is not enough: `yaml.safe_load()` parses these files fine; it is GitHub's expression pass that rejects them. Run `actionlint .github/workflows/*.yml` first — the `workflow-lint` job in `test.yml` now enforces this on every PR, but it is the first thing to run locally when a workflow misbehaves. This shipped twice undetected: `deploy.yml` (staging down for a week, an empty `${{ }}` inside a `run:` block) and `claude-review` (#1011).

---

## Testing / Demoing

### Quality check
```bash
uv run pytest && uv run ruff check .
```

New v2 tests: add `@pytest.mark.v2` or `pytestmark = pytest.mark.v2` at module level.

### Demoing against a sample project (e.g., `cf-test/`)
You are **observing the CodeFRAME agent's work, not doing the work yourself**.
- Do NOT help out, fix errors, or write code on behalf of the agent
- Do NOT intervene when the agent makes mistakes — that's data
- Report what worked, what failed, final state vs. acceptance criteria

---

## Practical Working Mode

1. Read `docs/GOLDEN_PATH.md` — confirm the change is required
2. Find the command in `docs/CLI_WIREFRAME.md`
3. Implement core functionality in `codeframe/core/`
4. Call it from Typer command in `codeframe/cli/`
5. Emit events + persist state
6. Keep it runnable. Commit.

When unsure: simpler state, fewer dependencies, smaller surface area, core-first, CLI-first.

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...          # Required for Anthropic provider (default), unless
                                      # stored via `cf auth setup`.
                                      # One resolver (#1264): llm_resolution.resolve_api_key —
                                      # env → stored credential. Build providers with
                                      # create_provider(settings), never get_provider bare.
E2B_API_KEY=e2b_...                   # Required for --engine cloud
DATABASE_PATH=./codeframe.db          # Optional

# Repo-committed hook trust (#905) — default OFF (refuse)
CODEFRAME_ALLOW_HOOKS=1               # Run a workspace's configured lifecycle
                                      # hooks without a recorded trust decision.
                                      # Hooks come from .codeframe/config.yaml,
                                      # a file a cloned repo can commit, and
                                      # `cf init` fires after_init immediately —
                                      # so by default a hook runs only after
                                      # `cf hooks trust` records approval in
                                      # ~/.codeframe/trusted_hooks.json (outside
                                      # the repo tree, keyed to the exact
                                      # commands, so editing a hook re-asks).
                                      # `cf init --allow-hooks` sets this for
                                      # one run. CODEFRAME.md can no longer
                                      # supply hooks at all: it is found by
                                      # walking UP from the workspace.

# Experimental cloud engine (#966) — default OFF (refuse)
CODEFRAME_ENABLE_CLOUD_ENGINE=1       # Unlock `--engine cloud` (the E2B adapter).
                                      # Off by default and off the advertised
                                      # surface: it is out of launch scope and
                                      # does not currently work end-to-end, but
                                      # it was reachable and listed next to the
                                      # engines that do. `resolve_engine` and
                                      # `get_external_adapter` now both refuse it
                                      # (so CODEFRAME_ENGINE=cloud is not a way
                                      # around the flag) with a message naming
                                      # this variable. IsolationLevel.CLOUD is a
                                      # separate thing and stays unimplemented.
                                      #
                                      # KNOWN DEFECTS — the price of lifting the
                                      # gate. Deliberately NOT fixed in #966;
                                      # this is the checklist for whoever makes
                                      # the engine real:
                                      #   1. Wrong package. `_INSTALL_CMD` runs
                                      #      `pip install codeframe`, but the
                                      #      project publishes as `codeframe-ai`
                                      #      — every sandbox installs someone
                                      #      else's package or nothing.
                                      #   2. `CommandExitException` from the E2B
                                      #      SDK is not handled, so a non-zero
                                      #      command in the sandbox surfaces as
                                      #      an unhandled traceback instead of a
                                      #      failed run.
                                      #   3. No working sync-back: results
                                      #      produced in the sandbox do not
                                      #      reliably land in the workspace, so a
                                      #      "successful" run can leave nothing
                                      #      behind.
                                      #   4. File upload is unbatched (one
                                      #      round-trip per file) — unusable on a
                                      #      real repo.
                                      #   5. The adapter's tests mock with
                                      #      non-autospec mocks, so they pass
                                      #      against signatures the SDK does not
                                      #      have — they are not evidence the
                                      #      engine works.

# Delegated-agent HOME sandbox (#996) — default ON (sandboxed)
CODEFRAME_AGENT_INHERIT_HOME=1        # Run delegated coding CLIs (claude-code,
                                      # codex, opencode, kilocode) with the
                                      # operator's REAL $HOME instead of a
                                      # per-adapter one. Off by default: those
                                      # subprocesses used to inherit the whole
                                      # environment and the real HOME, which
                                      # resolves ~/.codeframe/credentials,
                                      # ~/.ssh and ~/.config/gh/hosts.yml — on a
                                      # test machine, 69 env vars (5 of them API
                                      # keys) down to 12 (0 keys) once fixed.
                                      # Each adapter now declares the credentials
                                      # it needs (`credential_env_vars`) and its
                                      # own login dir (`home_passthrough`, e.g.
                                      # ~/.claude, ~/.codex), which is symlinked
                                      # into ~/.codeframe/agent-homes/<adapter>
                                      # so `claude`/`codex` stay logged in. Set
                                      # this only if a CLI keeps state somewhere
                                      # CodeFrame does not forward. It does NOT
                                      # reopen the env allowlist — separate knob.
                                      # Like build_agent_env, not containment: an
                                      # absolute path still reaches whatever the
                                      # operator can read.

# LLM Provider selection (multi-provider support)
# Priority: CLI flag > env var > .codeframe/config.yaml > default (anthropic)
CODEFRAME_LLM_PROVIDER=anthropic      # Provider: anthropic (default), openai, ollama, vllm, compatible
CODEFRAME_LLM_MODEL=gpt-4o            # Model override (used with openai/ollama/vllm/compatible)
OPENAI_API_KEY=sk-...                 # Required for openai provider; not needed for local providers
OPENAI_BASE_URL=http://localhost:11434/v1  # Base URL override (OpenAI-compatible providers only, #780)
# Per-workspace config: .codeframe/config.yaml supports llm: block
# llm:
#   provider: openai
#   model: qwen2.5-coder:7b
#   base_url: http://localhost:11434/v1   # optional; local models, or an API proxy/gateway (any provider incl. anthropic, #780)

# Repo-supplied LLM endpoint opt-in (#903) — default OFF (refuse)
CODEFRAME_ALLOW_CONFIG_BASE_URL=1    # Allow a `.codeframe/config.yaml`
                                      # `llm.base_url` that is NOT this machine.
                                      # That file lives inside the repository,
                                      # so cloning an untrusted repo would
                                      # otherwise redirect API traffic — and the
                                      # operator's API key — to whatever host it
                                      # names. Loopback URLs (localhost/127.0.0.1/
                                      # ::1) are always allowed: they are the
                                      # documented local-model setup and cannot
                                      # exfiltrate. The env tier
                                      # (OPENAI_BASE_URL) is the operator's own
                                      # environment and is unaffected (#780).
                                      # Note the gate is not limited to
                                      # anthropic/openai: get_provider hands
                                      # OPENAI_API_KEY to ollama/vllm/compatible
                                      # too when it is set.

# Credential-file confidentiality (#772 — opt-in)
CODEFRAME_CREDENTIAL_SECRET=<secret>  # Mixed into the PBKDF2 KDF for the
                                      # encrypted-file credential fallback
                                      # (codeframe/core/credentials.py). Unset =
                                      # key derived from the (non-secret)
                                      # machine-id alone — obfuscation-at-rest,
                                      # not confidentiality vs a local reader.
                                      # Set it for real confidentiality; prefer
                                      # the OS keyring where available. WARNING:
                                      # adding/changing this rekeys the store, so
                                      # previously stored credentials become
                                      # undecryptable and must be re-entered.

# Unresponsive keyring backends (#1181)
CODEFRAME_DISABLE_KEYRING=1           # Skip the OS keyring entirely and use the
                                      # encrypted file store. A backend that is
                                      # installed and *selected* but never
                                      # answers — SecretService on a headless
                                      # box, container or SSH session with no
                                      # session D-Bus — raises nothing, it
                                      # blocks. Detection by exception therefore
                                      # never fired, so the fallback never
                                      # engaged and every credential read hung
                                      # forever and the test suite wedged.
                                      # Every keyring call is now
                                      # time-boxed and a timeout is treated
                                      # exactly like KeyringError; the verdict
                                      # is sticky per process, so the timeout is
                                      # paid once, not once per request. This
                                      # variable is the explicit opt-out (and
                                      # avoids even the first timeout).
CODEFRAME_KEYRING_TIMEOUT=2.0         # Seconds allowed per keyring call before
                                      # falling through to the encrypted file.
                                      # Read at call time, not import (#963).
                                      # Raise it if a healthy backend with an
                                      # unlock prompt needs longer.
                                      # `PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring`
                                      # remains the keyring-native equivalent.

# Outbound webhook SSRF guard (#656, #746) — default OFF (block)
CODEFRAME_ALLOW_PRIVATE_WEBHOOKS=1    # Allow webhook URLs whose host resolves to
                                      # private/loopback/link-local/metadata/CGNAT
                                      # IPs. Off by default: such hosts are
                                      # rejected at dispatch time (#746):
                                      # send_event resolves-and-checks
                                      # the host and pins the vetted IPs into the
                                      # connector (defeats hand-edited config and
                                      # DNS rebinding; e.g. 169.254.169.254 IMDS).
                                      # Set for self-hosted ops with legit internal
                                      # webhook targets (localhost, RFC1918).

# Telemetry (default: off — must be explicitly opted in)
CODEFRAME_TELEMETRY=on|off            # Force telemetry on or off; overrides ~/.codeframe/telemetry.json
CODEFRAME_TELEMETRY_ENDPOINT=<url>    # Override collector URL (default: https://telemetry.codeframe.sh/v1/events)
DO_NOT_TRACK=1                        # Standard convention; disables telemetry when set (and not 0/false)
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| `docs/VISION.md` | North star: Think → Build → Prove → Ship thesis |
| `docs/PRODUCT_ROADMAP.md` | **Current roadmap** — phase status (Summary table is the authority) |
| `docs/GOLDEN_PATH.md` | CLI-first workflow contract |
| `docs/CLI_WIREFRAME.md` | Command → module mapping |
| `docs/AGENT_SYSTEM_REFERENCE.md` | Component table, model selection, execution flows, self-correction |
| `docs/REACT_AGENT_ARCHITECTURE.md` | ReAct deep-dive: tools, editor, token management |
| `docs/QUICKSTART.md` | User-facing quickstart guide |
| `docs/CLI_GUIDE.md` | CLI walkthrough + full command reference |

v1 history (sprint plans, specs, legacy docs), archived v2 plans, and the web UI /
server docs removed in #1477 remain in git history.
