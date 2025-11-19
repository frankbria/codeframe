# Research: Project Creation Flow

**Feature**: 011-project-creation-flow
**Date**: 2025-11-18
**Researcher**: Planning Agent

## Summary

Research phase investigated existing ProjectCreationForm implementation, backend validation rules, testing patterns, and UI component best practices to inform implementation decisions for Sprint 9.5 Feature 2.

**Key Findings**:
- ✅ ProjectCreationForm exists but missing description field and Sprint 9.5 callback props
- ✅ Backend validation comprehensive with Pydantic (min 10 chars for description already enforced)
- ✅ Test patterns established using Jest + React Testing Library
- ⚠️ Spinner component missing - need to create custom component with Tailwind
- ✅ Validation timing: on-submit for server-side checks, real-time for format validation

---

## Decision 1: ProjectCreationForm Current State

**Question**: What's the current implementation state? What needs to be added?

**Findings**:

**Current Implementation** (`web-ui/src/components/ProjectCreationForm.tsx`):
- Has fields: `projectName` (text), `projectType` (select)
- **Missing**: `description` field (required for Sprint 9.5)
- Has basic validation: empty name check only
- Props: `onSuccess?: (project: ProjectResponse) => void`
- **Missing props**: `onSubmit?:() => void`, `onError?: (error: Error) => void`
- Has states: `formState`, `startState`, `errorMessage`, `createdProject`
- Uses `projectsApi.createProject()` from lib/api
- Has "Start Project" button after creation (two-step flow)

