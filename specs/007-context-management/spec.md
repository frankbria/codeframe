# Context Management Feature Specification

**Feature ID**: 007-context-management
**Sprint**: Sprint 7
**Status**: Planning
**Created**: 2025-11-14

## Overview

Implement a Virtual Project system for intelligent context management that prevents context pollution and enables long-running autonomous agent sessions. The system uses tiered memory (HOT/WARM/COLD) with importance scoring to optimize token usage while maintaining agent effectiveness.

## Problem Statement

Current agent sessions suffer from context pollution as tasks accumulate:
- Agent context grows linearly with task duration
- Token limits force premature session termination
- No mechanism to archive completed/irrelevant context
- Agents lose effectiveness as context becomes diluted
- Long-running autonomous sessions are impractical (>2 hours)

**Impact**: Agents cannot execute complex multi-day projects autonomously due to context limit constraints.

## Goals

### Primary Goal
Enable agents to work on complex projects for extended periods (4+ hours) by intelligently managing context through a tiered memory system that reduces token usage by 30-50%.

### Success Metrics
- **Token Reduction**: 30-50% reduction in average context size
- **Session Duration**: Support 4+ hour autonomous sessions without manual intervention
- **Context Quality**: Maintain >90% task completion rate with reduced context
- **Response Time**: Context operations complete in <50ms (tier lookup)

## User Stories

### P0: Core Context Management

#### Story 1: Context Item Storage
**As a** worker agent
**I want to** save important context items to persistent storage
**So that** I can retrieve them later without keeping everything in active memory

**Acceptance Criteria**:
- Agent can save context items (code snippets, task descriptions, error messages)
- Each item has: content, item_type, importance_score, tier, access_count
- Items are associated with agent_id for isolation
- Items persist across agent restarts

**Technical Notes**:
- Database schema already exists: `context_items` table
- Fields: id, agent_id, item_type, content, importance_score, tier, access_count, created_at, last_accessed

#### Story 2: Importance Scoring
**As a** worker agent
**I want to** automatically calculate importance scores for context items
**So that** critical information stays accessible while stale data is archived

**Acceptance Criteria**:
- Importance score calculated from: item type weight, age decay, access frequency
- Score range: 0.0 (lowest) to 1.0 (highest)
- Scores decay over time (exponential decay function)
- Recently accessed items get score boost
- Item types have different base weights (e.g., current task = 1.0, old error = 0.3)

**Technical Notes**:
- Formula: `score = type_weight * age_decay * access_boost`
- Age decay: `exp(-age_days / decay_constant)`
- Access boost: `log(access_count + 1) / 10`

#### Story 3: Automatic Tier Assignment
**As a** worker agent
**I want to** automatically tier context items based on importance
**So that** I load only relevant context into my working memory

**Acceptance Criteria**:
- Three tiers: HOT (always loaded), WARM (on-demand), COLD (archived)
- HOT tier: importance_score >= 0.8
- WARM tier: 0.4 <= importance_score < 0.8
- COLD tier: importance_score < 0.4
- Tier reassignment runs after each task completion
- Agents load only HOT tier items by default

#### Story 4: Flash Save
**As a** worker agent
**I want to** checkpoint my context when approaching token limits
**So that** I can continue working without losing progress

**Acceptance Criteria**:
- Detect when context reaches 80% of token limit
- Save all HOT/WARM items to database
- Archive COLD items (mark as archived)
- Clear working context
- Resume with only HOT tier loaded
- Flash save completes in <2 seconds

**Technical Notes**:
- Stub exists: `WorkerAgent.flash_save()` in worker_agent.py:48-51
- Token limit detection: monitor context size before each LLM call
- Checkpoint format: JSON snapshot of current context state

### P1: Enhancements

#### Story 5: Context Visualization
**As a** developer
**I want to** see what context my agents are keeping
**So that** I can understand their memory usage and debug issues

**Acceptance Criteria**:
- Dashboard shows context breakdown per agent
- Displays: tier counts, token usage per tier, total items
- List view of items with importance scores
- Filterable by tier (HOT/WARM/COLD)
- Real-time updates via WebSocket

**UI Components**:
- `ContextPanel`: Main container
- `ContextTierChart`: Pie chart showing tier distribution
- `ContextItemList`: Table of items with scores

#### Story 6: Context Diffing (Optional)
**As a** worker agent
**I want to** efficiently update my context between tasks
**So that** I don't reload unchanged information

**Acceptance Criteria**:
- Calculate diff between current context and stored context
- Load only new/modified items
- Remove items no longer in HOT tier
- Diff calculation completes in <100ms

**Technical Notes**:
- Use content hashing (SHA256) for change detection
- Store previous context hash for comparison

## Technical Architecture

### Database Schema

