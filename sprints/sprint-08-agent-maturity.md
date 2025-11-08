# Sprint 8: Agent Maturity

**Status**: ⚠️ Schema Only
**Duration**: Week 8 (Planned)
**Epic/Issues**: cf-36 through cf-39 (Need new IDs)

## Goal
Enable agents to learn and improve over time, graduating from detailed instructions to autonomous operation.

## User Story
As a developer, I want to watch agents graduate from needing detailed instructions to working autonomously as they gain experience.

## Planned Tasks

### Core Features (P0)
- [ ] **cf-NEW-36**: Agent metrics tracking (Status: Schema exists, never populated)
  - Track success rate, blockers, tests, rework
  - Store in agents.metrics JSON field (field exists)
  - Update after each task
  - Demo: Metrics visible in dashboard

- [ ] **cf-NEW-37**: Maturity assessment logic (Status: Stub with TODO)
  - Calculate maturity based on metrics
  - Promote/demote based on performance
  - Store maturity level in DB (field exists)
  - NOTE: WorkerAgent.assess_maturity() exists but has TODO (worker_agent.py:45-47)
  - Demo: Agent auto-promotes after good performance

- [ ] **cf-NEW-38**: Adaptive task instructions (Status: Not started)
  - D1 (Directing): Detailed step-by-step
  - D2 (Coaching): Guidance + examples
  - D3 (Supporting): Minimal instructions
  - D4 (Delegating): Goal only
  - Demo: Instructions change based on maturity

### Enhancements (P1)
- [ ] **cf-NEW-39**: Maturity visualization (Status: Not started)
  - Show current maturity level
  - Display metrics chart
  - Show progression history
  - Demo: See agent growth over time

## Definition of Done
- [ ] Metrics tracked for all agents (success rate, blocker frequency, test pass rate, rework rate)
- [ ] Maturity levels auto-adjust based on performance
- [ ] Task instructions adapt to maturity (D1/D2/D3/D4 templates)
- [ ] Dashboard shows maturity and metrics
- [ ] Agents become more autonomous over time (measured over 20+ tasks)
- [ ] Working demo of agent progressing from D1 → D3

## Current Status

**What Exists**:
- Database field: `agents.maturity_level` (created in database.py:132)
- Database field: `agents.metrics` (JSON, for tracking performance)
- Enum: `AgentMaturity` with values D1/D2/D3/D4 (in models.py)
- Stub method: WorkerAgent.assess_maturity() (currently just `pass` with TODO)

**What's Missing**:
- Metrics collection logic (agents.metrics field never updated)
- Maturity calculation algorithm (assess_maturity() is empty)
- Promotion/demotion triggers (no threshold logic)
- Adaptive instruction templates (no D1/D2/D3/D4 prompt variations)
- UI components for maturity visualization
- Performance tracking over time

## Implementation Notes
**Blockers**:
- Issue IDs cf-36 through cf-39 not yet created in beads tracker
- Need to define maturity thresholds (e.g., D1→D2 requires 10 tasks, 80% success)

**Architecture Decisions**:
- Maturity calculation: TBD (weighted formula vs. rule-based promotion)
- Demotion policy: TBD (single failure vs. trend-based)
- Instruction templates: TBD (system prompt variations vs. dynamic generation)
- Metrics to track: Success rate, blocker frequency, test pass rate, rework rate (confirmed)

**Dependencies**: Sprint 6 (Human in the Loop) recommended but not required

## References
- **Feature Specs**: (Will be created in specs/008-agent-maturity/)
- **Dependencies**: Sprint 5 (Async Worker Agents) - COMPLETE
- **Database Schema**: codeframe/database/schema.py lines 130-145
- **Stub Code**: codeframe/agents/worker_agent.py lines 45-47
- **Model Enum**: codeframe/models/agent.py (AgentMaturity enum)
