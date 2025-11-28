# Claude Agent SDK vs CodeFRAME: Overlap Analysis & Integration Opportunities

**Author**: Claude Code Analysis
**Date**: 2025-11-28
**Version**: 1.1
**Updated**: 2025-11-28 - Implementation planning corrections added

---

## Executive Summary

This document provides a comprehensive analysis comparing the CodeFRAME codebase (~25,771 lines across 86 Python files) against the Claude Agent SDK's capabilities. The goal is to identify opportunities for SDK adoption that would reduce maintenance burden while preserving CodeFRAME's unique value propositions.

### Key Findings

| Metric | CodeFRAME | Claude Agent SDK | Overlap |
|--------|-----------|------------------|---------|
| Agent Architecture | Custom multi-tier | Built-in orchestrator/subagent | **High** |
| Context Management | 3-tier (HOT/WARM/COLD) | Automatic compaction | **Medium** |
| Tool System | Manual execution | Native tool framework | **High** |
| State Persistence | Custom DB + JSON | Session-based | **Low** |
| Quality Gates | 4-stage custom | Not built-in | **None** |
| Cost Tracking | Custom metrics tracker | Usage API | **Medium** |
| WebSocket/Real-time | Custom broadcasts | Streaming API | **Medium** |
| Checkpoints | Git + DB + Context | `/rewind` command | **Low** |

### Recommendation Summary

- **Adopt SDK**: Agent base classes, tool execution, basic streaming
- **Keep Custom**: Quality gates, tiered context, checkpoint system, blocker management
- **Hybrid Approach**: Use SDK foundation with CodeFRAME extensions
- **Estimated Effort Reduction**: 30-40% maintenance savings on adopted components

---

## 1. Feature-by-Feature Overlap Analysis

### 1.1 Agent Architecture

#### CodeFRAME Implementation
```python
# codeframe/agents/worker_agent.py
class WorkerAgent:
    def __init__(self, agent_id, agent_type, project_id, maturity, db):
        self.agent_id = agent_id
        self.agent_type = agent_type  # backend, frontend, test, review
        self.project_id = project_id
        self.maturity = maturity  # D1-D4 (Situational Leadership II)
        self.db = db
```

Key CodeFRAME features:
- **Multi-project support**: Agents scoped by `(project_id, agent_id)`
- **Maturity levels**: D1 (directive) → D4 (delegating) with adaptive prompts
- **Specialized agents**: BackendWorkerAgent, FrontendWorkerAgent, TestWorkerAgent, ReviewWorkerAgent
- **AgentPoolManager**: Manages up to 10 concurrent agents with idle reuse

#### Claude Agent SDK Approach
```python
# SDK approach
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

client = ClaudeSDKClient(
    options=ClaudeAgentOptions(
        system_prompt="You are a backend developer...",
        allowed_tools=["Read", "Write", "Bash"],
        max_turns=50,
        cwd="/project/path"
    )
)

# Subagents via .claude/agents/backend.md
```

SDK features:
- **Subagents**: Markdown files define specialized workers
- **200K context per subagent**: Independent context windows
- **Parallelization**: Spawn multiple subagents simultaneously
- **No maturity levels**: Same autonomy for all agents

#### Overlap Assessment: **HIGH (70%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| Base agent class | Custom | Built-in | **Adopt SDK** |
| Multi-project scope | ✅ | ❌ | Keep custom |
| Maturity levels | ✅ | ❌ | Keep custom |
| Agent pooling | ✅ | Partial | Keep custom |
| Subagent spawning | Custom | Native | **Adopt SDK** |
| Agent state persistence | DB-backed | Session ID | Hybrid |

**Refactoring Opportunity**:
- Extend SDK's `ClaudeSDKClient` with CodeFRAME's maturity/project extensions
- Replace `AgentFactory` with SDK's subagent markdown pattern
- Keep `AgentPoolManager` for concurrency control

---

### 1.2 Context Management

