# Data Model: Project Creation Flow

**Feature**: 011-project-creation-flow
**Date**: 2025-11-18

## Overview

This feature primarily deals with **ephemeral frontend state** (form data) and leverages **existing database schema**. No database migrations required.

---

## Frontend State Models

### 1. ProjectCreationForm State

**Scope**: Component-local state (React `useState`)
**Lifecycle**: Created on component mount, destroyed on navigation away
**Purpose**: Track form input, validation errors, and submission status

```typescript
interface ProjectFormState {
  // Input Fields
  name: string;                    // Project name (lowercase, alphanumeric, hyphens, underscores)
  projectType: ProjectType;        // 'python' | 'typescript' | 'fullstack' | 'other'
  description: string;             // Project description (10-500 chars)

  // Validation State
  errors: Record<string, string>;  // Field-level errors: { name: "...", description: "..." }
  touched: Record<string, boolean>; // Track if field has been blurred (for on-blur validation)

  // Submission State
  isSubmitting: boolean;           // True during API call
  submitError: string | null;      // Server error message (409 duplicate, 500 server error)

  // Success State
  createdProjectId: number | null; // Set after successful creation, used for redirect
}
```

**State Transitions**:
```
[Initial State]
  name: ""
  projectType: "python"
  description: ""
  errors: {}
  touched: {}
  isSubmitting: false
  submitError: null
  createdProjectId: null

↓ User types in name input

[After user input]
  name: "my-app"
  errors: {}  // No errors yet (not blurred)
  touched: { name: false }

↓ User blurs from name input (triggers validation)

[After blur validation]
  touched: { name: true }
  errors: { name: "Project name must be at least 3 characters" }  // If invalid

↓ User fixes name and submits form

[During submission]
  isSubmitting: true
  errors: {}  // Cleared on submit

↓ API returns success

[After successful creation]
  isSubmitting: false
  createdProjectId: 123

↓ Parent component receives `onSuccess(123)` callback and redirects to /projects/123
```

**Validation Rules**:

| Field | Required | Min Length | Max Length | Pattern | Validation Trigger |
|-------|----------|------------|------------|---------|-------------------|
| `name` | Yes | 3 | 100 | `/^[a-z0-9-_]+$/` | On blur, on submit |
| `description` | Yes | 10 | 500 | None | On blur, on submit |
| `projectType` | Yes | N/A | N/A | Enum | On submit (dropdown always valid) |

**Error Messages**:
```typescript
const errorMessages = {
  name: {
    required: "Project name is required",
    minLength: "Project name must be at least 3 characters",
    pattern: "Only lowercase letters, numbers, hyphens, and underscores allowed",
    duplicate: "Project '{name}' already exists"  // From API 409 response
  },
  description: {
    required: "Project description is required",
    minLength: "Description must be at least 10 characters",
    maxLength: "Description must be 500 characters or less"
  },
  submit: {
    network: "Failed to create project. Please check your connection and try again.",
    server: "Server error occurred. Please try again later."
  }
};
```

---

### 2. HomePage State

**Scope**: Page-level state (React `useState`)
**Lifecycle**: Created when page renders, destroyed on navigation
**Purpose**: Control loading spinner display during project creation

```typescript
interface HomePageState {
  isCreating: boolean;  // True from form submit until redirect
}
```

**State Flow**:
```
[Initial] isCreating: false → Show ProjectCreationForm

↓ User submits form → ProjectCreationForm calls onSubmit()

[Loading] isCreating: true → Show Spinner with "Creating your project..." message

↓ API returns success → ProjectCreationForm calls onSuccess(projectId)

[Redirecting] HomePage calls router.push('/projects/123') and navigates away
```

---

### 3. Spinner Component State

**Scope**: Stateless presentational component
**Props**:
```typescript
interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';  // Default: 'md'
}
```

**No Internal State** - Pure visual component driven by props

---

## API Request/Response Models

### POST /api/projects

**Request Body**:
```typescript
interface ProjectCreateRequest {
  name: string;           // 3-100 chars, lowercase/numbers/hyphens/underscores
  description: string;    // 10-500 chars
  projectType?: string;   // Optional: 'python', 'typescript', 'fullstack', 'other'
}
```

**Success Response (201 Created)**:
```typescript
interface ProjectCreateResponse {
  id: number;             // Auto-generated project ID
  name: string;           // Echoed back from request
  status: string;         // Always "created" for new projects
  phase?: string;         // "discovery" (default phase)
  created_at?: string;    // ISO timestamp
}
```

**Error Responses**:

**400 Bad Request** (Validation Error):
```json
{
  "detail": "Invalid project name format"
}
```

**409 Conflict** (Duplicate Name):
```json
{
  "detail": "Project with name 'my-app' already exists"
}
```

**500 Internal Server Error** (Workspace Creation Failed):
```json
{
  "detail": "Workspace creation failed: [error details]"
}
```

---

## Backend Database Schema

**Table**: `projects` (already exists, no changes required)

