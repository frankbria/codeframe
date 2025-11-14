# Implementation Tasks: Context Management

**Feature**: 007-context-management
**Branch**: `007-context-management`
**Generated**: 2025-11-14
**Status**: Ready for implementation

## Overview

This document breaks down the Context Management feature into actionable tasks organized by user story. Each phase corresponds to a user story from [spec.md](spec.md) and can be implemented and tested independently.

**Total Tasks**: 69 tasks across 7 phases
**Parallel Opportunities**: 42 parallelizable tasks (marked with [P])
**Est. Total Effort**: 3-4 days for full implementation

## Task Organization

Tasks are organized into phases that align with user stories:

- **Phase 1**: Setup (T001-T008) - Project initialization and infrastructure
- **Phase 2**: Foundational (T009-T015) - Blocking prerequisites for all stories
- **Phase 3**: User Story 1 - Context Item Storage (T016-T026)
- **Phase 4**: User Story 2 - Importance Scoring (T027-T036)
- **Phase 5**: User Story 3 - Automatic Tier Assignment (T037-T046)
- **Phase 6**: User Story 4 - Flash Save (T047-T059)
- **Phase 7**: User Story 5 - Context Visualization (T060-T067)
- **Phase 8**: Polish & Integration (T068-T069)

## Task Format

```
- [ ] [TaskID] [P] [Story] Description with file path
```

- **TaskID**: Sequential number (T001, T002, ...)
- **[P]**: Parallelizable (can run concurrently with other [P] tasks)
- **[Story]**: User story label ([US1], [US2], etc.)
- **File path**: Exact location in codebase

---

## Phase 1: Setup & Infrastructure

**Goal**: Initialize project structure and install dependencies

**Dependencies**: None (blocking for all other phases)

### Tasks

- [X] T001 Install tiktoken library for token counting: `pip install tiktoken`
- [X] T002 [P] Create `codeframe/lib/` directory for new library modules
- [X] T003 [P] Create `codeframe/persistence/migrations/` directory if not exists
- [X] T004 [P] Create tests directory structure: `tests/context/` for context-specific tests
- [X] T005 [P] Create frontend directory structure: `web-ui/src/components/context/`, `web-ui/src/api/`, `web-ui/src/types/`, `web-ui/src/hooks/`
- [X] T006 [P] Create OpenAPI contract validation setup in `tests/contract/test_context_api_contract.py`
- [X] T007 Update `.gitignore` to exclude `*.pyc` and `__pycache__` in new directories
- [X] T008 Create feature flag in `codeframe/core/config.py`: `CONTEXT_MANAGEMENT_ENABLED = True`

**Completion Criteria**:
- All directories created
- tiktoken installed and importable
- Feature flag accessible

---

## Phase 2: Foundational Layer

**Goal**: Implement core infrastructure needed by all user stories

**Dependencies**: Phase 1 complete

**Parallel Opportunities**: Tasks T009-T015 can run in parallel (different files)

### Tasks

- [X] T009 [P] Create Pydantic models in `codeframe/core/models.py`:
  - `ContextItemType` enum (TASK, CODE, ERROR, TEST_RESULT, PRD_SECTION)
  - `ContextTier` enum (HOT, WARM, COLD) - Already exists in models.py
  - `ContextItemModel` model with all fields from data-model.md
  - `ContextItemCreateModel` request model
  - `ContextItemResponse` response model
  - `ContextStats` response model
  - `FlashSaveRequest` request model
  - `FlashSaveResponse` response model

- [ ] T010 [P] Create database migration 004 in `codeframe/persistence/migrations/migration_004_add_context_checkpoints.py`:
  - Create `context_checkpoints` table per data-model.md schema
  - Add index `idx_checkpoints_agent_created`
  - Include rollback logic

- [ ] T011 [P] Create database migration 005 in `codeframe/persistence/migrations/migration_005_add_context_indexes.py`:
  - Add `idx_context_agent_tier` index
  - Add `idx_context_importance` index
  - Add `idx_context_last_accessed` index
  - Include rollback logic