#### CodeFRAME Implementation
```python
# codeframe/lib/context_manager.py
class ContextManager:
    def calculate_importance_score(self, item):
        # Hybrid algorithm
        score = 0.4 * type_weight + 0.4 * age_decay + 0.2 * access_boost
        return score

    def assign_tier(self, score):
        if score >= 0.8: return ContextTier.HOT    # Always loaded
        if score >= 0.4: return ContextTier.WARM   # On-demand
        return ContextTier.COLD                     # Archived
```

Key CodeFRAME features:
- **3-tier memory**: HOT (~20K tokens), WARM (~40K tokens), COLD (archived)
- **Importance scoring**: Type weight + age decay + access boost
- **Flash save**: Archives COLD tier when >80% of limit (144K of 180K)
- **Token counting**: tiktoken with SHA-256 content caching
- **Manual pinning**: Keep critical items regardless of score

#### Claude Agent SDK Approach
```python
# SDK automatic compaction
# Triggered internally when approaching token limits
# Uses /compact command for manual triggering
# CLAUDE.md files for persistent project context
```

SDK features:
- **Automatic compaction**: Built-in context summarization
- **200K context window**: Per session/subagent
- **CLAUDE.md persistence**: Project-wide instructions
- **Session forking**: Branch conversations

#### Overlap Assessment: **MEDIUM (40%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| Automatic compaction | Flash save | Native | **Consider SDK** |
| Tiered memory | ✅ HOT/WARM/COLD | ❌ | Keep custom |
| Importance scoring | ✅ Custom algo | ❌ | Keep custom |
| Token counting | tiktoken | Built-in | **Adopt SDK** |
| Manual pinning | ✅ | ❌ | Keep custom |
| Persistent memory | DB + JSON | CLAUDE.md | Hybrid |

**Refactoring Opportunity**:
- SDK's compaction could replace flash save as **fallback mechanism**
- Keep tiered context as **CodeFRAME's differentiator** - this provides more control
- Replace `TokenCounter` with SDK's built-in token accounting (reduces dependency)

**Trade-off Analysis**:
- CodeFRAME's tiered system provides **30-50% token reduction** through intelligent archival
- SDK's compaction is simpler but less controllable
- **Recommendation**: Keep tiered system, use SDK compaction as emergency fallback

---

### 1.3 Tool System

#### CodeFRAME Implementation
```python
# codeframe/agents/worker_agent.py
class WorkerAgent:
    async def execute_task(self, task: Task):
        # Manual tool orchestration
        result = await self._call_anthropic_api(prompt)
        if self._should_run_tests(task):
            test_result = await self._run_pytest()
        # ... manual file operations, git operations, etc.
```

Tools are manually invoked via:
- Direct API calls to Claude
- Subprocess execution (pytest, ruff, mypy, git)
- Database operations
- File system operations

#### Claude Agent SDK Approach
```python
# SDK native tool framework
from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server

# Built-in tools
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Bash", "WebSearch"],
    mcp_servers=[custom_server]  # Extend with MCP
)

# Custom tool as Python function (in-process MCP)
async def run_quality_checks(file_path: str) -> dict:
    """Run tests, type checking, and linting."""
    return {"passed": True, "details": "..."}

server = create_sdk_mcp_server()
server.register_tool(run_quality_checks)
```

#### Overlap Assessment: **HIGH (75%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| File read/write | Manual | Built-in Read/Write | **Adopt SDK** |
| Bash execution | subprocess | Built-in Bash | **Adopt SDK** |
| Web search | Not implemented | Built-in | **Adopt SDK** |
| Custom tools | Manual | MCP servers | **Adopt SDK** |
| Tool permissions | Quality gates | canUseTool + hooks | **Adopt SDK** |
| Tool tracking | Custom metrics | PostToolUse hook | **Adopt SDK** |

**Refactoring Opportunity**: **SIGNIFICANT**
- Replace manual tool execution with SDK's native tool framework
- Expose quality gates as MCP tools
- Use SDK hooks (PreToolUse/PostToolUse) for metrics tracking
- **Estimated code reduction**: 500-700 lines

