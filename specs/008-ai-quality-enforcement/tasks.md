---
description: "Task list for AI Quality Enforcement feature - incorporating ALL GitHub issue recommendations #12-17"
---

# Tasks: AI Quality Enforcement

**Input**: Design documents from `/specs/008-ai-quality-enforcement/` + GitHub Issues #12-17 with detailed code recommendations
**Prerequisites**: plan.md (complete), spec.md (complete)

**Tests**: Tests ARE required for this feature - all enforcement tools must be thoroughly tested

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

**GitHub Issues Context**: Issues #12-17 contain detailed implementation recommendations from traycer.ai that MUST be followed.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions
- Single project structure at repository root
- **All enforcement tools**: `scripts/` directory (more conventional)
- Tests: `tests/enforcement/` for tool tests
- Config: `.claude/`, `.pre-commit-config.yaml`, `pyproject.toml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency setup

- [X] T001 Install pre-commit package via `pip install -e ".[dev]"` after adding to pyproject.toml
- [X] T002 [P] Create `.claude/` directory if it doesn't exist

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Add `pre-commit>=3.5.0` to `[project.optional-dependencies]` dev section in pyproject.toml
- [X] T005 [P] Add `hypothesis>=6.0.0` to dev dependencies in pyproject.toml (issue #15: version >=6.0.0)
- [X] T006 [P] Enable branch coverage in pyproject.toml: add `[tool.coverage.run]` with `branch = true`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Enforcement Foundation (Priority: P0) 🎯 MVP

**Goal**: Establish basic enforcement rules and infrastructure to prevent AI agents from claiming tests pass without proof

**Independent Test**: Run `scripts/verify-ai-claims.sh` and verify it executes all checks and provides clear pass/fail output; intentionally create failing test and verify pre-commit hooks block the commit

**GitHub Issue**: #12 - Foundation layer with TDD requirements and pre-commit infrastructure

### Implementation for User Story 1

- [X] T007 [US1] Create `.claude/rules.md` with TDD requirements (test-first workflow), forbidden actions (skip decorators, false claims), and context management guidelines (issue #12)
- [X] T008 [US1] Create `.pre-commit-config.yaml` with pytest hook, coverage check hook, black formatter hook, ruff linter hook, and local custom hooks section (issue #12)
- [X] T009 [US1] Create basic `scripts/verify-ai-claims.sh` that runs pytest, checks coverage ≥85%, and displays summary with exit codes (issue #12, #16)
- [X] T010 [US1] Make `scripts/verify-ai-claims.sh` executable with `chmod +x`
- [X] T011 [US1] Update `.claude/rules.md` to reference `scripts/verify-ai-claims.sh` in verification process section

**Checkpoint**: At this point, basic enforcement should block commits with failing tests and low coverage

---

## Phase 4: User Story 2 - Skip Decorator Detection (Priority: P1)

**Goal**: Automated detection of skip decorators to prevent AI agents from circumventing failing tests

**Independent Test**: Create test file with `@pytest.mark.skip` decorator and verify `scripts/detect-skip-abuse.py` detects it; add to pre-commit hook and verify commit is blocked

**GitHub Issue**: #13 - AST-based skip detection following `scripts/verify_migration_001.py` patterns (using scripts/ directory)

**Dependencies**: US1 (needs pre-commit infrastructure)

### Tests for User Story 2

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T012 [P] [US2] Unit test for skip detector in tests/enforcement/test_skip_detector.py - test `@skip` detection
- [X] T013 [P] [US2] Unit test in tests/enforcement/test_skip_detector.py - test `@skipif` detection
- [X] T014 [P] [US2] Unit test in tests/enforcement/test_skip_detector.py - test `@pytest.mark.skip` detection
- [X] T015 [P] [US2] Unit test in tests/enforcement/test_skip_detector.py - test skip with no reason (violation)
- [X] T016 [P] [US2] Unit test in tests/enforcement/test_skip_detector.py - test skip with strong justification (allowed if policy changes)
- [X] T017 [P] [US2] Unit test in tests/enforcement/test_skip_detector.py - test nested decorators handling
- [X] T018 [P] [US2] Unit test in tests/enforcement/test_skip_detector.py - test non-test file handling (no false positives)
- [X] T019 [P] [US2] Unit test in tests/enforcement/test_skip_detector.py - test performance <100ms on large files

### Implementation for User Story 2

- [X] T020 [US2] Create `tests/enforcement/` directory for enforcement tool tests
- [X] T021 [US2] Create `scripts/detect-skip-abuse.py` with shebang, docstring, and CLI using argparse (issue #13)
- [X] T022 [US2] Implement `SkipDetectorVisitor` class using `ast.NodeVisitor` to walk AST and find skip decorators in `scripts/detect-skip-abuse.py` (issue #13)
- [X] T023 [US2] Add skip pattern detection: `@skip`, `@skipif`, `@pytest.mark.skip`, `@pytest.mark.skipif` to `scripts/detect-skip-abuse.py` (issue #13)
- [X] T024 [US2] Add justification checking to `scripts/detect-skip-abuse.py`: extract reason argument and check for weak justifications (TODO, fix later, etc.) (issue #13)
- [X] T025 [US2] Add helper functions to `scripts/detect-skip-abuse.py`: `check_file()`, `is_test_file()`, `format_violation()`, `print_summary()` following `scripts/verify_migration_001.py` patterns (issue #13)
- [X] T026 [US2] Make `scripts/detect-skip-abuse.py` executable with `chmod +x`
- [X] T027 [US2] Add local hook to `.pre-commit-config.yaml` for skip detection with entry `python scripts/detect-skip-abuse.py` and `files: ^tests/.*\.py$` pattern (issue #13)
- [X] T028 [US2] Update TESTING.md with new "Test Skip Policy & Enforcement" section explaining why skips are forbidden and what to do instead (issue #13)
- [X] T029 [US2] Update CONTRIBUTING.md to reference skip policy and add "Fixing Failing Tests" subsection (issue #13)
- [X] T030 [US2] Update docs/process/TDD_WORKFLOW.md with "Fixing Failing Tests" section (issue #13)
- [X] T031 [US2] Test all 8 unit tests pass for skip detector

**Checkpoint**: Skip decorator detection should now prevent test circumvention via pre-commit hooks

---

## Phase 5: User Story 3 - Quality Ratchet System (Priority: P1)

**Goal**: Automated quality metric tracking across sessions to detect context window degradation before it causes problems

**Independent Test**: Run `python scripts/quality-ratchet.py record --response-count 5`, then `check` command, verify degradation detection works; simulate quality drop and verify alert

**GitHub Issue**: #14 - Quality tracking using Typer + Rich, parsing pytest-json-report and coverage.json (using scripts/ directory)

**Dependencies**: US1 (needs test infrastructure)

### Tests for User Story 3

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T032 [P] [US3] Unit test for quality ratchet in tests/enforcement/test_quality_ratchet.py - test `record` command creates history entry
- [ ] T033 [P] [US3] Unit test in tests/enforcement/test_quality_ratchet.py - test `check` command detects degradation >10%
- [ ] T034 [P] [US3] Unit test in tests/enforcement/test_quality_ratchet.py - test `stats` command formats Rich Table output correctly
- [ ] T035 [P] [US3] Unit test in tests/enforcement/test_quality_ratchet.py - test `reset` command clears history
- [ ] T036 [P] [US3] Unit test in tests/enforcement/test_quality_ratchet.py - test moving average calculation (last 3 checkpoints)
- [ ] T037 [P] [US3] Unit test in tests/enforcement/test_quality_ratchet.py - test peak quality detection algorithm
- [ ] T038 [P] [US3] Unit test in tests/enforcement/test_quality_ratchet.py - test JSON persistence to `.claude/quality_history.json`
- [ ] T039 [P] [US3] Unit test in tests/enforcement/test_quality_ratchet.py - test handles missing history file gracefully

### Implementation for User Story 3

- [X] T040 [US3] Create `scripts/quality-ratchet.py` with Typer app and Rich Console (NOT argparse - see issue #14)
- [X] T041 [US3] Implement core functions in `scripts/quality-ratchet.py`: `load_history()`, `save_history()`, `run_tests()`, `get_coverage()` (issue #14)
- [X] T042 [US3] Add `run_tests()` to execute pytest with `--json-report --json-report-file` and parse `.report.json` for metrics (issue #14)
- [X] T043 [US3] Add `get_coverage()` to read `coverage.json` and extract `totals.percent_covered` (issue #14)
- [X] T044 [US3] Implement `detect_degradation()` with algorithm: recent_avg < peak - 10% for coverage and pass rate (issue #14)
- [X] T045 [US3] Implement `record` command using `@app.command()` decorator with `--response-count` option (issue #14)
- [X] T046 [US3] Implement `check` command to load history and call `detect_degradation()` (issue #14)
- [X] T047 [US3] Implement `stats` command with Rich Table displaying current/peak/average metrics (issue #14)
- [X] T048 [US3] Implement `reset` command with `--yes` confirmation flag (issue #14)
- [X] T049 [US3] Create `.claude/quality_history.json` with empty history array (issue #14)
- [X] T050 [US3] Make `scripts/quality-ratchet.py` executable with `chmod +x`
- [X] T051 [US3] Update CLAUDE.md with "Quality Ratchet Checkpoints" section after Commands section (issue #14)
- [X] T052 [US3] Update TESTING.md with "Quality Ratchet Integration" section and Test 11 subsections (issue #14)
- [X] T053 [US3] Create `.github/workflows/quality-check.yml` for automated quality tracking in CI/CD, reference `scripts/quality-ratchet.py` (issue #14)
- [X] T054 [US3] Test all 8 unit tests pass for quality ratchet

**Checkpoint**: Quality tracking should now detect degradation and recommend context resets

---

## Phase 6: User Story 4 - Comprehensive Test Template (Priority: P2)

**Goal**: Provide reference test template so AI agents have concrete examples of best practices

**Independent Test**: Review `tests/test_template.py` and verify it contains all required patterns; AI agents can reference it for examples

**GitHub Issue**: #15 - Test template with Hypothesis property-based testing, parametrized tests, fixtures

**Dependencies**: None (can run in parallel with other stories)

### Implementation for User Story 4

- [ ] T057 [P] [US4] Create `tests/test_template.py` with comprehensive module-level docstring explaining purpose and patterns (issue #15)
- [ ] T058 [P] [US4] Add `TestTraditionalUnitTests` class with specific known input/output tests and error handling examples (issue #15)
- [ ] T059 [P] [US4] Add `TestParametrizedTests` class using `@pytest.mark.parametrize` with boundary value examples (issue #15)
- [ ] T060 [P] [US4] Add `TestPropertyBasedTests` class with Hypothesis strategies: idempotent, commutative, type stability, length preservation (issue #15)
- [ ] T061 [P] [US4] Add `TestFixtureUsage` class demonstrating fixtures from conftest.py and fixture composition (issue #15)
- [ ] T062 [P] [US4] Add `TestIntegrationPatterns` class with `@pytest.mark.integration` for multi-step workflows (issue #15)
- [ ] T063 [P] [US4] Add `TestAsyncPatterns` class with `@pytest.mark.asyncio` for async function testing (issue #15)
- [ ] T064 [P] [US4] Add helper functions: `reverse_string()`, `add_numbers()`, `normalize_data()` for testing examples (issue #15)
- [ ] T065 [P] [US4] Add pattern coverage matrix docstring with table showing when to use each pattern (issue #15)
- [X] T066 [US4] Update AGENTS.md with "Writing Tests" section referencing test_template.py (issue #15)
- [X] T067 [US4] Update TESTING.md with "Test Pattern Reference" section at beginning (issue #15)
- [X] T068 [US4] Update CLAUDE.md with "Testing Standards" section after Code Style (issue #15)
- [X] T069 [US4] Create `.claude/rules.md` testing standards section if not already created in US1 (issue #15)
- [X] T070 [US4] Verify all template examples execute successfully with `pytest tests/test_template.py -v`

**Checkpoint**: Test template should provide comprehensive examples for AI agents to follow

---

## Phase 7: User Story 5 - Enhanced Verification and Reporting (Priority: P1)

**Goal**: Comprehensive verification with detailed reports for complete confidence in code quality

**Independent Test**: Run `scripts/verify-ai-claims.sh` and verify it completes in <30 seconds with detailed multi-step report; intentionally introduce violations and verify detection

**GitHub Issue**: #16 - Shell script with colored output, artifacts storage, git integration (using scripts/ directory)

**Dependencies**: US1 (foundation), US2 (skip detection)

### Tests for User Story 5

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T071 [P] [US5] Integration test in tests/enforcement/test_verification_script.py - test script exits 0 when all checks pass
- [ ] T072 [P] [US5] Integration test in tests/enforcement/test_verification_script.py - test script exits 1 when any check fails
- [ ] T073 [P] [US5] Integration test in tests/enforcement/test_verification_script.py - test report includes all verification steps
- [ ] T074 [P] [US5] Integration test in tests/enforcement/test_verification_script.py - test execution time <30 seconds

### Implementation for User Story 5

- [ ] T075 [US5] Expand `scripts/verify-ai-claims.sh` with shebang, color codes, exit code constants (issue #16)
- [ ] T076 [US5] Add configuration variables to `scripts/verify-ai-claims.sh`: `COVERAGE_THRESHOLD=85`, `ARTIFACTS_DIR="artifacts/verify/$(date +%Y%m%d_%H%M%S)"` (issue #16)
- [ ] T077 [US5] Implement Step 1 in verification script: Run test suite with pytest verbose output and JSON report to artifacts directory (issue #16)
- [ ] T078 [US5] Implement Step 2 in verification script: Check coverage with pytest-cov, compare against 85% threshold, save HTML report to artifacts (issue #16)
- [ ] T079 [US5] Implement Step 3 in verification script: Detect skip decorator abuse by calling `scripts/detect-skip-abuse.py` (issue #16)
- [ ] T080 [US5] Implement Step 4 in verification script: Run code quality checks (black --check, ruff check, mypy) and save results (issue #16)
- [ ] T081 [US5] Implement Step 5 in verification script: Generate comprehensive verification report in markdown format with emoji indicators (issue #16)
- [ ] T082 [US5] Add command-line options to `scripts/verify-ai-claims.sh`: `--no-fail-fast`, `--skip-tests`, `--skip-coverage`, `--skip-quality`, `--help` (issue #16)
- [ ] T083 [US5] Add performance optimizations to verification script: parallel pytest execution, caching, progress indicators (issue #16)
- [ ] T084 [US5] Create `.gitmessage` template with AI verification checklist using Conventional Commits format (issue #16)
- [ ] T085 [US5] Add git config command to `scripts/verify-ai-claims.sh`: `git config commit.template .gitmessage` (issue #16)
- [ ] T086 [US5] Update README.md with "AI Verification Workflow" section referencing `scripts/verify-ai-claims.sh` (issue #16)
- [ ] T087 [US5] Update TESTING.md with "AI Verification Workflow" section with detailed steps and examples (issue #16)
- [ ] T088 [US5] Test all 4 integration tests pass for verification script

**Checkpoint**: Comprehensive verification should provide detailed reporting in <30 seconds

---

## Phase 8: User Story 6 - Context Management System (Priority: P2)

**Goal**: Systematic context reset mechanisms so quality remains consistent across long conversations

**Independent Test**: Simulate 20 AI responses with quality tracking, verify checkpoint system triggers at response 5, 10, 15, 20; test context handoff template workflow

**GitHub Issue**: #17 - Context management with detailed template from traycer.ai recommendations

**Dependencies**: US3 (quality-ratchet for detection)

### Implementation for User Story 6

- [ ] T089 [P] [US6] Document context rules in `.claude/rules.md`: token budget (~50k), checkpoint frequency (every 5 responses) (issue #17)
- [ ] T090 [P] [US6] Document reset triggers in `.claude/rules.md`: quality drop >10%, response count >15-20, token budget >45k, AI laziness signs (issue #17)
- [ ] T091 [US6] Create context handoff template section in `.claude/rules.md` with all fields from issue #17: completed features, current state, next tasks, test evidence, architecture notes
- [ ] T092 [US6] Add checkpoint system section to `.claude/rules.md` with required actions: full test run, coverage report, "continue or reset?" (issue #17)
- [ ] T093 [US6] Integrate quality-ratchet check into `.claude/rules.md` checkpoint workflow: reference `scripts/quality-ratchet.py check` (issue #17)
- [ ] T094 [US6] Add auto-suggestion logic to `scripts/quality-ratchet.py` check command: recommend reset when degradation detected (issue #17)
- [ ] T095 [US6] Update CLAUDE.md "Context Management for AI Conversations" section with references to rules.md and scripts/quality-ratchet.py (issue #17)
- [ ] T096 [US6] Create example context handoff in `.claude/rules.md` demonstrating template usage (issue #17)
- [ ] T097 [US6] Create `scripts/quality-ratchet-example.json` with example metrics for testing (issue #17)
- [ ] T098 [US6] Test context handoff template workflow manually (simulate long conversation with checkpoints)

**Checkpoint**: Context management should enable smooth quality maintenance across conversation resets

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T099 [P] Update `CLAUDE.md` "Commands" section to reference all new scripts (scripts/verify-ai-claims.sh, scripts/quality-ratchet.py, scripts/detect-skip-abuse.py)
- [ ] T100 [P] Update `README.md` "Documentation" section with links to new enforcement documentation
- [ ] T101 [P] Create `docs/AI_ENFORCEMENT.md` with comprehensive user guide and examples
- [ ] T102 Run full test suite to verify all tests pass (should be 93+ existing + new enforcement tests)
- [ ] T103 Run coverage report to verify ≥85% coverage maintained
- [ ] T104 Run `scripts/verify-ai-claims.sh` to validate all enforcement mechanisms work end-to-end
- [ ] T105 Install pre-commit hooks with `pre-commit install`
- [ ] T106 Test pre-commit hooks with intentional violations (failing test, low coverage, skip decorator)
- [ ] T107 Verify artifacts directory structure created correctly by verification script

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - US1 (P0): Foundation - must complete first (blocks US2, US5)
  - US2 (P1): Skip Detection - depends on US1 (needs tools/ dir, pre-commit hooks)
  - US3 (P1): Quality Ratchet - depends on US1 (needs test infrastructure)
  - US4 (P2): Test Template - independent, can run in parallel with others after US1
  - US5 (P1): Enhanced Verification - depends on US1, US2 (integrates both)
  - US6 (P2): Context Management - depends on US3 (uses quality-ratchet)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P0)**: Can start after Foundational (Phase 2) - No dependencies on other stories (MVP!)
- **US2 (P1)**: Depends on US1 completion (needs `tools/` directory, pre-commit infrastructure)
- **US3 (P1)**: Depends on US1 completion (needs test infrastructure, `.claude/` directory)
- **US4 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **US5 (P1)**: Depends on US1 and US2 completion (integrates verify-ai-claims.sh and skip detection)
- **US6 (P2)**: Depends on US3 completion (uses quality-ratchet.py for auto-suggestions)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Tools directory before scripts
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

**Setup Phase**:
- T001 and T002 can run in parallel

**Foundational Phase**:
- T004, T005, T006 can all run in parallel

**After US1 Complete**:
- US2 tests (T012-T019) can all run in parallel
- US3 tests (T032-T039) can all run in parallel
- US4 implementation (T057-T065) can all run in parallel with US2/US3 work

**Within US5**:
- T071-T074 tests can all run in parallel

**Within US6**:
- T089-T090 documentation tasks can run in parallel

**Polish Phase**:
- T099, T100, T101 can all run in parallel

---

## Parallel Example: User Story 2 (Skip Detection)

```bash
# Launch all tests for US2 together (after writing them to fail):
Task: "Unit test for skip detector - test @skip detection"
Task: "Unit test - test @skipif detection"
Task: "Unit test - test @pytest.mark.skip detection"
# ... all 8 test tasks (T012-T019) in parallel

