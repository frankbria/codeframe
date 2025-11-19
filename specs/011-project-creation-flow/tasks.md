# Tasks: Project Creation Flow

**Feature**: 011-project-creation-flow
**Input**: Design documents from `/specs/011-project-creation-flow/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Following TDD approach - tests written FIRST, must FAIL before implementation

**Organization**: Tasks grouped by user story for independent implementation and testing

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Include exact file paths in descriptions

## Path Conventions
- **Frontend**: `web-ui/src/` (Next.js App Router)
- **Backend**: `codeframe/` (FastAPI Python)
- **Tests (Frontend)**: `web-ui/__tests__/`
- **Tests (Backend)**: `tests/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project verification and test infrastructure setup

- [ ] T001 Verify existing project structure matches plan.md expectations
- [ ] T002 [P] Verify frontend dependencies (React 18, Next.js 14, Tailwind CSS, Jest/Vitest)
- [ ] T003 [P] Verify backend dependencies (FastAPI, Pydantic, aiosqlite, pytest)
- [ ] T004 [P] Check existing components (ProjectCreationForm, ProjectList) in web-ui/src/components/
- [ ] T005 [P] Check existing backend endpoint POST /api/projects in codeframe/ui/server.py
- [ ] T006 [P] Verify database schema (projects table) in codeframe/persistence/database.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core test infrastructure and type definitions

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T007 [P] Create TypeScript types for ProjectCreationFormProps in web-ui/src/types/project.ts
- [ ] T008 [P] Create TypeScript types for SpinnerProps in web-ui/src/types/project.ts
- [ ] T009 [P] Setup Jest test configuration for new test files in web-ui/__tests__/
- [ ] T010 Verify backend Pydantic models (ProjectCreateRequest, ProjectResponse) in codeframe/ui/models.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 5 - Spinner Component (Priority: P1) 🎯

**Goal**: Create reusable loading spinner component used by all other stories

**Why First?**: US1 and US3 depend on Spinner component for loading states

**Independent Test**: Import and render Spinner in isolation, verify accessibility and sizing

### Tests for User Story 5 ⚠️ WRITE FIRST

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T011 [P] [US5] Test spinner renders with default medium size in web-ui/__tests__/components/Spinner.test.tsx
- [ ] T012 [P] [US5] Test spinner renders with small size in web-ui/__tests__/components/Spinner.test.tsx
- [ ] T013 [P] [US5] Test spinner renders with large size in web-ui/__tests__/components/Spinner.test.tsx
- [ ] T014 [P] [US5] Test spinner has correct accessibility attributes (role, aria-label) in web-ui/__tests__/components/Spinner.test.tsx

### Implementation for User Story 5

- [ ] T015 [US5] Create Spinner component in web-ui/src/components/Spinner.tsx
- [ ] T016 [US5] Add Tailwind animate-spin animation with blue-600 color
- [ ] T017 [US5] Add size variants (sm: 16px, md: 32px, lg: 48px)
- [ ] T018 [US5] Add accessibility attributes (role="status", aria-label="Loading")
- [ ] T019 [US5] Verify all tests pass for US5

**Checkpoint**: Spinner component complete and tested - can be used by US1 and US3

---

## Phase 4: User Story 1 - Welcome Page (Priority: P0) 🎯 MVP FOUNDATION

**Goal**: Display welcome page with ProjectCreationForm at root route

**Independent Test**: Navigate to http://localhost:8080, verify welcome message and form appear

### Tests for User Story 1 ⚠️ WRITE FIRST

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T020 [P] [US1] Test HomePage renders welcome heading "Welcome to CodeFRAME" in web-ui/__tests__/app/page.test.tsx
- [ ] T021 [P] [US1] Test HomePage renders tagline "AI coding agents..." in web-ui/__tests__/app/page.test.tsx
- [ ] T022 [P] [US1] Test HomePage renders ProjectCreationForm component in web-ui/__tests__/app/page.test.tsx
- [ ] T023 [P] [US1] Test HomePage shows Spinner when isCreating=true in web-ui/__tests__/app/page.test.tsx
- [ ] T024 [P] [US1] Test HomePage is mobile responsive (320px, 768px, 1024px viewports) in web-ui/__tests__/app/page.test.tsx

### Implementation for User Story 1

