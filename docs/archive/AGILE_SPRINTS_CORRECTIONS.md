# AGILE_SPRINTS.md Required Corrections
## Quick Reference Guide for Updates

**Date**: 2025-11-08
**Source**: AGILE_SPRINTS_AUDIT_REPORT.md

---

## Correction #1: Sprint 5 Title and Scope (Line 2049)

**Current**:
```markdown
## Sprint 5: Human in the Loop (Week 5)
```

**Change to**:
```markdown
## Sprint 5: Async Worker Agents (Week 5) ✅ COMPLETE
```

**Rationale**: Actual work completed was cf-48 (async migration), not blocker system. README already reflects this.

---

## Correction #2: Sprint 5 Implementation Tasks (Lines 2080-2108)

**Current**:
```markdown
**Implementation Tasks**:
- [ ] **cf-26**: Blocker creation and storage (P0)
- [ ] **cf-27**: Blocker resolution UI (P0)
- [ ] **cf-28**: Agent resume after blocker resolved (P0)
- [ ] **cf-29**: SYNC vs ASYNC blocker handling (P1)
- [ ] **cf-30**: Notification system (email/webhook) (P1)
```

**Change to**:
```markdown
**Implementation Tasks**:
- [x] **cf-48**: Convert worker agents to async (P0)
  - [x] BackendWorkerAgent to async/await pattern
  - [x] FrontendWorkerAgent to async/await pattern
  - [x] TestWorkerAgent to async/await pattern
  - [x] LeadAgent direct await (removed run_in_executor)
  - [x] AsyncAnthropic client integration
  - [x] All 93 tests migrated and passing
  - Demo: ✅ Multiple agents execute concurrently without threading
  - Git PR: #11 (commits: 9ff2540, 324e555, b4b61bf, debcf57)
```

---

## Correction #3: Sprint 5 Definition of Done (Lines 2110-2116)

**Current**:
```markdown
**Definition of Done**:
- ✅ Agents create blockers when stuck
- ✅ Blockers appear in dashboard with severity
- ✅ Can answer questions via UI
- ✅ Agents resume after answer received
- ✅ SYNC blockers pause work, ASYNC don't
- ✅ Notifications sent for SYNC blockers
```

**Change to**:
```markdown
**Definition of Done**:
- ✅ All worker agents use async/await pattern
- ✅ AsyncAnthropic client replaces sync client
- ✅ WebSocket broadcasts work without deadlocks
- ✅ No threading overhead (native async)
- ✅ 93/93 tests passing
- ✅ 30-50% performance improvement verified
- ✅ Breaking changes documented in README
```

---

## Correction #4: Sprint 5 Sprint Review (Line 2117)

**Current**:
```markdown
**Sprint Review**: Working human-AI collaboration - agents ask for help when needed!
```

**Change to**:
```markdown
**Sprint Review**: ✅ Async migration complete - true concurrent execution achieved! 30-50% performance improvement with cleaner architecture (-115 LOC).
```

---

## Correction #5: Insert New Sprint 6 - Human in the Loop (After line 2120)

**Add**:
```markdown
---

## Sprint 6: Human in the Loop (Week 6) - DEFERRED

**Goal**: Agents can ask for help when blocked

**User Story**: As a developer, I want agents to ask me questions when stuck, answer via the dashboard, and watch them continue working.

**Implementation Tasks**:
- [ ] **cf-NEW-26**: Blocker creation and storage (P0)
  - ⚠️ Status: Database schema exists, no implementation
  - Agent creates blocker when stuck
  - Store in blockers table
  - Classify as SYNC or ASYNC
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-27**: Blocker resolution UI (P0)
  - ⚠️ Status: API endpoints exist, no UI components
  - Modal for answering questions
  - Submit answer via API
  - Update blocker status
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-28**: Agent resume after blocker resolved (P0)
  - ⚠️ Status: Not implemented
  - Agent receives answer
  - Continues task execution
  - Updates dashboard
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-29**: SYNC vs ASYNC blocker handling (P1)
  - ⚠️ Status: Severity field in schema, no logic
  - SYNC: Pause dependent work
  - ASYNC: Continue other tasks
  - Visual distinction in UI
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-30**: Notification system (email/webhook) (P1)
  - ⚠️ Status: Config exists, no sending logic
  - Send notification on SYNC blocker
  - Zapier webhook integration
  - Demo: CANNOT DEMO (not implemented)

**Definition of Done**:
- [ ] Agents create blockers when stuck
- [ ] Blockers appear in dashboard with severity
- [ ] Can answer questions via UI
- [ ] Agents resume after answer received
- [ ] SYNC blockers pause work, ASYNC don't
- [ ] Notifications sent for SYNC blockers

**Sprint Review**: DEFERRED - Database schema exists, implementation pending.

**Dependencies**: Requires async agents (Sprint 5) ✅ complete.
```

