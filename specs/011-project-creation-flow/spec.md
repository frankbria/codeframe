# Feature Specification: Project Creation Flow

**Feature ID**: 011-project-creation-flow
**Sprint**: 9.5 - Critical UX Fixes
**Priority**: P0 - Critical (Enables new user onboarding)
**Effort**: 4 hours
**Status**: Planning

## Overview

Enable new users to create projects through the web UI, removing the critical onboarding blocker where the dashboard assumes a project already exists.

### Problem Statement

**Current Behavior**:
- User runs `codeframe serve` and opens http://localhost:8080
- Dashboard.tsx expects a `projectId` prop
- Result: "Project not found" error or blank page
- User has NO way to create a project via the UI
- Forces users to use CLI (`codeframe init`) which most don't discover

**Impact**: 8/10 complexity score - Users give up during onboarding

**Expected Behavior**:
- User opens http://localhost:8080 (root route)
- Sees ProjectCreationForm with clear welcome message
- Fills in: project name, type, description
- Submits → POST /api/projects → Creates project in SQLite
- Automatically redirects to /projects/:id (Dashboard)
- Discovery phase begins automatically

## User Stories

### US1: New User Lands on Welcome Page (P0 - Critical)

**As a** new user who just ran `codeframe serve`
**I want to** see a welcoming project creation form when I open localhost:8080
**So that** I can immediately start creating a project without learning CLI commands

**Acceptance Criteria**:
- [ ] Root route `/` renders a centered welcome page with:
  - "Welcome to CodeFRAME" heading
  - Tagline: "AI coding agents that work autonomously while you sleep"
  - ProjectCreationForm component below
- [ ] Page uses clean, modern styling (Tailwind CSS)
- [ ] Mobile responsive (works on tablets/phones)
- [ ] No project ID required to access the page

**Test Cases**:
```typescript
describe('HomePage', () => {
  it('renders welcome message', () => {
    render(<HomePage />);
    expect(screen.getByText('Welcome to CodeFRAME')).toBeInTheDocument();
  });

  it('renders ProjectCreationForm', () => {
    render(<HomePage />);
    expect(screen.getByRole('form')).toBeInTheDocument();
  });

  it('is mobile responsive', () => {
    // Test viewport widths: 320px, 768px, 1024px
  });
});
```

---

### US2: User Fills Project Creation Form (P0 - Critical)

**As a** new user
**I want to** fill out a simple form with project name, type, and description
**So that** I can quickly define my project without complex configuration

**Acceptance Criteria**:
- [ ] Form has 3 fields:
  - **Project Name**: Text input (required, 3+ chars, lowercase/numbers/hyphens/underscores only)
  - **Project Type**: Dropdown (python, typescript, fullstack, other)
  - **Description**: Textarea (required, 10+ chars, max 5000 chars)
- [ ] Real-time validation with error messages:
  - Empty field → "Project name is required"
  - Too short → "Project name must be at least 3 characters"
  - Invalid format → "Only lowercase letters, numbers, hyphens, and underscores allowed"
  - Description too short → "Description must be at least 10 characters"
- [ ] Character counter for description: "0 / 5000 characters"
- [ ] Submit button disabled when form invalid
- [ ] Submit button text: "Create Project & Start Discovery"
- [ ] Hint text below button: "After creation, you'll begin Socratic discovery with the Lead Agent"

**Test Cases**:
```typescript
describe('ProjectCreationForm validation', () => {
  it('shows error for empty project name', async () => {
    const { getByRole, getByText } = render(<ProjectCreationForm {...props} />);
    fireEvent.submit(getByRole('form'));
    await waitFor(() => {
      expect(getByText('Project name is required')).toBeInTheDocument();
    });
  });

  it('shows error for too short name', async () => {
    // Test with "ab" (2 chars)
  });

  it('shows error for invalid characters', async () => {
    // Test with "My Project!" (uppercase, space, special char)
  });

  it('disables submit when form invalid', () => {
    // Verify button disabled attribute
  });

  it('updates character counter as user types', () => {
    // Type in description, verify counter updates
  });
});
```

---

### US3: User Submits Form and Creates Project (P0 - Critical)

**As a** new user
**I want to** submit the form and have my project created in the database
**So that** I can start working with CodeFRAME immediately

**Acceptance Criteria**:
- [ ] Clicking "Create Project & Start Discovery" button:
  - Shows loading spinner
  - Disables form inputs (prevents double-submit)
  - Sends POST /api/projects with JSON body: `{ name, projectType, description }`