- [ ] T025 [US1] Update HomePage root route in web-ui/src/app/page.tsx
- [ ] T026 [US1] Add welcome header with heading and tagline to HomePage
- [ ] T027 [US1] Add useState hook for isCreating state in HomePage
- [ ] T028 [US1] Add useRouter hook for navigation in HomePage
- [ ] T029 [US1] Add handleProjectCreated callback that calls router.push in HomePage
- [ ] T030 [US1] Add handleSubmit callback that sets isCreating=true in HomePage
- [ ] T031 [US1] Add handleError callback that sets isCreating=false in HomePage
- [ ] T032 [US1] Conditionally render Spinner when isCreating=true in HomePage
- [ ] T033 [US1] Conditionally render ProjectCreationForm when isCreating=false in HomePage
- [ ] T034 [US1] Add Tailwind responsive classes (min-h-screen, flex, items-center, justify-center) in HomePage
- [ ] T035 [US1] Verify all tests pass for US1

**Checkpoint**: Welcome page displays correctly, Spinner shows/hides based on state

---

## Phase 5: User Story 2 - Form Validation (Priority: P0) 🎯 MVP CORE

**Goal**: Add description field and comprehensive validation to ProjectCreationForm

**Independent Test**: Fill form with invalid data, verify inline error messages appear

### Tests for User Story 2 ⚠️ WRITE FIRST

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T036 [P] [US2] Test form shows error for empty project name in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T037 [P] [US2] Test form shows error for name too short (<3 chars) in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T038 [P] [US2] Test form shows error for invalid name pattern (uppercase, spaces) in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T039 [P] [US2] Test form shows error for empty description in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T040 [P] [US2] Test form shows error for description too short (<10 chars) in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T041 [P] [US2] Test character counter updates as user types in description in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T042 [P] [US2] Test submit button disabled when form invalid in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T043 [P] [US2] Test on-blur validation triggers for name field in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T044 [P] [US2] Test on-blur validation triggers for description field in web-ui/__tests__/components/ProjectCreationForm.test.tsx

### Implementation for User Story 2

- [ ] T045 [US2] Add description state variable to ProjectCreationForm in web-ui/src/components/ProjectCreationForm.tsx
- [ ] T046 [US2] Add errors state object (Record<string, string>) to ProjectCreationForm
- [ ] T047 [US2] Add validateName function with regex /^[a-z0-9-_]+$/ to ProjectCreationForm
- [ ] T048 [US2] Add validateDescription function with min 10 chars check to ProjectCreationForm
- [ ] T049 [US2] Add description textarea field to ProjectCreationForm JSX
- [ ] T050 [US2] Add character counter below description (0 / 500 characters) to ProjectCreationForm
- [ ] T051 [US2] Add onBlur handler to name input that calls validateName in ProjectCreationForm
- [ ] T052 [US2] Add onBlur handler to description textarea that calls validateDescription in ProjectCreationForm
- [ ] T053 [US2] Add conditional CSS classes for error states (border-red-500) to ProjectCreationForm inputs
- [ ] T054 [US2] Add inline error message display below each field to ProjectCreationForm
- [ ] T055 [US2] Add submit button disabled logic (disabled={!isFormValid}) to ProjectCreationForm
- [ ] T056 [US2] Update submit button text to "Create Project & Start Discovery" in ProjectCreationForm
- [ ] T057 [US2] Add hint text "After creation, you'll begin Socratic discovery..." below button in ProjectCreationForm
- [ ] T058 [US2] Verify all tests pass for US2

**Checkpoint**: Form validates all fields correctly, shows helpful error messages

---

## Phase 6: User Story 3 - Form Submission (Priority: P0) 🎯 MVP CRITICAL

**Goal**: Submit form, create project via API, handle success/error responses

**Independent Test**: Fill valid form, submit, verify API called with correct payload

### Tests for User Story 3 ⚠️ WRITE FIRST

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T059 [P] [US3] Test form submits valid data to API in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T060 [P] [US3] Test form calls onSubmit callback before API request in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T061 [P] [US3] Test form calls onSuccess(projectId) on successful creation in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T062 [P] [US3] Test form calls onError(error) on API failure in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T063 [P] [US3] Test form shows error for duplicate project name (409) in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T064 [P] [US3] Test form shows error for network failure in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T065 [P] [US3] Test form sets isSubmitting=true during API call in web-ui/__tests__/components/ProjectCreationForm.test.tsx
- [ ] T066 [P] [US3] Test form disables inputs during submission in web-ui/__tests__/components/ProjectCreationForm.test.tsx

