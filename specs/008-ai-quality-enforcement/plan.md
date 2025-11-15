# Implementation Plan: AI Quality Enforcement

**Branch**: `008-ai-quality-enforcement` | **Date**: 2025-11-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-ai-quality-enforcement/spec.md`

**Note**: This plan is filled in by the `/speckit.plan` command.

## Summary

Implement systematic enforcement mechanisms to prevent common AI agent failure modes in code generation. The feature addresses five core problems where AI agents optimize for conversation termination rather than code correctness: false test claims, ignoring failing tests, skip decorator abuse, coverage ignorance, and context window degradation.

**Technical Approach**: Create a layered enforcement system with:
1. Foundation layer (`.claude/rules.md`, pre-commit hooks, coverage configuration)
2. Detection layer (AST-based skip detector, comprehensive verification script)
3. Monitoring layer (quality tracking across sessions, context management)

**Primary Goals**:
- Pre-commit hooks block 100% of commits with failing tests or coverage <80%
- Skip decorator detection prevents test circumvention via AST parsing
- Quality ratchet system detects >10% degradation and recommends context reset
- Verification scripts provide pass/fail feedback in <30 seconds

## Technical Context

**Language/Version**: Python 3.11+ (existing requirement)
**Primary Dependencies**: pytest 8.0+, pytest-cov 4.1+, pre-commit 3.0+, black 24.1+, mypy 1.8+, ruff 0.2+
**Storage**: JSON file storage (`.claude/quality_history.json`) - no database required
**Testing**: pytest with coverage enforcement (branch coverage enabled)
**Target Platform**: Cross-platform (Linux, macOS, Windows WSL)
**Project Type**: Single Python project with existing test infrastructure
**Performance Goals**:
- Skip detection: <100ms for typical test suite (100-500 tests)
- Quality ratchet check: <50ms
- Verification script: <30 seconds total
- Pre-commit hooks: <5 seconds overhead
**Constraints**:
- Zero false positives in skip detection
- No breaking changes to existing workflow
- Must work with existing pytest/pre-commit infrastructure
- Cross-platform compatibility
**Scale/Scope**:
- Test suites: 100-500 tests typical
- Conversation length: Up to 20 responses before mandatory reset
- Token budget: ~50k tokens per conversation
- Quality history: Unlimited retention (JSON append-only)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Principle I: Test-First Development** ✅
- This feature enforces TDD through pre-commit hooks and verification scripts
- Test template (US4) provides concrete examples of test-first patterns
- No violations

**Principle II: Async-First Architecture** ✅
- No async operations required (all enforcement runs synchronously in git hooks)
- Scripts are CLI tools, not long-running services
- N/A - no violations

**Principle III: Context Efficiency** ✅
- US6 (Context Management System) directly supports this principle
- Quality ratchet (US3) detects when context degrades
- Aligns with existing Virtual Project system
- No violations

**Principle IV: Multi-Agent Coordination** ✅
- Enforcement applies to all agents equally through shared git hooks
- No agent-specific modifications needed
- No violations

**Principle V: Observability & Traceability** ✅
- Verification scripts provide detailed output
- Quality history tracks metrics over time
- Git hooks log enforcement actions
- No violations

**Principle VI: Type Safety** ✅
- Python scripts will use type hints (enforced by mypy)
- Configuration files are validated
- No violations

**Principle VII: Incremental Delivery** ✅
- Six user stories prioritized P0, P1, P2
- Each story independently testable and deployable
- MVP-first approach: US1 delivers core value
- No violations

**GATE STATUS**: ✅ **PASSED** - All constitution principles satisfied

## Project Structure

### Documentation (this feature)

```
specs/008-ai-quality-enforcement/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification (already created)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   ├── rules-schema.json         # .claude/rules.md structure
│   ├── quality-history-schema.json  # Quality tracking format
│   └── verification-api.md       # Verification script interface
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
# Single project structure (existing codeframe layout)
.claude/
├── rules.md                    # AI development rules (US1)
└── quality_history.json        # Quality metrics over time (US3)

scripts/
├── verify-ai-claims.sh         # Comprehensive verification (US1, US5)
├── detect-skip-abuse.py        # Skip decorator detection (US2)
└── quality-ratchet.py          # Quality tracking (US3)

