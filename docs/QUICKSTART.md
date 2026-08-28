# CodeFRAME CLI Quickstart Guide

Get your project built with AI agents in minutes.

## Install

```bash
uv tool install codeframe-ai     # installs the `cf` command globally
cf --help                        # smoke test — should print the command tree
```

No `uv`? `pipx install codeframe-ai` works too, or run without installing via
`uvx codeframe-ai --help`. The PyPI package is `codeframe-ai`; it installs two
equivalent executables, `cf` and `codeframe`. This guide spells out `codeframe`;
`cf` is the short form used in the README and is interchangeable everywhere.

## Prerequisites

1. **Python 3.11+** with `uv` package manager
2. **LLM Provider API Key** — Anthropic is the default:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
   To use OpenAI-compatible providers (OpenAI, Ollama, vLLM, or any compatible endpoint):
   ```bash
   export CODEFRAME_LLM_PROVIDER=openai      # or: ollama, vllm, compatible
   export CODEFRAME_LLM_MODEL=gpt-4o         # model name for the chosen provider
   export OPENAI_API_KEY=sk-...              # required for openai; not needed for local providers
   export OPENAI_BASE_URL=http://localhost:11434/v1  # for local providers (ollama, vllm)
   ```
3. **`AUTH_SECRET` (required to run the server)** — the web UI / API
   (`codeframe serve`) signs JWTs with this secret. Authentication is **on by
   default**, so the server **refuses to start** with the built-in default
   secret — set a strong random value:
   ```bash
   export AUTH_SECRET=$(openssl rand -hex 32)
   ```
   The Golden Path CLI does not use auth and needs no secret. For a throwaway
   local server only, set `CODEFRAME_ALLOW_INSECURE_SECRET=1` to start without
   a secret — it signs JWTs with the known default (forgeable, never expose it)
   while keeping auth on so the REST API and the session/terminal WebSockets all
   work. (`CODEFRAME_AUTH_REQUIRED=false` is a separate knob that disables auth
   entirely for local dev — both the REST API and the session/terminal
   WebSockets then accept unauthenticated connections, so the sessions UI is
   fully usable in that mode.)
4. **`CODEFRAME_BOOTSTRAP_TOKEN` (only once the server is reachable over a
   network)** — creating the very first account uses an unauthenticated route,
   so on a fresh deploy whoever reaches it first claims the instance as admin.
   Locally you need nothing: requests from this machine are allowed as-is. The
   moment the server sits behind a proxy or a public address, set this and pass
   it as the `X-Bootstrap-Token` header (or use the field on the sign-up form):
   ```bash
   export CODEFRAME_BOOTSTRAP_TOKEN=$(openssl rand -hex 32)
   ```
   See `deploy/README.md` → "Creating the first account".

## Coming from ralph?