---

### 1.4 State Persistence

#### CodeFRAME Implementation
```
.codeframe/
├── state.db              # SQLite database (15 tables)
├── session_state.json    # CLI session recovery
└── checkpoints/          # Git + DB + context snapshots
```

- **15+ database tables**: projects, tasks, agents, blockers, context_items, etc.
- **Session lifecycle**: Auto-save/restore across CLI restarts
- **Migration system**: 7 sequential schema migrations
- **Row-level tracking**: Full history with timestamps

#### Claude Agent SDK Approach
```python
# SDK state management
response = await client.query("...")
session_id = response.session_id  # Persist for resume

# Resume session
await client.resume(session_id)
```

- **Session IDs**: Resume conversations
- **CLAUDE.md**: Persistent project memory
- **Message history**: Per session
- **No built-in database**: Stateless by default

#### Overlap Assessment: **LOW (20%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| Comprehensive DB | ✅ 15 tables | ❌ | Keep custom |
| Session resume | JSON + DB | Session ID | Hybrid |
| Migration system | ✅ | ❌ | Keep custom |
| Task/project tracking | ✅ | ❌ | Keep custom |
| Blocker management | ✅ | ❌ | Keep custom |

**Refactoring Opportunity**: **MINIMAL**
- SDK's session ID could complement existing session state
- Keep SQLite as **CodeFRAME's core differentiator**
- SDK provides no equivalent to comprehensive state tracking

**Trade-off Analysis**:
- CodeFRAME's persistence is **mission-critical** for long-running autonomous sessions
- SDK is stateless; any production system needs custom persistence
- **Recommendation**: Keep 100% of custom persistence layer

---

### 1.5 Quality Gates

#### CodeFRAME Implementation
```python
# codeframe/lib/quality_gates.py
class QualityGates:
    async def run_all_gates(self, task: Task) -> QualityGateResult:
        # Stage 1: Tests (pytest/jest)
        if not await self._run_tests(task):
            return QualityGateResult(status="failed", failures=[...])

        # Stage 2: Type checking (mypy/tsc)
        if not await self._run_type_check(task):
            return QualityGateResult(status="failed", failures=[...])

        # Stage 3: Coverage (85% minimum)
        if await self._check_coverage(task) < 0.85:
            return QualityGateResult(status="failed", failures=[...])

        # Stage 4: Code review (critical findings block)
        if await self._trigger_review(task).has_critical:
            return QualityGateResult(status="failed", failures=[...])

        return QualityGateResult(status="passed")
```

#### Claude Agent SDK Approach
- **No built-in quality gates**
- `/rewind` for code recovery (not prevention)
- Relies on developer judgment

#### Overlap Assessment: **NONE (0%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| Pre-completion checks | ✅ 4-stage | ❌ | Keep custom |
| Test integration | ✅ pytest/jest | ❌ | Keep custom |
| Type checking | ✅ mypy/tsc | ❌ | Keep custom |
| Coverage enforcement | ✅ 85% min | ❌ | Keep custom |
| Code review gate | ✅ ReviewAgent | ❌ | Keep custom |

**Refactoring Opportunity**: **NONE**
- Quality gates are **CodeFRAME's unique value proposition**
- No SDK equivalent - this is a custom innovation
- **Recommendation**: Keep 100%, potentially expose as MCP tool for SDK users

---

### 1.6 Checkpoint System

#### CodeFRAME Implementation
```python
# codeframe/lib/checkpoint_manager.py
class CheckpointManager:
    def create_checkpoint(self, name, trigger):
        # 1. Create git commit
        git_commit = self._create_git_commit(f"Checkpoint: {name}")

        # 2. Backup SQLite database
        db_backup = self._backup_database()

        # 3. Save context snapshot
        context_snapshot = self._save_context_items()

        return Checkpoint(git_commit, db_backup, context_snapshot)

    def restore_checkpoint(self, checkpoint_id):
        # Full state restoration: git + DB + context
```

