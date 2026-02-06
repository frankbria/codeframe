# Implementation Plan: Task Board View - Kanban & Batch Execution

**Issue:** #331 — [Phase 3] Task Board View - Kanban & Batch Execution
**Last updated:** 2026-02-05

---

## Observations

The codebase is ready for Task Board implementation:

- **Backend APIs**: Complete v2 endpoints for tasks (`codeframe/ui/routers/tasks_v2.py`) and batches (`codeframe/ui/routers/batches_v2.py`)
- **Frontend Stack**: Next.js 16 App Router, Shadcn/UI (Nova template, gray color scheme), Tailwind CSS, Hugeicons (`@hugeicons/react`), Nunito Sans font
- **Active UI Directory**: `web-ui/` — all new files go here (not `legacy/web-ui/`)
- **Existing Patterns**: `web-ui/src/lib/api.ts` uses axios with namespace objects (`workspaceApi`, `tasksApi`, `prdApi`). Types live in `web-ui/src/types/index.ts`. Components organized in subdirectories under `web-ui/src/components/`.
- **Existing Task Types**: `Task`, `TaskStatus`, `TaskStatusCounts`, `TaskListResponse` already defined in `web-ui/src/types/index.ts`
- **Existing Task API**: `tasksApi.getAll()` already exists in `web-ui/src/lib/api.ts`
- **Badge Variants**: Status-colored badge variants (ready, in-progress, done, blocked, failed, backlog, merged) already defined in `web-ui/src/components/ui/badge.tsx`
- **Sidebar**: Tasks nav link exists in `AppSidebar.tsx` but is disabled (`enabled: false`)
- **Shadcn/UI Components Available**: Button, Card, Dialog, Badge, Tabs
- **Missing Shadcn Components**: Select (needed for strategy selector), Checkbox (needed for batch selection), Input (needed for search) — must be added via `npx shadcn@latest add`

---

## Approach

Following the Phase 3 UI Architecture (`docs/PHASE_3_UI_ARCHITECTURE.md` Sections 1.3, 3.3, 5.4):

1. **Reuse existing types & API**: Extend `tasksApi` with missing methods; add new batch types
2. **Kanban board**: Responsive column layout grouped by status — 3 columns at `md`, wrapping or horizontal scroll for 6 statuses
3. **Task detail via Dialog**: Modal overlay using existing `Dialog` component (not parallel routes — avoids over-engineering per Section 6.5)
4. **Batch execution**: Header bar with checkbox selection, strategy selector, and execute button
5. **SWR data fetching**: Match existing pattern from PRD page (`useSWR` with `mutate` for post-action refresh)
6. **Navigation**: Enable existing `/tasks` sidebar link

---

## Acceptance Criteria (from issue #331)

| # | Criterion | Covered in Step |
|---|-----------|-----------------|
| 1 | Kanban-style columns grouped by status | Step 6 |
| 2 | Task cards show title, description snippet, status badge | Step 4 |
| 3 | Task cards show dependency indicators | Step 4 |
| 4 | Click task to open detail modal | Step 7 |
| 5 | Execute button on READY tasks | Step 4 |
| 6 | Mark Ready button on BACKLOG tasks | Step 4 |
| 7 | Search/filter by task title or status | Step 8 |
| 8 | Checkbox selection for batch execution | Step 9 |
| 9 | Strategy selector (serial/parallel/auto) | Step 9 |
| 10 | Execute batch button starts batch run | Step 9 |
| 11 | Navigate to Execution Monitor on task/batch start | Step 11 |

---

## API Endpoints (verified against backend routers)

### Tasks (`/api/v2/tasks`)
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v2/tasks` | List tasks (with optional `status` filter) |
| `GET` | `/api/v2/tasks/{task_id}` | Get single task details |
| `PATCH` | `/api/v2/tasks/{task_id}` | Update task (status, title, description, priority) |
| `DELETE` | `/api/v2/tasks/{task_id}` | Delete task |
| `POST` | `/api/v2/tasks/{task_id}/start` | Start single task execution (`?execute=true`) |
| `POST` | `/api/v2/tasks/{task_id}/stop` | Stop running task |
| `POST` | `/api/v2/tasks/{task_id}/resume` | Resume blocked task |
| `POST` | `/api/v2/tasks/execute` | Start batch execution |
| `GET` | `/api/v2/tasks/{task_id}/stream` | SSE stream for task output |
| `GET` | `/api/v2/tasks/{task_id}/run` | Get latest run for task |

### Batches (`/api/v2/batches`)
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v2/batches` | List batches |
| `GET` | `/api/v2/batches/{batch_id}` | Get batch details |
| `POST` | `/api/v2/batches/{batch_id}/stop` | Stop batch |
| `POST` | `/api/v2/batches/{batch_id}/resume` | Resume batch |
| `POST` | `/api/v2/batches/{batch_id}/cancel` | Cancel batch |