- [ ] T012 [P] Add database methods to `codeframe/persistence/database.py`:
  - `create_context_item(agent_id, item_type, content, importance_score, tier)` -> int
  - `get_context_item(item_id)` -> dict | None
  - `list_context_items(agent_id, tier=None, limit=100, offset=0)` -> List[dict]
  - `update_context_item_tier(item_id, tier, importance_score)` -> None
  - `delete_context_item(item_id)` -> None
  - `update_context_item_access(item_id)` -> None (updates last_accessed, access_count)

- [ ] T013 [P] Add checkpoint database methods to `codeframe/persistence/database.py`:
  - `create_checkpoint(agent_id, checkpoint_data, items_count, items_archived, hot_items_retained, token_count)` -> int
  - `list_checkpoints(agent_id, limit=10)` -> List[dict]
  - `get_checkpoint(checkpoint_id)` -> dict | None

- [ ] T014 [P] Create `codeframe/lib/token_counter.py`:
  - `TokenCounter` class with tiktoken integration
  - `count_tokens(content: str)` -> int method
  - Caching mechanism using content hash as key
  - Support for batch counting: `count_tokens_batch(contents: List[str])` -> List[int]

- [ ] T015 [P] Create WebSocket event types in `codeframe/core/models.py`:
  - `ContextTierUpdated` event (agent_id, item_count, tier_changes)
  - `FlashSaveCompleted` event (agent_id, checkpoint_id, reduction_percentage)

**Completion Criteria**:
- All Pydantic models defined and importable
- Migrations created and can be applied successfully
- Database methods accessible and type-hinted
- TokenCounter can count tokens using tiktoken
- WebSocket events defined

---

## Phase 3: User Story 1 - Context Item Storage

**Goal**: Agents can save and retrieve context items with persistence

**User Story**: As a worker agent, I want to save important context items to persistent storage so that I can retrieve them later without keeping everything in active memory.

**Dependencies**: Phase 2 complete

**Independent Test Criteria**:
- Can create context item via API
- Can retrieve context item by ID
- Can list context items for an agent
- Can delete context item
- Items persist across agent restarts (database test)

### Tasks

#### Tests (TDD - Write First)

- [ ] T016 [P] [US1] Create test file `tests/context/test_context_storage.py`:
  - `test_create_context_item_success()` - Verify item created in DB
  - `test_create_context_item_with_all_types()` - Test all 5 item types
  - `test_get_context_item_by_id()` - Retrieve existing item
  - `test_get_nonexistent_context_item_returns_none()` - 404 case
  - `test_list_context_items_for_agent()` - List all items
  - `test_list_context_items_pagination()` - Test limit/offset
  - `test_delete_context_item()` - Remove item from DB
  - `test_context_item_persists_across_sessions()` - DB persistence

- [ ] T017 [P] [US1] Create API contract test `tests/contract/test_context_create_api.py`:
  - `test_create_context_endpoint_exists()` - POST /api/agents/{id}/context returns 201
  - `test_create_context_validates_item_type()` - Rejects invalid type with 400
  - `test_create_context_validates_content_not_empty()` - Rejects empty content with 400

- [ ] T018 [P] [US1] Create API contract test `tests/contract/test_context_get_api.py`:
  - `test_get_context_endpoint_exists()` - GET /api/agents/{id}/context/{item_id} returns 200
  - `test_get_context_returns_404_for_nonexistent()` - Proper error handling
  - `test_get_context_updates_last_accessed()` - Timestamp updated on read

#### Implementation

- [ ] T019 [US1] Add API endpoint in `codeframe/ui/server.py`:
  - `POST /api/agents/{agent_id}/context` - Create context item
  - Request validation using `ContextItemCreate`
  - Auto-calculate initial importance_score (use placeholder 0.5 for now)
  - Auto-assign initial tier (WARM for now)
  - Return `ContextItemResponse`

- [ ] T020 [P] [US1] Add API endpoint in `codeframe/ui/server.py`:
  - `GET /api/agents/{agent_id}/context/{item_id}` - Get single item
  - Update `last_accessed` and `access_count` on read
  - Return 404 if not found