**Backend Tests** (verify existing endpoint):

- [ ] T067 [P] [US3] Test POST /api/projects with valid data returns 201 in tests/api/test_project_creation_api.py
- [ ] T068 [P] [US3] Test POST /api/projects with duplicate name returns 409 in tests/api/test_project_creation_api.py
- [ ] T069 [P] [US3] Test POST /api/projects with invalid name format returns 400 in tests/api/test_project_creation_api.py
- [ ] T070 [P] [US3] Test POST /api/projects with description too short returns 422 in tests/api/test_project_creation_api.py

### Implementation for User Story 3

- [ ] T071 [US3] Update ProjectCreationForm props interface to include onSubmit, onSuccess, onError in web-ui/src/components/ProjectCreationForm.tsx
- [ ] T072 [US3] Add isSubmitting state variable to ProjectCreationForm
- [ ] T073 [US3] Update handleSubmit to call validateName() and validateDescription() before submitting in ProjectCreationForm
- [ ] T074 [US3] Update handleSubmit to call onSubmit?.() callback before API request in ProjectCreationForm
- [ ] T075 [US3] Update handleSubmit to include description in API request body in ProjectCreationForm
- [ ] T076 [US3] Update handleSubmit to call onSuccess(response.data.id) on 201 response in ProjectCreationForm
- [ ] T077 [US3] Update handleSubmit to call onError(error) on API failure in ProjectCreationForm
- [ ] T078 [US3] Add error handling for 409 Conflict (duplicate name) in ProjectCreationForm
- [ ] T079 [US3] Add error handling for 400/422 validation errors in ProjectCreationForm
- [ ] T080 [US3] Add error handling for 500 server errors in ProjectCreationForm
- [ ] T081 [US3] Set isSubmitting=true at start of handleSubmit in ProjectCreationForm
- [ ] T082 [US3] Set isSubmitting=false in catch block of handleSubmit in ProjectCreationForm
- [ ] T083 [US3] Add disabled={isSubmitting} to all form inputs in ProjectCreationForm
- [ ] T084 [US3] Update projectsApi.createProject() to accept description parameter in web-ui/src/lib/api.ts
- [ ] T085 [US3] Verify backend endpoint POST /api/projects accepts description (already exists)
- [ ] T086 [US3] Verify all frontend tests pass for US3
- [ ] T087 [US3] Verify all backend tests pass for US3

**Checkpoint**: Form submission works end-to-end, errors handled gracefully

---

## Phase 7: User Story 4 - Redirect to Dashboard (Priority: P0) 🎯 MVP COMPLETE

**Goal**: After successful project creation, redirect user to Dashboard automatically

**Independent Test**: Submit form, verify redirect to `/projects/:id` after success

### Tests for User Story 4 ⚠️ WRITE FIRST

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T088 [P] [US4] Test HomePage redirects to /projects/:id after successful creation in web-ui/__tests__/app/page.test.tsx
- [ ] T089 [P] [US4] Test useRouter().push() called with correct project ID in web-ui/__tests__/app/page.test.tsx
- [ ] T090 [P] [US4] Test navigation happens only after onSuccess callback in web-ui/__tests__/app/page.test.tsx

**Integration Tests**:

- [ ] T091 [P] [US4] Test full flow: fill form → submit → create project → redirect in web-ui/__tests__/integration/project-creation.test.tsx
- [ ] T092 [P] [US4] Test Dashboard loads correctly after redirect in web-ui/__tests__/integration/project-creation.test.tsx

### Implementation for User Story 4

- [ ] T093 [US4] Verify HomePage handleProjectCreated calls router.push(`/projects/${projectId}`) in web-ui/src/app/page.tsx
- [ ] T094 [US4] Verify ProjectCreationForm onSuccess prop passes projectId to HomePage in web-ui/src/components/ProjectCreationForm.tsx
- [ ] T095 [US4] Test redirect manually: create project → verify Dashboard loads
- [ ] T096 [US4] Verify all tests pass for US4

