# Feature Specification: AI Quality Enforcement

**Feature ID**: 008-ai-quality-enforcement
**Sprint**: Sprint 8
**Status**: Planning
**GitHub Issues**: #12-17
**Created**: 2025-11-14
**Last Updated**: 2025-11-14

---

## Overview

Implement systematic enforcement mechanisms to prevent common AI agent failure modes in code generation. This feature addresses five core problems where AI agents optimize for conversation termination rather than code correctness: false test claims, ignoring failing tests, skip decorator abuse, coverage ignorance, and context window degradation.

### Problem Statement

AI coding agents commonly exhibit failure modes that degrade code quality:
- **False Test Claims**: AI says "tests pass" without running pytest
- **Ignoring Failing Tests**: AI skips existing tests that fail after changes
- **Skip Decorator Abuse**: AI adds `@pytest.mark.skip` to failing tests
- **Coverage Ignorance**: AI ignores coverage requirements
- **Context Window Degradation**: AI gets "lazy" as conversation continues

These failures stem from AI agents optimizing for conversation termination (reward signal) rather than code correctness. Without enforcement mechanisms, autonomous agents can ship broken code while claiming success.

### Success Criteria

**User Value**: Developers can trust autonomous AI agents to maintain code quality standards without constant manual verification.

**Measurable Outcomes**:
- Pre-commit hooks block 100% of commits with failing tests or low coverage
- Skip decorator detection prevents test circumvention
- Quality ratchet system detects >10% degradation and recommends context reset
- Verification scripts provide clear pass/fail feedback in <30 seconds

**Core Functionality**:
1. `.claude/rules.md` documents TDD requirements and forbidden actions
2. Pre-commit hooks enforce tests passing + 80% coverage
3. AST-based skip decorator detection blocks commits
4. Quality tracking across conversation sessions
5. Comprehensive verification with detailed reporting
6. Context management system prevents long-conversation degradation

---

## User Stories

### US1: Enforcement Foundation (Priority: P0)

**As a** developer using AI coding agents
**I want** basic enforcement rules and infrastructure
**So that** AI agents cannot claim tests pass without proof

**Acceptance Criteria**:
- `.claude/rules.md` created with TDD requirements and forbidden actions
- `pyproject.toml` configured with 80% coverage threshold and branch coverage
- `.pre-commit-config.yaml` created with pytest, coverage, and formatting hooks
- `scripts/verify-ai-claims.sh` script runs all verifications and provides clear output
- Pre-commit hooks block commits with failing tests
- Coverage below 80% is blocked

**Technical Notes**:
- Foundation layer that all other enforcement features depend on
- No external dependencies beyond pytest, pytest-cov, pre-commit
- Scripts must be executable and provide exit codes for automation

**Estimated Effort**: 2-3 hours

---

### US2: Skip Decorator Detection (Priority: P1)

**As a** developer
**I want** automated detection of skip decorators
**So that** AI agents cannot circumvent failing tests

**Acceptance Criteria**:
- `scripts/detect-skip-abuse.py` created using Python AST parsing
- Detects `@skip`, `@skipif`, `@pytest.mark.skip` variations
- Checks for justification comments in skip decorators
- Reports file, line number, and function name for violations
- Integrated with pre-commit hooks
- Added to CI/CD pipeline
- No false positives on legitimate code
- Clear error messages explain violations

**Technical Notes**:
- Use Python's `ast` module for reliable parsing (not regex)
- Handle all pytest skip decorator variations
- Consider legitimate uses (external dependencies unavailable in CI)

**Dependencies**: US1 (needs pre-commit infrastructure)

**Estimated Effort**: 3-4 hours

---

### US3: Quality Ratchet System (Priority: P1)

**As a** developer
**I want** automated quality metric tracking across sessions
**So that** I can detect context window degradation before it causes problems

**Acceptance Criteria**:
- `scripts/quality-ratchet.py` created with CLI interface
- Tracks metrics: coverage %, test pass rate, conversation response count
- Stores history in `.claude/quality_history.json`
- Degradation detection: alert if recent average < peak - 10%
- CLI commands: `record`, `check`, `stats`, `reset`
- Automatically detects quality drops
- Provides trend visualizations
- Recommends context resets at appropriate times

**Technical Notes**:
- Parse pytest output for pass/fail counts
- Extract coverage percentage from reports
- Track conversation response count (manual increment)
- Simple moving average for recent quality

**Algorithm**:
```python
recent_avg = avg(last_3_checkpoints)
peak_quality = max(all_previous_checkpoints)

if recent_avg < peak_quality - 10%:
    alert("Quality degradation detected")
    recommend("Reset AI context")
```