Checkpoint artifacts:
- **Git commit**: Code state versioning
- **SQLite backup**: Database state
- **Context JSON**: Context items at checkpoint time
- **Metadata**: Phase, tasks completed, costs

#### Claude Agent SDK Approach
```bash
# SDK /rewind command
/rewind <checkpoint-id>  # Revert code only
```

- Code-level recovery only
- No database restoration
- No context restoration
- Simpler but less comprehensive

#### Overlap Assessment: **LOW (25%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| Git integration | ✅ | ✅ | SDK sufficient |
| DB backup | ✅ | ❌ | Keep custom |
| Context snapshot | ✅ | ❌ | Keep custom |
| Phase restoration | ✅ | ❌ | Keep custom |
| Diff preview | ✅ | Partial | Keep custom |

**Refactoring Opportunity**: **MINIMAL**
- SDK's `/rewind` could handle simple code reverts
- Keep full checkpoint system for comprehensive state restoration
- **Recommendation**: Keep custom system, potentially integrate SDK's `/rewind` as lightweight alternative

---

### 1.7 Cost/Token Tracking

#### CodeFRAME Implementation
```python
# codeframe/lib/metrics_tracker.py
class MetricsTracker:
    MODEL_PRICING = {
        "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
        "claude-opus-4": {"input": 15.00, "output": 75.00},
        "claude-haiku-4": {"input": 0.80, "output": 4.00},
    }

    def record_token_usage(self, task_id, agent_id, model, tokens):
        cost = self._calculate_cost(model, tokens)
        self.db.save_token_usage(task_id, agent_id, model, tokens, cost)
```

Features:
- Per-task, per-agent, per-model tracking
- Real-time cost calculation
- Historical aggregation (by day, by project)
- Dashboard visualization

#### Claude Agent SDK Approach
```python
# SDK token tracking in response
response = await client.query("...")
print(response.usage)
# {"input_tokens": 1500, "output_tokens": 800, "total_cost_usd": 0.042}

# Organization-wide Usage API
# GET /v1/usage - Detailed breakdowns by model, workspace, time
```

#### Overlap Assessment: **MEDIUM (50%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| Per-request tracking | ✅ | ✅ | **Adopt SDK** |
| Cost calculation | ✅ | ✅ | **Adopt SDK** |
| Per-task aggregation | ✅ | ❌ | Keep custom |
| Per-agent aggregation | ✅ | ❌ | Keep custom |
| Historical storage | ✅ DB | Usage API | Hybrid |
| Real-time dashboard | ✅ | ❌ | Keep custom |

**Refactoring Opportunity**: **MODERATE**
- Use SDK's `response.usage` instead of manual extraction
- Keep custom aggregation and dashboard
- **Estimated code reduction**: 50-100 lines

---

### 1.8 WebSocket/Real-time Updates

#### CodeFRAME Implementation
```python
# codeframe/ui/websocket_broadcasts.py
class ConnectionManager:
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

# 13+ event types
# task_status_changed, agent_status_changed, test_result, etc.
```

#### Claude Agent SDK Approach
```python
# SDK streaming mode
async for message in client.receive_messages():
    if message.type == "assistant":
        print(message.content)  # Real-time streaming
```

#### Overlap Assessment: **MEDIUM (45%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| Message streaming | Custom WS | Native streaming | **Adopt SDK** |
| Event broadcasting | ✅ 13+ types | Partial | Keep custom |
| Auto-reconnect | ✅ exp backoff | Not specified | Keep custom |
| Dashboard integration | ✅ React | ❌ | Keep custom |

**Refactoring Opportunity**: **MODERATE**
- SDK streaming could replace some WebSocket complexity
- Keep custom event broadcasting for dashboard
- **Estimated simplification**: 100-200 lines

---

### 1.9 Blocker/Human-in-Loop System

#### CodeFRAME Implementation
```python
# codeframe/core/models.py
class BlockerType(Enum):
    SYNC = "sync"   # Blocks agent immediately
    ASYNC = "async" # Agent continues, answer when available

class Blocker:
    agent_id: str
    task_id: int
    blocker_type: BlockerType
    question: str
    answer: Optional[str]
    status: BlockerStatus  # PENDING, RESOLVED, EXPIRED
```

