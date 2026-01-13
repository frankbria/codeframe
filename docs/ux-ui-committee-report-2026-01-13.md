# CodeFrame UX/UI Committee Report

**Date:** 2026-01-13
**Committee:** 11 Expert Subagents
**Scope:** Complete UX/UI Gap Analysis for 10-Step User Journey

---

## Executive Summary

**Overall Grade: C+ (72/100)**

The CodeFrame application demonstrates solid foundational architecture for steps 1-7 of the user journey, but critically fails on steps 8-10 (Git/PR workflow). The UI suffers from over-engineering, unclear navigation paths, and missing core features that would complete the development lifecycle.

### Journey Step Grades

| Step | Description | Grade | Status |
|------|-------------|-------|--------|
| 1 | Create Project | B+ | Functional |
| 2 | PRD Generation | B | Functional, needs polish |
| 3 | Tasks from PRD | B+ | Functional |
| 4 | Agent Assignment | B | Functional |
| 5 | Quality Gate Review | B+ | Functional |
| 6 | Fix Failing Code | C | Partial - blockers UI broken |
| 7 | Approve Passing Code | C | Button visibility issues |
| 8 | Git Commits | F | **Missing entirely** |
| 9 | PR Creation | F | **Missing entirely** |
| 10 | PR Merge | F | **Missing entirely** |

---

## Committee Members & Grades

| Expert | Focus Area | Grade |
|--------|------------|-------|
| Backend Architect | API completeness | B+ |
| Frontend Architect | Component structure | C+ |
| Product Manager | User journey clarity | B+ |
| Project Shipper | Launch readiness | C+ |
| Python Expert | Code quality | B+ (85/100) |
| React Expert | Component architecture | B+ |
| Requirements Analyst | Spec coverage | C+ |
| Security Engineer | Auth/security | B+ |
| System Architect | Overall architecture | B+ |
| WebSocket Expert | Real-time updates | B+ |
| UX/UI Designer | User experience | C+ |

---

## Section-by-Section Gap Analysis

### 1. Project Creation & Onboarding
**Grade: B-**

**Gaps:**
- No onboarding flow for new users
- No global progress indicator showing where user is in 10-step journey
- Landing page jumps directly to project creation without context
- No "Getting Started" guide or walkthrough

**Over-engineering:**
- Cost estimation UI is "version 3+" functionality that confuses new users
- Token optimization settings exposed too early

**Related Issues:** None open

---

### 2. Discovery/PRD Phase
**Grade: B**