```sql
CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,               -- Project identifier
  description TEXT,                        -- Project description (nullable in DB, but required by API)
  source_type TEXT,                        -- 'new_repo', 'local_path', 'git_url'
  source_location TEXT,                    -- Path or URL (nullable)
  source_branch TEXT,                      -- Git branch (nullable)
  workspace_path TEXT,                     -- Absolute path to workspace
  status TEXT DEFAULT 'init',              -- 'init', 'active', 'paused', 'completed'
  phase TEXT DEFAULT 'discovery',          -- 'discovery', 'prd_generation', 'implementation', 'testing'
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  config TEXT,                             -- JSON blob for project settings
  git_initialized BOOLEAN DEFAULT 0        -- Whether git repo created in workspace
);

CREATE INDEX idx_projects_name ON projects(name);  -- For duplicate check performance
CREATE INDEX idx_projects_status ON projects(status);
```

**Fields Used by This Feature**:
- `name` - From form input (required, unique)
- `description` - From form input (required in API, nullable in DB)
- `source_type` - Default: 'new_repo' (set by backend)
- `workspace_path` - Generated by WorkspaceManager (set by backend)
- `status` - Default: 'init' (set by backend)
- `phase` - Default: 'discovery' (set by backend)
- `created_at` - Auto-generated timestamp

**Fields Not Used**:
- `source_location`, `source_branch` - Null for new projects
- `config` - Not set during creation (default null)
- `git_initialized` - Set to true after workspace creation

---

## Type Definitions

### Frontend TypeScript

**Location**: `web-ui/src/types/project.ts` (existing file, may need extension)

```typescript
// Form-specific types
export type ProjectType = 'python' | 'typescript' | 'fullstack' | 'other';

export interface ProjectCreationFormProps {
  onSuccess: (projectId: number) => void;   // Required: called with project ID on success
  onSubmit?: () => void;                     // Optional: called before API request (for loading state)
  onError?: (error: Error) => void;          // Optional: called on API error
}

export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
}

// API types (may already exist)
export interface ProjectResponse {
  id: number;
  name: string;
  status: string;
  phase?: string;
  created_at?: string;
  config?: any;
}
```

### Backend Python

**Location**: `codeframe/ui/models.py` (existing file, already has ProjectCreateRequest)

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class SourceType(str, Enum):
    NEW_REPO = "new_repo"
    LOCAL_PATH = "local_path"
    GIT_URL = "git_url"

class ProjectCreateRequest(BaseModel):
    """Request model for creating a new project."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    source_type: Optional[SourceType] = Field(default=SourceType.NEW_REPO)
    # ... other optional fields

class ProjectResponse(BaseModel):
    """Response model for project details."""
    id: int
    name: str
    status: str
    phase: Optional[str] = None
    created_at: Optional[str] = None
    config: Optional[dict] = None
```

**Note**: Frontend validation will be **stricter** than Pydantic:
- Frontend: name min 3 chars, pattern `/^[a-z0-9-_]+$/`
- Backend: name min 1 char, no pattern check
- This is intentional for better UX (catch errors client-side)

---

## Validation Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend Validation (Client-Side)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [User Types] → [On Blur] → Validate:                       │
│   - Required? (name, description)                          │
│   - Length? (name ≥ 3, description ≥ 10)                   │
│   - Pattern? (name: /^[a-z0-9-_]+$/)                       │
│                                                             │
│ ↓ Errors found?                                             │
│   YES → Display inline error messages                      │
│   NO  → Field valid ✓                                       │
│                                                             │
│ [User Submits] → Validate all fields again                 │
│   ↓ All valid?                                              │
│     YES → Send POST /api/projects                          │
│     NO  → Show errors, prevent submit                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Backend Validation (Server-Side)                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [Receive Request] → Pydantic Validation:                   │
│   - Type check (name: str, description: str)               │
│   - Length check (min_length, max_length)                  │
│   ↓ Invalid?                                                │
│     → 422 Unprocessable Entity                             │
│                                                             │
│ [Business Logic] → Check duplicate name:                   │
│   - Query: SELECT * FROM projects WHERE name = ?           │
│   ↓ Exists?                                                 │
│     → 409 Conflict                                         │
│                                                             │
│ [Create Workspace] → WorkspaceManager.create_workspace()   │
│   ↓ Fails?                                                  │
│     → 500 Internal Server Error                            │
│                                                             │
│ [Insert DB] → INSERT INTO projects (...)                   │
│   ↓ Success                                                 │
│     → 201 Created + { id, name, status }                   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Frontend Success Handling                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [Receive 201] → Extract project.id                         │
│   → Call onSuccess(projectId)                              │
│   → HomePage receives callback                             │
│   → router.push(`/projects/${projectId}`)                  │
│   → User redirected to Dashboard                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow Summary

1. **User Input** → `ProjectFormState` (React state)
2. **Validation** → Client-side (on blur, on submit) → Display errors inline
3. **Submission** → POST `/api/projects` → Server-side validation
4. **Success** → `ProjectResponse` → Extract `id` → `onSuccess(id)` callback
5. **Redirect** → HomePage → `router.push('/projects/123')`
6. **Database** → `projects` table row inserted with default values

**No data persistence on frontend** - all form data is ephemeral and cleared after successful submission.

---

**Data Model Complete** ✅
**Next**: Generate `contracts/api.openapi.yaml` and `quickstart.md`