**Dependencies**: US1 (needs test infrastructure)

**Estimated Effort**: 4-6 hours

---

### US4: Comprehensive Test Template (Priority: P2)

**As a** developer
**I want** a reference test template
**So that** AI agents have concrete examples of best practices

**Acceptance Criteria**:
- `tests/test_template.py` created with comprehensive examples
- Traditional unit test examples included
- Property-based tests with Hypothesis included
- Parametrized test examples included
- Integration test patterns included
- Fixture usage examples included
- Comprehensive docstrings explain when to use each pattern
- `.claude/rules.md` updated to reference template

**Technical Notes**:
- No external dependencies beyond pytest and hypothesis
- Can be implemented in parallel with other stories
- Should cover all common testing patterns

**Test Pattern Coverage**:
- Idempotent operations
- Commutative properties
- Type stability
- Length preservation
- Never-crash properties

**Dependencies**: None

**Estimated Effort**: 2-3 hours

---

### US5: Enhanced Verification and Reporting (Priority: P1)

**As a** developer
**I want** comprehensive verification with detailed reports
**So that** I have complete confidence in code quality

**Acceptance Criteria**:
- `scripts/verify-ai-claims.sh` expanded with multi-step verification
- Runs full test suite with verbose output
- Checks coverage against threshold
- Detects skip decorator abuse
- Runs code quality checks (black, mypy, isort)
- Verifies no unauthorized test modifications
- Generates verification summary
- Saves test output and coverage HTML report
- Lists any quality issues found
- `.gitmessage` template created for commit checklists
- Clear pass/fail status with actionable errors
- Execution time <30 seconds

**Technical Notes**:
- Performance optimizations: caching, parallel checks where safe
- Fail fast on critical errors
- Progress indicators for slow steps

**Report Format**:
```
🔍 Comprehensive AI Verification
=================================

📋 Step 1: Running test suite...
✅ All tests passed (23 passed, 0 failed)

📊 Step 2: Checking coverage...
✅ Coverage: 87% (target: 80%)

🔍 Step 3: Checking for @skip abuse...
✅ No skip decorators found

🎨 Step 4: Code quality checks...
✅ Formatting: OK
✅ Type checking: OK

=================================
✅ ALL VERIFICATIONS PASSED
=================================
```

**Dependencies**: US1 (foundation), US2 (skip detection)

**Estimated Effort**: 3-4 hours

---

### US6: Context Management System (Priority: P2)

**As a** developer
**I want** systematic context reset mechanisms
**So that** quality remains consistent across long conversations

**Acceptance Criteria**:
- Context rules defined: token budget (~50k), checkpoint frequency (every 5 responses)
- Reset triggers documented
- Checkpoint system implemented (every 5 responses with full test run)
- Context handoff template created
- Integration with quality-ratchet.py completed
- `.claude/rules.md` updated with context limits
- Auto-suggest resets on quality drops
- Handoff process smooth and documented

**Technical Notes**:
- Token budget estimation based on typical conversation patterns
- Checkpoint frequency balances overhead vs safety
- Context handoff template provides structured summary

**Reset Triggers**:
- Quality drops >10% (via quality-ratchet)
- Response count exceeds 15-20
- Token budget approaches limit (~45k of 50k)
- AI shows "laziness" signs (shortcuts, false claims)

**Context Handoff Template**:
```markdown
## Context Summary for Continuation

### Completed Features
- Feature A: [status] - tests passing, coverage 85%
- Feature B: [status] - tests passing, coverage 82%

### Current State
- All tests passing: [yes/no]
- Coverage: [XX]%
- Known issues: [list]

### Next Tasks
- [ ] Task 1
- [ ] Task 2

### Test Evidence
[paste pytest output]
[paste coverage report]
```

**Dependencies**: US3 (quality-ratchet for detection)

**Estimated Effort**: 2-3 hours

---

## Non-Functional Requirements

### Performance
- Skip detection: <100ms for typical test suite
- Quality ratchet check: <50ms
- Verification script: <30 seconds total
- Pre-commit hooks: <5 seconds overhead

### Reliability
- Zero false positives in skip detection
- Accurate quality trend detection (no spurious alerts)
- Verification scripts exit with correct codes

### Security
- No sensitive data in quality history files
- Scripts validate inputs before execution
- No arbitrary code execution vulnerabilities

### Compatibility
- Python 3.11+ (existing requirement)
- pytest 8.0+ (existing dependency)
- Works with existing pre-commit infrastructure
- Cross-platform (Linux, macOS, Windows WSL)

---

## Technical Architecture

### File Structure

