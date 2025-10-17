# API Contract Evolution Roadmap

**Purpose**: Track planned API enhancements across sprints to prevent refactoring.

**Philosophy**: Additive changes only - never break existing contracts.

---

## Sprint 2 (Current): Foundation Contract ✅

**Endpoints:**
- `GET /api/projects/{id}/prd`
- `GET /api/projects/{id}/issues?include=tasks`

**Key Decisions:**
- ✅ IDs as `string` (future UUID support)
- ✅ RFC 3339 timestamps (`created_at`, `updated_at`, `completed_at`)
- ✅ `depends_on: string[]` (array, not single value)
- ✅ `proposed_by: 'agent' | 'human'` (provenance foundation)
- ✅ Pagination structure ready (`next_cursor`, `prev_cursor`)

**TypeScript Contract:**
```typescript
export type ISODate = string; // RFC 3339
export type WorkStatus = 'pending' | 'assigned' | 'in_progress' | 'blocked' | 'completed' | 'failed';

export interface Task {
  id: string;
  task_number: string;
  title: string;
  description: string;
  status: WorkStatus;
  depends_on: string[];
  proposed_by: 'agent' | 'human';
  created_at: ISODate;
  updated_at: ISODate;
  completed_at: ISODate | null;
}

export interface Issue {
  id: string;
  issue_number: string;
  title: string;
  description: string;
  status: WorkStatus;
  priority: number; // 0-4
  depends_on: string[];
  proposed_by: 'agent' | 'human';
  created_at: ISODate;
  updated_at: ISODate;
  completed_at: ISODate | null;
  tasks?: Task[]; // Conditional on include=tasks
}

export interface PRDResponse {
  project_id: string;
  prd_content: string;
  generated_at: ISODate;
  updated_at: ISODate;
  status: 'available' | 'generating' | 'not_found';
}

export interface IssuesResponse {
  issues: Issue[];
  total_issues: number;
  total_tasks: number;
  next_cursor?: string;
  prev_cursor?: string;
}
```

---

## Sprint 3: Agent Metadata & Filtering 🔜

**New Endpoints:**
- `GET /api/projects/{id}/issues?filter[status]=...&filter[assignee_id]=...&sort=-priority`

**Enhancements to Issue/Task:**
```typescript
interface Task {
  // ... Sprint 2 fields +
  labels?: string[];
  assignee_id?: string;
  estimate_minutes?: number;
  agent_meta?: {
    model_id: string;        // e.g., "claude-sonnet-4"
    run_id: string;          // Unique execution ID
    confidence: number;      // 0.0-1.0
    rationale?: string;      // Why agent created this
  };
  source_refs?: Array<{
    type: 'repo' | 'doc' | 'url';
    value: string;
  }>;
}
```

**Query Parameters:**
- `filter[status]` - Comma-separated statuses
- `filter[assignee_id]` - Filter by assignee
- `filter[updated_since]` - ISO date
- `sort` - e.g., `-priority,created_at`
- `page[size]` - Default 50, max 100
- `page[cursor]` - Opaque cursor string

**Database Changes:**
- Add `labels TEXT` (JSON array)
- Add `assignee_id TEXT`
- Add `estimate_minutes INTEGER`
- Add `agent_meta TEXT` (JSON blob)
- Add `source_refs TEXT` (JSON array)

---

## Sprint 4: Hierarchy & Advanced Coordination 🔜

**New Endpoints:**
- `GET /api/projects/{id}/milestones`
- `GET /api/projects/{id}/sprints`

**Enhancements to Issue:**
```typescript
interface Issue {
  // ... Sprint 3 fields +
  parent_issue_id?: string;      // Epic/parent story
  milestone_id?: string;
  sprint_id?: string;
  order_index?: number;          // Manual ordering in UI
  reviewer_id?: string;
  due_date?: ISODate | null;
  blocked_by?: string[];         // Denormalized convenience
  blocks?: string[];
}
```

**New Resources:**
```typescript
interface Milestone {
  id: string;
  title: string;
  description: string;
  due_date: ISODate;
  status: 'active' | 'completed';
  issues: Issue[];
}

interface Sprint {
  id: string;
  sprint_number: number;
  start_date: ISODate;
  end_date: ISODate;
  status: 'planning' | 'active' | 'completed';
  issues: Issue[];
}
```

**Database Changes:**
- Add `parent_issue_id INTEGER REFERENCES issues(id)`
- Add `milestone_id TEXT`
- Add `sprint_id TEXT`
- Add `order_index INTEGER`
- Create `milestones` table
- Create `sprints` table

