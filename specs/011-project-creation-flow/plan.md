# Implementation Plan: Project Creation Flow

**Branch**: `011-project-creation-flow` | **Date**: 2025-11-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-project-creation-flow/spec.md`

## Summary

Enhance the existing project creation workflow to meet Sprint 9.5 UX requirements by updating the root route to display ProjectCreationForm, adding description field validation, implementing a Spinner component, and ensuring automatic redirect to the Dashboard after project creation. The backend `/api/projects` endpoint already exists with comprehensive validation, so this feature focuses primarily on frontend UX improvements and integration.

**Key Technical Approach**:
- Modify `web-ui/src/app/page.tsx` to use ProjectCreationForm instead of ProjectList
- Enhance ProjectCreationForm with description field (min 10 chars) and improved callback props
- Create reusable Spinner component for loading states
- Add comprehensive frontend validation matching backend Pydantic rules
- Ensure TDD approach with tests written before implementation

## Technical Context

**Language/Version**:
- Frontend: TypeScript 5.3+ with React 18, Next.js 14 (App Router)
- Backend: Python 3.11 with FastAPI, aiosqlite

**Primary Dependencies**:
- Frontend: React 18, Next.js, Tailwind CSS, axios (existing)
- Backend: FastAPI, Pydantic, aiosqlite (existing)
- Testing: Jest/Vitest (frontend), pytest (backend)

**Storage**: SQLite async (aiosqlite) - `projects` table already exists with schema:
```sql
CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  source_type TEXT,
  source_location TEXT,
  workspace_path TEXT,
  status TEXT DEFAULT 'init',
  phase TEXT DEFAULT 'discovery',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  ...
)
```

**Testing**:
- Frontend: Jest/Vitest with React Testing Library
- Backend: pytest with pytest-asyncio
- Target coverage: ≥85%

**Target Platform**: Web (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)

**Project Type**: Web application (monorepo: backend=Python FastAPI, frontend=Next.js TypeScript)

**Performance Goals**:
- Form validation response: <50ms
- API project creation: <500ms
- Page redirect after creation: <200ms

**Constraints**:
- Browser-based form validation must match backend Pydantic validation exactly
- No breaking changes to existing ProjectCreationForm API consumers (if any)
- Must work offline (form validation client-side, network errors handled gracefully)

**Scale/Scope**: Single-page form with 3 input fields, ~5 React components affected, ~200 lines of new/modified code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Test-First Development ✅

**Status**: PASS
**Rationale**: Feature spec includes comprehensive test cases for all user stories. Tests will be written before implementation following TDD red-green-refactor cycle.

**Evidence**:
- 15+ frontend unit tests defined in spec
- 6+ backend unit tests defined (though endpoint exists, we'll add validation tests)
- 2+ integration tests defined
- All tests defined BEFORE implementation code

### II. Async-First Architecture ✅

**Status**: PASS (N/A for this feature)
**Rationale**: This feature is purely frontend form handling and uses existing async backend endpoint. No new async/await patterns required.

**Evidence**:
- Existing `/api/projects` endpoint already uses `async def`
- Frontend uses async/await for fetch calls (existing pattern)

### III. Context Efficiency ✅

**Status**: PASS (N/A for this feature)
**Rationale**: No agent context or context management involved. Form state is ephemeral (cleared after submission).

### IV. Multi-Agent Coordination ✅

**Status**: PASS (N/A for this feature)
**Rationale**: No multi-agent coordination. This is a user-facing UI feature.

### V. Observability & Traceability ✅

**Status**: PASS
**Rationale**: Project creation is already logged and tracked in SQLite. WebSocket broadcasts already implemented for project creation events.

**Evidence**:
- Existing logging in `/api/projects` endpoint
- SQLite changelog tracks project creation
- WebSocket broadcasts handled by `websocket_broadcasts.py`

### VI. Type Safety ✅

**Status**: PASS
**Rationale**: TypeScript strict mode enabled. All component props will have interfaces. Backend already uses Pydantic validation.

**Evidence**:
- Frontend: `ProjectCreationFormProps`, `SpinnerProps` interfaces defined in spec
- Backend: `ProjectCreateRequest` Pydantic model already exists
- No `any` types (enforced by eslint)

### VII. Incremental Delivery ✅

**Status**: PASS
**Rationale**: Feature broken into 5 user stories (US1-US5) prioritized P0-P1. Each story independently testable.

**Evidence**:
- US1 (Welcome page) - P0
- US2 (Form validation) - P0
- US3 (Submission) - P0
- US4 (Redirect) - P0
- US5 (Spinner) - P1

**All gates PASS** ✅ - Proceed to Phase 0 research

## Project Structure

### Documentation (this feature)

```
specs/011-project-creation-flow/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
│   └── api.openapi.yaml # OpenAPI spec for validation rules
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
# Web application structure (frontend + backend)