- [ ] T021 [P] [US1] Add API endpoint in `codeframe/ui/server.py`:
  - `GET /api/agents/{agent_id}/context` - List items with filters
  - Support `tier` query param (optional)
  - Support `limit` and `offset` for pagination
  - Return total count + items

- [ ] T022 [P] [US1] Add API endpoint in `codeframe/ui/server.py`:
  - `DELETE /api/agents/{agent_id}/context/{item_id}` - Delete item
  - Return 204 on success, 404 if not found

- [ ] T023 [US1] Add method to `codeframe/agents/worker_agent.py`:
  - `async def save_context_item(self, item_type: ContextItemType, content: str) -> int`
  - Call database `create_context_item()` with `agent_id=self.id`
  - Return created item ID

- [ ] T024 [P] [US1] Add method to `codeframe/agents/worker_agent.py`:
  - `async def load_context(self, tier: ContextTier | None = ContextTier.HOT) -> List[ContextItem]`
  - Call database `list_context_items()` filtered by tier
  - Update `last_accessed` for loaded items
  - Return list of `ContextItem` objects

- [ ] T025 [P] [US1] Add method to `codeframe/agents/worker_agent.py`:
  - `async def get_context_item(self, item_id: int) -> ContextItem | None`
  - Call database `get_context_item()`
  - Update access tracking
  - Return `ContextItem` or None

- [ ] T026 [US1] Add integration test in `tests/integration/test_worker_context_storage.py`:
  - `test_worker_saves_and_loads_context()` - End-to-end workflow
  - Create worker agent, save item, load item, verify persistence

**Completion Criteria**:
- ✅ All 3 contract tests passing (endpoints exist, validate input)
- ✅ All 8 storage tests passing (CRUD operations work)
- ✅ 1 integration test passing (worker agent can save/load)
- ✅ Can demonstrate: Agent saves task description → retrieves it later

---

## Phase 4: User Story 2 - Importance Scoring

**Goal**: Automatically calculate importance scores for context items based on type, age, and access patterns

**User Story**: As a worker agent, I want to automatically calculate importance scores for context items so that critical information stays accessible while stale data is archived.

**Dependencies**: Phase 3 complete (needs context storage)

**Independent Test Criteria**:
- Importance score calculated correctly for new items
- Score decays over time (age component)
- Score increases with access (frequency component)
- Item type affects base score (type component)
- Score stays within [0.0, 1.0] range

### Tasks

#### Tests (TDD - Write First)

- [ ] T027 [P] [US2] Create test file `tests/context/test_importance_scoring.py`:
  - `test_calculate_importance_for_new_task()` - Fresh TASK item gets high score (>0.8)
  - `test_calculate_importance_with_age_decay()` - 7-day-old item has lower score
  - `test_calculate_importance_with_access_boost()` - High access_count increases score
  - `test_importance_type_weights()` - TASK > CODE > ERROR > TEST_RESULT > PRD_SECTION
  - `test_importance_score_clamped_to_range()` - Result always in [0.0, 1.0]
  - `test_importance_formula_components()` - Verify 40% type + 40% age + 20% access

- [ ] T028 [P] [US2] Create test file `tests/context/test_score_decay.py`:
  - `test_exponential_decay_over_time()` - Verify e^(-0.5 × days) formula
  - `test_zero_age_gives_max_decay()` - New item: age_decay = 1.0
  - `test_old_items_approach_zero()` - 30-day-old item: age_decay < 0.1

#### Implementation

- [ ] T029 [US2] Create `codeframe/lib/importance_scorer.py`:
  - `ITEM_TYPE_WEIGHTS` constant dict (per data-model.md)
  - `calculate_age_decay(created_at: datetime) -> float` function
    - Formula: `exp(-0.5 * age_days)`
  - `calculate_access_boost(access_count: int) -> float` function
    - Formula: `log(access_count + 1) / 10`, capped at 1.0
  - `calculate_importance_score(item_type, created_at, access_count, last_accessed) -> float`
    - Combine components: `0.4 * type_weight + 0.4 * age_decay + 0.2 * access_boost`
    - Clamp to [0.0, 1.0]

