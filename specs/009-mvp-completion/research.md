# Research: Sprint 9 MVP Completion

**Date**: 2025-11-15
**Branch**: 009-mvp-completion
**Spec**: /home/frankbria/projects/codeframe/specs/009-mvp-completion/spec.md

## Overview

This document consolidates research findings for Sprint 9 MVP Completion. The sprint adds 5 critical features identified in the architectural spec audit: Review Agent, Auto-Commit Integration, Linting Integration, Desktop Notifications, and Composite Index Fix.

---

## 1. Code Quality Tools Selection

### Decision: Radon + Bandit + OWASP Patterns

#### Radon (Complexity Analysis)
- **Purpose**: Cyclomatic complexity, Halstead metrics, maintainability index
- **Integration**: Python library, can be invoked programmatically
- **Metrics**:
  - Cyclomatic complexity (CC): 1-5 (simple), 6-10 (moderate), 11+ (complex)
  - Maintainability Index (MI): 0-100 (higher is better)
  - Halstead metrics: Program volume, difficulty, effort
- **Installation**: `pip install radon`
- **Usage**: `radon cc codeframe/ -a -nb` (average complexity, no badges)

**Example API usage**:
```python
from radon.complexity import cc_visit
from radon.metrics import mi_visit

code = """
def example_function():
    if condition:
        return True
    return False
"""

complexity = cc_visit(code)  # Returns ComplexityVisitor
mi = mi_visit(code, multi=True)  # Maintainability index
```

#### Bandit (Security Scanning)
- **Purpose**: Security vulnerability detection for Python
- **Coverage**: SQL injection, XSS, hardcoded secrets, insecure functions
- **Severity Levels**: HIGH, MEDIUM, LOW
- **Installation**: `pip install bandit`
- **Usage**: `bandit -r codeframe/ -f json -o bandit_report.json`

**Example API usage**:
```python
import bandit
from bandit.core import manager

# Create manager and run scan
mgr = manager.BanditManager(config, agg_type='file')
mgr.discover_files(['codeframe/'])
mgr.run_tests()

# Get results
results = mgr.results
for issue in results:
    print(f"{issue.severity}: {issue.text}")
```

**OWASP Top 10 Patterns** (Custom Rules):
- A01:2021 - Broken Access Control: Check for missing auth decorators
- A02:2021 - Cryptographic Failures: Bandit covers this (B105, B106, B107)
- A03:2021 - Injection: SQL injection (B608), Command injection (B602, B603)
- A07:2021 - Identification and Authentication Failures: Hardcoded passwords (B105, B106)
- A09:2021 - Security Logging and Monitoring Failures: Custom check for logging

#### Code Duplication Detection
- **Tool**: pylint with `duplicate-code` check or custom implementation
- **Alternative**: `radon raw` provides lines of code metrics
- **Threshold**: Flag functions > 50 lines, classes > 300 lines

### TypeScript/JavaScript Quality Tools

For frontend review (future enhancement):
- **ESLint**: Already integrated for linting
- **TypeScript Compiler**: Type checking via `tsc --noEmit`
- **Complexity**: eslint-plugin-complexity
- **Security**: eslint-plugin-security

---

## 2. Desktop Notification Libraries

### Decision: Platform-Specific Native Libraries

#### macOS: `pync` (Python Notification Center)
- **Installation**: `pip install pync`
- **Requirements**: macOS 10.8+
- **Features**: Title, message, sound, click action
- **API**:
```python
import pync

pync.notify(
    'Agent blocked: Authentication method unclear',
    title='CodeFRAME',
    sound='default',
    open='http://localhost:3000/projects/123'
)
```

**Fallback for macOS**: `osascript` (AppleScript via subprocess)
```python
import subprocess

script = f'''
display notification "Agent blocked"
with title "CodeFRAME"
sound name "Glass"
'''
subprocess.run(['osascript', '-e', script])
```

#### Linux: `notify-send` (libnotify)
- **Installation**: Pre-installed on most Linux desktops (GNOME, KDE, XFCE)
- **Requirements**: D-Bus, notification daemon
- **Features**: Title, message, urgency level, icon
- **API**:
```python
import subprocess

subprocess.run([
    'notify-send',
    '--urgency=critical',
    '--icon=dialog-warning',
    'CodeFRAME',
    'Agent blocked: Authentication method unclear'
])
```

**Fallback for Linux**: Python `dbus` library (more reliable)
```python
import dbus

bus = dbus.SessionBus()
notify = bus.get_object('org.freedesktop.Notifications', '/org/freedesktop/Notifications')
interface = dbus.Interface(notify, 'org.freedesktop.Notifications')
interface.Notify('CodeFRAME', 0, '', 'Agent Blocked', 'Authentication method unclear', [], {}, 5000)
```