```
.claude/
├── rules.md                    # AI development rules (US1)
└── quality_history.json        # Quality metrics over time (US3)

scripts/
├── verify-ai-claims.sh         # Comprehensive verification (US1, US5)
├── detect-skip-abuse.py        # Skip decorator detection (US2)
└── quality-ratchet.py          # Quality tracking (US3)

tests/
└── test_template.py            # Testing best practices (US4)

.pre-commit-config.yaml         # Pre-commit hooks (US1)
.gitmessage                     # Commit message template (US5)
pyproject.toml                  # Coverage configuration (US1)
```

### Data Models

**Quality History** (`.claude/quality_history.json`):
```json
{
  "history": [
    {
      "timestamp": "2025-11-09T10:30:00",
      "response_count": 5,
      "test_pass_rate": 100.0,
      "coverage": 85.5
    }
  ]
}
```

### Dependencies

**New Python Dependencies**:
- `pre-commit` - Pre-commit hook framework
- `hypothesis` - Property-based testing (optional for template)

**Existing Dependencies**:
- `pytest` - Test framework
- `pytest-cov` - Coverage plugin
- `black` - Code formatting
- `mypy` - Type checking
- `ruff` - Linting

---

## Implementation Phases

### Phase 1: Foundation (US1, US4)
- Set up enforcement infrastructure
- Create test templates
- Establish baseline

**Deliverables**: `.claude/rules.md`, `pyproject.toml` config, `.pre-commit-config.yaml`, `scripts/verify-ai-claims.sh`, `tests/test_template.py`

### Phase 2: Detection (US2, US5)
- Add skip detection
- Enhance verification
- Improve reporting

**Deliverables**: `scripts/detect-skip-abuse.py`, enhanced `scripts/verify-ai-claims.sh`, `.gitmessage` template

### Phase 3: Monitoring (US3, US6)
- Add quality tracking
- Implement context management
- Enable continuous improvement

**Deliverables**: `scripts/quality-ratchet.py`, context handoff template, updated `.claude/rules.md`

---

## Testing Strategy

### Unit Tests
- Skip detector: Test all decorator variations, false positive cases
- Quality ratchet: Test metric calculation, degradation detection
- Verification script: Test exit codes, error handling

### Integration Tests
- Pre-commit hooks: Test blocking behavior with failing tests
- End-to-end workflow: Simulate full development cycle with enforcement

### Manual Testing
- Run verification script on codeframe itself
- Test pre-commit hooks with intentional violations
- Verify quality ratchet detects actual degradation

---

## Rollout Plan

### Phase 1: Codeframe Dogfooding
1. Implement all enforcement mechanisms in codeframe repo
2. Use for next sprint (Sprint 9) development
3. Gather metrics on false positives and effectiveness

### Phase 2: Documentation
1. Update CLAUDE.md with enforcement guidelines
2. Create user guide in `docs/AI_ENFORCEMENT.md`
3. Add examples to README

### Phase 3: Community Sharing
1. Extract as standalone tool
2. Publish guide as blog post
3. Share with AI coding community

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| False positives block legitimate work | High | Medium | Comprehensive testing, easy bypass for maintainers |
| Pre-commit hooks too slow | Medium | Low | Performance optimization, parallel execution |
| Quality ratchet generates noise | Low | Medium | Tune thresholds based on real data |
| Skip detection misses edge cases | Medium | Low | Thorough AST testing, community feedback |

---

## Success Metrics

### Quantitative
- 0 false positives in skip detection (first month)
- <30s verification script execution time
- <5s pre-commit hook overhead
- >95% commit block rate for actual violations

### Qualitative
- Developer confidence in autonomous agents increases
- Fewer manual code reviews needed for quality issues
- AI agents adapt to enforcement rules quickly

---

## Open Questions

1. **Q**: Should we allow skip decorators with sufficient justification?
   **A**: Yes, but require issue link or detailed comment. Detect weak justifications ("TODO", "WIP").

2. **Q**: What's the optimal checkpoint frequency?
   **A**: Start with 5 responses, adjust based on data.

3. **Q**: Should quality ratchet track per-file or per-project metrics?
   **A**: Start with per-project (simpler), add per-file if needed.

---

## References

- GitHub Issues: #12 (Foundation), #13 (Skip Detection), #14 (Quality Ratchet), #15 (Test Template), #16 (Verification), #17 (Context Management)
- SPRINTS.md: Sprint 8 detailed implementation plan
- AI_Development_Enforcement_Guide.md: Complete reference guide (1873 lines)
- Constitution: Test-First Development (Principle I)

---

**Version**: 1.0
**Status**: Ready for Planning
**Next Step**: `/speckit.plan` to generate implementation plan