- [ ] Backend validates:
  - Name format (regex: `^[a-z0-9-_]+$`)
  - Name uniqueness (no duplicate projects)
  - Description length (1-5000 chars)
- [ ] Backend creates project in SQLite:
  - Generates unique project ID
  - Sets initial status: "created"
  - Sets initial phase: "discovery"
  - Stores timestamp
- [ ] Backend returns: `{ id, name, status }`
- [ ] Frontend receives response:
  - Success → redirect to `/projects/:id`
  - Error (409 duplicate) → show "Project 'name' already exists"
  - Error (400 validation) → show validation error
  - Error (500 server) → show "Failed to create project. Please try again."
- [ ] Loading state clears on success or error

**Test Cases**:
```typescript
describe('ProjectCreationForm submission', () => {
  it('submits valid form data', async () => {
    const onSuccess = jest.fn();
    const { getByRole, getByLabelText } = render(
      <ProjectCreationForm onSuccess={onSuccess} />
    );

    fireEvent.change(getByLabelText('Project Name *'), {
      target: { value: 'my-app' }
    });
    fireEvent.change(getByLabelText('Description *'), {
      target: { value: 'A test project description' }
    });
    fireEvent.submit(getByRole('form'));

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(expect.any(Number));
    });
  });

  it('shows loading state during submission', async () => {
    // Verify spinner appears, form disabled
  });

  it('handles duplicate project name error', async () => {
    // Mock 409 response
    // Verify error message displayed
  });

  it('handles network error gracefully', async () => {
    // Mock fetch failure
    // Verify error message displayed
  });
});
```

**Backend Test Cases**:
```python
async def test_create_project_success(api_client):
    response = await api_client.post("/api/projects", json={
        "name": "test-project",
        "projectType": "python",
        "description": "A test project description"
    })
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["name"] == "test-project"
    assert data["status"] == "created"

async def test_create_project_duplicate_name(api_client, test_db):
    # Create first project
    await test_db.create_project("test-project", "python", "Description")

    # Attempt duplicate
    response = await api_client.post("/api/projects", json={
        "name": "test-project",
        "projectType": "python",
        "description": "Another description"
    })
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

async def test_create_project_invalid_name_format(api_client):
    response = await api_client.post("/api/projects", json={
        "name": "My Project!",
        "projectType": "python",
        "description": "Description"
    })
    assert response.status_code == 400
    assert "Invalid project name format" in response.json()["detail"]
```

---

### US4: User Redirected to Dashboard After Creation (P0 - Critical)

**As a** user who just created a project
**I want to** be automatically redirected to the project dashboard
**So that** I can immediately start the discovery phase

**Acceptance Criteria**:
- [ ] On successful project creation:
  - Extract `project.id` from API response
  - Call `router.push(`/projects/${projectId}`)`
  - User sees Dashboard with their new project
- [ ] Dashboard loads with:
  - Project name in header
  - Status: "created"
  - Phase: "discovery"
  - Discovery progress UI visible (but no questions yet)
- [ ] No manual navigation required
- [ ] URL updates to `/projects/:id`

**Test Cases**:
```typescript
describe('HomePage redirect after creation', () => {
  it('redirects to dashboard after successful creation', async () => {
    const mockRouter = { push: jest.fn() };
    jest.spyOn(require('next/navigation'), 'useRouter').mockReturnValue(mockRouter);

    const { getByRole, getByLabelText } = render(<HomePage />);

    // Fill and submit form
    fireEvent.change(getByLabelText('Project Name *'), {
      target: { value: 'my-app' }
    });
    fireEvent.change(getByLabelText('Description *'), {
      target: { value: 'A test project' }
    });
    fireEvent.submit(getByRole('form'));

    await waitFor(() => {
      expect(mockRouter.push).toHaveBeenCalledWith('/projects/1');
    });
  });
});
```

---

### US5: Spinner Component for Loading States (P1 - Important)

**As a** user
**I want to** see a loading spinner during project creation
**So that** I know the system is processing my request

**Acceptance Criteria**:
- [ ] Spinner component created (`web-ui/src/components/Spinner.tsx`)
- [ ] Accepts `size` prop: 'sm' | 'md' | 'lg'
- [ ] Default size: 'md'
- [ ] Renders spinning animation (Tailwind CSS `animate-spin`)
- [ ] Blue color (`border-blue-600`)
- [ ] Accessible: `role="status"` and `aria-label="Loading"`
- [ ] Used in HomePage during project creation