# After tests written, implementation proceeds sequentially (T020-T031)
# but documentation updates (T028-T030) can run in parallel
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (3 tasks)
2. Complete Phase 2: Foundational (3 tasks)
3. Complete Phase 3: US1 (5 tasks)
4. **STOP and VALIDATE**: Test enforcement blocks commits with failing tests and low coverage
5. Dogfood on Sprint 9 development

**Total MVP**: 10 tasks (~2-3 hours)

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 → Test independently → Deploy (MVP! - basic enforcement working)
3. Add US2 → Test independently → Deploy (Skip detection active)
4. Add US3 → Test independently → Deploy (Quality tracking active)
5. Add US4 → Test independently → Deploy (Reference templates available)
6. Add US5 → Test independently → Deploy (Comprehensive verification active)
7. Add US6 → Test independently → Deploy (Context management complete)
8. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 (must finish first)
3. Once US1 is done:
   - Developer A: US2 (Skip Detection)
   - Developer B: US3 (Quality Ratchet)
   - Developer C: US4 (Test Template - independent)
4. Once US2 and US3 are done:
   - Developer A: US5 (Enhanced Verification - needs US2)
   - Developer B: US6 (Context Management - needs US3)
5. Stories complete and integrate independently

---

## Performance Targets

| Component | Target | Task Reference |
|-----------|--------|----------------|
| Skip detector | <100ms | T019, T022 |
| Quality ratchet check | <50ms | T033, T044 |
| Verification script | <30s total | T074, T083 |
| Pre-commit hooks | <5s overhead | T008, T027 |