If your project already runs under [ralph-claude-code](https://github.com/frankbria/ralph-claude-code), one command turns it into a CodeFRAME project:

```bash
cd ~/projects/my-ralph-project
cf import ralph              # import in place (or: cf import ralph /path/to/project)
```

Preview the mapping first with `--dry-run`:

```bash
cf import ralph --dry-run    # human-readable report, no changes made
```

What maps where:

| ralph concept | CodeFRAME equivalent |
|---|---|
| `.ralph/fix_plan.md` checkboxes | Tasks (`cf tasks list`), file order preserved |
| Items under Optional/Future/Nice to Have headings | Tasks in `BACKLOG` (deferred) |
| Other unchecked items | Tasks in `READY` |
| Checked `- [x]` items | Skipped (already completed) |
| `.ralph/PROMPT.md` + `.ralph/specs/` | PRD (`cf prd show`), with source attribution |
| `.ralph/AGENT.md` build/test commands | `AGENTS.md` **Commands** section |
| `.ralphrc` `ALLOWED_TOOLS` | `AGENTS.md` **Always Do** section |
| `.ralphrc` `OPTIONAL_SECTIONS` | Which fix_plan headings import as `BACKLOG` |
| ralph state files (`status.json`, `.call_count`, ...) | Never read — reported as ignored |

Notes:

- **Optional sections**: headings matching `OPTIONAL_SECTIONS` from your `.ralphrc` (or the defaults: Optional, Future, Nice to Have, Backlog, Later, Someday) import as `BACKLOG` so they don't block execution — mirroring ralph's "doesn't block exit" semantics.
- **Idempotent**: re-running `cf import ralph` skips everything already imported; only new fix_plan items are added. If `PROMPT.md`/specs changed, the PRD gets a new version. An existing `AGENTS.md` is never overwritten.
- Use `--workspace <path>` to import into a different directory than the ralph project root.

After importing, continue with `cf work start` / `cf work batch run` as usual — see The Happy Path below (you can skip the PRD step; your tasks are already generated).

## The Happy Path

### Step 1: Initialize Your Workspace

Navigate to your project directory and initialize CodeFRAME with tech stack detection:

```bash
cd ~/projects/my-project
codeframe init . --detect
```

This scans your project files (pyproject.toml, package.json, Cargo.toml, go.mod) and describes your tech stack.

**Output:**
```
Workspace initialized
  Path: /home/user/projects/my-project
  ID: abc123...
  State: .codeframe/
  Tech Stack: Python with uv, pytest, ruff for linting
```

**Alternative: Explicit Tech Stack**
```bash
# Describe your stack directly
codeframe init . --tech-stack "Rust project using cargo"
codeframe init . --tech-stack "TypeScript monorepo with pnpm, Next.js, jest"

# Or use interactive mode
codeframe init . --tech-stack-interactive
```

**Why this matters:** The agent uses your tech stack description to choose appropriate commands and patterns. This works with any technology — Python, TypeScript, Rust, Go, Java, or mixed monorepos.

### Step 2: Add Your PRD

Create a markdown file describing what you want to build (e.g., `requirements.md`):

```markdown
# My Awesome App

Build a REST API for todo list management.

## Features
- Create, read, update, delete todos
- Filter by status (pending/completed)
- Priority levels (high, medium, low)

## Technical Requirements
- FastAPI backend
- SQLite database
- Include tests
```

Add it to CodeFRAME:

```bash
codeframe prd add requirements.md
```

### Step 3: Generate Tasks

Let the LLM break down your PRD into actionable tasks:

```bash
codeframe tasks generate
```

**Output:**
```
Generated 12 tasks
  1. Set up project structure
  2. Define data models
  3. Implement CRUD endpoints
  ...
```

### Step 4: Review and Approve Tasks

See what was generated:

```bash
codeframe tasks list
```

All tasks start in `BACKLOG`. Move them to `READY` when you're satisfied:

```bash
# One task -- copy the 8-char ID from `codeframe tasks list` (id before status)
codeframe tasks set status <task-id> READY

# Or every BACKLOG task at once
codeframe tasks set status READY --all --from BACKLOG
```

### Step 5: Execute Tasks

#### Option A: Run a Single Task (Start Here)

```bash
codeframe work start <task-id> --execute
```

One agent run, a few minutes. This is what the README quickstart does, and it is
the fastest way to see the whole loop.

#### Option B: Run All Ready Tasks

```bash
codeframe work batch run --all-ready --strategy auto
```

This will:
- Analyze task dependencies using LLM
- Execute tasks in parallel where possible
- Create blockers when human input is needed

A generated backlog is typically 20+ tasks and each one is a full agent run, so
this is **long-running**. Start it, then watch it from another terminal:
`codeframe work batch status` lists the batch IDs and
`codeframe work batch follow <batch-id>` streams one.

#### Option C: Run Specific Tasks

```bash
codeframe work batch run task-id-1 task-id-2 task-id-3
```

### Step 6: Monitor Progress

Option A is one synchronous run — it streams to your terminal and you just watch
it. For a batch (Options B and C), check on it from a second terminal:

```bash
codeframe work batch status            # all recent batches, with their IDs
codeframe work batch follow <batch-id> # live progress for one of them
codeframe status                       # workspace-wide summary
```

### Step 7: Handle Blockers

If agents get stuck, they'll create blockers:

```bash
# See open blockers
codeframe blocker list

# Answer a blocker
codeframe blocker answer <blocker-id> "Use JWT tokens for auth"

# Resume blocked work
codeframe work batch resume <batch-id>
```

### Step 8: Verify and Commit

Once complete, run verification:

```bash
codeframe review
```

Then run the PROOF9 quality gates:

```bash
codeframe proof run
```

> On a brand-new workspace this reports that **nothing was verified** and exits
> **2** — there is nothing to check yet, which is not the same as passing, so it
> is not reported as one (#1118). Exit codes: `0` obligations ran and none
> failed, `1` an obligation failed, `2` nothing was verified. Pass
> `--allow-empty` to exit 0 on an empty ledger where that is expected.
>
> Obligations accumulate as you capture glitches with `codeframe proof capture`;
> each one becomes a permanent check. See `codeframe proof status` for the ledger.

Create a checkpoint of your progress:

```bash
codeframe checkpoint create "MVP complete"
```

---

## Command Reference

### Workspace Commands
| Command | Description |
|---------|-------------|
| `codeframe init <path>` | Initialize workspace |
| `codeframe init <path> --detect` | Initialize + auto-detect tech stack |
| `codeframe init <path> --tech-stack "desc"` | Initialize + explicit tech stack |
| `codeframe init <path> -i` | Initialize + interactive tech stack |
| `codeframe status` | Show workspace overview |
| `codeframe summary` | Concise status report |

### Import Commands
| Command | Description |
|---------|-------------|
| `cf import ralph [path]` | Import a ralph-claude-code project |
| `cf import ralph --dry-run` | Preview the mapping report |
| `cf import ralph -w <path>` | Import into a different workspace |

### PRD Commands
| Command | Description |
|---------|-------------|
| `codeframe prd add <file>` | Add PRD document |
| `codeframe prd show` | Display current PRD |

### Task Commands
| Command | Description |
|---------|-------------|
| `codeframe tasks generate` | Generate tasks from PRD |
| `codeframe tasks list` | List all tasks |
| `codeframe tasks list --status READY` | Filter by status |
| `codeframe tasks set status <id> <STATUS>` | Update single task (id **before** status) |
| `codeframe tasks set status <STATUS> --all` | Update all tasks |
| `codeframe tasks set status <STATUS> --all --from BACKLOG` | Only tasks currently in BACKLOG |

### Work Commands
| Command | Description |
|---------|-------------|
| `codeframe work start <task-id>` | Start single task |
| `codeframe work start <task-id> --execute` | Execute with agent |
| `codeframe work stop <task-id>` | Stop task execution |
| `codeframe work resume <task-id>` | Resume blocked task |

### Batch Commands
| Command | Description |
|---------|-------------|
| `codeframe work batch run --all-ready` | Run all ready tasks |
| `codeframe work batch run --strategy parallel` | Run in parallel |
| `codeframe work batch run --strategy auto` | LLM dependency inference |
| `codeframe work batch run --max-parallel 4` | Limit concurrency |
| `codeframe work batch run --retry 2` | Auto-retry failures |
| `codeframe work batch run --dry-run` | Preview execution plan |
| `codeframe work batch status` | Show batch status |
| `codeframe work batch resume <batch-id>` | Re-run failed tasks |
| `codeframe work batch stop <batch-id>` | Stop a running batch |
| `codeframe work batch follow <batch-id>` | Stream live batch output |

### Blocker Commands
| Command | Description |
|---------|-------------|
| `codeframe blocker list` | List open blockers |
| `codeframe blocker show <id>` | Show blocker details |
| `codeframe blocker answer <id> "response"` | Answer blocker |

### Quality Commands
| Command | Description |
|---------|-------------|
| `codeframe review` | Run verification gates |
| `codeframe patch export` | Export changes as patch |
| `codeframe checkpoint create "name"` | Save state snapshot |
| `codeframe checkpoint list` | List checkpoints |

### PROOF9 Commands
| Command | Description |
|---------|-------------|
| `codeframe proof run` | Run all applicable proof obligations |
| `codeframe proof capture` | Capture a glitch as a permanent requirement |
| `codeframe proof list` | List proof requirements |
| `codeframe proof status` | Summary across all gates |
| `codeframe proof show <id>` | Requirement detail and evidence |
| `codeframe proof waive <id> --reason "..."` | Waive with justification |

### Configuration Commands
| Command | Description |
|---------|-------------|
| `cf config telemetry on` | Enable anonymous usage telemetry (opt-in) |
| `cf config telemetry off` | Disable telemetry |
| `cf config telemetry status` | Show current telemetry state and config path |

> On first interactive use, CodeFRAME shows a one-time prompt asking whether to enable telemetry (default: No). You can also set `CODEFRAME_TELEMETRY=on|off` or `DO_NOT_TRACK=1` to skip the prompt. See [PRIVACY.md](../PRIVACY.md) for exactly what is collected.

### Rate limiting in production

The API server (`cf serve`) rate-limits requests, including auth brute-force
protection. The storage backend is selected by `RATE_LIMIT_STORAGE` (default
`memory`).

> ⚠️ **Multi-worker deployments require Redis.** With the default in-memory
> storage, each worker process keeps its **own** rate-limit counters, so running
> with more than one worker (e.g. `uvicorn --workers 4`) multiplies the effective
> limit by the worker count and silently weakens auth brute-force protection. For
> any multi-worker deployment, set `RATE_LIMIT_STORAGE=redis` and `REDIS_URL` for
> shared, cross-worker buckets. The server logs a `WARNING` at startup when it
> detects in-memory storage with multiple workers (via the `WEB_CONCURRENCY` /
> `UVICORN_WORKERS` env vars).

---

## Execution Strategies

### Serial (Default)
```bash
codeframe work batch run --all-ready --strategy serial
```
Runs tasks one at a time in order. Safe but slow.

### Parallel
```bash
codeframe work batch run --all-ready --strategy parallel --max-parallel 4
```
Runs up to N tasks concurrently. Fast but may have conflicts.

### Auto (Recommended)
```bash
codeframe work batch run --all-ready --strategy auto
```
Uses LLM to infer task dependencies, then runs independent tasks in parallel while respecting dependencies. Best of both worlds.

---

## Tips & Tricks

### Preview Before Running
Always use `--dry-run` first:
```bash
codeframe work batch run --all-ready --strategy auto --dry-run
```

### Check Task Dependencies
The `auto` strategy will show inferred dependencies:
```
Inferred dependencies:
  Implement API endpoints <- Define data models
  Write tests <- Implement API endpoints
```

### Recover from Failures
If a batch fails, you can:
1. Check what happened: `codeframe work batch status <batch-id>`
2. Fix any issues manually
3. Resume: `codeframe work batch resume <batch-id>`

### Environment Setup
For Python projects, ensure you have a virtualenv or use `uv`:
```bash
uv venv
source .venv/bin/activate
```

---

## Common Issues

### "externally-managed-environment" Error
Your system Python is managed by the OS. Create a virtual environment first:
```bash
uv venv
source .venv/bin/activate
```

### Tasks Stuck in IN_PROGRESS
Known issue. Manually reset tasks if needed:
```bash
# Current workaround (via SQLite)
sqlite3 .codeframe/state.db "UPDATE tasks SET status='READY' WHERE status='IN_PROGRESS'"
```

### "Task execution failed" with no explanation

The most common cause is the agent exhausting its iteration budget rather than
hitting an actual error. The run log records it plainly even though the CLI does
not:

```bash
tail -20 .codeframe/runs/<run-id>/output.log   # look for "Iteration 45/45"
```

Check your working tree before re-running — a run that reports failure often
leaves substantial, usable work behind (`git status`). See
[#1117](https://github.com/frankbria/codeframe/issues/1117).

### No Blockers Despite Failures
The agent may classify errors as "technical" and try to self-correct. Check event logs for details:
```bash
codeframe events tail
```

---

## Getting Help

```bash
codeframe --help
codeframe <command> --help
codeframe work batch run --help
```

For issues: https://github.com/frankbria/codeframe/issues