All endpoints require `workspace_path` query parameter.

---

## Implementation Steps

### Step 1. Add Missing Shadcn/UI Components

Install components needed for the Task Board that don't exist yet:

```bash
cd web-ui
npx shadcn@latest add select checkbox input
```

This provides:
- `Select` — strategy selector dropdown (serial/parallel/auto)
- `Checkbox` — batch task selection
- `Input` — search/filter input field

### Step 2. Add Task Board Types

**File:** `web-ui/src/types/index.ts`

Add new types for batch execution (Task, TaskStatus, TaskListResponse already exist):

```typescript
// Batch execution types
export type BatchStrategy = 'serial' | 'parallel' | 'auto';

export interface BatchExecutionRequest {
  task_ids?: string[];
  strategy: BatchStrategy;
  max_parallel?: number;
  retry_count?: number;
}

export interface StartExecutionResponse {
  success: boolean;
  batch_id: string;
  task_count: number;
  strategy: string;
  message: string;
}

export interface TaskStartResponse {
  success: boolean;
  run_id: string;
  task_id: string;
  status: string;
}
```

### Step 3. Extend API Client

**File:** `web-ui/src/lib/api.ts`

Add methods to existing `tasksApi` namespace and create new `batchesApi`:

```typescript
// Extend tasksApi with:
export const tasksApi = {
  getAll: /* ... existing ... */,

  getOne: async (workspacePath: string, taskId: string): Promise<Task> => {
    const response = await api.get<Task>(`/api/v2/tasks/${taskId}`, {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  updateStatus: async (workspacePath: string, taskId: string, status: TaskStatus): Promise<Task> => {
    const response = await api.patch<Task>(`/api/v2/tasks/${taskId}`, {
      status,
    }, {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  startExecution: async (workspacePath: string, taskId: string): Promise<TaskStartResponse> => {
    const response = await api.post<TaskStartResponse>(
      `/api/v2/tasks/${taskId}/start`,
      {},
      { params: { workspace_path: workspacePath, execute: true } }
    );
    return response.data;
  },

  executeBatch: async (workspacePath: string, request: BatchExecutionRequest): Promise<StartExecutionResponse> => {
    const response = await api.post<StartExecutionResponse>(
      '/api/v2/tasks/execute',
      request,
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },
};
```

### Step 4. Create TaskCard Component

**File:** `web-ui/src/components/tasks/TaskCard.tsx`

Build a reusable task card component:

- Use `Card` from `web-ui/src/components/ui/card.tsx` as base
- Display task title (truncated to 1 line), description snippet (2 lines max via `line-clamp-2`)
- Show `Badge` for status using existing variant mapping from `badge.tsx`
- Display dependency count indicator if `depends_on.length > 0` (e.g., "2 deps" pill)
- Include action buttons:
  - **"Execute"** — visible only when `status === 'READY'` (icon: `PlayCircleIcon` from `@hugeicons/react`)
  - **"Mark Ready"** — visible only when `status === 'BACKLOG'` (icon: `CheckmarkCircle01Icon`)
- Make entire card clickable to open detail modal
- Hover effect: `hover:border-primary/50 transition-colors`
- Optional `Checkbox` in top-right corner when selection mode is active

**Props:**
```typescript
interface TaskCardProps {
  task: Task;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: (taskId: string) => void;
  onClick: (taskId: string) => void;
  onExecute: (taskId: string) => void;
  onMarkReady: (taskId: string) => void;
}
```

**Acceptance criteria addressed:** #2, #3, #5, #6

### Step 5. Create TaskColumn Component

**File:** `web-ui/src/components/tasks/TaskColumn.tsx`

Build Kanban column component:

- Column header with status label + task count badge
- Scrollable list of `TaskCard` components (`overflow-y-auto max-h-[calc(100vh-280px)]`)
- Empty state message when no tasks in column (e.g., "No tasks")
- Column styling: `flex flex-col gap-3 bg-muted/30 rounded-lg p-4 min-w-[250px]`

**Props:**
```typescript
interface TaskColumnProps {
  status: TaskStatus;
  tasks: Task[];
  selectionMode: boolean;
  selectedTaskIds: Set<string>;
  onTaskClick: (taskId: string) => void;
  onToggleSelect: (taskId: string) => void;
  onExecute: (taskId: string) => void;
  onMarkReady: (taskId: string) => void;
}
```

### Step 6. Create TaskBoardContent Component

**File:** `web-ui/src/components/tasks/TaskBoardContent.tsx`

