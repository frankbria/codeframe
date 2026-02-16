# CodeFRAME v2 Strategic Roadmap

**Created**: 2026-01-29
**Updated**: 2026-02-15
**Status**: Active - Phase 2.5 Complete, Phase 3 Next

## Executive Summary

CodeFRAME v2 CLI **Phase 1 is complete** with a production-ready foundation. The path forward involves:
1. ~~Closing the remaining 5-10% CLI gap (mainly `prd generate` and observability)~~ ✅ DONE
2. Building server layer as thin adapter over core
3. Rebuilding web UI on the v2 foundation
4. Evolving toward the multi-agent "FRAME" vision

---

## Current State Assessment

### What's Working (Phase 1 Complete)
- Full agent execution: `cf work start <task-id> --execute`
- Batch orchestration: serial, parallel, auto (LLM-inferred dependencies)
- Self-correction loop with up to 3 retry attempts
- Blocker system for human-in-the-loop decisions
- Verification gates (ruff, pytest, BUILD)
- State persistence and checkpoint/restore
- Tech stack auto-detection
- 76+ integration tests, all passing
- GitHub PR workflow commands
- **Interactive PRD generation** (`cf prd generate`) ✅
- **Live execution streaming** (`cf work follow`) ✅
- **PRD template system** for customizable output ✅
- **Integration tests** for credentials/environment modules ✅

### Phase 1 Gaps - ALL CLOSED
| Gap | Issue | Status |
|-----|-------|--------|
| `cf prd generate` (Socratic discovery) | #307 | ✅ CLOSED |
| Live streaming (`cf work follow`) | #308 | ✅ CLOSED |
| PRD template system | #316 | ✅ CLOSED |
| Integration tests for credential/env modules | #309 | ✅ CLOSED |

---

## Phase 1: CLI Foundation Completion ✅ COMPLETE

**Goal**: Make CLI fully production-ready for headless agent workflows.
**Status**: ✅ **ALL DELIVERABLES COMPLETE** (2026-02-01)

### Deliverables

