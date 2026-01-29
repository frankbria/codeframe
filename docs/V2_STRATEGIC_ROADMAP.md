# CodeFRAME v2 Strategic Roadmap

**Created**: 2026-01-29
**Status**: Active

## Executive Summary

CodeFRAME v2 CLI is **95% complete** with a robust foundation. The path forward involves:
1. Closing the remaining 5-10% CLI gap (mainly `prd generate` and observability)
2. Building server layer as thin adapter over core
3. Rebuilding web UI on the v2 foundation
4. Evolving toward the multi-agent "FRAME" vision

---

## Current State Assessment

### What's Working (95% of CLI)
- Full agent execution: `cf work start <task-id> --execute`
- Batch orchestration: serial, parallel, auto (LLM-inferred dependencies)
- Self-correction loop with up to 3 retry attempts
- Blocker system for human-in-the-loop decisions
- Verification gates (ruff, pytest)
- State persistence and checkpoint/restore
- Tech stack auto-detection
- 70+ integration tests, all passing
- GitHub PR workflow commands

### Actual Remaining Gaps (~5%)
| Gap | Issue | Priority |
|-----|-------|----------|
| `cf prd generate` (Socratic discovery) | #307 | **CRITICAL** |
| Live streaming (`cf work follow`) | #308 | HIGH |
| Integration tests for credential/env modules | #309 | MEDIUM |

---

## Phase 1: CLI Foundation Completion

**Goal**: Make CLI fully production-ready for headless agent workflows.

### Deliverables

1. **`cf prd generate` command** (#307) - CRITICAL
   - Interactive AI-driven requirements discovery
   - Multi-turn Socratic questioning (5+ turns minimum)
   - Progressive refinement: broad vision → specific requirements → acceptance criteria
   - Outputs structured PRD document
   - Blocker integration: can pause discovery and resume later

2. **Live execution streaming** (#308)
   - `cf work follow <task-id>` for real-time output
   - WebSocket or polling-based stdout/stderr streaming

3. **Integration test expansion** (#309)
   - Test credential manager with keyring
   - Test environment validator with tool detection
   - Target: 100+ integration tests

### Success Criteria
- New user completes full workflow without hitting credential/env failures
- `cf prd generate` conducts 5+ turn discovery session
- All v2 integration tests pass

---

## Phase 2: Server Layer as Thin Adapter

**Goal**: FastAPI server exposing core functionality via REST + real-time events.

### Deliverables

1. **Server audit and refactor**
   - Review existing routes in `codeframe/server/`
   - Refactor to delegate all logic to `core.*` modules
   - One route per CLI command
   - OpenAPI documentation (#119)

2. **Real-time events**
   - SSE or WebSocket for task execution events
   - Event types: progress, output, blocker, completion

3. **Authentication & Security**
   - API key authentication
   - Rate limiting (#167)
   - API pagination (#118)

### Architecture Principle
```
CLI (typer) ─┬── core.* ─── adapters.*
             │
Server (fastapi) ─┘
```
Server and CLI are **siblings**, both calling core.

---

## Phase 3: Web UI Rebuild

**Goal**: Modern dashboard consuming REST/WebSocket API.

### Deliverables

1. **Project management** - Workspace list, creation, configuration
2. **PRD interface** - Visual editor with AI assistance
3. **Task board** - Drag-and-drop with dependency visualization
4. **Execution monitor** - Live dashboard showing agent progress
5. **Blocker resolution** - Interactive Q&A interface
6. **Onboarding flow** - First-time user experience

### Tech Stack
- Next.js with App Router
- Shadcn/UI + Tailwind (Nova template)
- Hugeicons
- Real-time via WebSocket/SSE

**Note**: v1-legacy issues (labeled and closed) serve as reference for this phase.

---

## Phase 4: Multi-Agent Coordination

**Goal**: Realize the "FRAME" vision - specialist agents working together.

### Deliverables

1. **Agent roles** (#310)
   - Backend Agent, Frontend Agent, Test Agent, Review Agent
   - Role-specific system prompts and tool access
   - Automatic task-to-agent matching

2. **Parallel multi-agent execution**
   - Multiple agents on independent tasks
   - Worker pool management

3. **Conflict detection & resolution** (#311)
   - Identify concurrent modifications to same files
   - Strategies: serialize, merge, escalate to blocker
   - 90%+ automatic resolution target

4. **Handoff protocols** (#312)
   - Context passing between roles
   - Implementation → Test → Review pipeline

### Related Issues
- #68: Subagent context isolation
- #72: Task-scoped vs agent-level context
- #71: Adaptive failure handling
- #73: Procedural memory for learning
- #70, #67, #63: Context engineering

---

## Phase 5: Advanced Features & Polish

**Goal**: Power user features and production hardening.

### Deliverables

1. **TUI Dashboard** (#313) - Rich/Textual terminal interface
2. **Token/cost tracking** (#314) - Usage metrics per task/batch
3. **Debug/replay mode** (#315) - Step through past executions
4. **Performance benchmarks** (#115) - Baseline metrics
5. **Context optimization** (#63, #67) - Assembly order, eviction strategy

---

## Execution Timeline

```
Phase 1 (CLI) ──────────────────────────────────►
                  │
                  ├── Phase 2 (Server) ────────────────►
                  │                     │
                  │                     ├── Phase 3 (UI) ──────►
                  │
                  └── Phase 4 (Multi-Agent) ────────────────────►
                                                          │
                                                          └── Phase 5 (Advanced) ──►
```

- **Phase 1 is prerequisite** for everything
- **Phases 2-3** (server/UI) can run in parallel with **Phase 4** (multi-agent)
- **Phase 5** depends on earlier phases but can start partially

---

## GitHub Issue Organization

### Labels
- `phase-1`: CLI Foundation (5 issues)
- `phase-2`: Server Layer (3 issues)
- `phase-4`: Multi-Agent (10 issues)
- `phase-5`: Advanced Features (5 issues)
- `v1-legacy`: V1-specific issues, closed but retained as Phase 3 reference (22 issues)

### Key Phase 1 Issues
| Issue | Title | Priority |
|-------|-------|----------|
| #307 | `cf prd generate` - Socratic Discovery | CRITICAL |
| #308 | `cf work follow` - Live streaming | HIGH |
| #309 | Integration tests for credential/env | MEDIUM |

---

## Architecture Decisions

### 1. Core-first pattern maintained
Core remains headless. Server and CLI are equal adapters.

### 2. Integration tests as guardrail
The existing 70+ tests ensure "always working codebase" through all phases.

### 3. No big-bang UI rewrite
Web UI is built incrementally on v2 server, not by fixing v1.

### 4. Agent swarms are Phase 4, not Phase 1
Focus on single-agent excellence first, then parallelize.

---

## Verification Plan

After each phase:
1. Run full integration test suite: `uv run pytest tests/cli/test_v2_cli_integration.py`
2. Manual smoke test of Golden Path
3. Confirm no regressions in existing functionality

---

## Summary

| Phase | Focus | Key Outcome |
|-------|-------|-------------|
| 1 | CLI Completion | Production-ready headless agent |
| 2 | Server Layer | REST API + real-time events |
| 3 | Web UI | Modern dashboard |
| 4 | Multi-Agent | Agent swarms |
| 5 | Advanced | Power features |

**Next immediate action**: Implement `cf prd generate` (#307).
