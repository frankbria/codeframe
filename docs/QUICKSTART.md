# CodeFRAME CLI Quickstart Guide

Get your project built with AI agents in minutes.

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
# Move all BACKLOG tasks to READY
codeframe tasks set status READY --all --from BACKLOG
```

### Step 5: Execute Tasks

#### Option A: Run All Ready Tasks (Recommended)

```bash
codeframe work batch run --all-ready --strategy auto
```

This will:
- Analyze task dependencies using LLM
- Execute tasks in parallel where possible
- Create blockers when human input is needed

#### Option B: Run Specific Tasks

```bash
codeframe work batch run task-id-1 task-id-2 task-id-3
```

### Step 6: Monitor Progress

While the batch runs, you can check status in another terminal:

```bash
codeframe work batch status
codeframe status
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
| `codeframe tasks set status <STATUS> <id>` | Update single task |
| `codeframe tasks set status <STATUS> --all` | Update all tasks |

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
| `codeframe work batch cancel <batch-id>` | Cancel running batch |

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
