# TypeScript Types Update Summary

**Phase:** Multi-Agent Per Project Architecture (Phase 3)
**Date:** 2025-12-03
**Status:** ✅ Complete

## Overview

Updated TypeScript types to support the new multi-agent per project architecture where:
- Agents are **project-agnostic** at creation time
- Agents can be **assigned to multiple projects** via many-to-many relationship
- Project context is derived from the **task being executed**, not from agent initialization

## Files Modified/Created

### 1. **Created: `/web-ui/src/types/agentAssignment.ts`** (New File)

**Purpose:** Comprehensive types for agent-project assignment operations

**Types Added:**

#### Request Types
- `AgentAssignmentRequest` - Request to assign agent to project
  - `agent_id: string`
  - `role?: string` (e.g., 'primary_backend', 'code_reviewer')

- `AgentRoleUpdateRequest` - Request to update agent's role on project
  - `role: string`

#### Response Types
- `AgentAssignment` - Agent assignment from project perspective
  - Agent metadata (id, type, provider, maturity_level, status)
  - Assignment metadata (role, assigned_at, unassigned_at, is_active)
  - Current task information (current_task_id, last_heartbeat)

- `ProjectAssignment` - Project assignment from agent perspective
  - Project metadata (id, name, description, status, phase)
  - Assignment metadata (role, assigned_at, unassigned_at, is_active)

- `AssignmentCreatedResponse` - Response when creating assignment
  - `assignment_id: number`
  - `message: string`

#### API Client Parameter Types
- `GetAgentsForProjectParams`
- `GetProjectsForAgentParams`
- `UnassignAgentParams`

### 2. **Modified: `/web-ui/src/types/agentState.ts`**

**Changes:**
- ✅ **Added `project_id: number` to `Task` interface**
  - Tasks are project-scoped (agents derive project context from tasks)
  - Breaking change for any code that creates Task objects

**No Changes Needed:**
- `Agent` interface already **doesn't have project_id** field ✅
- Agent is correctly project-agnostic in existing types

### 3. **Modified: `/web-ui/src/types/index.ts`**

**Changes:**
- Added re-exports for all agent assignment types from `agentAssignment.ts`
- Types now available via `import { AgentAssignment } from '@/types'`

### 4. **Created: `/web-ui/src/api/agentAssignment.ts`** (New File)

**Purpose:** Type-safe API client for agent assignment operations

**Functions Added:**

```typescript
// Get agents assigned to a project
getAgentsForProject(projectId: number, isActive?: boolean): Promise<AgentAssignment[]>

// Assign agent to project
assignAgentToProject(projectId: number, request: AgentAssignmentRequest): Promise<AssignmentCreatedResponse>

// Unassign agent from project
unassignAgentFromProject(projectId: number, agentId: string): Promise<void>

// Update agent's role on project
updateAgentRole(projectId: number, agentId: string, request: AgentRoleUpdateRequest): Promise<AgentAssignment>

// Get projects assigned to agent
getProjectsForAgent(agentId: string, isActive?: boolean): Promise<ProjectAssignment[]>
```

**Features:**
- Full TypeScript type safety
- Proper error handling with descriptive messages
- Support for optional query parameters (is_active filtering)
- Uses environment variable for API URL (VITE_API_URL)

## Breaking Changes

### 1. Task Interface - Added `project_id` Field

**Impact:** Medium
**Location:** `/web-ui/src/types/agentState.ts`

```typescript
// OLD
export interface Task {
  id: number;
  title: string;
  status: TaskStatus;
  // ...
}

// NEW
export interface Task {
  id: number;
  project_id: number;  // ⚠️ NEW REQUIRED FIELD
  title: string;
  status: TaskStatus;
  // ...
}
```

**Migration Required:**
- Any code creating `Task` objects must now include `project_id`
- WebSocket message handlers that create tasks need `project_id`
- Task reducers that initialize tasks must include `project_id`

**Example Fix:**
```typescript
// Before
const task: Task = {
  id: 42,
  title: "Implement API",
  status: "pending",
  timestamp: Date.now()
};

// After
const task: Task = {
  id: 42,
  project_id: 123,  // ⚠️ Required
  title: "Implement API",
  status: "pending",
  timestamp: Date.now()
};
```

### 2. No Breaking Changes to Agent Interface

**Good News:** The `Agent` interface in `agentState.ts` already doesn't have a `project_id` field, so existing code is compatible with the new architecture.

## Component Updates Needed

### Required Updates

1. **Task Creation Code**
   - Any components/reducers that create Task objects must now include `project_id`
   - Check: `agentReducer.ts`, WebSocket message handlers

2. **WebSocket Message Handlers**
   - Ensure `task_assigned`, `task_status_changed`, etc. messages include `project_id`
   - Map backend `project_id` field to frontend Task objects

### No Updates Required

1. **Agent-Related Components**
   - `AgentStateProvider.tsx` - Already uses correct types ✅
   - `AgentMetrics.tsx` - No changes needed ✅
   - Agent display/status components - No changes needed ✅

## API Endpoint Mapping

### New Endpoints Supported

| Endpoint | Method | TypeScript Function | Purpose |
|----------|--------|---------------------|---------|
| `/api/projects/{project_id}/agents` | GET | `getAgentsForProject()` | List agents for project |
| `/api/projects/{project_id}/agents` | POST | `assignAgentToProject()` | Assign agent to project |
| `/api/projects/{project_id}/agents/{agent_id}` | DELETE | `unassignAgentFromProject()` | Unassign agent |
| `/api/projects/{project_id}/agents/{agent_id}/role` | PUT | `updateAgentRole()` | Update agent role |
| `/api/agents/{agent_id}/projects` | GET | `getProjectsForAgent()` | List projects for agent |