**Checkpoint**: Full user journey works: land on homepage → create project → see Dashboard

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Code quality, documentation, and final validation

- [ ] T097 [P] Remove console.log statements from production code in web-ui/src/
- [ ] T098 [P] Verify no TypeScript `any` types used in web-ui/src/
- [ ] T099 [P] Run eslint and fix any linting errors in web-ui/
- [ ] T100 [P] Run ruff and fix any linting errors in codeframe/
- [ ] T101 [P] Verify test coverage ≥85% for frontend tests
- [ ] T102 [P] Verify test coverage ≥85% for backend tests (if new tests added)
- [ ] T103 Update README.md with project creation workflow (if needed)
- [ ] T104 Update CLAUDE.md with new component patterns (if needed)
- [ ] T105 [P] Manual testing: Complete quickstart.md validation checklist
- [ ] T106 [P] Manual testing: Test on Chrome, Firefox, Safari, Edge
- [ ] T107 [P] Manual testing: Test mobile responsive design (320px, 768px, 1024px)
- [ ] T108 Self-review or pair review code changes
- [ ] T109 Prepare PR with feature description and testing checklist
- [ ] T110 Squash commits if needed and use conventional commit format

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 5 (Phase 3)**: Depends on Foundational - BLOCKS US1 and US3 (Spinner dependency)
- **User Story 1 (Phase 4)**: Depends on Foundational + US5 (Spinner)
- **User Story 2 (Phase 5)**: Depends on Foundational - Independent of other stories
- **User Story 3 (Phase 6)**: Depends on Foundational + US2 (form validation)
- **User Story 4 (Phase 7)**: Depends on US1 + US3 (HomePage + submission)
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

```
Foundational (Phase 2) BLOCKS everything below
    ↓
US5: Spinner (Phase 3) - No other dependencies
    ↓
US1: Welcome Page (Phase 4) - Depends on US5 (uses Spinner)
    ↓ (parallel)
US2: Form Validation (Phase 5) - No dependencies on other stories
    ↓
US3: Form Submission (Phase 6) - Depends on US2 (validation logic)
    ↓
US4: Redirect (Phase 7) - Depends on US1 + US3 (HomePage + submission)
    ↓
Polish (Phase 8) - Depends on all stories
```

**Independent Stories**: US2 can be developed in parallel with US1 after US5 completes

### Within Each User Story

1. **Tests FIRST** - Write all tests, verify they FAIL
2. **Models/State** - Add state variables, props interfaces
3. **Validation** - Add validation functions
4. **UI Components** - Add JSX elements, event handlers
5. **Integration** - Wire up callbacks, API calls
6. **Verify** - All tests pass

### Parallel Opportunities

**Phase 1 - Setup**: All tasks T001-T006 can run in parallel

**Phase 2 - Foundational**: All tasks T007-T010 can run in parallel

**Phase 3 - US5 Tests**: All tasks T011-T014 can run in parallel (write tests together)

**Phase 4 - US1 Tests**: All tasks T020-T024 can run in parallel (write tests together)

**Phase 5 - US2 Tests**: All tasks T036-T044 can run in parallel (write tests together)

**Phase 6 - US3 Tests**: All tasks T059-T070 can run in parallel (write tests together)

**Phase 7 - US4 Tests**: All tasks T088-T092 can run in parallel (write tests together)

**Phase 8 - Polish**: Most tasks T097-T107 can run in parallel (different concerns)

**Across Stories**: US2 (Phase 5) can start in parallel with US1 (Phase 4) after US5 completes

---

## Parallel Example: User Story 2 (Form Validation)

```bash
# Step 1: Launch all tests for US2 together (write these FIRST):
Task T036: "Test form shows error for empty project name"
Task T037: "Test form shows error for name too short"
Task T038: "Test form shows error for invalid name pattern"
Task T039: "Test form shows error for empty description"
Task T040: "Test form shows error for description too short"
Task T041: "Test character counter updates"
Task T042: "Test submit button disabled when invalid"
Task T043: "Test on-blur validation for name"
Task T044: "Test on-blur validation for description"

# Step 2: Verify all tests FAIL (red phase)

# Step 3: Implement US2 tasks sequentially (T045-T058)
# Each implementation task makes some tests pass (green phase)

# Step 4: Verify all US2 tests PASS
```

