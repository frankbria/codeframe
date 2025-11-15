# Quickstart Guide: Sprint 9 MVP Completion Features

**Date**: 2025-11-15
**Sprint**: 009-mvp-completion
**Features**: Review Agent, Auto-Commit, Linting, Desktop Notifications, Composite Index

## Overview

This guide shows how to use the 5 new features added in Sprint 9. These features enhance code quality, version control continuity, and developer experience for autonomous coding workflows.

---

## 1. Review Agent

### What It Does

Automatically reviews code for quality issues (complexity, security, style) before marking tasks complete.

### Quick Start

**Automatic Integration** (no action needed):
```bash
# Review Agent runs automatically after testing (Step 11 in workflow)
cf run project-123

# If review finds issues, you'll get a SYNC blocker with findings
```

**Manual Review Trigger**:
```bash
# Trigger review for specific task
curl -X POST http://localhost:8000/api/agents/review-001/review \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 456,
    "project_id": 123,
    "files_modified": ["codeframe/agents/backend_worker_agent.py"]
  }'
```

### Check Review Status

```bash
# Get review results for task
curl http://localhost:8000/api/tasks/456/review-status?project_id=123
```

**Response** (approved):
```json
{
  "status": "reviewed",
  "overall_score": 87.5,
  "findings_count": 3,
  "status": "approved"
}
```

**Response** (changes requested):
```json
{
  "status": "reviewed",
  "overall_score": 62.0,
  "findings_count": 12,
  "critical_count": 2,
  "status": "changes_requested"
}
```

### Understanding Review Scores

- **90-100**: Excellent (auto-approve)
- **70-89**: Good (approve with suggestions)
- **50-69**: Needs Improvement (request changes, create blocker)
- **0-49**: Poor (block merge)

**Score Breakdown**:
- Complexity: 30% (cyclomatic complexity, function length)
- Security: 40% (SQL injection, XSS, secrets)
- Style: 20% (code duplication, naming)
- Coverage: 10% (test coverage assessment)

### Configure Review Thresholds

Edit `pyproject.toml`:
```toml
[tool.codeframe.review]
approve_threshold = 70.0  # Auto-approve if score >= 70
reject_threshold = 50.0   # Auto-reject if score < 50

max_complexity = 10       # Flag functions with CC > 10
max_function_length = 50  # Flag functions > 50 lines

block_on_critical = true  # Block if critical security finding
max_review_iterations = 2 # Max re-review attempts
```

### Responding to Review Feedback

When review creates blocker:

1. **View findings in dashboard**: Navigate to blocker panel
2. **Read blocker message**: Contains categorized findings with line numbers
3. **Fix issues**: Address critical/high severity first
4. **Re-submit**: Agent will automatically re-review after fixes
5. **Iteration limit**: Max 2 re-reviews, then escalates to human

**Example Blocker Message**:
```markdown
## Code Review: Changes Requested

**Overall Score**: 62.0/100

**Findings**: 12 issues (2 critical, 5 high)

### CRITICAL Issues

🔴 **CRITICAL** [security] codeframe/auth/login.py:42
   Hardcoded password detected: 'admin123'
   💡 Suggestion: Use environment variable or secrets manager

🔴 **CRITICAL** [security] codeframe/api/users.py:85
   Potential SQL injection vulnerability
   💡 Suggestion: Use parameterized queries

### HIGH Issues

🟠 **HIGH** [complexity] codeframe/agents/worker_agent.py:120
   Cyclomatic complexity 15 (threshold: 10)
   💡 Suggestion: Extract logic into smaller functions
```

---

## 2. Auto-Commit Integration

### What It Does

Automatically creates git commits after each task completion, linking commits to tasks for traceability.

### Quick Start

**No Configuration Needed** (works automatically):
```bash
# Run project - commits created automatically after task completion
cf run project-123

# Check git log to see auto-commits
git log --oneline

# Example output:
# abc1234 feat(cf-1.5.3): Implement user authentication
# def5678 test(cf-1.5.4): Add authentication unit tests
# ghi9012 fix(cf-1.5.5): Fix login error handling
```

### Commit Message Format

```
<type>(<scope>): <subject>

<description>

Modified files:
- path/to/file1.py
- path/to/file2.tsx
```

**Type** (auto-detected from task):
- `feat`: New feature implementation
- `fix`: Bug fix
- `test`: Test additions/modifications
- `refactor`: Code restructuring
- `docs`: Documentation changes
- `chore`: Config, setup, maintenance

**Scope**: Task number (e.g., `cf-1.5.3`)

**Subject**: Task title

### Find Task by Commit