---

## Correction #6: Renumber Current Sprint 6 to Sprint 7 (Line 2121)

**Current**:
```markdown
## Sprint 6: Context Management (Week 6)
```

**Change to**:
```markdown
## Sprint 7: Context Management (Week 7) - DEFERRED
```

---

## Correction #7: Sprint 7 (formerly 6) Definition of Done (Lines 2196-2203)

**Current**:
```markdown
**Definition of Done**:
- ✅ Context items stored with importance scores
- ✅ Items automatically tiered (HOT/WARM/COLD)
- ✅ Flash saves trigger before context limit
- ✅ Agents continue working after flash save
- ✅ Dashboard shows context breakdown
- ✅ 30-50% token reduction achieved
```

**Change to**:
```markdown
**Definition of Done**:
- [ ] Context items stored with importance scores (⚠️ Schema exists, no implementation)
- [ ] Items automatically tiered (HOT/WARM/COLD) (❌ Not implemented)
- [ ] Flash saves trigger before context limit (⚠️ Stub with TODO)
- [ ] Agents continue working after flash save (❌ Not implemented)
- [ ] Dashboard shows context breakdown (❌ Not implemented)
- [ ] 30-50% token reduction achieved (⏸️ Cannot measure without implementation)

**Status**: Database schema complete. Implementation deferred.
**Schema**: context_items table (database.py:169)
**Stubs**: WorkerAgent.flash_save() has TODO (worker_agent.py:50)
```

---

## Correction #8: Update Sprint 7 (formerly 6) Task Status (Lines 2158-2194)

**Add status indicators to each task**:

```markdown
- [ ] **cf-NEW-31**: Implement ContextItem storage (P0)
  - ⚠️ Status: Schema exists (context_items table), no write logic
  - Save context items to DB
  - Track importance scores
  - Access count tracking
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-32**: Importance scoring algorithm (P0)
  - ❌ Status: Not implemented
  - Calculate scores based on type, age, access
  - Automatic tier assignment
  - Score decay over time
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-33**: Context diffing and hot-swap (P0)
  - ❌ Status: Not implemented
  - Calculate context changes
  - Load only new/updated items
  - Remove stale items
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-34**: Flash save before compactification (P0)
  - ⚠️ Status: Stub exists with TODO comment
  - Detect context >80% of limit
  - Create checkpoint
  - Archive COLD items
  - Resume with fresh context
  - Demo: CANNOT DEMO (not implemented)
  - File: worker_agent.py:48-51

- [ ] **cf-NEW-35**: Context visualization in dashboard (P1)
  - ❌ Status: Not implemented
  - Show tier breakdown
  - Token usage per tier
  - Item list with importance scores
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-36.5**: Claude Code Hooks Integration (P1)
  - ⚠️ Status: Beads issue cf-36 exists but open
  - Integrate with Claude Code hooks system
  - before_compact hook for flash save
  - State preservation during compactification
  - Demo: CANNOT DEMO (not implemented)
  - **Estimated Effort**: 2-3 hours
```

---

## Correction #9: Renumber Current Sprint 7 to Sprint 8 (Line 2208)

**Current**:
```markdown
## Sprint 7: Agent Maturity (Week 7)
```

**Change to**:
```markdown
## Sprint 8: Agent Maturity (Week 8) - DEFERRED
```

---

## Correction #10: Sprint 8 (formerly 7) Definition of Done (Lines 2266-2270)

**Current**:
```markdown
**Definition of Done**:
- ✅ Metrics tracked for all agents
- ✅ Maturity levels auto-adjust based on performance
- ✅ Task instructions adapt to maturity
- ✅ Dashboard shows maturity and metrics
- ✅ Agents become more autonomous over time
```

**Change to**:
```markdown
**Definition of Done**:
- [ ] Metrics tracked for all agents (⚠️ agents.metrics JSON exists, never populated)
- [ ] Maturity levels auto-adjust based on performance (⚠️ Stub with TODO)
- [ ] Task instructions adapt to maturity (❌ Not implemented)
- [ ] Dashboard shows maturity and metrics (❌ Not implemented)
- [ ] Agents become more autonomous over time (⏸️ Cannot verify without implementation)

**Status**: Database schema complete (agents.maturity_level field). Implementation deferred.
**Schema**: agents table with maturity_level CHECK constraint (database.py:132)
**Stubs**: WorkerAgent.assess_maturity() has TODO (worker_agent.py:45)
**Model**: AgentMaturity enum exists (models.py)
```

---

