# Sprint 4: Multi-Agent Coordination

## Overview

**Goal**: Multiple agents work in parallel with dependency resolution

**User Story**: As a developer, I want to watch Backend, Frontend, and Test agents work simultaneously on independent tasks while respecting dependencies.

## Functional Requirements

### Core Features

1. **Multiple Agent Types**
   - Frontend Worker Agent (React/TypeScript code generation)
   - Test Worker Agent (unit test creation and execution)
   - Backend Worker Agent (existing, already implemented in Sprint 3)
   - Lead Agent coordinates all worker agents

2. **Parallel Agent Execution**
   - Multiple agents run concurrently on independent tasks
   - Lead Agent assigns tasks to appropriate agent types
   - No task conflicts between agents
   - Real-time status updates for all agents

3. **Task Dependency Resolution**
   - DAG (Directed Acyclic Graph) traversal for task dependencies
   - Tasks blocked until dependencies complete
   - Automatic unblocking when dependencies resolve
   - Visual indication of waiting/blocked tasks

4. **Agent Assignment System**
   - Automatic agent type selection based on task characteristics
   - Agent pool management (create, reuse, retire agents)
   - Load balancing across agents of same type
   - Integration with simple_assignment.py (from Sprint 3 conclusion)

### Advanced Features (P1 - Optional)

5. **Subagent Spawning**
   - Worker agents can spawn specialist subagents
   - Code reviewers, test runners, accessibility checkers
   - Hierarchical reporting to parent agent
   - Resource management for subagent lifecycle

6. **Claude Code Skills Integration**
   - Integration with Superpowers framework
   - Skills discovery and invocation
   - TDD, debugging, refactoring skills support
   - Skill execution tracking and reporting

7. **Bottleneck Detection**
   - Identify when multiple tasks wait on single dependency
   - Highlight bottlenecks in dashboard
   - Alert in activity feed
   - Suggest parallelization opportunities

## Functional Demo

```bash
# Dashboard shows 3 agents working:

# Backend Agent (green): Task #5 "API endpoints"
# Frontend Agent (yellow): Task #7 "Login UI" (waiting on #5)
# Test Agent (green): Task #6 "Unit tests for utils"

# Activity feed:
# 11:00 - Lead Agent assigned Task #5 to Backend
# 11:00 - Lead Agent assigned Task #6 to Test Agent
# 11:01 - Frontend Agent waiting on Task #5 (dependency)
# 11:05 - Test Agent completed Task #6 ✅
# 11:10 - Backend Agent completed Task #5 ✅
# 11:10 - Frontend Agent started Task #7 (dependency resolved)
# 11:15 - Frontend Agent completed Task #7 ✅

# Progress: 7/40 tasks (17.5%)
```

## Success Metrics

### Definition of Done
- ✅ 3 agent types working (Backend, Frontend, Test)
- ✅ Agents execute tasks in parallel
- ✅ Dependencies respected (tasks wait when needed)
- ✅ Dashboard shows all agents and their tasks
- ✅ Progress bar updates as tasks complete
- ✅ Lead Agent assigns tasks to appropriate agent types
- ✅ Agent pool managed efficiently (no resource leaks)

### Performance Targets
- Support 3-5 concurrent agents without performance degradation
- Task assignment latency < 100ms
- Dependency resolution latency < 50ms
- Dashboard updates in real-time (< 500ms after event)

### Quality Targets
- Test coverage ≥ 85% for all new modules
- All existing Sprint 3 tests continue passing
- Zero regressions in existing agent functionality
- Comprehensive integration tests for multi-agent scenarios

## Technical Constraints

### Existing System Integration
- Must integrate with existing BackendWorkerAgent (Sprint 3)
- Must use simple_assignment.py for agent type selection
- Must use existing WebSocket infrastructure (cf-45)
- Must use existing database schema (tasks, agents tables)

### Database Schema
- Reuse existing `tasks` table with `assigned_to` field
- Reuse existing `agents` table or agent_pool management
- Add dependency tracking in `tasks` table or new `task_dependencies` table
- Support concurrent updates without race conditions

### Technology Stack
- Python 3.11+ for agent implementations
- asyncio for concurrent agent execution
- SQLite for persistence
- WebSocket for real-time updates
- React/TypeScript for dashboard

## Risk Assessment

### High Risk
- **Race conditions**: Multiple agents updating same data
  - Mitigation: Database transactions, row-level locking

- **Deadlocks**: Circular task dependencies
  - Mitigation: DAG validation, cycle detection before execution

### Medium Risk
- **Resource exhaustion**: Too many agents spawned
  - Mitigation: Agent pool size limits, agent retirement

- **Task assignment errors**: Wrong agent type for task
  - Mitigation: Comprehensive keyword matching tests, fallback logic

### Low Risk
- **WebSocket connection failures**: Updates not delivered
  - Mitigation: Graceful degradation, existing error handling (cf-45)

## Out of Scope

- Advanced capability-based agent matching (deferred to Sprint 9)
- Project-level agent definitions (deferred to Sprint 9)
- Human-in-the-loop blockers (Sprint 5)
- Context management and flash saves (Sprint 6)
- Agent maturity and learning (Sprint 7)

## References

- AGILE_SPRINTS.md - Sprint 4 definition (lines 1884-1960)
- claudedocs/SPRINT_4_READY.md - Simple assignment approach
- claudedocs/SIMPLE_ASSIGNMENT_APPROACH.md - Assignment logic details
- codeframe/agents/simple_assignment.py - Existing assignment implementation