**Test Cases**:
```typescript
describe('Spinner', () => {
  it('renders with default medium size', () => {
    const { container } = render(<Spinner />);
    const spinner = container.querySelector('[role="status"]');
    expect(spinner).toHaveClass('w-8 h-8');
  });

  it('renders with small size', () => {
    const { container } = render(<Spinner size="sm" />);
    expect(container.querySelector('[role="status"]')).toHaveClass('w-4 h-4');
  });

  it('renders with large size', () => {
    const { container } = render(<Spinner size="lg" />);
    expect(container.querySelector('[role="status"]')).toHaveClass('w-12 h-12');
  });

  it('has correct accessibility attributes', () => {
    const { container } = render(<Spinner />);
    const spinner = container.querySelector('[role="status"]');
    expect(spinner).toHaveAttribute('aria-label', 'Loading');
  });
});
```

---

## Technical Requirements

### Frontend

**Files to Create**:
- `web-ui/src/app/page.tsx` - Root route with ProjectCreationForm
- `web-ui/src/components/Spinner.tsx` - Reusable loading spinner

**Files to Modify**:
- `web-ui/src/components/ProjectCreationForm.tsx` - Add `onSubmit`, `onSuccess`, `onError` props

**Dependencies**:
- React 18 (existing)
- Next.js App Router (existing)
- Tailwind CSS (existing)
- TypeScript (existing)

**Type Definitions**:
```typescript
// web-ui/src/types/project.ts
export interface ProjectCreateRequest {
  name: string;
  projectType: 'python' | 'typescript' | 'fullstack' | 'other';
  description: string;
}

export interface ProjectCreateResponse {
  id: number;
  name: string;
  status: 'created';
}

export interface ProjectCreationFormProps {
  onSuccess: (projectId: number) => void;
  onSubmit?: () => void;
  onError?: (error: Error) => void;
}

export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
}
```

### Backend

**API Endpoint**: `POST /api/projects`

**Request Body** (Pydantic model):
```python
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100, pattern=r'^[a-z0-9-_]+$')
    project_type: str = Field(..., alias='projectType')
    description: str = Field(..., min_length=10, max_length=5000)
```

**Response Model**:
```python
class ProjectResponse(BaseModel):
    id: int
    name: str
    status: str
```

**Implementation** (`codeframe/ui/server.py` or `app.py`):
```python
@app.post("/api/projects", response_model=ProjectResponse, status_code=201)
async def create_project(project: ProjectCreate):
    """Create a new project."""
    # Validate name format (Pydantic already validates)

    # Check for duplicate
    existing = await db.get_project_by_name(project.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Project '{project.name}' already exists"
        )

    # Create project in database
    project_id = await db.create_project(
        name=project.name,
        project_type=project.project_type,
        description=project.description,
    )

    return ProjectResponse(
        id=project_id,
        name=project.name,
        status="created"
    )
```

**Database Method** (`codeframe/persistence/database.py`):
```python
async def create_project(
    self,
    name: str,
    project_type: str,
    description: str,
) -> int:
    """Create a new project and return its ID."""
    async with aiosqlite.connect(self.db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO projects (name, project_type, description, status, phase, created_at)
            VALUES (?, ?, ?, 'created', 'discovery', datetime('now'))
            """,
            (name, project_type, description),
        )
        await db.commit()
        return cursor.lastrowid

async def get_project_by_name(self, name: str) -> Optional[Dict]:
    """Get project by name (for duplicate check)."""
    async with aiosqlite.connect(self.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM projects WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
```

### Database Schema

**Verify `projects` table exists** with columns:
- `id` INTEGER PRIMARY KEY AUTOINCREMENT
- `name` TEXT UNIQUE NOT NULL
- `project_type` TEXT NOT NULL
- `description` TEXT NOT NULL
- `status` TEXT NOT NULL
- `phase` TEXT NOT NULL
- `created_at` TIMESTAMP NOT NULL
- `updated_at` TIMESTAMP

If missing, create migration or add to existing schema.

---

## Non-Functional Requirements

### Performance
- Form validation: <50ms
- Project creation API call: <500ms
- Redirect after creation: <200ms

### Accessibility
- All form inputs have labels
- Error messages associated with inputs (`aria-describedby`)
- Spinner has `role="status"` and `aria-label="Loading"`
- Keyboard navigation works (Tab, Enter to submit)
- Focus management (error inputs get focus)

### Security
- Input sanitization (handled by Pydantic validation)
- SQL injection prevention (parameterized queries)
- XSS prevention (React auto-escapes)
- CSRF protection (if using cookies, add CSRF token)