---

## Key Code Recommendations Incorporated

### From Issue #13 (Skip Detector):
- ✅ Use `scripts/` directory (per user preference)
- ✅ AST module with `ast.NodeVisitor` class
- ✅ Follow `scripts/verify_migration_001.py` output patterns
- ✅ Pre-commit hook with `files: ^tests/.*\.py$` pattern
- ✅ Update TESTING.md, CONTRIBUTING.md, TDD_WORKFLOW.md

### From Issue #14 (Quality Ratchet):
- ✅ Use **Typer + Rich** (not argparse)
- ✅ Parse pytest-json-report (`.report.json`)
- ✅ Parse `coverage.json` for `totals.percent_covered`
- ✅ Use `scripts/` directory (per user preference)
- ✅ GitHub Actions workflow `.github/workflows/quality-check.yml`
- ✅ Update CLAUDE.md and TESTING.md

### From Issue #15 (Test Template):
- ✅ Hypothesis property-based testing patterns
- ✅ Pattern coverage matrix
- ✅ Update AGENTS.md, TESTING.md, CLAUDE.md
- ✅ Create `.claude/rules.md` testing standards

### From Issue #16 (Enhanced Verification):
- ✅ Shell script with colored output
- ✅ Artifacts directory: `artifacts/verify/YYYYMMDD_HHMMSS/`
- ✅ Git commit template `.gitmessage`
- ✅ Git config command integration
- ✅ Performance optimizations
- ✅ Use `scripts/` directory (per user preference)
- ✅ Update README.md and TESTING.md

### From Issue #17 (Context Management):
- ✅ Detailed context handoff template from issue
- ✅ Checkpoint system every 5 responses
- ✅ Integration with quality-ratchet.py
- ✅ Example metrics file
- ✅ Update CLAUDE.md

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- **ALL GitHub Issues #12-17 code recommendations have been incorporated**
- This feature enforces Constitution Principle I (Test-First Development)

---

**Total Tasks**: 107 tasks across 6 user stories
**Estimated Effort**: 16-23 hours (per SPRINTS.md)
**MVP Scope**: US1 only (T001-T011) - ~2-3 hours
**Full Feature**: All user stories (T001-T107) - ~16-23 hours
