# Sprint 7: Context Management

**Status**: 🚧 In Progress - Phases 2-5 Complete
**Duration**: Week 7 (In Progress)
**Epic/Issues**: cf-31 through cf-35, cf-36 (cf-36 exists in beads, open)
**Test Status**: ✅ 59/59 tests passing (100%)

## Goal
Implement Virtual Project system to prevent context pollution and enable long-running agent sessions.

## User Story
As a developer, I want to see agents intelligently manage their memory, keeping relevant context hot and archiving old information.

## Planned Tasks

### Core Features (P0)
- [ ] **cf-NEW-31**: ContextItem storage (Status: Schema exists, no implementation)
  - Save context items to DB (context_items table ready)
  - Track importance scores
  - Access count tracking
  - Demo: Context items stored and queryable

- [ ] **cf-NEW-32**: Importance scoring algorithm (Status: Not started)
  - Calculate scores based on type, age, access
  - Automatic tier assignment (HOT/WARM/COLD)
  - Score decay over time
  - Demo: Items auto-tier based on importance

- [ ] **cf-NEW-33**: Context diffing and hot-swap (Status: Not started)
  - Calculate context changes
  - Load only new/updated items
  - Remove stale items
  - Demo: Agent context updates efficiently

- [ ] **cf-NEW-34**: Flash save before compactification (Status: Stub with TODO)
  - Detect context >80% of limit
  - Create checkpoint
  - Archive COLD items
  - Resume with fresh context
  - NOTE: WorkerAgent.flash_save() exists but has TODO (worker_agent.py:48-51)
  - Demo: Agent continues after flash save

### Enhancements (P1)
- [ ] **cf-NEW-35**: Context visualization in dashboard (Status: Not started)
  - Show tier breakdown (HOT/WARM/COLD)
  - Token usage per tier
  - Item list with importance scores
  - Demo: Inspect what agent "remembers"

- [ ] **cf-36**: Claude Code Hooks Integration (Status: Open in beads)
  - Integrate with Claude Code hooks system
  - before_compact hook for flash save
  - State preservation during compactification
  - Estimated Effort: 2-3 hours

## Definition of Done
- [ ] Context items stored with importance scores
- [ ] Items automatically tiered (HOT/WARM/COLD)
- [ ] Flash saves trigger before context limit
- [ ] Agents continue working after flash save
- [ ] Dashboard shows context breakdown
- [ ] 30-50% token reduction achieved (measured with real tasks)
- [ ] Working demo of multi-hour agent session with flash saves

## Implementation Progress (2025-11-14)

### ✅ Completed: Phases 2-5

**Phase 2: Foundational Layer** ✅
- ✅ Created Pydantic models (ContextItemType, ContextTier, ContextItemModel)
- ✅ Created database migrations (004: context_checkpoints, 005: indexes)
- ✅ Added database methods (create/get/list/update/delete context items)
- ✅ Created checkpoint database methods
- ✅ Created TokenCounter with tiktoken integration
- ✅ Created WebSocket event types

**Phase 3: User Story 1 - Context Item Storage** ✅
- ✅ API endpoints for CRUD operations
- ✅ WorkerAgent.save_context_item() method
- ✅ WorkerAgent.load_context() method with tier filtering
- ✅ WorkerAgent.get_context_item() method
- ✅ Access tracking (last_accessed, access_count)
- ✅ Tests: test_context_storage.py (8 tests passing)

**Phase 4: User Story 2 - Importance Scoring** ✅
- ✅ Created importance_scorer.py with scoring algorithm
- ✅ Hybrid exponential decay formula: 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost
- ✅ Auto-calculation on item creation
- ✅ ContextManager.recalculate_scores_for_agent() method
- ✅ API endpoint: POST /api/agents/{id}/context/update-scores
- ✅ Tests: test_importance_scoring.py, test_score_decay.py, test_context_manager.py (15 tests passing)
- ✅ Integration test: test_score_recalculation.py (4 tests passing)