#### Windows: `win10toast`
- **Installation**: `pip install win10toast`
- **Requirements**: Windows 10+
- **Features**: Title, message, duration, icon
- **API**:
```python
from win10toast import ToastNotifier

toaster = ToastNotifier()
toaster.show_toast(
    'CodeFRAME',
    'Agent blocked: Authentication method unclear',
    duration=10,
    threaded=True
)
```

**Fallback for Windows**: `plyer` (cross-platform abstraction)
```python
from plyer import notification

notification.notify(
    title='CodeFRAME',
    message='Agent blocked',
    app_name='CodeFRAME',
    timeout=10
)
```

### Cross-Platform Strategy

**Primary approach**: Platform detection → native library
```python
import platform

def send_desktop_notification(title: str, message: str):
    system = platform.system()

    if system == 'Darwin':  # macOS
        try:
            import pync
            pync.notify(message, title=title, sound='default')
        except ImportError:
            # Fallback to osascript
            subprocess.run(['osascript', '-e', f'display notification "{message}" with title "{title}"'])

    elif system == 'Linux':
        subprocess.run(['notify-send', '--urgency=critical', title, message])

    elif system == 'Windows':
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=10, threaded=True)
```

**Dependency management**: Optional dependencies in setup.py
```python
extras_require={
    'notifications': [
        'pync; sys_platform == "darwin"',
        'win10toast; sys_platform == "win32"'
    ]
}
```

---

## 3. Review Agent Architecture

### Decision: Standalone ReviewWorkerAgent (extends WorkerAgent)

**Rationale**:
- Consistent with existing Backend/Frontend/Test worker agent pattern
- Enables parallel execution with other agents
- Integrates cleanly with AgentPoolManager and LeadAgent workflow
- Can be assigned tasks independently
- Maintains agent lifecycle (idle → working → blocked → offline)

### Architecture Options Considered

#### Option 1: ReviewWorkerAgent (Standalone) ✅ SELECTED
**Pros**:
- Clean separation of concerns
- Reuses WorkerAgent base class infrastructure
- Integrates with existing agent pool management
- Can run in parallel with other agents
- Natural fit for LeadAgent workflow step 11

**Cons**:
- Slightly more code duplication
- Requires database registration as agent type

**Structure**:
```
codeframe/agents/
├── worker_agent.py              # Base class
├── backend_worker_agent.py
├── frontend_worker_agent.py
├── test_worker_agent.py
└── review_worker_agent.py       # NEW
```

#### Option 2: Subagent (not recommended)
**Pros**:
- Less overhead
- Simpler integration

**Cons**:
- Not implemented in Sprint 9 scope (future enhancement)
- Breaks consistency with existing agent patterns
- Would require subagent infrastructure first

### Review Agent Responsibilities

1. **Code Quality Analysis**
   - Cyclomatic complexity (radon)
   - Function/method length
   - Nesting depth
   - Code duplication
   - Maintainability index

2. **Security Scanning**
   - Bandit vulnerability detection
   - OWASP Top 10 pattern matching
   - Hardcoded secrets
   - SQL injection patterns
   - XSS vulnerabilities

3. **LLM-Powered Review** (optional enhancement)
   - Architectural pattern validation
   - Code style consistency
   - Logic error detection
   - Test coverage assessment

4. **Report Generation**
   - Structured review report (JSON)
   - Severity scoring (0-100)
   - Actionable recommendations
   - Approve/Request Changes decision

### Review Workflow Integration

```
LeadAgent.execute_workflow() → Step 11: Code Review
    ↓
Task assigned to ReviewWorkerAgent
    ↓
ReviewWorkerAgent.execute_task()
    ├─ Run radon (complexity)
    ├─ Run bandit (security)
    ├─ Check OWASP patterns
    ├─ Generate review report
    └─ Decision: Approve OR Request Changes
        ↓
        If Request Changes:
            ├─ Create SYNC blocker with findings
            ├─ Assign to original agent for fixes
            └─ Re-review after fixes (max 2 iterations)
        ↓
        If Approve:
            └─ Mark task as reviewed, proceed to completion
```

### Review Scoring Algorithm

**Overall Score** (0-100):
- Complexity: 30% weight
- Security: 40% weight
- Style/Duplication: 20% weight
- Test Coverage: 10% weight

**Thresholds**:
- 90-100: Excellent (auto-approve)
- 70-89: Good (approve with minor suggestions)
- 50-69: Needs Improvement (request changes)
- 0-49: Poor (block merge)

---

## 4. Lint Configuration Defaults

### Ruff (Python)

**Selected Rule Sets**:
- **F** (Pyflakes): Basic errors (undefined names, unused imports)
- **E** (pycodestyle errors): PEP 8 violations
- **W** (pycodestyle warnings): Style warnings
- **I** (isort): Import sorting
- **N** (pep8-naming): Naming conventions
- **D** (pydocstyle): Docstring conventions (optional, may be too strict)