## Correction #11: Update Sprint 8 (formerly 7) Task Status (Lines 2240-2263)

**Add status indicators**:

```markdown
- [ ] **cf-NEW-36**: Agent metrics tracking (P0)
  - ⚠️ Status: Schema exists (agents.metrics JSON), never written
  - Track success rate, blockers, tests, rework
  - Store in agents.metrics JSON
  - Update after each task
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-37**: Maturity assessment logic (P0)
  - ⚠️ Status: Stub exists with TODO comment
  - Calculate maturity based on metrics
  - Promote/demote based on performance
  - Store maturity level in DB
  - Demo: CANNOT DEMO (not implemented)
  - File: worker_agent.py:43-46

- [ ] **cf-NEW-38**: Adaptive task instructions (P0)
  - ❌ Status: Not implemented
  - D1: Detailed step-by-step
  - D2: Guidance + examples
  - D3: Minimal instructions
  - D4: Goal only
  - Demo: CANNOT DEMO (not implemented)

- [ ] **cf-NEW-39**: Maturity visualization (P1)
  - ❌ Status: Not implemented
  - Show current maturity level
  - Display metrics chart
  - Show progression history
  - Demo: CANNOT DEMO (not implemented)
```

---

## Correction #12: Renumber Current Sprint 8 to Sprint 9 (Line 2276)

**Current**:
```markdown
## Sprint 8: Review & Polish (Week 8)
```

**Change to**:
```markdown
## Sprint 9: Review & Polish (Week 9) - NOT STARTED
```

---

## Correction #13: Sprint 9 (formerly 8) Definition of Done (Lines 2357-2363)

**Current**:
```markdown
**Definition of Done**:
- ✅ Review Agent operational
- ✅ Quality gates prevent bad code
- ✅ Checkpoint/resume works
- ✅ Cost tracking accurate
- ✅ Full system works end-to-end
- ✅ All Sprint 1-7 features integrated
- ✅ MVP complete and usable
```

**Change to**:
```markdown
**Definition of Done**:
- [ ] Review Agent operational (❌ No review_agent.py exists)
- [ ] Quality gates prevent bad code (❌ Not implemented)
- [ ] Checkpoint/resume works (⚠️ Schema exists, resume() has TODO)
- [ ] Cost tracking accurate (❌ Not implemented)
- [ ] Full system works end-to-end (❌ No E2E tests)
- [ ] All Sprint 1-8 features integrated (⏸️ Sprints 6-8 deferred)
- [ ] MVP complete and usable (⏸️ Pending Sprints 6-9)

**Status**: Not started. Database schema exists for checkpoints.
**Blockers**: Requires Sprints 6-8 completion.
```

---

## Correction #14: Update Sprint 9 (formerly 8) Task Status (Lines 2326-2354)

**CRITICAL**: Issue ID conflicts with Sprint 3. Need new IDs.

```markdown
- [ ] **cf-NEW-40**: Create Review Agent (P0)
  - ❌ Status: Not started (no review_agent.py or review.yaml)
  - Code quality analysis
  - Security scanning
  - Performance checks
  - Demo: CANNOT DEMO (not implemented)
  - Note: cf-40 already used for "Frontend Project Initialization"

- [ ] **cf-NEW-41**: Quality gates (P0)
  - ❌ Status: Not implemented
  - Block completion if tests fail
  - Block if review finds critical issues
  - Require human approval for risky changes
  - Demo: CANNOT DEMO (not implemented)
  - Note: cf-41 already used for "Backend Worker Agent"

- [ ] **cf-NEW-42**: Checkpoint and recovery system (P0)
  - ⚠️ Status: Schema exists, stubs have TODOs
  - Manual checkpoint creation
  - Restore from checkpoint
  - List checkpoints
  - Demo: CANNOT DEMO (not implemented)
  - Files: project.py:77 (TODO), server.py:866 (TODO)
  - Note: cf-42 already used for "Test Runner Integration"

- [ ] **cf-NEW-43**: Metrics and cost tracking (P1)
  - ❌ Status: Not implemented
  - Track token usage per agent
  - Calculate costs
  - Display in dashboard
  - Demo: CANNOT DEMO (not implemented)
  - Note: cf-43 already used for "Self-Correction Loop"

- [ ] **cf-NEW-44**: End-to-end integration testing (P0)
  - ❌ Status: Not implemented
  - Full workflow test
  - All features working together
  - No regressions
  - Demo: CANNOT DEMO (not implemented)
  - Note: cf-44 already used for "Git Auto-Commit"
```

---

## Correction #15: Renumber Current Sprint 9 to Sprint 10 (Line 2369)

**Current**:
```markdown
## Sprint 9: Advanced Agent Routing (Future)
```