---

## Implementation Strategy

### MVP First (Minimum Viable Product)

**Goal**: Get basic project creation working end-to-end

1. ✅ Complete Phase 1: Setup (verify existing structure)
2. ✅ Complete Phase 2: Foundational (types, test setup)
3. ✅ Complete Phase 3: US5 - Spinner (dependency for US1, US3)
4. ✅ Complete Phase 4: US1 - Welcome Page (user lands on form)
5. ✅ Complete Phase 5: US2 - Form Validation (can fill form correctly)
6. ✅ Complete Phase 6: US3 - Form Submission (creates project in DB)
7. ✅ Complete Phase 7: US4 - Redirect (user sees Dashboard)
8. **STOP and VALIDATE**: Test full user journey manually
9. Fix any bugs discovered
10. Deploy/demo if ready

**MVP Scope**: All 5 user stories (US1-US5) - Feature 2 is complete at this point

### Incremental Delivery

**Checkpoint 1**: After US5 (Spinner)
- ✅ Spinner component tested and working
- Can be used by other components

**Checkpoint 2**: After US1 (Welcome Page)
- ✅ User can navigate to http://localhost:8080
- ✅ Sees welcome message and form
- ⚠️ Cannot submit form yet (validation not done)

**Checkpoint 3**: After US2 (Form Validation)
- ✅ User can fill form with validation feedback
- ⚠️ Cannot submit yet (submission logic not done)

**Checkpoint 4**: After US3 (Form Submission)
- ✅ User can submit form and create project
- ⚠️ Must manually navigate to Dashboard (no auto-redirect)

**Checkpoint 5**: After US4 (Redirect) - **MVP COMPLETE** 🎯
- ✅ Full user journey works end-to-end
- ✅ New users can onboard without CLI
- ✅ Ready for Sprint 9.5 Feature 3

### Parallel Team Strategy

**With 2 developers**:

1. Both complete Setup + Foundational together (quick)
2. Dev A: Complete US5 (Spinner) - 30 min
3. After US5 completes:
   - Dev A: US1 (Welcome Page) + US4 (Redirect) - 1 hour
   - Dev B: US2 (Form Validation) + US3 (Form Submission) - 2 hours
4. Integration: Test full flow together - 30 min
5. Both: Polish tasks in parallel - 30 min

**Total Time**: ~3 hours with 2 devs (vs 4 hours solo)

---

## Notes

- **[P] tasks** = different files, no dependencies, can run in parallel
- **[Story] label** maps task to specific user story for traceability
- **TDD approach**: Write tests FIRST, verify FAIL, implement, verify PASS
- Each user story should be independently testable at its checkpoint
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- **Backend endpoint already exists**: POST /api/projects (minimal backend work)
- **Frontend focus**: 95% of work is frontend enhancements
- Total estimated effort: **4 hours** (18 hours remaining in Sprint 9.5)

---

## Task Count Summary

- **Phase 1 (Setup)**: 6 tasks (parallel, ~15 min)
- **Phase 2 (Foundational)**: 4 tasks (parallel, ~15 min)
- **Phase 3 (US5 - Spinner)**: 9 tasks (4 tests + 5 impl, ~30 min)
- **Phase 4 (US1 - Welcome Page)**: 16 tasks (5 tests + 11 impl, ~1 hour)
- **Phase 5 (US2 - Form Validation)**: 23 tasks (9 tests + 14 impl, ~1.5 hours)
- **Phase 6 (US3 - Form Submission)**: 29 tasks (12 tests + 17 impl, ~1.5 hours)
- **Phase 7 (US4 - Redirect)**: 9 tasks (5 tests + 4 impl, ~30 min)
- **Phase 8 (Polish)**: 14 tasks (parallel, ~30 min)

**Total**: 110 tasks over 4 hours estimated effort

**Tests**: 35 test tasks (32% of total) - Following TDD rigorously
**Implementation**: 61 implementation tasks
**Setup/Polish**: 14 tasks

**Parallel Opportunities**: 50+ tasks can run in parallel if team has capacity

---

**Generated**: 2025-11-18
**Feature**: 011-project-creation-flow
**Sprint**: 9.5 - Critical UX Fixes
**Status**: Ready for implementation