Features:
- **SYNC blockers**: Halt agent until human responds
- **ASYNC blockers**: Agent continues, integrates answer later
- **24-hour expiration**: Automatic cleanup
- **API for resolution**: `POST /api/blockers/{id}/resolve`
- **Dashboard visibility**: Real-time blocker notifications

#### Claude Agent SDK Approach
- **No built-in blocker system**
- Manual interrupt handling
- User prompts in conversation flow

#### Overlap Assessment: **NONE (0%)**

| Feature | CodeFRAME | SDK | Recommendation |
|---------|-----------|-----|----------------|
| SYNC blockers | ✅ | ❌ | Keep custom |
| ASYNC blockers | ✅ | ❌ | Keep custom |
| Question queue | ✅ | ❌ | Keep custom |
| Answer injection | ✅ | ❌ | Keep custom |
| Expiration | ✅ 24h | ❌ | Keep custom |

**Refactoring Opportunity**: **NONE**
- Blocker system is **CodeFRAME's unique innovation**
- Essential for true autonomous operation
- **Recommendation**: Keep 100%

---

## 2. Refactoring Recommendations

### 2.1 High Priority (Significant ROI)

#### A. Tool Execution Framework
**Current**: Manual subprocess calls, custom file operations
**Target**: SDK's native tool framework + MCP

**Changes**:
```python
# Before (CodeFRAME)
async def execute_task(self, task):
    result = await self._call_anthropic(prompt)
    if "write file" in result:
        self._write_file(path, content)  # Manual

# After (SDK-integrated)
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

client = ClaudeSDKClient(
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Bash"],
        hooks=[self._metrics_hook, self._quality_gate_hook]
    )
)
await client.query(task.description)  # Tools auto-executed
```

**Benefits**:
- Remove 500-700 lines of manual tool handling
- Native sandboxing and security
- Standard tool interface
- Reduced testing surface

**Effort**: Medium (1-2 weeks)
**Risk**: Low (SDK is production-tested)

#### B. Token Tracking Integration
**Current**: Manual extraction from API responses
**Target**: SDK's `response.usage` object

**Changes**:
```python
# Before
response = await anthropic.messages.create(...)
tokens = self._extract_tokens(response)  # Manual parsing

# After
response = await client.query(...)
tokens = response.usage  # SDK provides directly
```

**Benefits**:
- Simpler token extraction
- Future-proof (SDK handles API changes)
- Remove 50-100 lines

**Effort**: Low (2-3 days)
**Risk**: Very low

### 2.2 Medium Priority (Moderate ROI)

#### A. Subagent Pattern Adoption
**Current**: Custom `AgentFactory` and class hierarchy
**Target**: SDK's markdown subagent pattern

**Changes**:
```markdown
# .claude/agents/backend.md (SDK pattern)
---
name: Backend Developer
description: Specializes in API and database tasks
tools: [Read, Write, Bash]
---
You are a backend developer agent...
```

**Benefits**:
- Simpler agent definitions
- Standard pattern recognized by SDK
- Easier agent creation/modification

**Caveats**:
- Lose maturity level support
- Lose project_id scoping
- **Recommendation**: Hybrid - use SDK pattern for simple agents, keep custom for advanced

**Effort**: Medium (1-2 weeks)
**Risk**: Medium (feature loss)

#### B. Streaming Simplification
**Current**: Custom WebSocket implementation
**Target**: SDK streaming + custom event layer

**Changes**:
- Use SDK streaming for Claude responses
- Keep custom WebSocket for dashboard events
- Reduce WebSocket complexity

**Benefits**:
- Simpler Claude interaction
- Standard streaming format
- Remove 100-200 lines

**Effort**: Medium (1 week)
**Risk**: Low

### 2.3 Low Priority (Limited ROI)

#### A. Session ID Integration
**Current**: Custom session_state.json
**Target**: SDK session ID + custom persistence