**Change to**:
```markdown
## Sprint 10: Advanced Agent Routing (Future) - PARTIALLY COMPLETE
```

---

## Correction #16: Sprint 10 (formerly 9) Definition of Done (Lines 2408-2414)

**Current**:
```markdown
**Definition of Done**:
- ✅ Users can add custom agents via `.codeframe/agents/definitions/`
- ✅ Tasks auto-analyzed for required capabilities
- ✅ Agents matched to tasks by capability overlap
- ✅ Lead Agent uses AgentFactory for discovery
- ✅ No hardcoded agent type checks
- ✅ 100% backward compatible with simple assignment
```

**Change to**:
```markdown
**Definition of Done**:
- [x] Users can add custom agents via `.codeframe/agents/definitions/` (✅ Complete)
- [ ] Tasks auto-analyzed for required capabilities (❌ No TaskAnalyzer)
- [ ] Agents matched to tasks by capability overlap (❌ No AgentMatcher)
- [x] Lead Agent uses AgentFactory for discovery (✅ Complete)
- [ ] No hardcoded agent type checks (⚠️ Still uses simple_assignment.py)
- [x] 100% backward compatible with simple assignment (✅ Complete)

**Status**: Infrastructure complete, intelligent routing pending.
**Complete**: Agent definitions, AgentFactory, project overrides
**Pending**: TaskAnalyzer, AgentMatcher, scoring algorithm
```

---

## Correction #17: Add Implementation Status Section (Insert after line 2048)

**Add before Sprint 5**:

```markdown
---

## Implementation Status Legend

Use these indicators to track actual progress vs. planned work:

- ✅ **COMPLETE**: Code implemented, tests passing, demo verified
- ⚠️ **SCHEMA ONLY**: Database tables exist but no application code
- ⚠️ **STUB**: Function signature exists with TODO comment
- ⚠️ **PARTIAL**: Some components implemented, others missing
- ❌ **NOT STARTED**: No code or schema exists
- 🔄 **IN PROGRESS**: Active development underway
- ⏸️ **DEFERRED**: Postponed to future sprint
- 🔀 **REPLACED**: Original plan changed, different work completed

**Verification**:
- Schema: Check database.py for CREATE TABLE
- Code: Search for function definitions and grep for TODO
- Tests: Run test suite and check coverage
- Git: Look for commit messages referencing issue IDs
- Beads: Run `bd show <issue-id>` for status

---
```

---

## Correction #18: Add Cross-Reference Notes to Sprint 5

**Add after line 2117**:

```markdown
**Cross-References**:
- Git PR: #11 (https://github.com/frankbria/codeframe/pull/11)
- README: Lines 36-74 (Sprint 5 announcement)
- Beads Issue: cf-48 (should be closed but shows open)
- Key Commits:
  - 9ff2540: feat: convert worker agents to async/await (cf-48 Phase 1-3)
  - 324e555: fix: correct async test migration issues
  - b4b61bf: test: migrate all worker agent tests to async/await
  - debcf57: fix: complete async migration for self-correction integration tests

**Breaking Changes**: All worker agent methods now async. See CHANGELOG.md.

**Performance**: 30-50% improvement in concurrent task execution.

**Files Modified** (19 files, +3,463/-397 LOC):
- codeframe/agents/backend_worker_agent.py
- codeframe/agents/frontend_worker_agent.py
- codeframe/agents/test_worker_agent.py
- codeframe/agents/lead_agent.py
- tests/test_backend_worker_agent.py (async)
- tests/test_frontend_worker_agent.py (async)
- tests/test_test_worker_agent.py (async)
- tests/test_self_correction_integration.py (async)
```

---

## Summary Statistics

**Total Corrections**: 18
**Lines Affected**: ~400 lines
**Checkboxes to Change**: 32 (from ✅ to [ ])
**New Issues to Create**: ~20 (with non-conflicting IDs)
**Sprints Renumbered**: 5 sprints shifted by +1

**Priority Order**:
1. Corrections 1-5 (Sprint 5 alignment with README) - CRITICAL
2. Corrections 6-11 (Sprint 6-8 checkbox accuracy) - HIGH
3. Corrections 12-16 (Sprint numbering and conflict resolution) - MEDIUM
4. Corrections 17-18 (Documentation improvements) - LOW

**Estimated Time**: 45-60 minutes for all corrections

---

**Next Steps**:
1. Apply corrections 1-5 immediately (Sprint 5 alignment)
2. Review and apply corrections 6-16 (accuracy fixes)
3. Create new beads issues with correct IDs
4. Update README roadmap to match
5. Close cf-48 in beads (async migration complete)

---

**End of Corrections Guide**
