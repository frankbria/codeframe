# AI Development Rules for Codeframe

This document establishes rules for AI agents working on the codeframe project. These rules prevent common failure modes where AI agents optimize for conversation termination rather than code correctness.

## CRITICAL: Test-First Development (TDD) Requirements

### Test-First Workflow

**ALWAYS** follow this exact sequence:

1. **Write the test FIRST** (it must fail initially)
2. **Run the test** (verify it fails with the expected error message)
3. **Implement the code** to make the test pass
4. **Run the test again** (verify it now passes)
5. **Refactor** if needed (tests must remain passing)

### Evidence Requirements

When claiming "tests pass", you **MUST** provide:

- Full pytest output showing test execution
- Coverage report showing ≥85% coverage
- Verification script output (`scripts/verify-ai-claims.sh`)
- No failing tests, no skipped tests (without justification)

**Example of acceptable evidence:**
```
$ scripts/verify-ai-claims.sh
✅ Step 1: Running test suite... PASSED (93 tests, 0 failures)
✅ Step 2: Checking coverage... PASSED (87.3% coverage, threshold 85%)
✅ Step 3: Detecting skip abuse... PASSED (0 violations)
✅ Step 4: Running quality checks... PASSED

VERIFICATION RESULT: ✅ ALL CHECKS PASSED
```

## ABSOLUTELY FORBIDDEN Actions

These actions are **NEVER** acceptable without explicit discussion and approval:

### 1. Skip Decorators Without Justification

❌ **FORBIDDEN:**
```python
@pytest.mark.skip  # No reason provided
def test_authentication():
    pass

@pytest.mark.skip(reason="TODO")  # Weak justification
def test_user_permissions():
    pass

@pytest.mark.skip(reason="Fix later")  # Weak justification
def test_database_migration():
    pass
```

✅ **ACCEPTABLE** (only in rare cases, requires discussion):
```python
@pytest.mark.skip(reason="Blocked by external API downtime - Issue #123, expected resolution 2025-11-20")
def test_third_party_integration():
    pass
```

### 2. False Test Claims

❌ **FORBIDDEN:**
- Claiming "tests pass" without running them
- Reporting "100% coverage" without verification
- Saying "I've tested this" without providing evidence
- Ignoring failing tests and claiming success
- Running only a subset of tests and claiming full coverage

### 3. Coverage Reduction

❌ **FORBIDDEN:**
- Reducing coverage below the 85% threshold
- Commenting out existing tests to improve coverage numbers
- Adding `# pragma: no cover` without justification
- Ignoring coverage warnings

### 4. Test Circumvention

❌ **FORBIDDEN:**
- Modifying tests to make them pass incorrectly
- Removing assertions to avoid failures
- Mocking everything to bypass real logic
- Using `pass` statements instead of real test implementation

## Context Management Guidelines

### Token Budget

- **Maximum context**: ~50,000 tokens per conversation
- **Warning threshold**: 45,000 tokens (90%)
- **Checkpoint frequency**: Every 5 AI responses

### Checkpoint System

When reaching a checkpoint (every 5 responses), you **MUST**:

1. Run full verification: `scripts/verify-ai-claims.sh`
2. Generate coverage report
3. Ask: **"Continue or reset context?"**

**Auto-reset triggers:**
- Response count >15-20
- Quality degradation >10% (detected by `scripts/quality-ratchet.py check`)
- Token usage >45k
- Signs of AI "laziness" (skipping steps, false claims, incomplete implementation)

### Context Handoff Template

When resetting context, provide the new AI session with:

```markdown
## Context Handoff

**Completed Features:**
- Feature A: Fully implemented and tested (coverage: 92%)
- Feature B: 80% complete, needs error handling

**Current State:**
- Working on: Feature C - database integration
- Last commit: abc123 "Add user authentication"
- Test status: 87 passing, 0 failing

**Next Tasks:**
- Complete database migration for Feature C
- Add integration tests for auth flow
- Update documentation

**Test Evidence:**
[Paste verification script output]

**Architecture Notes:**
- Using async/await throughout
- SQLite for persistence
- FastAPI for REST endpoints
```

## Verification Process

### Before Every Commit

Run the comprehensive verification script:
```bash
scripts/verify-ai-claims.sh
```

This script performs:
1. Full test suite execution
2. Coverage check (≥85%)
3. Skip decorator detection
4. Code quality checks (black, ruff, mypy)
5. Comprehensive report generation

**Exit codes:**
- 0: All checks passed, safe to commit
- 1: One or more checks failed, DO NOT commit

### Pre-commit Hooks

The repository uses pre-commit hooks that **AUTOMATICALLY** block commits with:
- Failing tests
- Coverage <85%
- Skip decorators (without strong justification)
- Code quality violations

**To bypass** (use ONLY in emergencies):
```bash
git commit --no-verify  # MUST have approval from team lead
```

## Testing Standards

### Required Test Patterns

Use `tests/test_template.py` as a reference for:

1. **Traditional Unit Tests**: Specific inputs, expected outputs
2. **Property-Based Tests**: Hypothesis strategies for edge cases
3. **Parametrized Tests**: Multiple inputs with `@pytest.mark.parametrize`
4. **Integration Tests**: Multi-component workflows
5. **Async Tests**: Using `@pytest.mark.asyncio`

### Coverage Requirements

- **Minimum coverage**: 85% (branch coverage enabled)
- **Target coverage**: 90%+
- **Critical paths**: 100% coverage required (auth, payments, data loss scenarios)

### What to Test

✅ **MUST test:**
- Happy path (expected usage)
- Error handling (invalid inputs, edge cases)
- Boundary conditions (empty, null, max values)
- Async behavior (concurrency, race conditions)
- Database operations (ACID properties)

❌ **Do NOT test:**
- Third-party library internals
- Framework behavior (e.g., FastAPI routing)
- Getters/setters with no logic

## Quality Ratchet Integration

The project uses `scripts/quality-ratchet.py` to track quality metrics across sessions.

### Recording Checkpoints

```bash
python scripts/quality-ratchet.py record --response-count 5
```

### Checking for Degradation

```bash
python scripts/quality-ratchet.py check
```

If degradation >10% is detected, the script will recommend a context reset.

### Viewing Statistics

```bash
python scripts/quality-ratchet.py stats
```

Shows current, peak, and average quality metrics.

## Emergency Procedures

### If Tests Are Failing

1. **DO NOT** skip the tests
2. **DO NOT** claim tests pass
3. **INVESTIGATE** the root cause
4. **FIX** the implementation or the test
5. **VERIFY** all tests pass before proceeding

### If Coverage Drops Below 85%

1. **DO NOT** reduce the threshold
2. **DO NOT** add `# pragma: no cover`
3. **IDENTIFY** uncovered code paths
4. **ADD** tests to cover those paths
5. **VERIFY** coverage is back above 85%

### If You're Stuck

1. **STOP** and explain the blocker clearly
2. **ASK** for guidance or clarification
3. **DO NOT** make up a solution without understanding
4. **DO NOT** claim completion if uncertain

## Summary

These rules exist to ensure **code quality** and **developer confidence** in autonomous AI agents. When in doubt:

- **Write the test first**
- **Run verification scripts**
- **Provide evidence**
- **Ask for help if stuck**

**REMEMBER**: It's better to admit uncertainty than to deliver broken code with false confidence.