Responsive Kanban layout:

- Renders 6 `TaskColumn` components (BACKLOG, READY, IN_PROGRESS, BLOCKED, FAILED, DONE)
- Layout: `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4`
- On smaller screens, columns stack naturally — no horizontal scroll needed
- Groups tasks from the flat array into per-status buckets

**Acceptance criteria addressed:** #1

### Step 7. Create TaskDetailModal Component

**File:** `web-ui/src/components/tasks/TaskDetailModal.tsx`

Build modal using existing `Dialog` from `web-ui/src/components/ui/dialog.tsx`:

- Fetches full task details via `tasksApi.getOne(workspacePath, taskId)` on open
- Displays: title, full description (rendered as text), status badge, priority, dependency list, estimated hours
- Dependencies: list dependency task IDs (link to open their detail)
- Footer action buttons:
  - **"Execute"** — if `status === 'READY'` → calls `tasksApi.startExecution()` → navigates to `/execution`
  - **"Mark Ready"** — if `status === 'BACKLOG'` → calls `tasksApi.updateStatus(id, 'READY')` → refreshes board
  - **"Close"** — closes the dialog
- Loading skeleton while fetching, error state on failure

**Props:**
```typescript
interface TaskDetailModalProps {
  taskId: string | null;
  workspacePath: string;
  open: boolean;
  onClose: () => void;
  onExecute: (taskId: string) => void;
  onStatusChange: () => void; // triggers SWR mutate to refresh board
}
```

**Acceptance criteria addressed:** #4

### Step 8. Create TaskFilters Component

**File:** `web-ui/src/components/tasks/TaskFilters.tsx`

Build filter controls:

- Search `Input` with `Search01Icon` from `@hugeicons/react` (debounced 300ms via `setTimeout`)
- Status filter pills — clickable badges to toggle status visibility (all statuses shown by default, click to filter to one)
- Clear filters button when any filter is active

**Props:**
```typescript
interface TaskFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: TaskStatus | null;
  onStatusFilter: (status: TaskStatus | null) => void;
}
```

**Acceptance criteria addressed:** #7

### Step 9. Create BatchActionsBar Component

**File:** `web-ui/src/components/tasks/BatchActionsBar.tsx`

Build batch execution controls:

- **Toggle selection mode** button (icon: `CheckList01Icon` from `@hugeicons/react`)
- When in selection mode:
  - Display selected task count: "{N} tasks selected"
  - `Select` dropdown for strategy: Serial, Parallel, Auto
  - **"Execute Batch"** `Button` — disabled when no tasks selected
  - **"Clear Selection"** link button
- When not in selection mode: just the toggle button

**Props:**
```typescript
interface BatchActionsBarProps {
  selectionMode: boolean;
  onToggleSelectionMode: () => void;
  selectedCount: number;
  strategy: BatchStrategy;
  onStrategyChange: (strategy: BatchStrategy) => void;
  onExecuteBatch: () => void;
  onClearSelection: () => void;
  isExecuting: boolean;
}
```

**Acceptance criteria addressed:** #8, #9, #10

### Step 10. Create Main TaskBoardView Component

**File:** `web-ui/src/components/tasks/TaskBoardView.tsx`

Main board container that orchestrates all child components:

**State:**
```typescript
const [searchQuery, setSearchQuery] = useState('');
const [statusFilter, setStatusFilter] = useState<TaskStatus | null>(null);
const [selectionMode, setSelectionMode] = useState(false);
const [selectedTaskIds, setSelectedTaskIds] = useState<Set<string>>(new Set());
const [batchStrategy, setBatchStrategy] = useState<BatchStrategy>('serial');
const [detailTaskId, setDetailTaskId] = useState<string | null>(null);
const [isExecuting, setIsExecuting] = useState(false);
```

**Data fetching:** `useSWR` for task list (same pattern as PRD page):
```typescript
const { data: tasksData, isLoading, mutate } = useSWR<TaskListResponse, ApiError>(
  workspacePath ? `/api/v2/tasks?path=${workspacePath}` : null,
  () => tasksApi.getAll(workspacePath!)
);
```

**Client-side filtering:**
- Search: filter by title or description (case-insensitive substring match)
- Status: filter to single status when selected

**Layout:**
```tsx
<div className="space-y-4">
  <div className="flex items-center justify-between gap-4">
    <TaskFilters ... />
    <BatchActionsBar ... />
  </div>
  <TaskBoardContent ... />
  <TaskDetailModal ... />
</div>
```