```bash
# Find task that created a commit
curl http://localhost:8000/api/tasks/by-commit?sha=abc1234

# Response:
{
  "id": 456,
  "task_number": "1.5.3",
  "title": "Implement user authentication",
  "commit_sha": "abc1234567890...",
  "completed_at": "2025-11-15T14:30:00Z"
}
```

### Git Bisect for Debugging

```bash
# Find commit that introduced regression
git bisect start
git bisect bad HEAD
git bisect good v1.0.0

# Git will check out commits, you test each:
pytest tests/test_auth.py

# Mark commit as good or bad
git bisect good  # or bad

# Git bisects to find regression

# Once found, look up task:
curl http://localhost:8000/api/tasks/by-commit?sha=$(git rev-parse HEAD)
```

### Error Handling

**Dirty Working Tree**:
- Auto-commit skips if uncommitted changes exist
- Logs warning: "Cannot commit: working tree dirty"
- Task still marked complete (commit failure doesn't block)
- Creates ASYNC blocker if persistent issue

**Commit Failures**:
- Graceful degradation (task completion not blocked)
- Logged for debugging
- Webhook notification sent (if configured)

### Disable Auto-Commit (if needed)

Edit project config:
```json
{
  "git": {
    "auto_commit": false  // Disable auto-commit
  }
}
```

---

## 3. Linting Integration

### What It Does

Runs linting (ruff for Python, eslint for TypeScript) as quality gate before task completion. Blocks tasks with critical errors.

### Quick Start

**Automatic Integration** (no action needed):
```bash
# Linting runs automatically before task completion
cf run project-123

# If lint errors found, task blocked with blocker
```

### Manual Lint Execution

```bash
# Lint entire project
curl -X POST http://localhost:8000/api/lint/run \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 123,
    "task_id": 456
  }'

# Response:
{
  "status": "success",
  "results": [
    {
      "linter": "ruff",
      "error_count": 3,
      "warning_count": 12,
      "files_linted": 45
    }
  ],
  "summary": {
    "total_errors": 3,
    "total_warnings": 12,
    "blocking_errors": true
  }
}
```

### View Lint Results

```bash
# Get lint results for task
curl http://localhost:8000/api/lint/results?task_id=456

# Get trend over time
curl http://localhost:8000/api/lint/trend?project_id=123&days=7
```

### Configure Linting Rules

**Python (ruff)** - Edit `pyproject.toml`:
```toml
[tool.ruff]
select = ["F", "E", "W", "I", "N"]  # Rule sets to enable
ignore = ["E501", "N802"]           # Rules to ignore
line-length = 100
target-version = "py311"

[tool.ruff.per-file-ignores]
"tests/*" = ["D103", "D104"]  # Allow missing docstrings in tests
"__init__.py" = ["F401"]      # Allow unused imports

[tool.codeframe.lint]
block_on_critical = true  # Block task if critical errors
block_on_error = false    # Allow non-critical errors
max_warnings = null       # No limit on warnings
```

**TypeScript (eslint)** - Edit `.eslintrc.json`:
```json
{
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react/recommended"
  ],
  "rules": {
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/explicit-function-return-type": "off",
    "react/react-in-jsx-scope": "off"
  }
}
```

### Severity Levels

**CRITICAL** (blocks task):
- Python: F-series (Pyflakes errors like undefined names)
- TypeScript: ESLint errors

**ERROR** (warns, configurable blocking):
- Python: E-series (PEP 8 violations)
- TypeScript: TypeScript errors

**WARNING** (logs only):
- Python: W-series, I-series (style issues)
- TypeScript: ESLint warnings

### Responding to Lint Errors

When linting blocks task:

1. **View lint output in blocker**: Shows all errors with line numbers
2. **Fix errors**: Address critical errors first
3. **Re-run linting**: Agent automatically re-lints after fixes
4. **Task proceeds**: Once errors cleared, task completes

**Example Blocker Message**:
```markdown
## Linting Failed: 3 errors

**Linter**: ruff
**Files**: 45 files linted

### Errors

codeframe/agents/backend_worker_agent.py:42:10 [F401]
   'json' imported but unused

codeframe/api/users.py:85:5 [E501]
   line too long (105 > 100 characters)

tests/test_auth.py:120:1 [F821]
   undefined name 'response'
```

### View Lint Trends (Dashboard)

Navigate to project dashboard → Lint Quality tab:
- **Line chart**: Errors/warnings over time (7 days)
- **Table**: Recent lint results per task
- **Trend indicator**: "Improving", "Degrading", or "Stable"

---

## 4. Desktop Notifications

### What It Does

Sends native desktop notifications when SYNC blockers are created, improving local development UX.

### Quick Start

**Automatic Notifications** (enabled by default):
```bash
# Run project - notifications appear for SYNC blockers
cf run project-123

# When agent blocked, desktop notification appears:
# Title: "CodeFRAME: Agent Blocked"
# Message: "Authentication method unclear: Use JWT or session cookies?"
```

### Platform Support

**macOS**: Notification Center
- Appears in top-right corner
- Sound: "Glass" (default system sound)
- Click to open dashboard

**Linux**: libnotify (notify-send)
- GNOME: Top-right corner
- KDE: System tray
- Urgency: Critical (red, persistent)

**Windows**: Toast Notifications
- Bottom-right corner
- Duration: 10 seconds
- Sound: Default system notification sound

### Configure Notifications

Edit project `config.json`:
```json
{
  "notifications": {
    "desktop": {
      "enabled": true,
      "sound": true,
      "urgency": "critical",  // low, normal, critical (Linux only)
      "duration": 10,         // seconds (Windows)
      "sync_only": true       // Only notify for SYNC blockers
    },
    "webhook": {
      "enabled": false,
      "url": null
    }
  }
}
```

**Environment Variables**:
```bash
# Disable desktop notifications globally
export CODEFRAME_DESKTOP_NOTIFICATIONS=false

# Change urgency level
export CODEFRAME_NOTIFICATION_URGENCY=normal

# Disable sound
export CODEFRAME_NOTIFICATION_SOUND=false
```

### Installation (Platform-Specific)

**macOS**:
```bash
pip install pync
```

**Linux**:
```bash
sudo apt-get install libnotify-bin  # Ubuntu/Debian
sudo dnf install libnotify          # Fedora/RHEL

# Optional: D-Bus fallback
pip install dbus-python
```

**Windows**:
```bash
pip install win10toast
```

**Cross-Platform** (fallback):
```bash
pip install plyer
```

### Testing Notifications

```bash
# Test notification manually (Python)
python -c "
from codeframe.notifications.desktop import DesktopNotificationService

service = DesktopNotificationService()
if service.is_available():
    service.send_notification(
        title='CodeFRAME Test',
        message='Desktop notifications working!'
    )
    print('✓ Notification sent')
else:
    print('✗ Notifications not available on this platform')
"
```

### Troubleshooting

**Notifications not appearing (macOS)**:
- Check System Preferences → Notifications → Allow notifications
- Grant permission when prompted

**Notifications not appearing (Linux)**:
- Ensure notification daemon running: `ps aux | grep notification`
- Test manually: `notify-send "Test" "Message"`

**Notifications not appearing (Windows)**:
- Check Windows Settings → Notifications & actions → Allow notifications
- Ensure Focus Assist is off

**Fallback to Webhook**:
If desktop notifications unavailable, system falls back to webhook (if configured).

---

## 5. Composite Index Performance Fix

### What It Does

Optimizes context query performance with composite index on `(project_id, agent_id, current_tier)`.

### Quick Start

**Automatic Application**:
```bash
# Index created automatically when database initialized
cf init project-123

# Or apply migration manually:
cf migrate up
```

### Verify Index Exists

```bash
# Check database schema
sqlite3 .codeframe/state.db ".schema context_items"

# Should see:
# CREATE INDEX idx_context_project_agent
# ON context_items(project_id, agent_id, current_tier);
```

### Verify Index Usage

```sql
-- Check query plan
EXPLAIN QUERY PLAN
SELECT * FROM context_items
WHERE project_id = 123 AND agent_id = 'backend-001' AND current_tier = 'hot'
ORDER BY last_accessed DESC;

-- Should show:
-- SEARCH TABLE context_items USING INDEX idx_context_project_agent
```

### Performance Improvement

**Before Index**:
- Query time: ~50-100ms (1000 context items)
- Execution: Full table scan with agent_id filter

**After Index**:
- Query time: ~5-10ms (1000 context items)
- Execution: Index seek
- **Improvement**: 50-90% faster

### Benchmark Performance

```bash
# Run performance benchmark
python -c "
from codeframe.persistence.database import Database
from pathlib import Path
import time

db = Database('.codeframe/state.db')
db.initialize()

# Measure query time (with index)
start = time.time()
for _ in range(100):
    items = db.get_context_items(
        project_id=123,
        agent_id='backend-001',
        tier='hot'
    )
elapsed = (time.time() - start) * 1000 / 100
print(f'Average query time: {elapsed:.2f}ms')
"
```

### No Action Needed

This optimization is transparent - no configuration or code changes required. Queries automatically benefit from improved performance.

---

## Common Workflows

### Workflow 1: Complete Task with All Features

```bash
# Start project
cf run project-123

# Agent executes task (e.g., "Implement user authentication")

# Automatic workflow (no intervention):
1. Agent writes code
2. Agent runs tests (Step 9)
3. Agent runs linting (Step 10) ← NEW
   - If errors: Creates blocker, stops
   - If warnings: Logs, continues
4. Agent commits changes (auto-commit) ← NEW
5. Review Agent runs (Step 11) ← NEW
   - Analyzes complexity, security, style
   - If issues: Creates blocker with findings
   - If approved: Continues
6. Task marked complete

# You receive:
- Desktop notification (if blocker created) ← NEW
- Git commit with conventional message ← NEW
- Review report (stored in blocker details) ← NEW
- Lint results (stored for trending) ← NEW
```

### Workflow 2: Fix Review Findings

```bash
# Review Agent creates blocker:
# "Code Review: Changes Requested - Overall Score: 62.0/100"

# View findings in dashboard → Blocker Panel
# Click blocker to see detailed findings

# Agent automatically:
1. Reads blocker message with findings
2. Fixes issues (complexity, security, style)
3. Marks blocker resolved
4. Re-runs review (iteration 1 of max 2)

# If review passes:
- Task proceeds to completion
- Auto-commit created

# If review fails again:
- Iteration 2 (final attempt)
- If still fails: Escalates to human (SYNC blocker)
```

### Workflow 3: Investigate Regression

```bash
# Tests failing for "user authentication" feature
pytest tests/test_auth.py  # FAILED

# Find commit that broke tests
git bisect start
git bisect bad HEAD
git bisect good v1.0.0

# Git identifies commit: abc1234

# Find task that created commit
curl http://localhost:8000/api/tasks/by-commit?sha=abc1234

# Response shows task 1.5.3 "Implement password hashing"
# Review code changes in that task
# Fix regression, create new task for fix
```

---

## Dashboard Features

### New Panels (Sprint 9)

**Review Status Panel**:
- Shows review status for all tasks
- Overall score trend (improving/degrading)
- Top findings by category

**Lint Quality Chart**:
- Error/warning trend (7 days)
- Per-linter breakdown (ruff, eslint)
- Files linted over time

**Commit History**:
- Recent auto-commits
- Linked to tasks
- Conventional commit badges (feat, fix, test)

### New Badges

**Task Status**:
- 🔍 "In Review" (Review Agent analyzing)
- ✅ "Reviewed" (Review passed)
- ❌ "Changes Requested" (Review failed)
- 🔧 "Linting" (Lint in progress)

---

## Troubleshooting

### Review Agent Not Running

**Symptom**: Tasks completing without review

**Check**:
```bash
# Verify Review Agent registered
curl http://localhost:8000/api/agents

# Should see agent with type: "review"
```

**Fix**:
```bash
# Restart server to re-register agents
cf restart
```

### Auto-Commit Failing

**Symptom**: Tasks complete but no commits in git log

**Check**:
```bash
# Check git status
git status  # Should be clean after task completion

# Check auto-commit enabled
cf config get git.auto_commit  # Should be true
```

**Fix**:
```bash
# Enable auto-commit
cf config set git.auto_commit true

# Verify git initialized
git rev-parse --git-dir  # Should show .git
```

### Linting Always Blocking

**Symptom**: All tasks blocked by lint errors

**Check**:
```bash
# Check lint configuration
cat pyproject.toml | grep -A 10 "\[tool.ruff\]"

# Run linting manually
ruff check codeframe/
```

**Fix**:
```bash
# Fix lint errors
ruff check codeframe/ --fix

# Or adjust thresholds
# Edit pyproject.toml → [tool.codeframe.lint]
block_on_critical = true
block_on_error = false  # Don't block on style issues
```

### Desktop Notifications Not Appearing

**Symptom**: No notifications for SYNC blockers

**Check**:
```bash
# Verify notifications enabled
cf config get notifications.desktop.enabled  # Should be true

# Test manually
python -c "from codeframe.notifications.desktop import DesktopNotificationService; DesktopNotificationService().send_notification('Test', 'Message')"
```

**Fix**:
```bash
# Install platform-specific library
# macOS:
pip install pync

# Linux:
sudo apt-get install libnotify-bin

# Windows:
pip install win10toast
```

---

## Next Steps

1. **Read Feature Specs**: See `specs/009-mvp-completion/` for detailed documentation
2. **Run Tests**: `pytest tests/` to verify all features working
3. **Customize Configs**: Adjust review/lint thresholds for your project
4. **Monitor Dashboard**: Watch lint trends and review metrics

For issues or questions, see:
- [Review Agent Docs](contracts/review-api.md)
- [Linting Docs](contracts/lint-api.md)
- [Notification Docs](contracts/notification-service.md)