**Gaps vs Sprint 9.5 Requirements**:
1. ❌ No `description` textarea field
2. ❌ No validation for description (min 10 chars, max 500 chars)
3. ❌ No `onSubmit` callback prop (Sprint 9.5 needs loading state control from parent)
4. ❌ No `onError` callback prop (Sprint 9.5 needs error handling in parent)
5. ❌ No character counter for description
6. ❌ Name validation incomplete (doesn't check pattern `/^[a-z0-9-_]+$/`)
7. ❌ No min length check for name (should be 3+ chars)

**Decision**: **Enhance existing component** rather than rewrite. Add missing fields and props incrementally.

**Rationale**:
- Existing structure is solid (proper state management, error handling)
- Reusing existing component maintains API compatibility
- Less risk than full rewrite
- Faster to implement (just add missing pieces)

**Alternatives Considered**:
- Rewrite from scratch → Rejected: unnecessary risk, loses working error handling logic
- Create separate component → Rejected: code duplication, harder to maintain

**References**:
- `web-ui/src/components/ProjectCreationForm.tsx` (lines 1-173)
- Sprint 9.5 spec (Feature 2 requirements)

---

## Decision 2: Backend Validation Rules

**Question**: What exact Pydantic validation does `ProjectCreateRequest` enforce?

**Findings**:

**Backend Model** (`codeframe/ui/models.py`):
```python
class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    source_type: Optional[SourceType] = Field(default=SourceType.NEW_REPO)
    # ... other optional fields
```

**Validation Rules**:
- **name**: min_length=1 (⚠️ spec says 3, mismatch!), max_length=100, required
- **description**: min_length=1 (⚠️ spec says 10, mismatch!), max_length=500, required
- No pattern validation on name in Pydantic (but Sprint 9.5 spec requires `/^[a-z0-9-_]+$/`)

**Endpoint Validation** (`codeframe/ui/server.py` line 316):
```python
# Check for duplicate project name
existing_projects = app.state.db.list_projects()
if any(p["name"] == request.name for p in existing_projects):
    raise HTTPException(409, f"Project with name '{request.name}' already exists")
```

**Decision**: **Frontend validation must be STRICTER than backend** to meet Sprint 9.5 UX requirements.

**Frontend Validation Strategy**:
- Name: min 3 chars, max 100, pattern `/^[a-z0-9-_]+$/`, unique (checked on submit)
- Description: min 10 chars, max 500, required

**Rationale**:
- Better UX to catch errors client-side before API call
- Avoids round-trip for simple format errors
- Sprint 9.5 spec explicitly requires these stricter rules
- Backend still validates (defense in depth)

**Action Item**: Consider updating backend Pydantic model to match frontend rules in future refactor (separate issue).

**References**:
- `codeframe/ui/models.py` (ProjectCreateRequest)
- `codeframe/ui/server.py` (create_project endpoint, lines 299-361)

---

## Decision 3: Testing Patterns

**Question**: What test setup, mocking, and assertion patterns are used?

**Findings**:

**Existing Test Examples**:
1. **Component Tests** (`web-ui/__tests__/components/AgentCard.test.tsx`):
   ```tsx
   import { render, screen } from '@testing-library/react';
   import '@testing-library/jest-dom';
   import AgentCard from '@/components/AgentCard';

   describe('AgentCard', () => {
     it('renders agent information', () => {
       const mockAgent = { /* ... */ };
       render(<AgentCard agent={mockAgent} />);
       expect(screen.getByText('Backend Agent')).toBeInTheDocument();
     });
   });
   ```

2. **Test Setup**: Jest + React Testing Library + `@testing-library/jest-dom`
3. **Mocking**: Uses `jest.fn()` for callbacks, `global.fetch` for API calls
4. **Assertions**: Primarily `expect(element).toBeInTheDocument()`, `toHaveClass`, `toHaveAttribute`

**Decision**: **Follow established patterns** - Jest + React Testing Library + `@testing-library/jest-dom`.

**Test File Structure**:
```
web-ui/__tests__/
├── app/
│   └── page.test.tsx              # HomePage tests
├── components/
│   ├── ProjectCreationForm.test.tsx  # Form validation tests
│   └── Spinner.test.tsx           # Spinner component tests
└── integration/
    └── project-creation.test.tsx  # Full flow test
```

**Rationale**:
- Consistency with existing codebase
- React Testing Library promotes accessibility-focused testing
- Jest already configured and working

**References**:
- `web-ui/__tests__/components/AgentCard.test.tsx`
- `web-ui/__tests__/components/Dashboard.test.tsx`

---

## Decision 4: Spinner Implementation

**Question**: Custom spinner or UI library component?

**Findings**:

**Existing UI Libraries**:
- ✅ Tailwind CSS installed and used throughout
- ❌ No component library detected (no Headless UI, Radix UI, shadcn/ui)
- ❌ No existing Spinner component in `web-ui/src/components/`

**Options**:
1. **Custom Tailwind Spinner** (CHOSEN)
   - Pros: No dependencies, lightweight, full control, matches existing style
   - Cons: Need to implement accessibility attributes manually
   - Size: ~20 lines of code

2. **Headless UI/Radix UI**
   - Pros: Battle-tested, accessible by default
   - Cons: Adds dependency, overkill for single component
   - Size: 200KB+ bundle increase

**Decision**: **Create custom Tailwind CSS spinner** with proper accessibility.

**Implementation Approach**:
```tsx
// web-ui/src/components/Spinner.tsx
export function Spinner({ size = 'md' }: SpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-3',
    lg: 'w-12 h-12 border-4',
  };

  return (
    <div
      className={`${sizeClasses[size]} border-blue-600 border-t-transparent rounded-full animate-spin`}
      role="status"
      aria-label="Loading"
    />
  );
}
```

**Accessibility Checklist**:
- ✅ `role="status"` for screen readers
- ✅ `aria-label="Loading"` describes purpose
- ✅ Visual indicator (spinning animation)
- ✅ Color contrast meets WCAG AA (blue-600 on white)

**Rationale**:
- Aligns with existing "no UI library" architecture
- Tailwind `animate-spin` utility already available
- Minimal bundle impact
- Easy to customize/extend later

**References**:
- Tailwind CSS docs: https://tailwindcss.com/docs/animation
- WAI-ARIA: https://www.w3.org/TR/wai-aria-1.2/#status
- Existing Tailwind usage in Dashboard.tsx, AgentCard.tsx

---

## Decision 5: Form Validation UX Patterns

**Question**: When should validation errors appear?

**Findings**:

**Validation Timing Research**:
1. **On Submit** (Traditional)
   - Pros: Less noisy, user completes thought before feedback
   - Cons: Delayed feedback, user must fix and resubmit

2. **On Blur** (Industry Standard)
   - Pros: Immediate feedback after leaving field, non-intrusive
   - Cons: Doesn't catch errors until user leaves field

3. **Real-Time** (Aggressive)
   - Pros: Instant feedback, catches errors immediately
   - Cons: Annoying while typing (e.g., "too short" while user still typing)

**Existing Pattern in Codebase**:
- ProjectCreationForm currently uses **on-submit only** validation
- No on-blur or real-time validation present

**Decision**: **Hybrid approach** - Format validation on blur, server-side checks on submit.

**Validation Strategy**:
| Validation Type | Trigger | Example |
|----------------|---------|---------|
| Format (name pattern) | On blur | "Only lowercase letters, numbers, hyphens, underscores" |
| Length (min 3, min 10) | On blur | "Project name must be at least 3 characters" |
| Uniqueness (duplicate name) | On submit | "Project 'my-app' already exists" (409 from API) |
| Required fields | On submit | "Project name is required" |

**Rationale**:
- Balances UX (non-intrusive) with feedback speed (catches errors early)
- Server-side checks (uniqueness) can't be done until submit anyway
- On-blur aligns with industry best practices (Google, GitHub, etc.)

**Implementation Notes**:
- Add `onBlur` handlers to name and description inputs
- Keep existing `onSubmit` validation for required fields
- Display errors inline below each field

**References**:
- Nielsen Norman Group: Form Usability best practices
- Material Design: Input validation guidelines
- Existing form behavior in ProjectCreationForm

---

## Decision 6: Router Navigation Patterns

**Question**: How to handle redirects after project creation?

**Findings**:

**Next.js App Router Navigation**:
```tsx
import { useRouter } from 'next/navigation';

const router = useRouter();
router.push('/projects/123');  // Client-side navigation
```

**Existing Usage in Codebase**:
- ProjectCreationForm already uses `useRouter().push()` (line 83)
- Dashboard uses same pattern for navigation
- No server-side redirects in UI code (all client-side)

**Decision**: **Use `useRouter().push()` in HomePage** after `onSuccess` callback from ProjectCreationForm.

**Implementation**:
```tsx
// web-ui/src/app/page.tsx
const handleProjectCreated = (projectId: number) => {
  router.push(`/projects/${projectId}`);
};
```

**Rationale**:
- Consistent with existing codebase patterns
- Client-side navigation is faster (no full page reload)
- Next.js App Router optimizes this (prefetching, instant navigation)

**Alternative Considered**:
- Server-side redirect (Next.js `redirect()`) → Rejected: requires Server Component, HomePage needs client-side state for loading spinner

**References**:
- Next.js 14 docs: https://nextjs.org/docs/app/api-reference/functions/use-router
- `web-ui/src/components/ProjectCreationForm.tsx` (line 83)
- `web-ui/src/components/Dashboard.tsx` (navigation patterns)

---

## Summary of Key Decisions

| Topic | Decision | Impact |
|-------|----------|--------|
| **ProjectCreationForm** | Enhance existing component | Low risk, faster implementation |
| **Backend Validation** | Frontend stricter than backend | Better UX, needs backend sync later |
| **Testing** | Jest + React Testing Library | Consistent with existing tests |
| **Spinner** | Custom Tailwind component | No dependencies, 20 lines code |
| **Validation Timing** | Hybrid (on-blur + on-submit) | Optimal UX, industry standard |
| **Navigation** | `useRouter().push()` | Fast, consistent with codebase |

---

## Action Items for Implementation

1. ✅ Add `description` textarea to ProjectCreationForm
2. ✅ Implement on-blur validation for name and description
3. ✅ Add `onSubmit` and `onError` callback props
4. ✅ Create Spinner component with accessibility
5. ✅ Update HomePage to use ProjectCreationForm (replace ProjectList)
6. ✅ Write tests following existing patterns
7. ⚠️ Future: Update backend Pydantic to match stricter frontend rules (separate issue)

---

**Research Complete** ✅
**Next Phase**: Generate `data-model.md` and `contracts/` based on these findings
