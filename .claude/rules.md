# AI Development Rules

## CRITICAL: Test Evidence Required

Before claiming tests pass or task complete:
1. Run: `pytest -v --cov --cov-report=term-missing`
2. Copy FULL terminal output into your response
3. If ANY test fails, task is NOT complete
4. If coverage < 80%, task is NOT complete

**I will reject any claim without proof.**

## ABSOLUTELY FORBIDDEN

- Adding @skip, @skipif, or @pytest.mark.skip to ANY test
- Modifying existing tests without explicit approval
- Claiming tests pass without running them
- Ignoring failing tests as "unrelated"

Violation = complete task rejection.

## Test-Driven Development Required

1. Write failing test FIRST
2. Run pytest to verify it fails
3. Implement minimal code to pass
4. Run pytest to verify it passes
5. Show me the output at each step

## Context Management

After 3 completed features OR showing signs of quality degradation:
1. Summarize what was accomplished
2. State current test/coverage status WITH PROOF
3. Wait for human to start fresh conversation

Do NOT continue indefinitely in one conversation.
