# Sprint 7: Context Management

**Status**: ⚠️ Schema Only
**Duration**: Week 7 (Planned)
**Epic/Issues**: cf-31 through cf-35, cf-36 (cf-36 exists in beads, open)

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

## Current Status

**What Exists**:
- Database schema: `context_items` table (created in database.py:169-182)
- Fields: id, agent_id, item_type, content, importance_score, tier, access_count, created_at, last_accessed
- Stub method: WorkerAgent.flash_save() (currently just `pass` with TODO)
- Migration 004: `context_checkpoints` table with indexes (2025-11-14)
- Migration 005: Performance indexes on `context_items` table (2025-11-14)

**What's Missing**:
- Importance scoring algorithm (no code exists)
- Tier assignment logic (HOT/WARM/COLD not implemented)
- Context diffing mechanism
- flash_save() implementation (current stub does nothing)
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