1. **`cf prd generate` command** (#307) - ✅ COMPLETE
   - Interactive AI-driven requirements discovery
   - Multi-turn Socratic questioning (5+ turns minimum)
   - Progressive refinement: broad vision → specific requirements → acceptance criteria
   - Outputs structured PRD document
   - Template support for customizable output formats

2. **Live execution streaming** (#308) - ✅ COMPLETE
   - `cf work follow <task-id>` for real-time output
   - File-based streaming with tail support

3. **PRD template system** (#316) - ✅ COMPLETE (BONUS)
   - 5 built-in templates: standard, lean, enterprise, technical, user-story
   - Export/import for customization
   - `cf prd templates list/show/export/import` commands

4. **Integration test expansion** (#309) - ✅ COMPLETE
   - Test credential manager with keyring
   - Test environment validator with tool detection
   - 76+ integration tests (exceeded target)

### Success Criteria - ALL MET
- ✅ New user completes full workflow without hitting credential/env failures
- ✅ `cf prd generate` conducts 5+ turn discovery session
- ✅ All v2 integration tests pass (4285 total tests)

---

## Phase 2: Server Layer as Thin Adapter

**Goal**: FastAPI server exposing core functionality via REST + real-time events.
**Status**: 🔄 **90% COMPLETE** - Core routes done, finishing real-time events + docs

### Deliverables

1. **Server audit and refactor** (#322) - ✅ COMPLETE
   - ✅ Business logic audit completed (see `docs/PHASE_2_BUSINESS_LOGIC_AUDIT.md`)
   - ✅ CLI-to-API route mapping (see `docs/PHASE_2_CLI_API_MAPPING.md`)
   - ✅ V2 routers created following thin adapter pattern:
     - `blockers_v2.py` - Full CRUD delegating to `core.blockers`
     - `prd_v2.py` - Full CRUD + versioning delegating to `core.prd`
     - `tasks_v2.py` - Enhanced with PATCH/DELETE/streaming/run status
     - `workspace_v2.py` - Init, status, tech stack detection
     - `batches_v2.py` - Batch execution with strategies
     - `diagnose_v2.py` - Failed task analysis
     - `pr_v2.py` - GitHub PR workflow
     - `environment_v2.py` - Tool detection and validation
     - `gates_v2.py` - Verification gate execution
   - ✅ Integration tests: 130+ tests for v2 routers

2. **Real-time events** (#323) - 🔄 PARTIAL
   - ✅ SSE streaming via `/api/v2/tasks/{id}/stream`
   - ⚠️ WebSocket for bidirectional events still needed

3. **Authentication & Security**
   - ✅ API key authentication (#326) - COMPLETE
     - Scope-based permissions (read/write/admin)
     - CLI commands: `cf auth api-key-create/list/revoke/rotate`
     - REST header: `X-API-Key`
   - ✅ Rate limiting (#327) - COMPLETE
     - Configurable limits per endpoint type (auth/standard/AI/websocket)
     - Redis backend support for distributed deployments
     - SlowAPI integration
   - API pagination (#118) - Open

### Phase 2 Progress Summary

| Component | Routes | Status |
|-----------|--------|--------|
| Blockers v2 | 5 endpoints | ✅ Complete |
| PRD v2 | 8 endpoints | ✅ Complete |
| Tasks v2 (enhanced) | 12 endpoints | ✅ Complete |
| Discovery v2 | 5 endpoints | ✅ Complete |
| Checkpoints v2 | 6 endpoints | ✅ Complete |
| Schedule v2 | 3 endpoints | ✅ Complete |
| Templates v2 | 4 endpoints | ✅ Complete |
| Git v2 | 3 endpoints | ✅ Complete |
| Review v2 | 2 endpoints | ✅ Complete |
| Workspace v2 | 5 endpoints | ✅ Complete |
| Batches v2 | 5 endpoints | ✅ Complete |
| Diagnose v2 | 2 endpoints | ✅ Complete |
| PR v2 | 5 endpoints | ✅ Complete |
| Environment v2 | 4 endpoints | ✅ Complete |
| Gates v2 | 2 endpoints | ✅ Complete |
| API Key Auth | 4 endpoints | ✅ Complete |
| Rate Limiting | All routes | ✅ Complete |

### All Phase 2 Issues
| Issue | Title | Priority | Status |
|-------|-------|----------|--------|
| #322 | Server audit and refactor | HIGH | ✅ Complete |
| #325 | Phase 2 Server Layer PR | HIGH | ✅ Complete |
| #326 | API key authentication | HIGH | ✅ Complete |
| #327 | Rate limiting | HIGH | ✅ Complete |
| #323 | Real-time events (SSE/WebSocket) | HIGH | 🔄 Partial (SSE done) |
| #119 | OpenAPI documentation | MEDIUM | Open |
| #118 | API pagination | MEDIUM | Open |

### Architecture Principle: Thin Adapter Pattern
```
CLI (typer) ─┬── core.* ─── adapters.*
             │
Server (fastapi) ─┘
```
Server and CLI are **siblings**, both calling core.

**Key Pattern**: V2 routers follow the thin adapter pattern:
1. Parse HTTP request parameters
2. Call core module function with workspace
3. Transform result to HTTP response
4. Handle errors with standard format

See `docs/PHASE_2_DEVELOPER_GUIDE.md` for implementation guide.

---

## Phase 2.5: ReAct Agent Architecture ✅ COMPLETE

**Goal**: Replace plan-then-execute agent with iterative ReAct (Reasoning + Acting) loop as the default engine.
**Status**: ✅ **COMPLETE** (2026-02-15)

### Motivation

The plan-based agent had several failure modes discovered during testing:
- Config file overwrites (whole-file generation ignores existing content)
- Cross-file naming inconsistency (each file generated in isolation)
- Accumulated lint errors (no incremental verification)
- Ineffective self-correction (empty error context)

### Deliverables

1. **ReAct Agent Implementation** - ✅ COMPLETE
   - `core/react_agent.py` - Observe-Think-Act loop with tool use
   - `core/tools.py` - 7 structured tools (read/edit/create file, run command/tests, search, list)
   - `core/editor.py` - Search-replace editor with 4-level fuzzy matching

2. **Engine Selection** - ✅ COMPLETE
   - `--engine react` (default) or `--engine plan` (legacy) on all work commands
   - Runtime routes to ReactAgent or Agent based on engine parameter
   - API endpoints support engine parameter with validation

3. **CLI Validation** (#353) - ✅ COMPLETE
   - `--engine` flag on `cf work start` and `cf work batch run`
   - Default switched to "react"

4. **API Validation** (#354) - ✅ COMPLETE
   - Engine parameter on execute, approve, and stream endpoints
   - Backward compatible — omitting engine uses "react" default

5. **Default Switch + Documentation** (#355) - ✅ COMPLETE
   - Default engine changed from "plan" to "react" across CLI, API, and runtime
   - CLAUDE.md updated with ReAct architecture documentation

### Key Architecture Decisions

- **Search-replace editing**: ~98% accuracy vs ~70-80% for whole-file regeneration
- **Read before write**: Agent always sees actual file state before editing
- **Lint after every change**: Catch errors immediately, not after they accumulate
- **7 focused tools**: Fewer tools = higher accuracy
- **Token budget management**: 3-tier compaction prevents context window overflow
- **Adaptive iteration budget**: Task complexity scoring adjusts iteration limits

### Reference Documentation
- `docs/AGENT_V3_UNIFIED_PLAN.md` - Architecture design and rules
- `docs/REACT_AGENT_ARCHITECTURE.md` - Deep-dive on tools, editor, token management
- `docs/PHASE_25_VALIDATION_REPORT.md` - End-to-end validation results

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
- `phase-1`: CLI Foundation (7 issues - ALL CLOSED)
- `phase-2`: Server Layer (6 issues - ALL OPEN)
- `phase-4`: Multi-Agent (10 issues)
- `phase-5`: Advanced Features (5 issues)
- `v1-legacy`: V1-specific issues, closed but retained as Phase 3 reference (22 issues)

### Phase 1 Issues - ALL COMPLETE
| Issue | Title | Status |
|-------|-------|--------|
| #307 | `cf prd generate` - Socratic Discovery | ✅ CLOSED |
| #308 | `cf work follow` - Live streaming | ✅ CLOSED |
| #309 | Integration tests for credential/env | ✅ CLOSED |
| #316 | PRD template system | ✅ CLOSED |
| #318 | PRD template support | ✅ CLOSED |
| #265 | NoneType error fix | ✅ CLOSED |
| #253 | Checkpoint diff API fix | ✅ CLOSED |

### Phase 2 Issues - MOSTLY COMPLETE
| Issue | Title | Priority | Status |
|-------|-------|----------|--------|
| #322 | Server audit and refactor | HIGH | ✅ Complete |
| #325 | Phase 2 Server Layer PR | HIGH | ✅ Complete |
| #326 | API key authentication | HIGH | ✅ Complete |
| #327 | Rate limiting | HIGH | ✅ Complete |
| #323 | Real-time events (SSE/WebSocket) | HIGH | 🔄 Partial (SSE done) |
| #119 | OpenAPI documentation | MEDIUM | Open |
| #118 | API pagination | MEDIUM | Open |

---

## Architecture Decisions

### 1. Core-first pattern maintained
Core remains headless. Server and CLI are equal adapters.

### 2. Integration tests as guardrail
The existing 130+ v2 router tests ensure "always working codebase" through all phases.

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

| Phase | Focus | Key Outcome | Status |
|-------|-------|-------------|--------|
| 1 | CLI Completion | Production-ready headless agent | ✅ **COMPLETE** |
| 2 | Server Layer | REST API + real-time events | ✅ **COMPLETE** |
| 2.5 | ReAct Agent | Iterative tool-use execution engine | ✅ **COMPLETE** |
| 3 | Web UI | Modern dashboard | Planned |
| 4 | Multi-Agent | Agent swarms | Planned |
| 5 | Advanced | Power features | Planned |

**Current focus**: Phase 3 - Web UI rebuild on v2 foundation.