**context_items table** (already exists in database.py:169-182):
```sql
CREATE TABLE context_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK(item_type IN ('TASK', 'CODE', 'ERROR', 'TEST_RESULT', 'PRD_SECTION')),
    content TEXT NOT NULL,
    importance_score REAL NOT NULL CHECK(importance_score >= 0.0 AND importance_score <= 1.0),
    tier TEXT NOT NULL DEFAULT 'WARM' CHECK(tier IN ('HOT', 'WARM', 'COLD')),
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### API Endpoints

```python
# Context Management API
POST /api/agents/{agent_id}/context/save
  Request: { item_type, content, importance_score }
  Response: { item_id, tier }

GET /api/agents/{agent_id}/context
  Query: ?tier=HOT|WARM|COLD
  Response: { items: [{ id, type, content, score, tier }] }

POST /api/agents/{agent_id}/context/flash-save
  Request: {}
  Response: { checkpoint_id, items_archived, hot_items_retained }

GET /api/agents/{agent_id}/context/stats
  Response: { total_items, hot_count, warm_count, cold_count, total_tokens }
```

### Agent Methods

```python
class WorkerAgent:
    async def save_context_item(self, item_type: str, content: str) -> int:
        """Save context item with auto-calculated importance score."""

    async def load_context(self, tier: str = 'HOT') -> List[ContextItem]:
        """Load context items from specified tier."""

    async def flash_save(self) -> FlashSaveResult:
        """Checkpoint context and clear working memory."""

    async def update_tiers(self) -> TierUpdateResult:
        """Recalculate importance scores and reassign tiers."""
```

## Implementation Phases

### Phase 0: Research
- Research importance scoring algorithms (TF-IDF, recency-frequency scoring)
- Research context diffing strategies (content hashing, structural diff)
- Research token estimation techniques (tiktoken library)
- Document findings in research.md

### Phase 1: Core Context Storage
- Implement `save_context_item()` method
- Implement `load_context()` method
- Implement importance scoring algorithm
- Implement tier assignment logic
- Write unit tests (15+ tests)

### Phase 2: Flash Save
- Implement context size monitoring
- Implement `flash_save()` method
- Implement checkpoint creation
- Implement context restoration
- Write integration tests (10+ tests)

### Phase 3: Dashboard Visualization
- Create `ContextPanel` React component
- Create `ContextTierChart` component
- Create `ContextItemList` component
- Add WebSocket events for context updates
- Write component tests (8+ tests)

### Phase 4: Optimization
- Implement context diffing (optional)
- Optimize database queries (add indexes)
- Profile and optimize importance scoring
- Measure token reduction metrics

## Testing Strategy

### Unit Tests
- Importance scoring algorithm (edge cases, boundary conditions)
- Tier assignment logic (threshold testing)
- Age decay calculation
- Access count boost calculation

### Integration Tests
- End-to-end flash save workflow
- Context restoration after checkpoint
- Multi-agent context isolation
- Concurrent context updates

### Performance Tests
- Context load time with 1000+ items
- Flash save duration
- Tier reassignment performance
- Database query optimization

### Acceptance Tests
- Complete 4-hour autonomous session with flash saves
- Verify 30-50% token reduction
- Verify task completion rate >90% with reduced context

## Dependencies

**Required**:
- Sprint 5: Async Worker Agents (COMPLETE) - async/await patterns required
- SQLite database with context_items table (EXISTS)
- FastAPI backend (EXISTS)
- React dashboard (EXISTS)

**Optional**:
- tiktoken library for accurate token counting
- Claude Code hooks integration (beads issue cf-36)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Importance scoring too aggressive | Agents lose critical context | Conservative tier thresholds, extensive testing |
| Flash save too slow | Disrupts agent flow | Async background saving, optimize DB writes |
| Context diffing adds complexity | Maintenance burden | Make optional (P2), simple fallback to full reload |
| Token counting inaccurate | Wrong tier assignments | Use tiktoken library, test with real LLM calls |

## Open Questions

1. **Tier Thresholds**: Are 0.8 (HOT), 0.4 (WARM) the right thresholds? Need empirical testing.
2. **Decay Constant**: What decay rate keeps context fresh without being too aggressive?
3. **Item Type Weights**: What relative weights for TASK vs CODE vs ERROR items?
4. **Flash Save Trigger**: 80% of token limit or absolute token count (e.g., 150k tokens)?
5. **Claude Code Integration**: Should flash save integrate with Claude Code hooks or be standalone?

## References

- **Sprint Plan**: sprints/sprint-07-context-mgmt.md
- **Database Schema**: codeframe/persistence/database.py:169-182
- **Stub Code**: codeframe/agents/worker_agent.py:48-51
- **Constitution**: Principle III (Context Efficiency)
- **Related**: Sprint 5 (Async Workers), Sprint 6 (Human in Loop)

## Changelog

- 2025-11-14: Initial specification created
