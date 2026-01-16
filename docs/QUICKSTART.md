# CodeFRAME CLI Quickstart Guide

Get your project built with AI agents in minutes.

## Prerequisites

1. **Python 3.11+** with `uv` package manager
2. **Anthropic API Key** set as environment variable:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

## The Happy Path

### Step 1: Initialize Your Workspace

Navigate to your project directory and initialize CodeFRAME:

```bash
cd ~/projects/my-project
codeframe init .
```

**Output:**
```
Workspace initialized
  Path: /home/user/projects/my-project
  ID: abc123...
  State: .codeframe/
```

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
| `codeframe status` | Show workspace overview |
| `codeframe summary` | Concise status report |

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