### Browser Compatibility
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

---

## Testing Strategy

### Unit Tests (Frontend)

**Test Files**:
- `web-ui/__tests__/app/page.test.tsx` (HomePage)
- `web-ui/__tests__/components/ProjectCreationForm.test.tsx`
- `web-ui/__tests__/components/Spinner.test.tsx`

**Coverage Target**: ≥85%

**Test Categories**:
1. Component rendering
2. Form validation
3. Submission handling
4. Error states
5. Loading states
6. Redirect logic

### Integration Tests (Frontend)

```typescript
describe('Project creation flow', () => {
  it('completes full flow: fill form → submit → redirect', async () => {
    // Mock API
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ id: 1, name: 'test-app', status: 'created' }),
      })
    );

    const { getByRole, getByLabelText } = render(<HomePage />);

    // Fill form
    fireEvent.change(getByLabelText('Project Name *'), { target: { value: 'test-app' } });
    fireEvent.change(getByLabelText('Description *'), { target: { value: 'A test description' } });

    // Submit
    fireEvent.submit(getByRole('form'));

    // Wait for redirect
    await waitFor(() => {
      expect(mockRouter.push).toHaveBeenCalledWith('/projects/1');
    });
  });
});
```

### Unit Tests (Backend)

**Test File**: `tests/api/test_project_creation_api.py`

**Test Cases**:
1. Successful project creation
2. Duplicate project name (409 error)
3. Invalid name format (400 error)
4. Missing required fields (422 error)
5. Description too short (422 error)
6. Database error handling

### Integration Tests (Backend)

```python
@pytest.mark.asyncio
async def test_create_project_and_retrieve(api_client, test_db):
    """Test creating a project and retrieving it."""
    # Create project
    response = await api_client.post("/api/projects", json={
        "name": "integration-test",
        "projectType": "python",
        "description": "Integration test project"
    })
    assert response.status_code == 201
    project_id = response.json()["id"]

    # Verify in database
    project = await test_db.get_project(project_id)
    assert project is not None
    assert project["name"] == "integration-test"
    assert project["status"] == "created"
    assert project["phase"] == "discovery"
```

### End-to-End Test (Manual for now, Playwright in Sprint 10)

**Test Case**: New User Onboarding
1. Start fresh instance: `rm .codeframe/state.db && codeframe serve`
2. Open http://localhost:8080
3. Verify welcome page displays
4. Fill form: name="e2e-test", type="python", description="E2E test project"
5. Click "Create Project & Start Discovery"
6. Verify redirect to `/projects/:id`
7. Verify dashboard shows project with status "created"

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| POST /api/projects endpoint might not exist | High | Check server.py/app.py first, implement if missing |
| Database schema might not support all fields | Medium | Verify schema early, add migration if needed |
| Redirect might fail if Dashboard expects more props | Medium | Test redirect immediately after implementation |
| Form validation might conflict with backend validation | Low | Ensure frontend validation matches Pydantic rules exactly |

---

## Dependencies

**Blocked By**:
- ✅ Feature 1 (Server Start Command) - COMPLETE

**Blocks**:
- Feature 3 (Discovery Answer UI) - Needs projects to exist

**External Dependencies**:
- None (all dependencies already in package.json/pyproject.toml)

---

## Acceptance Checklist

### Functional
- [ ] Root route renders ProjectCreationForm
- [ ] Form validates all fields correctly
- [ ] Submit creates project in database
- [ ] Duplicate names rejected with 409 error
- [ ] Invalid names rejected with 400 error
- [ ] Success redirects to `/projects/:id`
- [ ] Loading state shown during creation
- [ ] Error messages user-friendly

### Testing
- [ ] 15+ unit tests (frontend)
- [ ] 6+ unit tests (backend)
- [ ] 2+ integration tests
- [ ] All tests passing
- [ ] ≥85% coverage

### Code Quality
- [ ] TypeScript strict mode (no `any`)
- [ ] Type hints on all Python functions
- [ ] Linting passes (eslint, ruff)
- [ ] No console.log in production code
- [ ] Conventional commit messages

### Documentation
- [ ] Inline comments for complex logic
- [ ] Component props documented (JSDoc)
- [ ] API endpoint documented (docstring)
- [ ] README.md updated if needed

---

**Next Steps**:
1. Run `/speckit.plan` to generate implementation plan
2. Run `/speckit.tasks` to generate task list
3. Begin implementation with TDD approach