**Changes**:
- Store SDK session_id alongside custom state
- Use for conversation resume
- Keep DB persistence unchanged

**Benefits**:
- Standard resume mechanism
- Minimal code change

**Effort**: Low (1-2 days)
**Risk**: Very low

#### B. Context Compaction Fallback
**Current**: Custom flash save only
**Target**: SDK compaction as fallback

**Changes**:
- Keep tiered context system
- Add SDK compaction as emergency fallback
- Trigger when flash save insufficient

**Effort**: Low (2-3 days)
**Risk**: Very low

---

## 3. Easy Wins

### 3.1 Immediate Adoption (< 1 day each)

| Change | Lines Saved | Benefit |
|--------|-------------|---------|
| Use `response.usage` for tokens | 50-100 | Simpler token tracking |
| SDK session ID storage | 20-30 | Standard resume pattern |
| Built-in web search tool | N/A | New capability |

### 3.2 Quick Wins (< 1 week each)

| Change | Lines Saved | Benefit |
|--------|-------------|---------|
| SDK tool framework for file ops | 200-300 | Native Read/Write/Bash |
| PostToolUse hook for metrics | 50-100 | Standard event pattern |
| Markdown subagent definitions | 100-150 | Simpler agent creation |

### 3.3 Medium Wins (1-2 weeks each)

| Change | Lines Saved | Benefit |
|--------|-------------|---------|
| Full tool framework migration | 500-700 | Major simplification |
| SDK streaming integration | 100-200 | Standard streaming |
| MCP tool exposure | N/A | Extensibility |

---

## 4. Features to Keep Custom

### 4.1 Critical Differentiators (Do Not Migrate)

| Feature | Reason |
|---------|--------|
| **Quality Gates** | Unique value proposition - no SDK equivalent |
| **Tiered Context (HOT/WARM/COLD)** | More control than SDK compaction |
| **Blocker System** | Essential for autonomous operation - no SDK equivalent |
| **Full Checkpoint System** | Comprehensive state restoration vs SDK's code-only |
| **Database Persistence** | Mission-critical for long-running sessions |
| **Maturity Levels** | Adaptive autonomy - no SDK equivalent |
| **AgentPoolManager** | Concurrency control beyond SDK basics |

### 4.2 Worth Extending (Keep + Enhance)

| Feature | Enhancement |
|---------|-------------|
| MetricsTracker | Keep aggregation, use SDK for extraction |
| SessionManager | Add SDK session_id, keep full persistence |
| WebSocket broadcasts | Keep custom events, use SDK streaming |

---

## 5. Trade-off Analysis

### 5.1 SDK Adoption Benefits

| Benefit | Impact |
|---------|--------|
| **Production-tested code** | High - fewer bugs |
| **Maintained by Anthropic** | High - automatic updates |
| **Standard patterns** | Medium - easier onboarding |
| **Security hardening** | High - sandboxed tools |
| **Documentation** | Medium - better discoverability |

### 5.2 SDK Adoption Risks

| Risk | Mitigation |
|------|------------|
| **Feature gaps** | Keep custom components for unique features |
| **API changes** | Abstract SDK behind interface |
| **Vendor lock-in** | Already locked in to Claude API |
| **Learning curve** | SDK is well-documented |

### 5.3 Migration vs Status Quo

| Scenario | Maintenance Cost | Feature Set |
|----------|------------------|-------------|
| **Status quo** | High (25K+ lines custom) | Full control |
| **Full SDK migration** | Low but lossy | Missing unique features |
| **Hybrid (recommended)** | Medium (~30% reduction) | Best of both |

---

## 6. Recommended Migration Path

### Phase 1: Foundation (Week 1-2)
1. ✅ Adopt `response.usage` for token tracking
2. ✅ Store SDK session_id alongside custom state
3. ✅ Add SDK's web search capability

### Phase 2: Tool Framework (Week 3-4)
1. Migrate file operations to SDK's Read/Write/Bash
2. Implement PostToolUse hook for metrics
3. Keep quality gates as wrapper around SDK tools