**Configuration** (pyproject.toml):
```toml
[tool.ruff]
select = ["F", "E", "W", "I", "N"]
ignore = [
    "E501",  # Line too long (let formatter handle)
    "N802",  # Function name should be lowercase (allow setUp/tearDown)
]
line-length = 100
target-version = "py311"

[tool.ruff.per-file-ignores]
"tests/*" = ["D103", "D104"]  # Allow missing docstrings in tests
"__init__.py" = ["F401"]  # Allow unused imports in __init__
```

**Severity Classification**:
- **CRITICAL** (block task): F (undefined names, syntax errors)
- **ERROR** (warn, consider blocking): E (PEP 8 violations)
- **WARNING** (log only): W, I, N (style issues)

### ESLint (TypeScript/JavaScript)

**Selected Rule Sets**:
- `@typescript-eslint/recommended`: Core TypeScript rules
- `eslint:recommended`: Core JavaScript rules
- `plugin:react/recommended`: React-specific rules (if React detected)
- `plugin:react-hooks/recommended`: React Hooks rules

**Configuration** (.eslintrc.json):
```json
{
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended"
  ],
  "parser": "@typescript-eslint/parser",
  "parserOptions": {
    "ecmaVersion": 2022,
    "sourceType": "module"
  },
  "rules": {
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/explicit-function-return-type": "off",
    "react/react-in-jsx-scope": "off"  // Not needed in React 17+
  }
}
```

**Severity Classification**:
- **CRITICAL**: Errors from eslint:recommended, type errors
- **WARNING**: Style issues, @typescript-eslint warnings

### Lint Execution Strategy

**Integration Point**: `AdaptiveTestRunner` or new `LintRunner` class

**Recommendation**: Create `LintRunner` class for separation of concerns
```python
class LintRunner:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.language_detector = LanguageDetector(project_path)

    async def run_lint(self) -> LintResult:
        """Run linting for detected language."""
        language_info = self.language_detector.detect()

        if language_info.language == 'python':
            return await self._run_ruff()
        elif language_info.language in ['typescript', 'javascript']:
            return await self._run_eslint()
        else:
            return LintResult(status='unsupported')
```

---

## 5. Performance Targets: Composite Index

### Current Problem

**Query Pattern** (from context_manager.py):
```sql
SELECT * FROM context_items
WHERE project_id = ? AND agent_id = ? AND current_tier = 'hot'
ORDER BY last_accessed DESC
```

**Existing Indexes**:
- `idx_context_agent_tier` on `(agent_id, current_tier)` - agent_id first
- `idx_context_importance` on `importance_score DESC` - no filtering
- `idx_context_last_accessed` on `last_accessed DESC` - no filtering

**Issue**: None of these indexes start with `project_id`, forcing SQLite to:
1. Scan all rows matching `agent_id`
2. Filter by `project_id` (sequential scan)
3. Filter by `current_tier`

### Proposed Solution

**New Index**:
```sql
CREATE INDEX idx_context_project_agent
ON context_items(project_id, agent_id, current_tier);
```

**Why This Works**:
- **Column order matches query filters**: project_id → agent_id → current_tier
- **Covers most common query**: "Get HOT context for agent X on project Y"
- **Enables index-only scans**: All filter columns in index
- **Reduces query complexity**: O(n) → O(log n) lookup

### Performance Benchmarks

**Measurement Approach**:
1. Create test database with 1000+ context items (10 agents × 100 items each)
2. Run query 100 times BEFORE index creation
3. Create index
4. Run query 100 times AFTER index creation
5. Compare average query time

**Expected Results**:
- **Before**: ~50-100ms per query (depends on total rows)
- **After**: ~5-10ms per query
- **Improvement**: 50-90% reduction in query time

**Validation with EXPLAIN QUERY PLAN**:
```sql
EXPLAIN QUERY PLAN
SELECT * FROM context_items
WHERE project_id = 123 AND agent_id = 'backend-001' AND current_tier = 'hot'
ORDER BY last_accessed DESC;
```

**Before Index**:
```
SCAN TABLE context_items USING INDEX idx_context_agent_tier (agent_id=?)
```

**After Index**:
```
SEARCH TABLE context_items USING INDEX idx_context_project_agent (project_id=? AND agent_id=? AND current_tier=?)
```

### Index Size Impact

**Estimated Size**:
- 3 columns (INTEGER, TEXT, TEXT) × 1000 rows ≈ 30KB
- Negligible compared to benefits

**Index Maintenance**:
- Automatic by SQLite on INSERT/UPDATE/DELETE
- No performance degradation expected

---

## 6. Technology Stack Summary

### Backend (Python)