- [ ] T030 [US2] Update `codeframe/persistence/database.py`:
  - Modify `create_context_item()` to auto-calculate importance_score using `calculate_importance_score()`
  - Remove hardcoded `importance_score` parameter

- [ ] T031 [US2] Update `codeframe/agents/worker_agent.py`:
  - Remove `importance_score` parameter from `save_context_item()` signature
  - Scoring happens automatically in database layer

- [ ] T032 [P] [US2] Create `codeframe/lib/context_manager.py`:
  - `ContextManager` class to encapsulate scoring logic
  - `recalculate_scores_for_agent(agent_id: str)` method
    - Load all items for agent
    - Recalculate importance_score for each
    - Update database
    - Return count of updated items

- [ ] T033 [US2] Add API endpoint in `codeframe/ui/server.py`:
  - `POST /api/agents/{agent_id}/context/update-scores` - Recalculate all scores
  - Call `ContextManager.recalculate_scores_for_agent()`
  - Return `{updated_count: int}`

- [ ] T034 [P] [US2] Update existing tests in `tests/context/test_context_storage.py`:
  - Verify `create_context_item()` now auto-calculates score
  - Check score is reasonable (0.5-1.0 for new items)

- [ ] T035 [P] [US2] Create integration test `tests/integration/test_score_recalculation.py`:
  - Create old item (mock created_at to 7 days ago)
  - Trigger score recalculation
  - Verify score decreased due to age decay

- [ ] T036 [US2] Add unit test for `ContextManager` in `tests/context/test_context_manager.py`:
  - `test_recalculate_scores_updates_all_items()`
  - `test_recalculate_scores_returns_count()`

**Completion Criteria**:
- ✅ All 9 scoring tests passing (formula correctness, decay, access boost)
- ✅ Context items created with auto-calculated scores
- ✅ Can demonstrate: New TASK (score ~0.95) vs 7-day-old ERROR (score ~0.4)
- ✅ Score recalculation endpoint works

---

## Phase 5: User Story 3 - Automatic Tier Assignment

**Goal**: Automatically assign tiers (HOT/WARM/COLD) based on importance scores

**User Story**: As a worker agent, I want to automatically tier context items based on importance so that I load only relevant context into my working memory.

**Dependencies**: Phase 4 complete (needs importance scoring)

**Independent Test Criteria**:
- Items with score >= 0.8 assigned to HOT tier
- Items with 0.4 <= score < 0.8 assigned to WARM tier
- Items with score < 0.4 assigned to COLD tier
- Tier reassignment updates when scores change
- Can filter context loading by tier

### Tasks

#### Tests (TDD - Write First)

- [ ] T037 [P] [US3] Create test file `tests/context/test_tier_assignment.py`:
  - `test_assign_tier_hot_for_high_score()` - score >= 0.8 → HOT
  - `test_assign_tier_warm_for_medium_score()` - 0.4 <= score < 0.8 → WARM
  - `test_assign_tier_cold_for_low_score()` - score < 0.4 → COLD
  - `test_tier_boundaries()` - Test exact threshold values (0.8, 0.4)
  - `test_tier_reassignment_on_score_change()` - Change score → tier updates

- [ ] T038 [P] [US3] Create test file `tests/context/test_tier_filtering.py`:
  - `test_load_context_hot_tier_only()` - Filter returns only HOT items
  - `test_load_context_all_tiers()` - No filter returns all items
  - `test_list_api_filters_by_tier()` - API query param works

#### Implementation

- [ ] T039 [US3] Add to `codeframe/lib/importance_scorer.py`:
  - `assign_tier(importance_score: float) -> ContextTier` function
    - Return HOT if score >= 0.8
    - Return WARM if 0.4 <= score < 0.8
    - Return COLD if score < 0.4

- [ ] T040 [US3] Update `codeframe/persistence/database.py`:
  - Modify `create_context_item()` to auto-assign tier using `assign_tier(score)`
  - Modify `update_context_item_tier()` to accept both tier and score

