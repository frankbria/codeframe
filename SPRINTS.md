# CodeFRAME Sprint Planning

**Current Sprint**: [Sprint 7: Context Management](sprints/sprint-07-context-mgmt.md) 📋 Planned
**Project Status**: Sprint 6 Complete - Human-in-the-Loop Delivered

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
| 7 | Context Management | 📋 Planned | Week 7 | Flash memory, Tier assignment, Context pruning | Planned |
| 8 | Agent Maturity | 📋 Planned | Week 8 | Maturity levels, Promotion logic, Checkpoints | Planned |
| 9 | Polish & Review | 📋 Planned | Week 9 | Review agent, E2E tests, Documentation | Planned |

---

## Quick Links

### Active Development
- 📍 [Current Sprint: Sprint 7](sprints/sprint-07-context-mgmt.md) - Context Management (Planned)
- 🔍 [Beads Issue Tracker](.beads/) - Run `bd list` for current tasks
- 📚 [Documentation Guide](AGENTS.md) - How to navigate project docs

### Completed Work
- [Sprint 6: Human in the Loop](sprints/sprint-06-human-loop.md) - Latest completed sprint
- [Sprint 5: Async Workers](sprints/sprint-05-async-workers.md) - Async/await migration
- [Sprint 4: Multi-Agent Coordination](sprints/sprint-04-multi-agent.md) - Parallel execution
- [Sprint 3: Single Agent Execution](sprints/sprint-03-single-agent.md) - Backend worker
- [Sprint 2: Socratic Discovery](sprints/sprint-02-socratic-discovery.md) - Chat & PRD
- [Sprint 1: Hello CodeFRAME](sprints/sprint-01-hello-codeframe.md) - Dashboard & Lead Agent
- [Sprint 0: Foundation](sprints/sprint-00-foundation.md) - Project setup

### Planning & Architecture
- [Future Roadmap](#future-sprints) - Sprints 6-9 overview
- [Architecture Spec](CODEFRAME_SPEC.md) - Overall system design
- [Feature Specifications](specs/) - Detailed feature implementation guides

### Development Standards
- [Agent Documentation Guide](AGENTS.md) - How to navigate docs
- [Project Guidelines](CLAUDE.md) - Coding standards and conventions
- [Testing Standards](TESTING.md) - Test requirements and procedures
- [Contributing Guide](CONTRIBUTING.md) - How to contribute

---

## Completed Sprints

### Sprint 6: Human in the Loop ✅ (Latest)

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

### Sprint 7: Context Management 📋 (Next)

**Goal**: Flash memory system for efficient context management

**Planned Features**:
- Flash memory with tiered importance
- Automatic context pruning
- Context item lifecycle management
- Dashboard context viewer

**Status**: Planned - Database schema exists

**Links**: [Sprint Plan](sprints/sprint-07-context-mgmt.md)

---

### Sprint 8: Agent Maturity 📋

**Goal**: Agent promotion system based on performance

**Planned Features**:
- Maturity level tracking (junior → senior)
- Promotion/demotion logic
- Checkpoint system for recovery
- Performance-based task assignment

**Status**: Planned - Data model exists

**Links**: [Sprint Plan](sprints/sprint-08-agent-maturity.md)

---

### Sprint 9: Polish & Review 📋

**Goal**: Production readiness with review agent and comprehensive testing

**Planned Features**:
- Review Agent for code quality checks
- End-to-end testing suite
- Cost tracking and optimization
- Performance benchmarking

**Status**: Planned

**Links**: [Sprint Plan](sprints/sprint-09-polish.md)

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
- **Sprints Completed**: 8 of 10 (80%)
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