**New Dependencies**:
- `radon==6.0.1` - Complexity analysis
- `bandit==1.7.5` - Security scanning
- `pync==2.0.3` - macOS notifications (optional)
- `win10toast==0.9` - Windows notifications (optional)

**Existing Dependencies** (already in use):
- `anthropic` - LLM provider (Review Agent)
- `ruff` - Python linter (already configured)
- `pytest` - Testing framework
- `aiosqlite` - Async SQLite

### Frontend (TypeScript)

**New Dependencies**: None (ESLint already installed)

**Existing Dependencies**:
- `eslint` - TypeScript/JavaScript linter
- `@typescript-eslint/parser` - TypeScript support
- `@typescript-eslint/eslint-plugin` - TypeScript rules

### Platform Support

**Operating Systems**:
- Linux (Ubuntu 20.04+, Debian 11+)
- macOS (10.14+)
- Windows (10+, 11)

**Desktop Environments** (Linux):
- GNOME
- KDE Plasma
- XFCE
- Any environment with D-Bus + notification daemon

---

## 7. Testing Strategy

### Unit Tests Breakdown

**Review Agent** (25 tests):
- Complexity analysis (radon integration): 8 tests
- Security scanning (bandit integration): 8 tests
- Review workflow (approve/reject): 5 tests
- Blocker creation on failure: 2 tests
- Report generation: 2 tests

**Auto-Commit** (15 tests):
- Commit integration in BackendWorkerAgent: 3 tests
- Commit integration in FrontendWorkerAgent: 3 tests
- Commit integration in TestWorkerAgent: 3 tests
- Commit message formatting: 2 tests
- Error handling (dirty working tree): 2 tests
- Database SHA recording: 2 tests

**Linting** (20 tests):
- Ruff execution and parsing: 6 tests
- ESLint execution and parsing: 6 tests
- Quality gate blocking: 4 tests
- Lint results persistence: 2 tests
- Configuration loading: 2 tests

**Desktop Notifications** (10 tests):
- Platform detection: 3 tests
- macOS notification delivery: 2 tests
- Linux notification delivery: 2 tests
- Windows notification delivery: 2 tests
- Fallback logic: 1 test

**Composite Index** (5 tests):
- Migration applies successfully: 1 test
- Index exists after migration: 1 test
- Query uses index (EXPLAIN): 2 tests
- Performance improvement: 1 test

**Total**: 75 unit tests

### Integration Tests (5 tests)

1. Full workflow: Task → Lint → Review → Auto-Commit → Complete
2. Review failure creates blocker
3. Desktop notification sent on SYNC blocker
4. Query performance with 1000+ context items
5. Multi-agent context scoping with composite index

---

## 8. Open Questions & Risks

### Resolved

✅ **Code quality tools**: Radon + Bandit + OWASP patterns
✅ **Desktop notification libraries**: pync (macOS), notify-send (Linux), win10toast (Windows)
✅ **Review Agent architecture**: Standalone ReviewWorkerAgent
✅ **Lint configuration**: Ruff (F, E, W, I, N), ESLint (recommended + typescript)
✅ **Performance targets**: 50%+ improvement with composite index

### Still Open

⚠️ **LLM prompts for Review Agent**: Need to design prompts for architectural review
- **Resolution**: Start with rule-based checks (radon/bandit), add LLM layer in v2
- **Risk Level**: Low (rule-based is sufficient for MVP)

⚠️ **Review iteration limit**: Max 2 iterations before escalating to human
- **Resolution**: Hardcode limit to 2, make configurable later
- **Risk Level**: Low (2 iterations covers most cases)

⚠️ **Desktop notification icon**: Need CodeFRAME icon for notifications
- **Resolution**: Use default system icons for MVP
- **Risk Level**: Low (cosmetic issue)

---

## 9. Recommendations

### Phase 1 Decisions

1. **Create ReviewWorkerAgent** as standalone agent (not subagent)
2. **Use LintRunner** separate from AdaptiveTestRunner
3. **Implement platform-specific notification** with fallbacks
4. **Start with rule-based review** (radon/bandit), defer LLM enhancement
5. **Create migration_006** for all database changes (commit_sha, lint_results, index)

### Phase 2 Priorities

**P0 (Must Have)**:
1. Review Agent with radon + bandit
2. Auto-commit integration in all worker agents
3. Linting quality gate (ruff + eslint)

**P1 (Should Have)**:
1. Desktop notifications (enhances UX)
2. Composite index (performance improvement)

**P2 (Nice to Have - Future)**:
1. LLM-powered architectural review
2. Multi-channel notifications (email, Slack)
3. Advanced security scanning (dependency vulnerabilities)

---

## References

- [Radon Documentation](https://radon.readthedocs.io/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [ESLint Documentation](https://eslint.org/docs/)
- [SQLite Index Optimization](https://www.sqlite.org/optoverview.html)