- [ ] T041 [US3] Update `codeframe/lib/context_manager.py`:
  - Add `update_tiers_for_agent(agent_id: str)` method
    - Recalculate scores for all items
    - Reassign tiers based on new scores
    - Return tier change statistics: `{hot_count, warm_count, cold_count, changes}`

- [ ] T042 [US3] Add API endpoint in `codeframe/ui/server.py`:
  - `POST /api/agents/{agent_id}/context/update-tiers` - Recalculate and reassign
  - Call `ContextManager.update_tiers_for_agent()`
  - Return tier counts and change count

- [ ] T043 [P] [US3] Update `codeframe/agents/worker_agent.py`:
  - Add `async def update_tiers(self) -> dict` method
  - Wrapper for `ContextManager.update_tiers_for_agent(self.id)`

- [ ] T044 [P] [US3] Update existing tests in `tests/context/test_context_storage.py`:
  - Verify new items assigned to correct tier (WARM for medium scores)
  - Verify `list_context_items(tier='HOT')` filtering works

- [ ] T045 [P] [US3] Create integration test `tests/integration/test_tier_lifecycle.py`:
  - Create new item (should be WARM/HOT based on type)
  - Wait (or mock time passage)
  - Recalculate tiers
  - Verify item moved to COLD as it aged

- [ ] T046 [US3] Add unit test `tests/context/test_assign_tier.py`:
  - Test `assign_tier()` function with various scores
  - Verify boundary conditions (0.8, 0.4, 0.0, 1.0)

**Completion Criteria**:
- ✅ All 7 tier assignment tests passing
- ✅ New items auto-assigned to appropriate tier
- ✅ Tier reassignment API works
- ✅ Can demonstrate: Filter loading by tier (load_context(tier='HOT'))

---

## Phase 6: User Story 4 - Flash Save

**Goal**: Checkpoint context when approaching token limits and resume with reduced memory

**User Story**: As a worker agent, I want to checkpoint my context when approaching token limits so that I can continue working without losing progress.

**Dependencies**: Phase 5 complete (needs tiered context)

**Independent Test Criteria**:
- Flash save triggers at 80% token threshold
- COLD items archived to checkpoint
- HOT items retained in memory
- Context restored from checkpoint
- Token count reduced by 30-50% after flash save

### Tasks

#### Tests (TDD - Write First)

- [ ] T047 [P] [US4] Create test file `tests/context/test_flash_save.py`:
  - `test_flash_save_creates_checkpoint()` - Checkpoint record in DB
  - `test_flash_save_archives_cold_items()` - COLD tier items marked archived
  - `test_flash_save_retains_hot_items()` - HOT tier items still accessible
  - `test_flash_save_calculates_reduction()` - Token count before/after tracked
  - `test_flash_save_below_threshold_fails()` - Returns 400 if not needed (unless force=True)

- [ ] T048 [P] [US4] Create test file `tests/context/test_token_counting.py`:
  - `test_count_tokens_single_item()` - TokenCounter works
  - `test_count_tokens_batch()` - Batch counting faster
  - `test_token_count_caching()` - Same content returns cached count
  - `test_count_context_tokens_for_agent()` - Total tokens across all items

- [ ] T049 [P] [US4] Create test file `tests/context/test_checkpoint_restore.py`:
  - `test_create_checkpoint_with_data()` - Checkpoint stores JSON state
  - `test_list_checkpoints_for_agent()` - Pagination works
  - `test_checkpoint_includes_metrics()` - items_count, token_count, etc.

#### Implementation

- [ ] T050 [US4] Update `codeframe/lib/token_counter.py`:
  - Add `count_context_tokens(context_items: List[dict]) -> int` method
    - Sum tokens across all item contents
    - Use caching for efficiency

- [ ] T051 [US4] Add to `codeframe/lib/context_manager.py`:
  - `should_flash_save(agent_id: str, force: bool = False) -> bool` method
    - Get current token count
    - Return True if >= 80% of 180k limit (144k tokens)
    - Return True if force=True

