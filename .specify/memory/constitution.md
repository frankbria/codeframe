# CodeFRAME Constitution

<!--
Sync Impact Report - Constitution v1.0.0

Version Change: INITIAL → 1.0.0 (initial ratification)
Modified Principles: N/A (initial version)
Added Sections: All core principles, development workflow, governance
Removed Sections: N/A

Templates Requiring Updates:
✅ plan-template.md - Constitution Check section aligned
✅ spec-template.md - Requirements aligned with test-first principle
✅ tasks-template.md - Task organization reflects async + test-first patterns
✅ Agent templates - Ready for use with constitution

Follow-up TODOs: None
-->

## Core Principles

### I. Test-First Development (NON-NEGOTIABLE)

Test-Driven Development is mandatory for all features:
- Tests MUST be written before implementation code
- Tests MUST fail initially, demonstrating the gap being filled
- Implementation proceeds only after user approval of failing tests
- Red-Green-Refactor cycle is strictly enforced

**Rationale**: TDD ensures requirements clarity, prevents regression, and builds confidence in autonomous agent execution. Without tests-first, agents may implement features that don't match user intent.

### II. Async-First Architecture

All I/O-bound operations MUST use Python's async/await pattern:
- Worker agents execute tasks concurrently using AsyncAnthropic
- No blocking synchronous calls in agent execution paths
- Event loops managed explicitly to prevent deadlocks
- WebSocket broadcasts use async patterns

**Rationale**: True concurrency enables multiple agents to work simultaneously. Sprint 5 demonstrated 30-50% performance improvement through async conversion. Blocking operations would bottleneck the multi-agent system.

### III. Context Efficiency

Agent context management follows the Virtual Project system:
- Hot tier (always loaded): Current task, active files, latest test results
- Warm tier (on-demand): Related files, project structure, PRD sections
- Cold tier (archived): Completed tasks, resolved issues, old versions
- Importance scoring determines tier placement (0.0-1.0 scale)

**Rationale**: Token efficiency is critical for long-running autonomous execution. The Virtual Project system (inspired by React's Virtual DOM) reduces token usage by 30-50% and prevents context pollution.

### IV. Multi-Agent Coordination

Agent collaboration follows hierarchical patterns:
- Lead Agent coordinates all work through shared SQLite state
- Worker agents (Backend, Frontend, Test) execute independently
- No direct agent-to-agent communication
- Dependency resolution via DAG (Directed Acyclic Graph)

**Rationale**: Centralized coordination prevents race conditions and ensures consistent project state. Shared-nothing architecture enables true parallelism.

### V. Observability & Traceability

All agent actions MUST be observable and traceable:
- WebSocket broadcasts for real-time dashboard updates
- SQLite changelog tracks every state mutation
- Git auto-commits after task completion with conventional commit messages
- Structured logging with agent ID, task ID, and timestamp

**Rationale**: Autonomous systems require transparency. Users must understand what agents are doing and be able to audit decisions. Observability enables debugging and trust.

### VI. Type Safety

Static type checking enforced across the codebase:
- Python: Type hints required for all function signatures (enforced by mypy)
- TypeScript: Strict mode enabled, no `any` types without justification
- React: Props interfaces defined for all components
- Database: Schema validation at runtime (Pydantic models)

**Rationale**: Type safety catches errors early and provides self-documenting code. Critical for multi-agent systems where agents modify shared code.

### VII. Incremental Delivery

Features MUST be deliverable in independent, testable slices:
- User stories prioritized (P1, P2, P3...) from critical to enhancement
- Each story independently testable and deployable
- MVP-first approach: P1 story delivers core value
- No monolithic "all-or-nothing" releases

**Rationale**: Incremental delivery reduces risk, enables faster feedback, and allows partial deployment. Essential for autonomous development where agents work in parallel.

## Development Workflow

### Sprint Execution

All work organized into time-boxed sprints:
- Sprint planning documents in `sprints/sprint-NN-name.md`
- Feature specifications in `specs/###-feature-name/`
- Sprint duration: 1-2 weeks typical
- Retrospectives documented in sprint summaries

### Specification Process

Features follow the `/speckit.*` command workflow:
1. `/speckit.specify` - Create feature specification with user stories
2. `/speckit.plan` - Generate implementation plan with research
3. `/speckit.tasks` - Generate actionable task list organized by user story
4. `/speckit.implement` - Execute tasks with agent coordination
5. `/speckit.checklist` - Validate feature completion

### Quality Gates

Before merging any feature branch:
- ✅ All tests passing (backend: pytest, frontend: jest/vitest)
- ✅ Type checking passes (mypy, tsc --noEmit)
- ✅ Linting clean (ruff for Python, eslint for TypeScript)
- ✅ Constitution compliance verified
- ✅ Documentation updated (README, CLAUDE.md if architecture changes)

### Git Conventions

Commit messages follow Conventional Commits:
- `feat: add user authentication`
- `fix: resolve WebSocket reconnection bug`
- `docs: update async migration guide`
- `test: add integration tests for Lead Agent`
- `refactor: extract context manager to separate module`

## Security & Privacy

### API Key Management

Sensitive credentials MUST NOT be committed:
- Store in `.env` files (gitignored)
- Use environment variables for runtime access
- Never hardcode API keys in source code
- Anthropic API key required: `ANTHROPIC_API_KEY`

### Data Privacy

All project data remains local:
- SQLite database: `.codeframe/state.db`
- Checkpoints: `.codeframe/checkpoints/`
- No data sent to external servers (except LLM provider APIs)
- User code never leaves the local machine

## Performance Standards

### Response Time

Agent operations MUST meet performance targets:
- Task assignment: <500ms
- WebSocket broadcast: <100ms
- Dashboard query: <200ms
- Context tier lookup: <50ms

### Concurrency

System MUST support concurrent execution:
- Up to 10 worker agents executing simultaneously
- 100+ WebSocket connections for dashboard monitoring
- Async operations prevent thread pool exhaustion
- No blocking calls in hot paths

## Governance

### Amendment Process

Constitution changes require:
1. Document proposed change in GitHub issue
2. Justify change with specific problem being solved
3. Update constitution with version increment (semantic versioning)
4. Propagate changes to all dependent templates
5. Update CLAUDE.md if development guidelines affected
6. Commit with message: `docs: amend constitution to vX.Y.Z (description)`

### Versioning Policy

Constitution follows semantic versioning:
- **MAJOR**: Backward-incompatible principle changes or removals
- **MINOR**: New principle added or materially expanded guidance
- **PATCH**: Clarifications, wording fixes, non-semantic refinements

### Compliance Review

All pull requests MUST:
- Reference this constitution in PR description
- Demonstrate compliance with core principles
- Justify any complexity added (see Complexity Tracking in plan.md)
- Include tests that validate principle adherence

### Enforcement

Constitution violations block merge:
- Automated checks: tests, type checking, linting (pre-commit hooks)
- Manual review: architecture decisions, complexity justification
- Lead Agent verifies compliance before task completion
- Review Agent flags violations in code review

### Guidance Documents

For runtime development guidance, see:
- **CLAUDE.md**: AI assistant development guidelines
- **AGENTS.md**: Documentation navigation for AI agents
- **CODEFRAME_SPEC.md**: Complete technical specification
- **SPRINTS.md**: Sprint timeline and execution guidelines

**Version**: 1.0.0 | **Ratified**: 2025-01-19 | **Last Amended**: 2025-01-19