**Phase 5: User Story 3 - Automatic Tier Assignment** ✅
- ✅ assign_tier() function (HOT >= 0.8, WARM 0.4-0.8, COLD < 0.4)
- ✅ Auto-assignment on item creation
- ✅ ContextManager.update_tiers_for_agent() method
- ✅ API endpoint: POST /api/agents/{id}/context/update-tiers
- ✅ WorkerAgent.update_tiers() method
- ✅ Tier filtering in list_context_items()
- ✅ Tests: test_tier_assignment.py, test_tier_filtering.py, test_assign_tier.py (18 tests passing)

**CRITICAL ARCHITECTURAL FIX: Multi-Agent Support** 🎯
- ✅ Added `agent_id` column to context_items schema
- ✅ Updated all database methods to accept `(project_id, agent_id)` scoping
- ✅ Added `project_id` parameter to WorkerAgent.__init__() and all context methods
- ✅ Updated ContextManager methods for multi-project support
- ✅ Updated API endpoints to accept project_id query parameter
- ✅ Fixed all 59 tests to support multi-agent architecture
- ✅ **Result**: Multiple agents (orchestrator, backend, frontend, test, review) can now collaborate on the same project with isolated context

**Test Results**: ✅ 59/59 tests passing (100% pass rate)
- 8 context storage tests
- 15 importance scoring tests
- 4 score recalculation integration tests
- 18 tier assignment/filtering tests
- 14 other context tests

### 🚧 In Progress: Phase 6 (User Story 4)

**Phase 6: Flash Save** (Not Started)
- [ ] Token counting for context items
- [ ] should_flash_save() logic (80% threshold)
- [ ] flash_save() implementation
- [ ] Checkpoint creation with JSON state
- [ ] COLD item archival
- [ ] Token reduction verification (target: 30-50%)
- [ ] Tests: test_flash_save.py, test_token_counting.py, test_checkpoint_restore.py

### 📋 Planned: Phases 7-8

**Phase 7: Context Visualization** (P1 - Optional)
- [ ] Frontend TypeScript types
- [ ] API client for context operations
- [ ] ContextPanel React component
- [ ] ContextTierChart component
- [ ] ContextItemList component with pagination
- [ ] GET /api/agents/{id}/context/stats endpoint

**Phase 8: Polish & Integration**
- [ ] Documentation updates
- [ ] Full test suite verification
- [ ] Performance benchmarking

## Current Status

**What Exists**:
- ✅ Database schema: `context_items` table with agent_id, project_id, current_tier
- ✅ Database methods: Full CRUD + access tracking + tier filtering
- ✅ Importance scoring: Hybrid exponential decay algorithm
- ✅ Tier assignment: Automatic HOT/WARM/COLD classification
- ✅ ContextManager: Score recalculation + tier updates
- ✅ WorkerAgent methods: save/load/get context + update_tiers
- ✅ API endpoints: CRUD + score/tier updates
- ✅ Multi-agent architecture: Multiple agents per project
- ✅ Migration 004: `context_checkpoints` table with indexes
- ✅ Migration 005: Performance indexes on `context_items`
- ✅ TokenCounter: tiktoken integration with caching

**What's Missing**:
- Flash save implementation (stub exists with TODO)
- Token threshold detection
- Checkpoint creation workflow
- COLD item archival
- UI components for context visualization
- Integration with Claude Code compactification hooks

## Implementation Notes
**Blockers**:
- Issue IDs cf-31 through cf-35 not yet created in beads tracker
- cf-33 ID conflicts with existing Sprint 2 issue (Git Branching)
- Need new non-conflicting issue IDs

**Architecture Decisions**:
- Importance score formula: TBD (age decay + access frequency + item type weight)
- Tier thresholds: TBD (e.g., >80 = HOT, 40-80 = WARM, <40 = COLD)
- Flash save trigger: TBD (percentage of context limit vs. absolute token count)

## References
- **Feature Specs**: (Will be created in specs/007-context-management/)
- **Dependencies**: Sprint 5 (Async Worker Agents) - COMPLETE
- **Database Schema**: codeframe/database/schema.py lines 169-182
- **Stub Code**: codeframe/agents/worker_agent.py lines 48-51