- [ ] T052 [US4] Add to `codeframe/lib/context_manager.py`:
  - `flash_save(agent_id: str) -> FlashSaveResponse` method
    - Get all context items
    - Count tokens before
    - Create checkpoint with full context state (JSON)
    - Archive COLD tier items (mark tier='ARCHIVED' or delete)
    - Count tokens after (only HOT tier)
    - Calculate reduction percentage
    - Return FlashSaveResponse

- [ ] T053 [US4] Update `codeframe/persistence/database.py`:
  - Add `archive_cold_items(agent_id: str)` method
    - Delete or mark all COLD tier items for agent

- [ ] T054 [US4] Add API endpoint in `codeframe/ui/server.py`:
  - `POST /api/agents/{agent_id}/flash-save` - Trigger flash save
  - Validate with `should_flash_save()` unless `force=True`
  - Call `ContextManager.flash_save()`
  - Return `FlashSaveResponse`

- [ ] T055 [P] [US4] Add API endpoint in `codeframe/ui/server.py`:
  - `GET /api/agents/{agent_id}/flash-save/checkpoints` - List checkpoints
  - Support `limit` query param (default 10)
  - Return checkpoint metadata (no full checkpoint_data)

- [ ] T056 [US4] Update `codeframe/agents/worker_agent.py`:
  - Implement `async def flash_save(self) -> FlashSaveResponse`
  - Remove TODO comment
  - Call `ContextManager.flash_save(self.id)`

- [ ] T057 [P] [US4] Update `codeframe/agents/worker_agent.py`:
  - Add `async def should_flash_save(self) -> bool` method
  - Count current context tokens
  - Call `ContextManager.should_flash_save()`

- [ ] T058 [P] [US4] Create integration test `tests/integration/test_flash_save_workflow.py`:
  - Create 150 context items (mix of HOT/WARM/COLD)
  - Trigger flash save
  - Verify COLD items archived
  - Verify HOT items still loadable
  - Verify token reduction >= 30%

- [ ] T059 [US4] Add WebSocket event emission in `codeframe/ui/server.py`:
  - Emit `FlashSaveCompleted` event after successful flash save
  - Include agent_id, checkpoint_id, reduction_percentage

**Completion Criteria**:
- ✅ All 11 flash save tests passing
- ✅ Flash save creates checkpoint with JSON state
- ✅ COLD items archived, HOT items retained
- ✅ Token count reduced by 30-50%
- ✅ Can demonstrate: Agent with 150k tokens → flash save → 50k tokens (HOT only)

---

## Phase 7: User Story 5 - Context Visualization (P1 - Optional Enhancement)

**Goal**: Dashboard displays context breakdown and tier statistics

**User Story**: As a developer, I want to see what context my agents are keeping so that I can understand their memory usage and debug issues.

**Dependencies**: Phase 6 complete (needs flash save + stats)

**Independent Test Criteria**:
- Dashboard shows tier counts (HOT/WARM/COLD)
- Dashboard shows token usage per tier
- Dashboard lists context items with scores
- Real-time updates via WebSocket
- Can filter items by tier

### Tasks

#### Tests (TDD - Write First)

- [ ] T060 [P] [US5] Create frontend test `web-ui/__tests__/components/ContextPanel.test.tsx`:
  - `test_renders_tier_breakdown()` - Shows HOT/WARM/COLD counts
  - `test_displays_token_usage()` - Shows total tokens and per-tier
  - `test_updates_on_websocket_event()` - Responds to ContextTierUpdated

- [ ] T061 [P] [US5] Create backend test `tests/context/test_context_stats.py`:
  - `test_get_context_stats_for_agent()` - Returns tier counts and tokens
  - `test_context_stats_calculates_tokens()` - Token count per tier correct

#### Implementation (Frontend)

- [ ] T062 [P] [US5] Create TypeScript types in `web-ui/src/types/context.ts`:
  - `ContextItem` interface
  - `ContextStats` interface
  - `ContextTier` type ('HOT' | 'WARM' | 'COLD')
  - `FlashSaveResponse` interface