## Testing Recommendations

### Unit Tests Needed

1. **Type Validation Tests**
   ```typescript
   // Test AgentAssignment type
   test('AgentAssignment has required fields', () => {
     const assignment: AgentAssignment = {
       agent_id: "backend-001",
       type: "backend",
       provider: "anthropic",
       // ... all required fields
     };
     expect(assignment.is_active).toBeDefined();
   });
   ```

2. **API Client Tests**
   ```typescript
   test('getAgentsForProject fetches agents', async () => {
     const agents = await getAgentsForProject(1, true);
     expect(agents).toBeInstanceOf(Array);
     expect(agents[0].agent_id).toBeDefined();
   });
   ```

3. **Task project_id Tests**
   ```typescript
   test('Task requires project_id', () => {
     const task: Task = {
       id: 1,
       project_id: 123, // Required
       title: "Test",
       status: "pending",
       timestamp: Date.now()
     };
     expect(task.project_id).toBe(123);
   });
   ```

### Integration Tests Needed

1. **Agent Assignment Flow**
   - Assign agent → Verify in project's agent list → Unassign → Verify removed

2. **Multi-Project Agent**
   - Assign agent to Project A → Assign to Project B → Verify both assignments active

3. **Task-to-Project Linking**
   - Create task with project_id → Assign to agent → Verify agent can execute

## Migration Checklist

- [x] Create `agentAssignment.ts` types file
- [x] Update `agentState.ts` Task interface with project_id
- [x] Add re-exports to `index.ts`
- [x] Create API client in `api/agentAssignment.ts`
- [ ] Update `agentReducer.ts` to handle project_id in tasks (if needed)
- [ ] Update WebSocket message handlers to include project_id (if needed)
- [ ] Add unit tests for new types
- [ ] Add integration tests for API client
- [ ] Update component code that creates Task objects
- [ ] Verify no regressions in existing agent features

## Usage Examples

### Example 1: Assign Agent to Project

```typescript
import { assignAgentToProject } from '@/api/agentAssignment';

async function assignBackendAgent(projectId: number) {
  try {
    const result = await assignAgentToProject(projectId, {
      agent_id: "backend-001",
      role: "primary_backend"
    });
    console.log(`Assignment created: ${result.assignment_id}`);
  } catch (error) {
    console.error("Failed to assign agent:", error);
  }
}
```

### Example 2: Get All Agents for Project

```typescript
import { getAgentsForProject } from '@/api/agentAssignment';

async function loadProjectAgents(projectId: number) {
  try {
    // Get only active agents
    const agents = await getAgentsForProject(projectId, true);

    agents.forEach(agent => {
      console.log(`${agent.agent_id} (${agent.role}): ${agent.status}`);
    });
  } catch (error) {
    console.error("Failed to load agents:", error);
  }
}
```

### Example 3: Check Agent's Projects

```typescript
import { getProjectsForAgent } from '@/api/agentAssignment';

async function showAgentWorkload(agentId: string) {
  try {
    const projects = await getProjectsForAgent(agentId, true);
    console.log(`${agentId} is working on ${projects.length} projects:`);

    projects.forEach(project => {
      console.log(`- ${project.name} (${project.role}) - ${project.phase}`);
    });
  } catch (error) {
    console.error("Failed to load projects:", error);
  }
}
```

### Example 4: Creating Tasks with project_id

```typescript
import type { Task } from '@/types/agentState';

function createTask(projectId: number, title: string): Task {
  return {
    id: generateTaskId(),
    project_id: projectId,  // ⚠️ Now required
    title,
    status: "pending",
    timestamp: Date.now()
  };
}
```

## Architecture Alignment

These TypeScript types now correctly reflect the backend architecture:

| Concept | Backend (Python) | Frontend (TypeScript) | Aligned? |
|---------|------------------|----------------------|----------|
| Agent creation | No project_id parameter | Agent interface has no project_id | ✅ Yes |
| Agent-Project relationship | Many-to-many (project_agents table) | AgentAssignment type | ✅ Yes |
| Project context | Derived from task.project_id | Task has project_id field | ✅ Yes |
| Assignment tracking | assigned_at, unassigned_at, is_active | Same fields in AgentAssignment | ✅ Yes |
| Agent roles | role field in project_agents | role field in AgentAssignment | ✅ Yes |

## Success Criteria

- ✅ All new types compile without TypeScript errors
- ✅ Types match backend Pydantic models exactly
- ✅ API client provides type-safe access to all endpoints
- ✅ Breaking changes clearly documented
- ✅ Migration examples provided
- ⏳ Unit tests pass (pending implementation)
- ⏳ Integration tests pass (pending implementation)
- ⏳ No regressions in existing features (pending verification)

## Next Steps

1. **Immediate:** Update reducer and WebSocket handlers to include project_id in tasks
2. **Short-term:** Add comprehensive unit tests for new types
3. **Medium-term:** Create UI components for agent assignment management
4. **Long-term:** Add visual indicators showing agent-project relationships in Dashboard

## Related Documentation

- Backend refactoring: `/home/frankbria/projects/codeframe/AGENT_REFACTORING_SUMMARY.md`
- API endpoints: `/home/frankbria/projects/codeframe/codeframe/ui/server.py`
- Database schema: `/home/frankbria/projects/codeframe/codeframe/persistence/database.py`
