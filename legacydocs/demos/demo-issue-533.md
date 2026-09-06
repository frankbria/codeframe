# WorktreeRegistry — Orphan Cleanup & get_base_branch (Issue #533)

*2026-04-04T00:39:21Z*

Issue #533 adds three things to the worktree isolation system:

1. **get_base_branch()** — reads the actual current branch from git instead of hardcoding "main"
2. **WorktreeRegistry** — atomically tracks live worktrees (PID + task_id) so orphaned ones can be detected
3. **Auto-cleanup** — _execute_parallel() cleans stale worktrees at batch start; cf env doctor reports them

These complete the worktree isolation loop: create → register → execute → cleanup → unregister.

## Acceptance Criterion 1: get_base_branch()

Returns the current branch name from git. Falls back to "main" on failure or in detached HEAD state.

```bash
uv run python -c "
from codeframe.core.worktrees import get_base_branch
from pathlib import Path

# Returns real branch name in a git repo
branch = get_base_branch(Path(\".\"))
print(f\"Current branch: {branch!r}\")

# Returns main for non-git directory
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    fallback = get_base_branch(Path(tmp))
    print(f\"Non-git dir fallback: {fallback!r}\")

# Returns main for detached HEAD (simulated)
from unittest.mock import patch, MagicMock
mock = MagicMock(returncode=0, stdout=\"HEAD\n\")
with patch(\"subprocess.run\", return_value=mock):
    detached = get_base_branch(Path(\".\"))
    print(f\"Detached HEAD fallback: {detached!r}\")
"
```

```output
Current branch: 'feat/worktree-registry-533'
Non-git dir fallback: 'main'
Detached HEAD fallback: 'main'
```

## Acceptance Criterion 2: WorktreeRegistry — register / unregister / list_worktrees

Atomically writes PID + task_id + batch_id to .codeframe/worktrees.json using a threading.Lock and os.replace for crash safety.

```bash
uv run python -c "
import tempfile, os, json
from pathlib import Path
from codeframe.core.worktrees import WorktreeRegistry, list_worktrees

with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    reg = WorktreeRegistry()

    # Register two tasks
    reg.register(p, \"task-001\", \"batch-abc\")
    reg.register(p, \"task-002\", \"batch-abc\")

    entries = list_worktrees(p)
    print(f\"Registered {len(entries)} entries:\")
    for e in entries:
        print(f\"  task={e[chr(39)+task_id+chr(39)]!r}  batch={e[chr(39)+batch_id+chr(39)]!r}  pid={e[chr(39)+pid+chr(39)]}\")

    # Unregister one
    reg.unregister(p, \"task-001\")
    after = list_worktrees(p)
    print(f\"After unregister: {[e[chr(39)+task_id+chr(39)] for e in after]}\")

    # Idempotent — re-registering same task does not duplicate
    reg.register(p, \"task-002\", \"batch-abc\")
    dup = list_worktrees(p)
    print(f\"After re-register (idempotent): {len(dup)} entries (expected 1)\")
"
```

```output
Traceback (most recent call last):
  File "<string>", line 17, in <module>
    print(f"  task={e[chr(39)+task_id+chr(39)]!r}  batch={e[chr(39)+batch_id+chr(39)]!r}  pid={e[chr(39)+pid+chr(39)]}")
                              ^^^^^^^
NameError: name 'task_id' is not defined
Registered 2 entries:
```

```bash
uv run python /tmp/demo_registry.py
```

```output
Registered 2 entries:
  task='task-001'  batch='batch-abc'  pid=64664
  task='task-002'  batch='batch-abc'  pid=64664
After unregister: ['task-002']
After re-register (idempotent): 1 entries (expected 1)
```

## Acceptance Criterion 3: Stale detection — list_stale() and cleanup_stale()

A "stale" entry is one whose PID is no longer alive. Checked via os.kill(pid, 0). PermissionError (process alive, different owner) is correctly excluded.

```bash
uv run python /tmp/demo_stale.py
```

```output
Stale entries: ['dead-task']
  (live-task excluded — its pid 64794 is our own process)
After cleanup_stale: ['live-task']
```

## Acceptance Criterion 4: register() is wired into create_execution_context()

When IsolationLevel.WORKTREE is used, the ExecutionContext now registers the PID on creation and unregisters it in the cleanup callback — making the orphan detection actually functional.

```bash
grep -A 12 "if isolation == IsolationLevel.WORKTREE:" codeframe/core/sandbox/context.py
```

```output
    if isolation == IsolationLevel.WORKTREE:
        from codeframe.core.worktrees import TaskWorktree, WorktreeRegistry, get_base_branch

        worktree = TaskWorktree()
        registry = WorktreeRegistry()
        base_branch = get_base_branch(repo_path)
        worktree_path = worktree.create(repo_path, task_id, base_branch=base_branch)
        registry.register(repo_path, task_id, batch_id="unknown")

        def cleanup() -> None:
            worktree.cleanup(repo_path, task_id)
            registry.unregister(repo_path, task_id)

```

## Acceptance Criterion 5: Auto-cleanup in _execute_parallel()

cleanup_stale() is called at the start of every parallel batch run when isolation=worktree — clearing any orphaned worktrees from previously crashed workers before starting new ones.

```bash
grep -A 4 "Clean up orphaned worktrees" codeframe/core/conductor.py
```

```output
    # Clean up orphaned worktrees from crashed workers on previous runs
    from codeframe.core.sandbox.context import IsolationLevel as _IL
    if batch.isolation == _IL.WORKTREE.value:
        from codeframe.core.worktrees import WorktreeRegistry
        WorktreeRegistry().cleanup_stale(workspace.repo_path)
```

## Acceptance Criterion 6: cf env doctor reports stale worktrees

```bash
grep -A 14 "Stale worktree check" codeframe/cli/env_commands.py
```

```output
    # Stale worktree check
    try:
        from codeframe.core.worktrees import WorktreeRegistry
        stale = WorktreeRegistry().list_stale(project_path)
        if stale:
            console.print()
            console.print("[bold yellow]Stale Worktrees:[/bold yellow]")
            for entry in stale:
                console.print(
                    f"  [yellow]⚠[/yellow] task [cyan]{entry['task_id']}[/cyan] "
                    f"(pid {entry.get('pid', '?')} no longer running)"
                )
            console.print()
            console.print(
                "[dim]To clean up, run:[/dim] codeframe work batch run --all-ready "
```

## Acceptance Criterion 7: All 27 tests pass

```bash
uv run pytest tests/core/test_worktrees.py -q --tb=short 2>&1 | tail -5
```

```output
0.02s call     tests/core/test_worktrees.py::TestTaskWorktreeCreate::test_returns_correct_path
0.01s call     tests/core/test_worktrees.py::TestTaskWorktreeCleanup::test_cleanup_nonexistent_does_not_raise
0.01s call     tests/core/test_worktrees.py::TestGetBaseBranch::test_returns_current_branch
0.01s call     tests/core/test_worktrees.py::TestBatchRunIsolate::test_defaults_to_true
============================== 27 passed in 1.02s ==============================
```

All 27 tests pass. The worktree isolation loop is now complete: create → register (PID) → execute → cleanup → unregister. Stale orphans from crashed workers are detected by PID liveness check and cleaned up at next batch run or reported by cf env doctor.
