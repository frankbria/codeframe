# CodeFRAME Sprint Planning

**Current Sprint**: [Sprint 8: AI Quality Enforcement](#sprint-8-ai-quality-enforcement-) 📋 Planned
**Project Status**: Sprint 7 Complete - Context Management Delivered

---

## Sprint Overview

| Sprint | Name | Status | Duration | Key Deliverables | Issues |
|--------|------|--------|----------|------------------|--------|
| 0 | Foundation | ✅ Complete | Setup | Repo, spec, architecture docs | cf-1 to cf-4 |
| 1 | Hello CodeFRAME | ✅ Complete | Week 1 | Dashboard, Lead Agent, Database | cf-5 to cf-13 |
| 2 | Socratic Discovery | ✅ Complete | Week 2 | Chat interface, PRD generation, Task decomposition | cf-14 to cf-29 |
| 3 | Single Agent Execution | ✅ Complete | Week 3 | Backend Worker Agent, Self-correction, Git integration | cf-41 to cf-46 |
| 4 | Multi-Agent Coordination | ✅ Complete | Week 4 | Parallel execution, Dependency resolution, Agent pool | Phase 1-4 |
| 4.5 | Project Schema Refactoring | ✅ Complete | Interim | Schema normalization, TypeScript types | cf-f03 to cf-73z |
| 5 | Async Worker Agents | ✅ Complete | Week 5 | Async/await migration, AsyncAnthropic, Performance boost | cf-48 |
| 6 | Human in the Loop | ✅ Complete | Week 6 | Blocker creation, Resolution UI, Agent resume | PR #18 |
| 7 | Context Management | ✅ Complete | Week 7 | Flash memory, Tier assignment, Context pruning | PR #19 |
| 8 | AI Quality Enforcement | 📋 Planned | Week 8 | Rules, pre-commit hooks, quality tracking, verification | #12-17 |
| 9 | E2E Testing Framework | 📋 Planned | Week 9 | Playwright setup, user workflow tests, CI integration | Planned |
| 10 | Final Polish | 📋 Planned | Week 10 | Review agent, Documentation, Performance tuning | Planned |
| ∞ | Agent Maturity | 🔮 Future | TBD | Maturity levels, Promotion logic, Checkpoints | Future |

---

## Quick Links

### Active Development
- 📍 [Current Sprint: Sprint 8](#sprint-8-ai-quality-enforcement-) - AI Quality Enforcement (Planned)
- 🔍 [Beads Issue Tracker](.beads/) - Run `bd list` for current tasks
- 📚 [Documentation Guide](AGENTS.md) - How to navigate project docs

### Completed Work
- [Sprint 7: Context Management](sprints/sprint-07-context-mgmt.md) - Latest completed sprint
- [Sprint 6: Human in the Loop](sprints/sprint-06-human-loop.md)
- [Sprint 5: Async Workers](sprints/sprint-05-async-workers.md)
- [Sprint 4: Multi-Agent Coordination](sprints/sprint-04-multi-agent.md)
- [Sprint 3: Single Agent Execution](sprints/sprint-03-single-agent.md)
- [Sprint 2: Socratic Discovery](sprints/sprint-02-socratic-discovery.md)
- [Sprint 1: Hello CodeFRAME](sprints/sprint-01-hello-codeframe.md)
- [Sprint 0: Foundation](sprints/sprint-00-foundation.md)

### Planning & Architecture
- [Future Roadmap](#future-sprints) - Sprints 8-10 overview
- [Architecture Spec](CODEFRAME_SPEC.md) - Overall system design
- [Feature Specifications](specs/) - Detailed feature implementation guides

### Development Standards
- [Agent Documentation Guide](AGENTS.md) - How to navigate docs
- [Project Guidelines](CLAUDE.md) - Coding standards and conventions
- [Testing Standards](TESTING.md) - Test requirements and procedures
- [Contributing Guide](CONTRIBUTING.md) - How to contribute

---

## Completed Sprints

### Sprint 7: Context Management ✅ (Latest)

**Goal**: Flash memory system for efficient context management with tiered importance scoring

**Delivered**:
- ✅ Context item storage with importance scoring
- ✅ Tiered memory system (HOT/WARM/COLD)
- ✅ Flash save mechanism for context pruning
- ✅ Hybrid exponential decay algorithm
- ✅ Multi-agent context support (project_id + agent_id)
- ✅ Token counting with tiktoken
- ✅ Dashboard context viewer components
- ✅ 31 comprehensive tests (100% passing)

**Key Metrics**:
- Tests: 31 passing (25 backend + 6 frontend)
- Token Reduction: 30-50% after flash save
- Context Tiers: HOT (≥0.8), WARM (0.4-0.8), COLD (<0.4)
- Multi-project: Full support for multiple agents per project

**Links**:
- [Full Sprint Details](sprints/sprint-07-context-mgmt.md)
- [Feature Spec](specs/007-context-management/spec.md)
- [Pull Request #19](https://github.com/frankbria/codeframe/pull/19)

**Commits**: b14c4bd, e92d6f6, 3e29ba2, 7ed9276, cd1a26a

---

### Sprint 6: Human in the Loop ✅

**Goal**: Enable agents to ask for help when blocked and resume work after receiving answers

**Delivered**:
- ✅ Blocker creation in all worker agents (Backend, Frontend, Test)
- ✅ Database schema with project_id support (migration 003)
- ✅ Blocker API endpoints (list, get, resolve)
- ✅ Dashboard UI components (BlockerPanel, BlockerModal, BlockerBadge)
- ✅ WebSocket real-time notifications
- ✅ SYNC vs ASYNC blocker handling
- ✅ Webhook notifications for critical blockers
- ✅ Blocker expiration cron job (24h timeout)
- ✅ 34+ test files with 100+ comprehensive tests

**Key Metrics**:
- Tests: All passing (100%)
- Coverage: Complete blocker lifecycle coverage
- Components: 3 new React components + 3 agent methods
- API: 5 new endpoints

**Links**:
- [Full Sprint Details](sprints/sprint-06-human-loop.md)
- [Feature Spec](specs/049-human-in-loop/spec.md)
- [Pull Request #18](https://github.com/frankbria/codeframe/pull/18)

**Commits**: 586df44 (merge), a038924, d482547, 25e8da6, 72f5684

---

### Sprint 5: Async Worker Agents ✅

**Goal**: Convert worker agents to async/await pattern for true concurrent execution

**Delivered**:
- ✅ Async migration of all 3 worker agents (Backend, Frontend, Test)
- ✅ AsyncAnthropic client integration
- ✅ Removed threading overhead from LeadAgent
- ✅ 30-50% performance improvement
- ✅ 93/93 tests passing after migration

**Key Metrics**:
- Tests: 93 passing (100%)
- Performance: 30-50% faster concurrent execution
- Breaking changes: Python 3.11+ required

**Links**:
- [Full Sprint Details](sprints/sprint-05-async-workers.md)
- [Feature Spec](specs/048-async-worker-agents/spec.md)
- [Beads Issue](https://github.com) - cf-48
- [Pull Request #11](https://github.com/frankbria/codeframe/pull/11)

**Commits**: 9ff2540, 324e555, b4b61bf, debcf57

---

### Sprint 4.5: Project Schema Refactoring ✅

**Goal**: Normalize database schema and improve type safety

**Delivered**:
- ✅ Schema normalization (projects, tasks, agents tables)
- ✅ TypeScript type definitions
- ✅ Migration scripts with zero data loss
- ✅ 21 tests covering all schema changes

**Links**: [Sprint Details](sprints/sprint-04.5-project-schema.md) | Spec: specs/005-project-schema-refactoring/

**Commits**: 78f6a0b, c2e8a3f, 80384f1, 5a208c8, 7e7727d, 1131fc5

---

### Sprint 4: Multi-Agent Coordination ✅

**Goal**: Multiple agents work in parallel with dependency resolution

**Delivered**:
- ✅ 3 agent types working (Backend, Frontend, Test)
- ✅ Parallel execution with AgentPoolManager
- ✅ Task dependency resolution (DAG-based)
- ✅ Dashboard shows all agents in real-time
- ✅ 118 tests passing (98% pass rate)

**Links**: [Sprint Details](sprints/sprint-04-multi-agent.md) | Spec: specs/004-multi-agent-coordination/

**Commits**: cc8b46e, ce2bfdb, 8b7d692, b7e868b

---

### Sprint 3: Single Agent Execution ✅

**Goal**: Backend worker agent with LLM-powered code generation and self-correction

**Delivered**:
- ✅ Backend Worker Agent with Anthropic integration
- ✅ Test runner with pytest execution
- ✅ Self-correction loop (max 3 attempts)
- ✅ Git auto-commit functionality
- ✅ Real-time WebSocket updates
- ✅ 37 tests + integration tests

**Links**: [Sprint Details](sprints/sprint-03-single-agent.md)

**Commits**: e18f6d6, 3b7081b, ddb495f, 6b9a41f, c91aacb, ef0105e

---

### Sprint 2: Socratic Discovery ✅

**Goal**: Interactive discovery flow with PRD generation and task decomposition

**Delivered**:
- ✅ Chat interface (frontend + backend)
- ✅ Socratic discovery flow (20+ questions)
- ✅ PRD generation from discovery answers
- ✅ Hierarchical task decomposition
- ✅ Project phase tracking
- ✅ Progress indicators
- ✅ 169 backend tests + 54 frontend tests

**Links**: [Sprint Details](sprints/sprint-02-socratic-discovery.md)

**Commits**: 2005c0e, 5e820e2, 3fc2dfc, 466163e, d3bb996, 8004d58, 462cca2

---

### Sprint 1: Hello CodeFRAME ✅

**Goal**: Working dashboard with Lead Agent and real-time status

**Delivered**:
- ✅ FastAPI backend with status server
- ✅ React dashboard with real-time updates
- ✅ MongoDB database with projects/tasks/agents
- ✅ Lead Agent with Anthropic SDK integration
- ✅ WebSocket real-time communication
- ✅ 111 tests passing (92% coverage)

**Links**: [Sprint Details](sprints/sprint-01-hello-codeframe.md)

**Commits**: 4166f2d, e849320, and 10+ others

---

### Sprint 0: Foundation ✅

**Goal**: Project setup and architectural foundation

**Delivered**:
- ✅ Git repository initialized
- ✅ GitHub README with architecture diagrams
- ✅ CODEFRAME_SPEC.md comprehensive specification
- ✅ CI/CD foundations

**Links**: [Sprint Details](sprints/sprint-00-foundation.md)

**Commits**: Initial commits cf-1 to cf-4

---

## Future Sprints

### Sprint 8: AI Quality Enforcement 📋 (Next)

**Goal**: Prevent AI agent failure modes through systematic enforcement

**Planned Features** (Issues #12-17):
- **Foundation** (#12): `.claude/rules.md`, coverage thresholds, pre-commit hooks, verification scripts
- **Skip Detection** (#13): AST-based detection of `@pytest.mark.skip` abuse
- **Quality Ratchet** (#14): Track metrics over time, detect quality degradation, auto-suggest resets
- **Test Template** (#15): Reference templates for unit, property-based, parametrized, integration tests
- **Enhanced Verification** (#16): Comprehensive verification reports with HTML artifacts
- **Context Management** (#17): Token budgets, checkpoint system, context handoff templates

**Success Criteria**:
- Pre-commit hooks block failing tests and low coverage
- Quality tracking prevents degradation in long conversations
- Clear test patterns reduce AI mistakes
- Context resets happen before quality drops

**Status**: Planned - All functionality needs implementation

**Estimated Effort**: 16-23 hours across 6 issues

**Links**: GitHub Issues [#12](https://github.com/frankbria/codeframe/issues/12)-[#17](https://github.com/frankbria/codeframe/issues/17)

---

### Sprint 9: E2E Testing Framework 📋

**Goal**: Comprehensive end-to-end testing with Playwright

**Planned Features**:
- Playwright setup and configuration
- User workflow tests:
  - New project creation flow
  - Socratic discovery conversation
  - Agent task execution
  - Blocker creation and resolution
  - Context management operations
- CI/CD integration
- Visual regression testing
- Performance benchmarking
- Test reporting and artifacts

**Success Criteria**:
- All critical user workflows covered
- Tests run in CI on every PR
- < 5 minutes total E2E test time
- Clear failure reporting with screenshots

**Status**: Planned

**Estimated Effort**: 12-16 hours

---

### Sprint 10: Final Polish 📋

**Goal**: Production readiness with comprehensive quality checks

**Planned Features**:
- Review Agent for code quality checks
- Documentation completeness audit
- Cost tracking and optimization
- Performance tuning and benchmarking
- Security audit
- User experience polish
- Production deployment guide

**Status**: Planned

**Links**: [Sprint Plan](sprints/sprint-10-final-polish.md)

---

## Future Releases

### Agent Maturity System 🔮

**Goal**: Agent promotion system based on performance

**Planned Features**:
- Maturity level tracking (junior → senior → principal)
- Promotion/demotion logic based on success metrics
- Checkpoint system for context recovery
- Performance-based task assignment
- Learning from past mistakes
- Skill specialization tracking

**Status**: Future Release - Data model exists

**Priority**: Low - Core functionality complete, this is enhancement

**Links**: [Sprint Plan](sprints/sprint-future-agent-maturity.md)

---

## Sprint 8: AI Quality Enforcement - Detailed Implementation Plan

### Overview

Sprint 8 addresses GitHub Issues #12-17, implementing systematic enforcement mechanisms to prevent common AI agent failure modes. This sprint builds a foundation of quality controls that will benefit all future development.

### Current State Analysis

**Existing Infrastructure:**
- ✅ `pyproject.toml` with basic pytest config
- ✅ GitHub workflows for Claude Code integration
- ✅ Dev dependencies (pytest, black, ruff, mypy)

**Missing Components (All issues #12-17 unaddressed):**
- ❌ No `.claude/rules.md` for AI enforcement
- ❌ No coverage threshold in `pyproject.toml`
- ❌ No `.pre-commit-config.yaml`
- ❌ No `tools/` directory with verification scripts
- ❌ No skip decorator detection
- ❌ No quality tracking system
- ❌ No test templates
- ❌ No context management system

### Issue-by-Issue Breakdown

#### Issue #12: AI Development Enforcement Foundation (Priority: HIGH)
**Estimated Effort:** 2-3 hours

**Tasks:**
1. Create `.claude/rules.md`:
   - Document TDD requirements
   - List forbidden actions (skip decorators, false claims)
   - Add context management guidelines

2. Configure `pyproject.toml`:
   - Add coverage threshold: 80%
   - Enable branch coverage
   - Configure pytest markers

3. Create `.pre-commit-config.yaml`:
   - Add pytest execution hook
   - Add coverage enforcement hook
   - Add skip decorator detection
   - Add black/ruff formatting

4. Create `tools/verify-ai-claims.sh`:
   - Run full test suite
   - Check coverage threshold
   - Generate pass/fail report
   - Make executable

**Dependencies:** None (foundation layer)

**Success Criteria:**
- Pre-commit hooks block commits with failing tests
- Coverage below 80% blocked
- Verification script provides clear feedback

---

#### Issue #13: Skip Decorator Abuse Detection (Priority: MEDIUM)
**Estimated Effort:** 3-4 hours

**Tasks:**
1. Create `tools/detect-skip-abuse.py`:
   - Use Python AST module to parse test files
   - Detect `@skip`, `@skipif`, `@pytest.mark.skip`
   - Check for justification comments
   - Report file, line, function name

2. Add validation logic:
   - Flag skips with weak/missing reasons
   - Handle false positives gracefully
   - Provide actionable error messages

3. Integration:
   - Add to pre-commit hooks
   - Add to CI/CD pipeline
   - Make script executable
   - Test with various skip patterns

**Dependencies:** Issue #12 (needs pre-commit infrastructure)

**Success Criteria:**
- Detects all skip decorator variations
- Pre-commit hook blocks commits with skips
- No false positives on legitimate code
- Clear error messages explain violations

---

#### Issue #14: Quality Ratchet System (Priority: MEDIUM)
**Estimated Effort:** 4-6 hours

**Tasks:**
1. Create `tools/quality-ratchet.py`:
   - Track metrics: coverage %, test pass rate, response count
   - Store history in `.claude/quality_history.json`
   - Implement degradation detection (>10% drop = alert)
   - CLI interface: `record`, `check`, `stats`, `reset`

2. Metrics collection:
   - Parse pytest output for pass/fail counts
   - Extract coverage percentage
   - Track conversation response count
   - Timestamp each checkpoint

3. Degradation detection:
   - Compare recent average to historical peak
   - Flag coverage drops >10%
   - Flag pass rate drops >10%
   - Recommend context reset when triggered

**Algorithm:**
```python
recent_avg = avg(last_3_checkpoints)
peak_quality = max(all_previous_checkpoints)

if recent_avg < peak_quality - 10%:
    alert("Quality degradation detected")
    recommend("Reset AI context")
```

**Dependencies:** Issue #12 (needs test infrastructure)

**Success Criteria:**
- Automatically detects quality drops
- Provides trend visualizations
- Recommends context resets at right time
- Integrates smoothly with workflow

---

#### Issue #15: Comprehensive Test Template (Priority: LOW)
**Estimated Effort:** 2-3 hours

**Tasks:**
1. Create `tests/test_template.py`:
   - Traditional unit test examples
   - Property-based tests with Hypothesis
   - Parametrized test examples
   - Integration test patterns
   - Proper fixture usage

2. Documentation:
   - Comprehensive docstrings
   - Explain when to use each pattern
   - Add "why" comments throughout
   - Link to pytest/Hypothesis docs

3. Pattern coverage:
   - Idempotent operations
   - Commutative properties
   - Type stability
   - Length preservation
   - Never-crash properties

4. Update `.claude/rules.md` to reference template

**Dependencies:** None (can be done in parallel)

**Success Criteria:**
- Template covers all common patterns
- AI agents can reference successfully
- Reduces test quality issues
- Serves as team reference

---

#### Issue #16: Enhanced Verification and Reporting (Priority: MEDIUM)
**Estimated Effort:** 3-4 hours

**Tasks:**
1. Expand `tools/verify-ai-claims.sh`:
   - Multi-step verification process
   - Run full test suite with verbose output
   - Check coverage against threshold
   - Detect skip decorator abuse
   - Run code quality checks (black, mypy, isort)
   - Verify no unauthorized test modifications

2. Reporting:
   - Create verification summary
   - Save test output to file
   - Generate coverage HTML report
   - List any quality issues found
   - Provide clear pass/fail status

3. Git integration:
   - Create `.gitmessage` template
   - Require test output in commits
   - Add checklist for AI commits

4. Performance:
   - Cache results when possible
   - Run checks in parallel
   - Fail fast on critical errors
   - Progress indicators for slow steps

**Report Format:**
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

**Dependencies:** Issues #12, #13 (needs foundation and skip detection)

**Success Criteria:**
- Single script validates all requirements
- Clear, actionable error messages
- Detailed reports saved for review
- Fast enough for iteration (<30s)

---

#### Issue #17: Context Management System (Priority: LOW)
**Estimated Effort:** 2-3 hours

**Tasks:**
1. Define context rules:
   - Token budget: ~50k per conversation
   - Checkpoint frequency: every 5 responses
   - Establish reset triggers
   - Document handoff process

2. Checkpoint system:
   - Mandatory checkpoint every 5 responses
   - Require full test run
   - Require coverage report
   - Ask "continue or reset?" at checkpoints

3. Create handoff template:
   - Completed features summary
   - Current state and test evidence
   - Known issues
   - Next tasks

4. Automated detection:
   - Integrate with quality-ratchet.py
   - Auto-suggest resets on quality drops
   - Track conversation length
   - Warn at token limits

5. Update `.claude/rules.md` with context limits

**Reset Triggers:**
- Quality drops >10% (via quality-ratchet)
- Response count exceeds 15-20
- Token budget approaches limit (~45k)
- AI shows "laziness" signs

**Dependencies:** Issue #14 (needs quality-ratchet for detection)

**Success Criteria:**
- Context resets happen before degradation
- Handoff process smooth and documented
- Quality consistent across resets
- Token budgets respected

---

### Implementation Order

**Phase 1: Foundation** (Issues #12, #15)
- Set up enforcement infrastructure
- Create test templates
- Establish baseline

**Phase 2: Detection** (Issues #13, #16)
- Add skip detection
- Enhance verification
- Improve reporting

**Phase 3: Monitoring** (Issues #14, #17)
- Add quality tracking
- Implement context management
- Enable continuous improvement

### Total Effort Estimate
- **Minimum:** 16 hours (all issues minimum estimates)
- **Maximum:** 23 hours (all issues maximum estimates)
- **Recommended:** 20 hours (buffer for integration testing)

---

## Sprint Execution Guidelines

### Definition of Done

Every sprint must meet these criteria:

#### Functional Requirements
- [ ] All P0 features implemented and working
- [ ] User story demonstrated successfully
- [ ] No regressions in existing features
- [ ] All beads issues for sprint closed

#### Testing Requirements
- [ ] Unit tests for all new code (≥ 85% coverage)
- [ ] Integration tests for cross-component features
- [ ] All tests passing (100%)
- [ ] Manual testing checklist completed

#### Code Quality
- [ ] Code reviewed (manual or AI-assisted)
- [ ] No TODOs or FIXMEs in production code
- [ ] Documentation updated (README, CLAUDE.md)
- [ ] Git commits follow conventional commit format

#### Integration
- [ ] Backend and frontend integrated (if applicable)
- [ ] WebSocket events working (if applicable)
- [ ] Database migrations applied successfully
- [ ] No breaking changes (or documented if unavoidable)

#### Documentation
- [ ] Sprint file created in `sprints/`
- [ ] Feature spec updated (if in `specs/`)
- [ ] CHANGELOG.md updated with user-facing changes
- [ ] Architecture docs updated if design changed

---

### Testing Standards

#### Unit Testing
- **Coverage Target**: ≥ 85% line coverage
- **Frameworks**: pytest (backend), Jest (frontend)
- **Requirements**:
  - Test happy path and edge cases
  - Test error handling
  - Mock external dependencies (Anthropic API, database)
  - Fast execution (< 5 seconds for unit tests)

#### Integration Testing
- **Scope**: Cross-component interactions
- **Requirements**:
  - Test WebSocket communication
  - Test database persistence
  - Test agent coordination
  - Use test database (not production)

#### Manual Testing
- **When**: Before marking sprint complete
- **Checklist**: See sprint-specific testing checklists
- **Deliverable**: Screen recording or detailed test log

---

### Git Workflow

#### Branching Strategy
- `main` branch is production-ready
- Feature branches: `NNN-feature-name` (e.g., `048-async-worker-agents`)
- Sprint branches: `sprint-N` (optional for multi-feature sprints)

#### Commit Messages
Follow conventional commits format:
```
feat(cf-XX): Add feature description
fix(cf-XX): Fix bug description
test(cf-XX): Add tests for feature
docs(cf-XX): Update documentation
refactor(cf-XX): Refactor code
```

#### Pull Requests
- Title: Match sprint or feature name
- Description: Link to beads issue, spec, and testing evidence
- Requires: All tests passing, code reviewed
- Merge: Squash or merge commit (keep history clean)

---

### Sprint Retrospective

At the end of each sprint, document:

1. **What went well**: Successes and wins
2. **What could improve**: Challenges and bottlenecks
3. **Action items**: Concrete improvements for next sprint
4. **Metrics**: Tests, coverage, performance, velocity

Add retrospective to sprint file in `sprints/sprint-NN-name.md`

---

## Project Metrics

### Cumulative Progress
- **Sprints Completed**: 9 of 11 (82%)
- **Features Delivered**: 35+ major features
- **Tests Written**: 400+ tests
- **Code Coverage**: 90%+ average
- **Commits**: 100+ commits
- **Team Velocity**: ~6-8 features per sprint

### Quality Metrics
- **Test Pass Rate**: 99%+ (occasional flaky tests)
- **Regression Rate**: < 2% (very few regressions)
- **Bug Density**: Low (comprehensive testing catches issues early)
- **Code Review Coverage**: 100% (all PRs reviewed)

### Performance Metrics
- **Dashboard Load Time**: < 2 seconds
- **WebSocket Latency**: < 100ms
- **Task Assignment**: < 200ms
- **Concurrent Agents**: Up to 10 without degradation

---

## Documentation Structure

For detailed navigation guidance, see [AGENTS.md](AGENTS.md).

### Quick Reference

| I need to... | Read this |
|--------------|-----------|
| Know current sprint status | This file (SPRINTS.md) |
| Understand a specific sprint | `sprints/sprint-NN-name.md` |
| Implement a feature | `specs/{feature}/plan.md` |
| See granular tasks | `specs/{feature}/tasks.md` |
| Check architecture | `CODEFRAME_SPEC.md` |
| Learn coding standards | `CLAUDE.md` |
| Navigate documentation | `AGENTS.md` |

---

## Change Log

### 2025-11-08
- Created SPRINTS.md as main sprint index
- Migrated sprint details to individual files in `sprints/`
- Added AGENTS.md for documentation navigation
- Archived AGILE_SPRINTS.md to `docs/archive/`

### Previous
- See individual sprint files for sprint-specific changes
- See CHANGELOG.md for user-facing changes
- See git history for detailed code changes

---

**For detailed sprint information**, see individual sprint files in the `sprints/` directory.

**For feature implementation details**, see the `specs/` directory.

**For documentation navigation help**, see [AGENTS.md](AGENTS.md).