**Gaps:**
- Discovery can get stuck with no recovery path (#255)
- Phase restart button non-functional (#247)
- No clear visual indication of PRD being generated

**Over-engineering:**
- DiscoveryProgress.tsx at 1,165 lines - should be split into smaller components
- Complex phase state machine exposed to UI

**Related Issues:** #255 (P1), #247 (P1)

---

### 3. Task Breakdown
**Grade: B+**

**Gaps:**
- Task list doesn't clearly show relationship to PRD requirements
- No task prioritization UI

**Over-engineering:**
- Multiple context providers for what could be simpler state

**Related Issues:** None critical

---

### 4. Agent Assignment
**Grade: B**

**Gaps:**
- Agent assignment happens automatically but UI doesn't clearly show which agent has which task
- No manual agent reassignment capability
- Agent status updates can be confusing

**Over-engineering:**
- AgentStateContext + reducer pattern adds complexity for simple state

**Related Issues:** None critical

---

### 5. Quality Gate Review
**Grade: B+**

**Gaps:**
- Gate failures don't clearly explain what user should do next
- No "re-run gates" button after fixes

**Over-engineering:**
- 5-stage gate system (tests, type_check, coverage, lint, ai_review) may be excessive for MVP

**Related Issues:** None critical

---

### 6. Fix Failing Code
**Grade: D**

**Gaps:**
- **Blockers buttons disappear** (#269 - P0)
- No inline code editing capability
- User must manually coordinate fixes outside the app
- No "suggest fix" functionality

**Over-engineering:**
- Complex blocker state management for non-functional feature

**Related Issues:** #269 (P0)

---

### 7. Approve Passing Code
**Grade: C**

**Gaps:**
- **Task approval button not visible** (#254 - P1)
- Approval workflow unclear
- No batch approval for multiple passing tasks

**Over-engineering:**
- Multiple confirmation dialogs

**Related Issues:** #254 (P1)

---

### 8. Git Commits to Branches
**Grade: F**

**Gaps:**
- **Feature completely missing from UI**
- GitWorkflowManager exists in backend but not exposed
- No branch visualization
- No commit history view
- No file diff viewer

**Backend Status:** Partial - `codeframe/git/workflow_manager.py` has local operations but no UI integration

**Related Issues:** #270 (NEW - P0)

---

### 9. PR Creation & Analysis
**Grade: F**

**Gaps:**
- **Feature completely missing**
- No GitHub integration UI
- No PR template generation
- No PR preview before creation

**Backend Status:** Missing - No GitHub API integration for PR creation

**Related Issues:** #272 (NEW - P0)

---

### 10. PR Merge
**Grade: F**

**Gaps:**
- **Feature completely missing**
- No merge conflict resolution UI
- No merge status tracking
- No post-merge cleanup

**Backend Status:** Missing entirely

**Related Issues:** #273 (NEW - P0)

---

## Additional Cross-Cutting Concerns

### Security (Grade: B+)
- JWT stored in localStorage (#165 - P2) - should use httpOnly cookies
- No API rate limiting (#167 - P2)
- Auth is solid with FastAPI Users

### Testing (Grade: C)
- 39 E2E test failures reported by project-shipper
- Tests verify DOM but not API success
- WebSocket tests accept 0 messages as success

### Architecture Over-Engineering
- LeadAgent at 110KB is a monolith that should be decomposed (#276)
- 17 repository pattern may be excessive
- Dashboard.tsx at 934 lines needs splitting (#277)
- DiscoveryProgress.tsx at 1,165 lines needs splitting (#278)

---

## GitHub Issues Summary

### New Issues Created

| Issue | Priority | Title |
|-------|----------|-------|
| #270 | P0 | Backend: Expose Git branch and commit APIs |
| #271 | P0 | Frontend: Git commit and branch visualization UI |
| #272 | P0 | Backend: GitHub PR creation and management API |
| #273 | P0 | Frontend: PR creation, review, and merge UI |
| #274 | P1 | UX: Add global progress stepper showing 10-step journey position |
| #275 | P1 | UX: Add first-time user onboarding flow |
| #276 | P2 | Refactor: Decompose LeadAgent monolith (110KB) |
| #277 | P2 | Refactor: Split Dashboard.tsx (934 lines) |
| #278 | P2 | Refactor: Split DiscoveryProgress.tsx (1,165 lines) |
| #279 | P1 | Backend: Add WebSocket events for Git and PR operations |
| #280 | P2 | UX: Add explicit task retry and re-assignment workflow |

### Existing Issues Cross-Referenced

| Issue | Priority | Status |
|-------|----------|--------|
| #269 | P0 | Blockers buttons disappear - **CRITICAL** |
| #255 | P1 | Discovery stuck state |
| #254 | P1 | Task approval button not visible |
| #247 | P1 | Restart Discovery button non-functional |
| #219 | P1 | Emoji cleanup |
| #165 | P2 | JWT storage in localStorage (security) |
| #167 | P2 | API Rate Limiting |

### Issues Closed (Superseded)

| Issue | Reason |
|-------|--------|
| #116 | Superseded by #272 (PR creation) |
| #117 | Superseded by #272 (merge conflicts) |

### Issues Re-labeled as "Future"

| Issue | Reason |
|-------|--------|
| #73 | Procedural memory - advanced AI/ML feature |
| #71 | Adaptive failure handling - not core |
| #55 | TaskTreeView memoization - premature optimization |
| #120 | by_day token aggregation - over-engineering |
| #121 | Workspace upload extraction - not core |
| #122 | Issue dependencies parsing - optimization |
| #123 | Custom SDK hooks - advanced extensibility |
| #232 | PostgreSQL migration - infrastructure |

---

## Priority Order for Implementation

### P0 - Critical (Must Fix Before Beta)

**Dependency Order:**
1. **#269** - Fix blockers button visibility (bug fix, no deps)
2. **#254** - Fix task approval button visibility (bug fix, no deps)
3. **#270** - Git branch/commit APIs (backend, foundation for UI)
4. **#271** - Git commit UI (frontend, requires #270)
5. **#272** - GitHub PR API (backend, requires #270)
6. **#279** - WebSocket events for Git/PR (backend, parallel with #272)
7. **#273** - PR UI components (frontend, requires #271, #272)

### P1 - High Priority (Should Fix Before Beta)

8. **#274** - Global progress stepper
9. **#275** - Onboarding flow
10. **#255** - Discovery stuck state fix
11. **#247** - Restart Discovery button fix
12. **#219** - Emoji cleanup

### P2 - Medium Priority (Nice to Have for Beta)

13. **#276** - LeadAgent refactoring
14. **#277** - Dashboard.tsx refactoring
15. **#278** - DiscoveryProgress.tsx refactoring
16. **#280** - Task retry/re-assignment UX
17. **#165** - JWT to httpOnly cookies
18. **#167** - API rate limiting

---

## Frontend TODOs (Priority Order)

### P0 - Critical (Must fix)
1. **Fix blockers button visibility** - #269
2. **Fix task approval button visibility** - #254
3. **Add global progress stepper** - #274

### P1 - High Priority
4. **Implement Git commit UI** (#271)
   - Branch selector/creator
   - Staged files view
   - Commit message input
   - Commit history panel

5. **Implement PR creation UI** (#273)
   - PR form with title, description, reviewers
   - Diff preview
   - GitHub integration status

6. **Implement PR merge UI** (#273)
   - Merge status indicator
   - Conflict resolution view
   - Merge confirmation

7. **Fix discovery restart button** - #247
8. **Add recovery path for stuck discovery** - #255

### P2 - Medium Priority
9. **Add onboarding flow** - #275
10. **Split DiscoveryProgress.tsx** - #278
11. **Split Dashboard.tsx** - #277
12. **Hide advanced features** - Token optimization, cost estimation behind "Advanced" toggle
13. **Remove unnecessary emojis** - #219
14. **Add batch task approval**
15. **Add "re-run quality gates" button**

---

## Backend TODOs (Priority Order)

### P0 - Critical (Must implement)
1. **Create Git Branch API** (#270)
   ```
   POST /api/projects/{id}/git/branches
   GET /api/projects/{id}/git/branches
   GET /api/projects/{id}/git/status
   POST /api/projects/{id}/git/commit
   ```

2. **Create GitHub PR API** (#272)
   ```
   POST /api/projects/{id}/prs
   GET /api/projects/{id}/prs
   POST /api/projects/{id}/prs/{number}/merge
   ```

### P1 - High Priority
3. **Add WebSocket events for Git/PR** (#279)
   - `branch_created`
   - `pr_created`
   - `pr_merged`
   - `pr_closed`

4. **Fix blocker state management** - #269

5. **Add API rate limiting** - #167

### P2 - Medium Priority
6. **Migrate JWT to httpOnly cookies** - #165
7. **Decompose LeadAgent** - #276
8. **Add task retry endpoint** - #280

---

## Committee Consensus

All 11 experts agree:

1. **Steps 8-10 are completely missing** - This is the most critical gap. The app stops at code approval but never delivers code to the user's repository.

2. **Over-engineering is present** - 17 repositories, 110KB LeadAgent, 1,165-line components are excessive for current functionality.

3. **UX clarity is lacking** - No onboarding, no progress indicator, expert features exposed to novice users.

4. **Core flows (1-7) are functional** - The foundation is solid; focus should be on completing the journey, not adding more features to existing steps.

---

## Recommended Sprint Focus

### Week 1: Fix P0 Bugs + Git API
- Fix #269 (blockers)
- Fix #254 (approval button)
- Implement #270 (Git branch/commit API)

### Week 2: PR Workflow
- Implement #272 (GitHub PR API)
- Implement #279 (WebSocket events)
- Implement #271 (Git UI)

### Week 3: Complete Journey + Polish
- Implement #273 (PR UI)
- Implement #274 (Progress stepper)
- Implement #275 (Onboarding)

---

## Final Assessment

CodeFrame has a solid technical foundation but is **not shippable** in its current state. The 10-step user journey is only 70% complete (steps 1-7), and the remaining 30% (steps 8-10) represents the **entire value proposition** - getting code from AI agents into the user's repository.

**Recommendation:** Pause new feature development. Focus exclusively on completing the Git/PR workflow and fixing critical UI bugs before any marketing or user acquisition.

---

*Report generated by UX/UI Committee Review - 11 expert subagents*