### Phase 3: Agent Pattern (Week 5-6)
1. Create markdown subagent definitions for simple agents
2. Keep WorkerAgent class for advanced features
3. Hybrid: SDK subagents + custom extensions

### Phase 4: Streaming (Week 7-8)
1. Integrate SDK streaming for Claude responses
2. Keep custom WebSocket for dashboard events
3. Reduce custom WebSocket complexity

### Phase 5: Optimization (Ongoing)
1. Monitor SDK updates for new features
2. Consider SDK compaction as flash save fallback
3. Expose quality gates as MCP tools for SDK users

---

## 7. Conclusion

### Summary Table

| Component | Recommendation | Effort | ROI |
|-----------|----------------|--------|-----|
| Tool execution | **Adopt SDK** | Medium | High |
| Token tracking | **Adopt SDK** | Low | High |
| Subagent pattern | Hybrid | Medium | Medium |
| Streaming | **Adopt SDK** | Medium | Medium |
| Quality gates | Keep custom | N/A | N/A |
| Tiered context | Keep custom | N/A | N/A |
| Checkpoint system | Keep custom | N/A | N/A |
| Blocker system | Keep custom | N/A | N/A |
| Database persistence | Keep custom | N/A | N/A |
| WebSocket events | Keep custom | N/A | N/A |

### Key Takeaways

1. **SDK provides strong foundation** for tool execution and basic agent operations
2. **CodeFRAME's unique value** is in quality gates, tiered context, and blocker systems
3. **Hybrid approach recommended** - SDK for basics, custom for differentiation
4. **30-40% maintenance reduction** possible with recommended migrations
5. **No urgency** - CodeFRAME works; migrate incrementally as resources allow

### Risk Assessment

- **Low risk**: Token tracking, session ID integration
- **Medium risk**: Tool framework migration (well-defined scope)
- **Avoid**: Migrating quality gates, blockers, or full persistence to SDK

The Claude Agent SDK is a production-tested foundation that can reduce CodeFRAME's maintenance burden while preserving its unique capabilities for autonomous, long-running agent sessions.

---

## 8. Implementation Planning Corrections

> **Note**: This section documents findings discovered during detailed implementation planning.
> See [SDK_MIGRATION_IMPLEMENTATION_PLAN.md](SDK_MIGRATION_IMPLEMENTATION_PLAN.md) for the full plan.

### 8.1 Corrections to Original Analysis

| Section | Original Statement | Actual Finding | Impact |
|---------|-------------------|----------------|--------|
| 1.7 Token Tracking | "Manual extraction from API responses" | **Already uses `response.usage.input_tokens/output_tokens`** (anthropic.py:101-107) | **Simpler** - minimal refactoring needed |
| 2.1 Tool Framework | "Replace 500-700 lines" | Tools tightly integrated with quality gates, context management | **More complex** - careful extraction required |
| 2.1 Agent Pattern | "Markdown subagent pattern can replace YAML" | YAML includes maturity_progression, error_recovery, integration_points not expressible in markdown | **Hybrid approach mandatory** |
| 3.2 Quick Wins | "< 1 week each" | Some dependencies require architecture decisions first | **Sequencing matters** |

### 8.2 Additional Complexity Discovered

#### Dual API Patterns
The codebase uses **both** synchronous and asynchronous Anthropic clients:

```python
# Synchronous (codeframe/providers/anthropic.py)
from anthropic import Anthropic
self.client = Anthropic(api_key=api_key)

# Asynchronous (codeframe/agents/frontend_worker_agent.py, test_worker_agent.py)
from anthropic import AsyncAnthropic
self.client = AsyncAnthropic(api_key=api_key)
```

**Impact**: Migration must handle both patterns or consolidate to one.

#### Rich YAML Agent Definitions
Current YAML definitions include features not mappable to SDK markdown:

```yaml
# From backend.yaml
maturity_progression:
  - level: D1
    description: "Basic task execution with supervision"
    capabilities: ["simple_functions", "basic_tests"]
  - level: D4
    description: "System-level thinking and mentorship"
    capabilities: ["architectural_design", "code_review"]

error_recovery:
  max_correction_attempts: 3
  escalation_policy: "Create blocker for manual intervention"

integration_points:
  - database: "Task queue, status updates"
  - codebase_index: "Symbol search, file discovery"
```

**Impact**: Cannot fully replace YAML with markdown. Hybrid approach required.

### 8.3 Open Questions Requiring Resolution

| ID | Question | Impact | Blocking |
|----|----------|--------|----------|
| OPEN-001 | SDK package name and installation method | Cannot start Phase 1 | **Yes** |
| OPEN-002 | Does SDK support async/await natively? | Affects wrapper implementation | Yes |
| OPEN-003 | Exact PreToolUse/PostToolUse hook signatures? | Affects Phase 2 quality gate integration | Yes |
| OPEN-004 | How to programmatically spawn SDK subagents? | Affects Phase 3 agent creation | Yes |

### 8.4 Revised Effort Estimates

| Phase | Original | Revised | Reason |
|-------|----------|---------|--------|
| Phase 1: Foundation | 1-2 weeks | **1 week** | Token tracking simpler than expected |
| Phase 2: Tool Framework | 3-4 weeks | **3-4 weeks** | Unchanged - complexity matches estimate |
| Phase 3: Agent Pattern | 5-6 weeks | **4-6 weeks** | Hybrid approach adds flexibility |
| Phase 4: Streaming | 7-8 weeks | **2-3 weeks** | Overestimated - SDK streaming simpler |
| Phase 5: Optimization | Ongoing | **Ongoing** | Unchanged |

### 8.5 Architecture Decisions Required

Before implementation can proceed, these decisions must be made:

1. **Quality Gate Integration Pattern**
   - Option A: Pre-tool hooks block execution
   - Option B: Wrapper tools combine checks + execution
   - Option C: Post-tool validation
   - **Recommendation**: Option A with Option C fallback

2. **Maturity Level Preservation**
   - Option A: Multiple markdown files per maturity level
   - Option B: Dynamic prompt injection at runtime
   - Option C: Keep YAML as source of truth, generate SDK prompts
   - **Recommendation**: Option C (Hybrid)

3. **Async vs Sync Consolidation**
   - Option A: Migrate all to async SDK
   - Option B: Keep dual patterns with wrappers
   - Option C: Consolidate to sync with asyncio.to_thread()
   - **Recommendation**: Option A if SDK supports async, else Option B

---

## Appendix A: Component Mapping

| CodeFRAME Component | SDK Equivalent | Migration Status |
|---------------------|----------------|------------------|
| `WorkerAgent` | `ClaudeSDKClient` | Partial |
| `LeadAgent` | Orchestrator pattern | Partial |
| `AgentFactory` | Subagent markdown | Replaceable |
| `AgentPoolManager` | Not available | Keep |
| `ContextManager` | Automatic compaction | Keep (enhanced) |
| `ImportanceScorer` | Not available | Keep |
| `TokenCounter` | `response.usage` | Replaceable |
| `QualityGates` | Not available | Keep |
| `CheckpointManager` | `/rewind` | Keep (enhanced) |
| `MetricsTracker` | Usage API | Keep (hybrid) |
| `SessionManager` | Session ID | Keep (hybrid) |
| `Database` | Not available | Keep |
| `ConnectionManager` | Streaming | Keep (hybrid) |

## Appendix B: Code Reduction Estimates

| Migration | Lines Removed | Lines Added | Net Reduction |
|-----------|---------------|-------------|---------------|
| Tool framework | 700 | 150 | 550 |
| Token extraction | 100 | 20 | 80 |
| Subagent pattern | 150 | 50 | 100 |
| Streaming | 200 | 80 | 120 |
| **Total** | **1150** | **300** | **850** |

Estimated reduction: ~3.3% of total codebase (850 of 25,771 lines)
Maintenance reduction: ~30-40% for affected components