tests/
├── test_template.py            # Testing best practices (US4)
├── enforcement/                # Tests for enforcement tools
│   ├── test_skip_detector.py
│   ├── test_quality_ratchet.py
│   └── test_verification_script.py
└── integration/
    └── test_enforcement_workflow.py

.pre-commit-config.yaml         # Pre-commit hooks (US1)
.gitmessage                     # Commit message template (US5)
pyproject.toml                  # Coverage configuration (US1 - existing file, add config)
```

**Structure Decision**: Single project structure with enforcement tools in `scripts/` directory. All enforcement mechanisms live at repository root for accessibility by git hooks and CI/CD. Test coverage validation runs against existing `tests/` directory. No new packages or modules required - purely tooling layer.

## Complexity Tracking

*No constitution violations - section not applicable*

---

## Phase 0: Research & Discovery

**Goal**: Resolve all "NEEDS CLARIFICATION" items from Technical Context and research implementation approaches.

### Research Tasks

#### R1: Pre-commit Hook Best Practices
**Question**: What's the optimal configuration for pre-commit hooks in Python projects?
**Research Areas**:
- Pre-commit framework configuration patterns
- Performance optimization (caching, parallel execution)
- Error message best practices
- Skip/bypass mechanisms for emergencies

**Deliverable**: Document recommended hook configuration with performance benchmarks

#### R2: Python AST Parsing for Skip Detection
**Question**: How to reliably detect all skip decorator variations using AST?
**Research Areas**:
- Python `ast` module capabilities and limitations
- Skip decorator patterns in pytest (`@skip`, `@skipif`, `@pytest.mark.skip`)
- False positive scenarios (legitimate skip usage)
- Performance characteristics for large codebases

**Deliverable**: Proof-of-concept skip detector with test cases

#### R3: Quality Metric Tracking Approaches
**Question**: What metrics best indicate AI conversation quality degradation?
**Research Areas**:
- Test pass rate calculation from pytest output
- Coverage percentage extraction
- Response count tracking mechanisms
- Degradation detection algorithms (moving average, threshold-based)

**Deliverable**: Algorithm specification with sample data

#### R4: Test Template Patterns
**Question**: What test patterns should be included in the reference template?
**Research Areas**:
- Pytest best practices
- Hypothesis property-based testing
- Parametrized test patterns
- Fixture usage patterns
- Integration test examples

**Deliverable**: Template outline with pattern categories

#### R5: Context Management Strategies
**Question**: What's the optimal checkpoint frequency and token budget?
**Research Areas**:
- Typical AI conversation token usage patterns
- Context window limits (Claude, GPT-4)
- Checkpoint overhead vs. safety trade-offs
- Context handoff template design

**Deliverable**: Recommended checkpoint strategy with rationale

**Output**: `research.md` with all findings and decisions documented

---

## Phase 1: Design & Contracts

**Prerequisites**: `research.md` complete

### D1: Data Model Design

**Goal**: Define data structures for quality tracking and configuration

**Entities**:

1. **Quality Checkpoint** (stored in `.claude/quality_history.json`)
   - Fields: timestamp, response_count, test_pass_rate, coverage_percentage
   - Validation: test_pass_rate in [0, 100], coverage in [0, 100]
   - Relationships: Sequential checkpoints form trend

2. **AI Rules Configuration** (`.claude/rules.md`)
   - Sections: CRITICAL, ABSOLUTELY FORBIDDEN, TDD Required, Context Management
   - Format: Markdown with structured sections
   - Validation: Required sections present

3. **Verification Result** (output from `scripts/verify-ai-claims.sh`)
   - Fields: status (pass/fail), test_results, coverage, skip_check, quality_check
   - Exit codes: 0 (pass), 1 (fail)
   - Output format: Text with emoji indicators

**Output**: `data-model.md`

### D2: Contract Design

**Goal**: Define interfaces for enforcement tools and configuration files

**Contracts**:

1. **Pre-commit Hook Interface** (`.pre-commit-config.yaml`)
   - Entry points for each hook
   - Exit codes and error handling
   - Performance requirements

2. **Skip Detector API** (`scripts/detect-skip-abuse.py`)
   - Input: Test file path or directory
   - Output: List of violations (file, line, function)
   - Exit codes: 0 (clean), 1 (violations found)

3. **Quality Ratchet CLI** (`scripts/quality-ratchet.py`)
   - Commands: record, check, stats, reset
   - JSON output format for automation
   - File format specification for `.claude/quality_history.json`

4. **Verification Script API** (`scripts/verify-ai-claims.sh`)
   - Input: None (runs on current repository state)
   - Output: Detailed verification report
   - Exit codes: 0 (all checks pass), 1 (any check fails)

**Output**: `contracts/` directory with JSON schemas and API specifications

### D3: Quickstart Guide

**Goal**: Provide 30-minute setup guide for new projects

**Content**:
1. Installation steps (pre-commit, dependencies)
2. Initial configuration (copy templates)
3. First verification run
4. Common workflows
5. Troubleshooting guide

**Output**: `quickstart.md`

### D4: Agent Context Update

**Action**: Run `.specify/scripts/bash/update-agent-context.sh claude`

**Purpose**: Update `CLAUDE.md` with new enforcement tooling

**New Context**:
- Pre-commit hook enforcement
- Skip detector usage
- Quality ratchet workflow
- Verification script commands

---

## Phase 2: Task Generation (Done by `/speckit.tasks`)

**Note**: Phase 2 is executed by the `/speckit.tasks` command, NOT by `/speckit.plan`. This section documents the expected task organization.

### Task Organization

**US1: Enforcement Foundation** (P0)
- T001: Create `.claude/rules.md` with TDD requirements
- T002: Configure `pyproject.toml` coverage thresholds
- T003: Create `.pre-commit-config.yaml` with hooks
- T004: Create `scripts/verify-ai-claims.sh` basic version
- T005: Test pre-commit hooks block failing tests
- T006: Test coverage enforcement blocks low coverage

**US2: Skip Decorator Detection** (P1)
- T007: Create `scripts/detect-skip-abuse.py` with AST parsing
- T008: Implement skip decorator detection logic
- T009: Add justification comment checking
- T010: Integrate with pre-commit hooks
- T011: Add to CI/CD pipeline
- T012: Test false positive scenarios
- T013: Test all skip decorator variations

**US3: Quality Ratchet System** (P1)
- T014: Create `scripts/quality-ratchet.py` CLI framework
- T015: Implement `record` command (capture metrics)
- T016: Implement `check` command (degradation detection)
- T017: Implement `stats` command (visualization)
- T018: Implement `reset` command
- T019: Test degradation detection algorithm
- T020: Test quality history persistence

**US4: Comprehensive Test Template** (P2)
- T021: Create `tests/test_template.py` skeleton
- T022: Add traditional unit test examples
- T023: Add property-based test examples (Hypothesis)
- T024: Add parametrized test examples
- T025: Add integration test examples
- T026: Add fixture usage examples
- T027: Add comprehensive docstrings
- T028: Update `.claude/rules.md` to reference template

**US5: Enhanced Verification** (P1)
- T029: Expand `scripts/verify-ai-claims.sh` with multi-step checks
- T030: Add coverage HTML report generation
- T031: Add quality checks integration
- T032: Create `.gitmessage` commit template
- T033: Add performance optimizations (caching, parallel)
- T034: Test verification script on codeframe
- T035: Verify <30s execution time requirement

**US6: Context Management System** (P2)
- T036: Define context rules in documentation
- T037: Create checkpoint system design
- T038: Create context handoff template
- T039: Integrate with quality-ratchet for auto-suggestions
- T040: Update `.claude/rules.md` with context limits
- T041: Test context reset workflow
- T042: Document reset triggers

---

## Testing Strategy

### Unit Tests (per enforcement tool)

**Skip Detector** (`tests/enforcement/test_skip_detector.py`):
- Test detects `@skip` decorator
- Test detects `@skipif` decorator
- Test detects `@pytest.mark.skip` decorator
- Test detects skip with no reason
- Test allows skip with strong justification
- Test handles nested decorators
- Test handles non-test files gracefully
- Test performance on large files (<100ms)

**Quality Ratchet** (`tests/enforcement/test_quality_ratchet.py`):
- Test record command creates history entry
- Test check command detects degradation
- Test stats command formats output correctly
- Test reset command clears history
- Test moving average calculation
- Test peak quality detection
- Test JSON persistence
- Test handles missing history file

**Verification Script** (`tests/enforcement/test_verification_script.py`):
- Test script exits 0 when all checks pass
- Test script exits 1 when any check fails
- Test report includes all verification steps
- Test execution time <30s
- Test handles missing dependencies gracefully

### Integration Tests

**Enforcement Workflow** (`tests/integration/test_enforcement_workflow.py`):
- Test pre-commit hook blocks commit with failing test
- Test pre-commit hook blocks commit with low coverage
- Test pre-commit hook blocks commit with skip decorator
- Test verification script runs full workflow
- Test quality ratchet detects real degradation
- Test context reset workflow end-to-end

### Manual Testing Checklist

- [ ] Install pre-commit hooks on clean codeframe clone
- [ ] Intentionally add failing test, verify commit blocked
- [ ] Reduce coverage below 80%, verify commit blocked
- [ ] Add `@pytest.mark.skip`, verify commit blocked
- [ ] Run verification script, verify <30s execution
- [ ] Simulate conversation with quality degradation
- [ ] Test context handoff template workflow

---

## Performance Targets

| Component | Target | Measurement Method |
|-----------|--------|-------------------|
| Skip detector | <100ms | Time 500-test suite scan |
| Quality ratchet check | <50ms | Time degradation detection |
| Verification script | <30s total | Full workflow timing |
| Pre-commit hooks | <5s overhead | Git commit timing |

**Optimization Strategies**:
- AST parsing: Cache parsed files, skip non-test files
- Quality ratchet: In-memory calculations, lazy file I/O
- Verification script: Parallel checks where safe, fail fast
- Pre-commit hooks: Only run on changed files

---

## Rollout Plan

### Phase 1: Codeframe Dogfooding (Week 1)
1. Implement all enforcement mechanisms in codeframe repo
2. Use for Sprint 9 development
3. Gather metrics on false positives and effectiveness
4. Iterate based on real-world usage

### Phase 2: Documentation (Week 2)
1. Update CLAUDE.md with enforcement guidelines
2. Create comprehensive user guide
3. Add examples to README
4. Record demo video

### Phase 3: Community Sharing (Week 3+)
1. Extract as standalone tool
2. Publish guide as blog post
3. Share with AI coding community
4. Gather feedback and iterate

---

## Risk Mitigation

| Risk | Mitigation Strategy |
|------|-------------------|
| False positives block legitimate work | Comprehensive testing, easy bypass mechanism for maintainers |
| Pre-commit hooks too slow | Performance profiling, parallel execution, caching |
| Quality ratchet generates noise | Tune thresholds based on real data, allow user configuration |
| Skip detection misses edge cases | Thorough AST testing, community feedback loop |
| Enforcement frustrates developers | Clear error messages, quick feedback, easy opt-out for emergencies |

---

## Success Metrics

### Quantitative (collect in Phase 1)
- False positive rate: <1% (target: 0%)
- Verification script execution time: <30s (target: <20s)
- Pre-commit hook overhead: <5s (target: <3s)
- Commit block rate for actual violations: >95% (target: 100%)
- Quality degradation detection accuracy: >90%

### Qualitative (assess in Phases 2-3)
- Developer confidence in autonomous agents increases
- Fewer manual code reviews needed for quality issues
- AI agents adapt to enforcement rules quickly
- Community adoption of enforcement patterns

---

## Dependencies

**External**:
- `pre-commit` package (new dependency)
- `hypothesis` package (optional for test template)

**Internal**:
- Existing pytest infrastructure
- Existing pytest-cov configuration
- Existing code quality tools (black, mypy, ruff)

**No Blockers**: All dependencies already available or easily installable

---

## Open Questions (to be resolved in Phase 0)

1. **Q**: Should we allow skip decorators with sufficient justification?
   **Status**: Research in R2
   **Decision Criteria**: Balance between strictness and flexibility

2. **Q**: What's the optimal checkpoint frequency?
   **Status**: Research in R5
   **Decision Criteria**: Balance between overhead and safety

3. **Q**: Should quality ratchet track per-file or per-project metrics?
   **Status**: Research in R3
   **Decision Criteria**: Complexity vs. value trade-off

4. **Q**: How to handle platform-specific test skips (Windows vs. Linux)?
   **Status**: Research in R2
   **Decision Criteria**: False positive avoidance

---

## Next Steps

1. Execute Phase 0 research (estimated: 4-6 hours)
2. Complete Phase 1 design artifacts (estimated: 2-3 hours)
3. Run `/speckit.tasks` to generate detailed task list
4. Begin implementation with `/speckit.implement`

**Total Estimated Effort**: 16-23 hours (as documented in SPRINTS.md)

---

**Version**: 1.0
**Status**: Ready for Phase 0 Execution
**Last Updated**: 2025-11-14