backend (codeframe/):
├── ui/
│   ├── server.py          # [EXISTING] Contains POST /api/projects endpoint
│   ├── models.py          # [EXISTING] ProjectCreateRequest, ProjectResponse models
│   └── websocket_broadcasts.py  # [EXISTING] WebSocket event handling
└── persistence/
    └── database.py        # [EXISTING] create_project(), get_project_by_name() methods

frontend (web-ui/):
├── src/
│   ├── app/
│   │   └── page.tsx                    # [MODIFY] Change from ProjectList to ProjectCreationForm
│   ├── components/
│   │   ├── ProjectCreationForm.tsx     # [MODIFY] Add description field, enhance validation
│   │   └── Spinner.tsx                 # [CREATE] New reusable loading spinner
│   ├── types/
│   │   └── project.ts                  # [EXISTING] ProjectResponse type
│   └── lib/
│       └── api.ts                      # [EXISTING] projectsApi.createProject()
└── __tests__/
    ├── app/
    │   └── page.test.tsx               # [CREATE] HomePage tests
    ├── components/
    │   ├── ProjectCreationForm.test.tsx  # [CREATE] Form validation tests
    │   └── Spinner.test.tsx            # [CREATE] Spinner component tests
    └── integration/
        └── project-creation.test.tsx   # [CREATE] End-to-end flow test

tests/ (backend):
└── api/
    └── test_project_creation_api.py    # [MODIFY] Add new validation test cases
```

**Structure Decision**:
Using existing web application monorepo structure. Frontend modifications focused on `web-ui/src/app/page.tsx` and `web-ui/src/components/ProjectCreationForm.tsx`. Backend changes minimal (validation tests only) since POST /api/projects endpoint already exists with comprehensive Pydantic validation.

## Complexity Tracking

*No Constitution violations - no justifications needed*

---

## Phase 0: Research & Discovery

**Objective**: Resolve all "NEEDS CLARIFICATION" items from Technical Context and identify best practices.

### Research Tasks

1. **Existing ProjectCreationForm Analysis**
   - **Question**: What's the current state of ProjectCreationForm? Does it have description field? What are current validation rules?
   - **Method**: Read `web-ui/src/components/ProjectCreationForm.tsx`
   - **Outcome**: Document current fields, validation, and gaps vs Sprint 9.5 requirements

2. **Backend Validation Rules**
   - **Question**: What exact validation rules does `ProjectCreateRequest` enforce?
   - **Method**: Read `codeframe/ui/models.py` ProjectCreateRequest model
   - **Outcome**: Document Pydantic validation rules to ensure frontend matches exactly

3. **Existing Test Patterns**
   - **Question**: What testing patterns are used for existing React components?
   - **Method**: Examine `web-ui/__tests__/` directory for existing component tests
   - **Outcome**: Identify test setup, mocking patterns, assertion style

4. **Spinner Implementation Best Practices**
   - **Question**: Should we create custom spinner or use existing UI library component?
   - **Method**: Check if Tailwind UI or other UI library is already in use, research accessibility requirements
   - **Outcome**: Decision on custom vs library spinner with accessibility guidelines

5. **Form Validation UX Patterns**
   - **Question**: When should validation errors appear? On blur, on submit, or real-time?
   - **Method**: Research React Hook Form best practices, check existing form components in codebase
   - **Outcome**: Validation timing strategy (likely: real-time for format, on submit for uniqueness)

6. **Router Navigation Patterns**
   - **Question**: How does Next.js App Router handle redirects? Any special patterns in existing code?
   - **Method**: Check existing navigation code in Dashboard, examine Next.js 14 docs
   - **Outcome**: Confirmed `useRouter().push()` pattern for client-side navigation

### Research Outputs

All findings will be documented in `research.md` with structure:
```markdown
## Decision: [Topic]
**Choice**: [What was selected]
**Rationale**: [Why this choice]
**Alternatives Considered**: [Other options evaluated]
**References**: [Docs, existing code, or external resources]
```

---

## Phase 1: Design & Contracts

**Prerequisites**: `research.md` complete

### 1. Data Model (`data-model.md`)

**Entities**:
1. **ProjectCreationForm State** (Frontend ephemeral state)
   - Fields: name (string), projectType (enum), description (string)
   - Validation state: errors (Record<string, string>), isSubmitting (boolean)
   - Lifecycle: Exists only during form interaction, cleared on submit

2. **Project** (Database entity - already exists)
   - No schema changes required
   - Existing fields support all requirements

**Validation Rules**:
```typescript
// Frontend validation (must match backend Pydantic)
interface ValidationRules {
  name: {
    required: true,
    minLength: 3,
    maxLength: 100,
    pattern: /^[a-z0-9-_]+$/,
    message: "Only lowercase letters, numbers, hyphens, and underscores allowed"
  },
  description: {
    required: true,
    minLength: 10,
    maxLength: 500,  // Match backend Pydantic max_length
    message: "Description must be at least 10 characters"
  }
}
```

### 2. API Contracts (`contracts/api.openapi.yaml`)

**Endpoint**: `POST /api/projects` (already exists, documenting for completeness)

```yaml
openapi: 3.0.0
paths:
  /api/projects:
    post:
      summary: Create a new project
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name, description]
              properties:
                name:
                  type: string
                  minLength: 3
                  maxLength: 100
                  pattern: '^[a-z0-9-_]+$'
                description:
                  type: string
                  minLength: 10
                  maxLength: 500
                projectType:
                  type: string
                  enum: [python, typescript, fullstack, other]
                  default: python
      responses:
        '201':
          description: Project created successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: integer
                  name:
                    type: string
                  status:
                    type: string
                    example: "created"
        '400':
          description: Validation error (invalid name format, description too short)
        '409':
          description: Conflict (duplicate project name)
        '500':
          description: Server error (workspace creation failed)