**Handlers:**
- `handleExecuteTask(taskId)` → call API, then navigate to `/execution`
- `handleMarkReady(taskId)` → call API, then `mutate()` to refresh board
- `handleExecuteBatch()` → call API with selected IDs + strategy, then navigate to `/execution`
- `handleToggleSelect(taskId)` → toggle task ID in `selectedTaskIds` set
- `handleTaskClick(taskId)` → set `detailTaskId` to open modal

### Step 11. Create Tasks Page Route

**File:** `web-ui/src/app/tasks/page.tsx`

Follow the exact pattern from `web-ui/src/app/prd/page.tsx`:

```typescript
'use client';

import { useState, useEffect } from 'react';
import { TaskBoardView } from '@/components/tasks';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';

export default function TasksPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  if (!workspaceReady) return null;

  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border bg-muted/50 p-6 text-center">
            <p className="text-muted-foreground">
              No workspace selected. Use the sidebar to return to{' '}
              <a href="/" className="text-primary hover:underline">Workspace</a>{' '}
              and select a project.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <TaskBoardView workspacePath={workspacePath} />
      </div>
    </main>
  );
}
```

**Acceptance criteria addressed:** #11 (via `useRouter().push('/execution')` after execution start)

### Step 12. Enable Navigation Link

**File:** `web-ui/src/components/layout/AppSidebar.tsx`

Change line 26:
```diff
- { href: '/tasks', label: 'Tasks', icon: Task01Icon, enabled: false },
+ { href: '/tasks', label: 'Tasks', icon: Task01Icon, enabled: true },
```

### Step 13. Barrel Export

**File:** `web-ui/src/components/tasks/index.ts`

```typescript
export { TaskBoardView } from './TaskBoardView';
export { TaskCard } from './TaskCard';
export { TaskColumn } from './TaskColumn';
export { TaskBoardContent } from './TaskBoardContent';
export { TaskDetailModal } from './TaskDetailModal';
export { TaskFilters } from './TaskFilters';
export { BatchActionsBar } from './BatchActionsBar';
```

### Step 14. Testing

**Component tests (Jest):**
- `__tests__/components/tasks/TaskCard.test.tsx` — renders title, description, badge, action buttons for each status
- `__tests__/components/tasks/TaskBoardView.test.tsx` — renders columns, handles filtering, selection mode

**Manual testing:**
- End-to-end golden path: navigate to /tasks → see Kanban → click task → modal opens → execute → navigates to /execution
- Batch flow: enable selection → select multiple → choose strategy → execute batch

---

## File Structure (all under `web-ui/`)

```
web-ui/src/
├── app/
│   └── tasks/
│       └── page.tsx                     # Task board route
├── components/
│   └── tasks/
│       ├── index.ts                     # Barrel export
│       ├── TaskBoardView.tsx            # Main container + state management
│       ├── TaskBoardContent.tsx         # Kanban column grid layout
│       ├── TaskColumn.tsx               # Single status column
│       ├── TaskCard.tsx                 # Individual task card
│       ├── TaskDetailModal.tsx          # Task detail dialog
│       ├── TaskFilters.tsx              # Search + status filter
│       └── BatchActionsBar.tsx          # Batch execution controls
├── lib/
│   └── api.ts                           # Extend tasksApi with new methods
└── types/
    └── index.ts                         # Add batch execution types
```

---

## Component Dependency Graph

```
TasksPage (app/tasks/page.tsx)
└── TaskBoardView
    ├── TaskFilters
    ├── BatchActionsBar
    ├── TaskBoardContent
    │   └── TaskColumn (×6)
    │       └── TaskCard (×N)
    └── TaskDetailModal
```

---

## API Integration Summary

| Action | Endpoint | Method | Post-Action |
|--------|----------|--------|-------------|
| Load tasks | `/api/v2/tasks` | GET | — |
| Get task detail | `/api/v2/tasks/{id}` | GET | — |
| Mark task ready | `/api/v2/tasks/{id}` | PATCH `{status: "READY"}` | `mutate()` refresh board |
| Execute single task | `/api/v2/tasks/{id}/start?execute=true` | POST | Navigate → `/execution` |
| Execute batch | `/api/v2/tasks/execute` | POST `{task_ids, strategy}` | Navigate → `/execution` |

---

## Implementation Order

Recommended build sequence (each step produces a testable increment):

1. **Shadcn components + types + API** — foundation, no UI yet
2. **Tasks page route + empty TaskBoardView** — renders at `/tasks`
3. **Enable sidebar link** — can navigate to `/tasks`
4. **TaskCard + TaskColumn + TaskBoardContent** — Kanban board visible with real data
5. **TaskDetailModal** — click card to see details
6. **TaskFilters** — search and status filtering
7. **BatchActionsBar** — batch selection and execution
8. **Execute + Mark Ready actions** — wire up API calls and navigation
9. **Testing** — component tests