- [ ] T063 [P] [US5] Create API client in `web-ui/src/api/context.ts`:
  - `fetchContextStats(agentId: string)` -> Promise<ContextStats>
  - `fetchContextItems(agentId: string, tier?: string)` -> Promise<ContextItem[]>
  - `triggerFlashSave(agentId: string)` -> Promise<FlashSaveResponse>

- [ ] T064 [US5] Create React component `web-ui/src/components/context/ContextPanel.tsx`:
  - Main container component
  - Displays tier breakdown (HOT/WARM/COLD counts)
  - Displays total token usage and percentage (X / 180k tokens)
  - Auto-refresh every 5 seconds
  - Props: `agentId: string`

- [ ] T065 [P] [US5] Create React component `web-ui/src/components/context/ContextTierChart.tsx`:
  - Pie chart or bar chart showing tier distribution
  - Color-coded: HOT (red), WARM (yellow), COLD (blue)
  - Shows percentages
  - Props: `stats: ContextStats`

- [ ] T066 [P] [US5] Create React component `web-ui/src/components/context/ContextItemList.tsx`:
  - Table displaying context items
  - Columns: Type, Content (truncated), Score, Tier, Age
  - Filterable by tier (dropdown)
  - Pagination (show 20 per page)
  - Props: `agentId: string`

#### Implementation (Backend)

- [ ] T067 [US5] Add API endpoint in `codeframe/ui/server.py`:
  - `GET /api/agents/{agent_id}/context/stats` - Get statistics
  - Calculate tier counts from database
  - Calculate token counts per tier using TokenCounter
  - Return `ContextStats`

**Completion Criteria**:
- ✅ All 3 component tests passing
- ✅ ContextPanel renders and shows tier breakdown
- ✅ ContextItemList displays items with pagination
- ✅ Stats endpoint returns correct counts
- ✅ Can demonstrate: Dashboard showing agent context (20 HOT, 50 WARM, 30 COLD)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Goal**: Final integration, documentation, and cleanup

**Dependencies**: All user stories complete

### Tasks

- [ ] T068 [P] Update `CLAUDE.md` with context management usage patterns and examples

- [ ] T069 Run full test suite and verify all 60+ tests passing:
  - `pytest tests/context/ -v`
  - `pytest tests/integration/ -v -k context`
  - `cd web-ui && npm test -- context`

**Completion Criteria**:
- All tests passing
- Documentation updated
- No TODOs remaining in code
- Feature ready for merge

---

## Dependency Graph

### Story Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational)
    ↓
Phase 3 (US1: Storage) ──────────┐
    ↓                             │
Phase 4 (US2: Scoring) ──────────┤
    ↓                             │
Phase 5 (US3: Tiers) ────────────┤ (All independent after Storage)
    ↓                             │
Phase 6 (US4: Flash Save) ───────┤
    ↓                             │
Phase 7 (US5: Visualization) ────┘
    ↓
Phase 8 (Polish)
```

**Critical Path**: Setup → Foundational → Storage → Scoring → Tiers → Flash Save → Polish

**Parallel Opportunities**:
- After Storage (Phase 3): Visualization (Phase 7) can start in parallel
- Within each phase: All [P] tasks can run concurrently

### Blocking Tasks

**Must Complete Before Any User Story**:
- T001-T008 (Setup)
- T009-T015 (Foundational)

**Must Complete Before Scoring (US2)**:
- T016-T026 (Storage - US1)

**Must Complete Before Tiers (US3)**:
- T027-T036 (Scoring - US2)

**Must Complete Before Flash Save (US4)**:
- T037-T046 (Tiers - US3)

**Visualization (US5) Can Start After**:
- T016-T026 (Storage - US1) only
- Does not depend on US2-US4 completion

---

## Parallel Execution Examples

### Phase 2 (Foundational) - Maximum Parallelism

Can run **all 7 tasks concurrently** (different files):

```bash
# Terminal 1
Task T009: Create Pydantic models

# Terminal 2
Task T010: Create migration 004

# Terminal 3
Task T011: Create migration 005

# Terminal 4
Task T012: Add context_items DB methods

# Terminal 5
Task T013: Add checkpoints DB methods

# Terminal 6
Task T014: Create TokenCounter