```

### 3. Component Interfaces

**ProjectCreationFormProps** (Enhanced):
```typescript
interface ProjectCreationFormProps {
  onSuccess: (projectId: number) => void;   // Required callback
  onSubmit?: () => void;                     // Optional: called before API call
  onError?: (error: Error) => void;          // Optional: called on API error
}
```

**SpinnerProps**:
```typescript
interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';  // Default: 'md'
}
```

### 4. Quickstart Guide (`quickstart.md`)

Minimal example of using the enhanced ProjectCreationForm:

```tsx
// app/page.tsx
import { ProjectCreationForm } from '@/components/ProjectCreationForm';

export default function HomePage() {
  const router = useRouter();

  const handleSuccess = (projectId: number) => {
    router.push(`/projects/${projectId}`);
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <ProjectCreationForm onSuccess={handleSuccess} />
    </div>
  );
}
```

### 5. Agent Context Update

Run `.specify/scripts/bash/update-agent-context.sh claude` to update agent-specific context with:
- React 18 component patterns
- Next.js 14 App Router navigation
- Tailwind CSS utility classes for forms
- Jest/Vitest testing patterns

---

## Phase 2: Task Generation

**Note**: This phase is handled by `/speckit.tasks` command, NOT by `/speckit.plan`.

Tasks will be organized by user story with dependencies:
- US1 tasks (Welcome page) → foundation for US2-US4
- US2 tasks (Form validation) → blocks US3 (submission)
- US3 tasks (Submission logic) → blocks US4 (redirect)
- US5 tasks (Spinner) → parallel track, used by US1

Expected task count: ~15-20 tasks over 4 hours estimated effort.

---

## Post-Planning Actions

1. **Review & Approval**
   - Review this plan.md with team/user
   - Confirm technical approach and scope
   - Approve to proceed to `/speckit.tasks`

2. **Next Command**
   - Run `/speckit.tasks` to generate actionable task list
   - Tasks will reference this plan for context

3. **Implementation Kickoff**
   - Create feature branch (already done: `011-project-creation-flow`)
   - Begin TDD: Write failing tests → Implement → Pass tests → Refactor
   - Follow incremental delivery (US1 → US2 → US3 → US4 → US5)

---

**Plan Status**: ✅ COMPLETE (Ready for `/speckit.tasks`)
**Next Step**: Run `/speckit.tasks` to generate task list for implementation