---

## Sprint 5: PRD Versioning & Structured Sections 🔜

**New Endpoints:**
- `GET /api/projects/{id}/prd/versions` - List all PRD versions
- `GET /api/projects/{id}/prd/versions/{version}` - Get specific version
- `POST /api/projects/{id}/prd:regenerate` - Long-running operation

**Enhanced PRD Response:**
```typescript
interface PRDResponse {
  project_id: string;
  version: number;               // Monotonically increasing
  status: 'available' | 'generating' | 'not_found' | 'failed';
  generated_at: ISODate;
  updated_at: ISODate;
  format: 'markdown' | 'html' | 'json';

  // Structured sections (parseable)
  sections: {
    title: string;
    summary: string;
    problem: string;
    goals: string[];
    non_goals: string[];
    user_stories: Array<{
      id: string;
      as_a: string;
      i_want: string;
      so_that: string;
      acceptance_criteria: string[];
      priority: number;
      links?: string[];          // Link to issue IDs
    }>;
    requirements: {
      functional: string[];
      non_functional: string[];  // Performance, security, SLOs
    };
    success_metrics: string[];   // KPIs
    risks: string[];
    assumptions: string[];
    open_questions: string[];
    release_plan?: string;
  };

  raw: string;                   // Canonical markdown

  provenance?: {
    model_id: string;
    run_id: string;
    prompt_hash: string;
    citations?: Array<{ title: string; url: string }>;
    authors: Array<{ id: string; type: 'human' | 'agent' }>;
  };
}
```

**Database Changes:**
- Add `prd_versions` table
- Add `version INTEGER` to PRD storage
- Store structured JSON alongside raw markdown

---

## Sprint 6+: Advanced Features 🔮

### Concurrency Control
- **ETags**: `If-None-Match` for caching, `If-Match` for updates
- **Optimistic locking**: `version` field on mutable resources

### Webhooks
- `issue.created`
- `issue.status_changed`
- `task.completed`
- `prd.version.created`

### Soft Deletes
- Add `deleted_at` to issues/tasks
- Support `include_deleted=true` query param

### Batch Operations
- `POST /api/projects/{id}/issues:batch` - Bulk create/update
- `POST /api/projects/{id}/tasks:batch`

### Graph API
- `GET /api/projects/{id}/dependency-graph` - Full DAG visualization
- `POST /api/projects/{id}/issues/{id}/dependencies` - Add/remove deps

---

## Implementation Guidelines

### Additive Changes Only
- ✅ Add new optional fields
- ✅ Add new query parameters
- ✅ Add new endpoints
- ❌ Never remove fields
- ❌ Never change field types
- ❌ Never break existing queries

### Versioning Strategy
- **API version in URL**: `/api/v1/...` (when breaking changes needed)
- **Resource versioning**: `version` field for optimistic locking
- **Deprecation policy**: 2 sprint warning period

### Testing Requirements
- All new fields must have tests
- Backwards compatibility tests for existing contracts
- Integration tests for new query parameters

### Documentation
- Update OpenAPI spec with each sprint
- Document migration path for breaking changes
- Keep this roadmap updated

---

## Migration Checklist (Sprint 2 → Sprint 3)

When implementing Sprint 3 enhancements:

1. ✅ Add new fields to TypeScript interfaces as **optional**
2. ✅ Add database columns with `NULL` defaults
3. ✅ Write migration script for `depends_on` JSON array conversion
4. ✅ Update API serialization to include new fields
5. ✅ Add tests for new fields
6. ✅ Update frontend components to handle optional fields gracefully
7. ✅ Document new query parameters in API docs

---

## Notes

**ID Strategy:**
- Sprint 2: SQLite INTEGER PKs, exposed as string in API (e.g., `"1"`, `"42"`)
- Sprint 3+: Consider UUIDs for distributed systems (e.g., `"550e8400-e29b-41d4-a716-446655440000"`)

**Timestamp Format:**
- Always RFC 3339: `2025-10-17T21:13:37Z`
- Include timezone (UTC default)
- Frontend: Use `new Date(isoString)` for parsing

**Error Codes:**
- Use structured error codes (e.g., `PROJECT_NOT_FOUND`, not generic `404`)
- Include `hint` field for user-friendly guidance

---

**Last Updated**: 2025-10-17
**Status**: Living document - update with each sprint