# Terminal 7
Task T015: Add WebSocket events
```

### Phase 3 (US1) - Test + Implementation Parallelism

Can run **tests and implementation in parallel** (TDD allows):

```bash
# Terminal 1 (Tests)
Task T016, T017, T018: Write all tests first

# Terminal 2 (API Implementation)
Task T019, T020, T021, T022: Implement API endpoints

# Terminal 3 (Agent Methods)
Task T023, T024, T025: Implement worker methods

# Terminal 4 (Integration)
Task T026: Integration test
```

### Phase 4 (US2) - Scoring Implementation

```bash
# Terminal 1
Task T027, T028: Write scoring tests

# Terminal 2
Task T029: Implement ImportanceScorer

# Terminal 3
Task T032: Implement ContextManager

# Terminal 4
Task T036: Unit tests for ContextManager
```

---

## Implementation Strategy

### MVP Scope (Recommended First Delivery)

**Deliver**: User Story 1 (Context Storage) only
- Agents can save and retrieve context items
- Basic persistence with database
- No scoring, tiers, or flash save yet
- ~11 tasks (T001-T026, excluding optional tests)
- **Est. Effort**: 4-6 hours
- **Value**: Agents gain basic memory persistence

**Demo**: Agent saves task description → loads it later → verifies in database

### Incremental Delivery Plan

1. **Sprint 1** (MVP): US1 - Context Storage (T001-T026)
2. **Sprint 2**: US2 - Importance Scoring (T027-T036)
3. **Sprint 3**: US3 - Tier Assignment (T037-T046)
4. **Sprint 4**: US4 - Flash Save (T047-T059)
5. **Sprint 5** (Optional): US5 - Visualization (T060-T067)

Each sprint delivers independently testable value.

### Test-First Approach

For each user story:
1. Write all test tasks first ([P] tasks can run in parallel)
2. Run tests → they fail (RED)
3. Implement features to make tests pass (GREEN)
4. Refactor if needed (REFACTOR)

Example for US1:
```bash
# Step 1: Write tests (all in parallel)
Task T016, T017, T018

# Step 2: Run tests → RED
pytest tests/context/test_context_storage.py  # All fail

# Step 3: Implement → GREEN
Tasks T019-T025

# Step 4: Verify → All pass
pytest tests/context/test_context_storage.py  # All pass ✓
```

---

## Task Summary

| Phase | User Story | Task Range | Count | Parallel | Est. Effort |
|-------|------------|------------|-------|----------|-------------|
| 1 | Setup | T001-T008 | 8 | 6 | 1-2 hours |
| 2 | Foundational | T009-T015 | 7 | 7 | 2-3 hours |
| 3 | US1: Storage | T016-T026 | 11 | 8 | 4-6 hours |
| 4 | US2: Scoring | T027-T036 | 10 | 6 | 3-4 hours |
| 5 | US3: Tiers | T037-T046 | 10 | 6 | 3-4 hours |
| 6 | US4: Flash Save | T047-T059 | 13 | 7 | 5-6 hours |
| 7 | US5: Viz (P1) | T060-T067 | 8 | 6 | 4-5 hours |
| 8 | Polish | T068-T069 | 2 | 1 | 1 hour |
| **Total** | | **T001-T069** | **69** | **42** | **24-31 hours** |

**Key Metrics**:
- **MVP Scope**: 26 tasks (Setup + Foundational + US1)
- **P0 Core**: 59 tasks (all except US5 visualization)
- **Parallelizable**: 42 tasks (61% can run concurrently)
- **Est. Time with Parallelism**: 12-16 hours (assuming 2-3 parallel workers)

---

## References

- **Feature Specification**: [spec.md](spec.md)
- **Implementation Plan**: [plan.md](plan.md)
- **Data Model**: [data-model.md](data-model.md)
- **API Contracts**: [contracts/openapi.yaml](contracts/openapi.yaml)
- **Research**: [research.md](research.md)
- **Quickstart Guide**: [quickstart.md](quickstart.md)

---

**Next Step**: Run `/speckit.implement` to begin executing these tasks with agent coordination.
