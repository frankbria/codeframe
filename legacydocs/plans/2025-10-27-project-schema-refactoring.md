# Project Schema Refactoring Design

**Date**: 2025-10-27
**Status**: Approved
**Scope**: Refactor project creation to be flexible, support both deployment modes, enable future discovery features

---

## Problem Statement

The current project creation flow is too restrictive:

1. **Forces single language selection** - Doesn't work for monorepos (e.g., Python backend + TypeScript frontend)
2. **Asks wrong questions upfront** - Requires `project_type` enum instead of discovering tech stack
3. **No deployment mode support** - Schema doesn't distinguish between self-hosted vs hosted SaaS
4. **Missing discovery phase** - Goes directly from creation to dashboard, no onboarding flow
5. **No PRD generation** - System doesn't know what to build

## Design Principles

1. **Minimal upfront requirements** - Only ask for name + description
2. **Progressive discovery** - Learn tech stack through Socratic questioning
3. **Deployment mode aware** - Schema supports both self-hosted and hosted SaaS
4. **Git-first foundation** - All projects use git from the start
5. **Sandbox isolation** - Always work in managed workspace, regardless of source

---

## New Project Schema

```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,  -- NEW: Required context for AI understanding

    -- Source tracking (optional, can be set during setup or later)
    source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')) DEFAULT 'empty',
    source_location TEXT,  -- Git URL, local filesystem path, or upload filename
    source_branch TEXT DEFAULT 'main',

    -- Managed workspace (always local to running instance)
    workspace_path TEXT NOT NULL,  -- Auto-generated: {WORKSPACE_ROOT}/{project_id}

    -- Git tracking (foundation for all projects)
    git_initialized BOOLEAN DEFAULT FALSE,
    current_commit TEXT,

    -- Workflow state
    status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
    phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config JSON  -- Discovery state, PRD versioning, tech stack, conventions
)
```

### Key Changes

**Removed**:
- `project_type` enum (too restrictive for monorepos)
- `root_path` (replaced by `workspace_path` with clearer semantics)

**Added**:
- `description` (required) - Gives AI context about project purpose
- `source_type` + `source_location` (optional) - Flexible source handling
- `workspace_path` (required) - Managed sandbox where code lives
- `git_initialized` + `current_commit` - Git tracking from the start

---

## Source Types

### `git_remote`
- **Use case**: Clone from GitHub, GitLab, Bitbucket, etc.
- **Source location**: Git URL (e.g., `https://github.com/user/repo.git`)
- **Both modes**: ✅ Self-hosted, ✅ Hosted SaaS
- **Behavior**: `git clone {source_location} {workspace_path}`

### `local_path`
- **Use case**: Copy existing project from user's filesystem
- **Source location**: Absolute path (e.g., `/home/user/myproject`)
- **Deployment**: ✅ Self-hosted only (🚫 Hosted SaaS - security risk)
- **Behavior**: `cp -r {source_location} {workspace_path}`

### `upload`
- **Use case**: User uploads zip/tar file via web UI
- **Source location**: Upload filename (stored temporarily)
- **Both modes**: ✅ Self-hosted, ✅ Hosted SaaS
- **Behavior**: Extract to `workspace_path`, then `git init`

### `empty`
- **Use case**: Start fresh, no existing code
- **Source location**: NULL
- **Both modes**: ✅ Self-hosted, ✅ Hosted SaaS
- **Behavior**: `mkdir {workspace_path} && git init {workspace_path}`

---

## API Changes

### New Request Model

```python
class SourceType(str, Enum):
    GIT_REMOTE = "git_remote"
    LOCAL_PATH = "local_path"
    UPLOAD = "upload"
    EMPTY = "empty"

class ProjectCreateRequest(BaseModel):
    # Required
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)

    # Optional - source configuration
    source_type: Optional[SourceType] = Field(default=SourceType.EMPTY)
    source_location: Optional[str] = None
    source_branch: Optional[str] = Field(default="main")

    # Optional - workspace naming (auto-generated if not provided)
    workspace_name: Optional[str] = None

    @model_validator(mode='after')
    def validate_source(self):
        if self.source_type != SourceType.EMPTY and not self.source_location:
            raise ValueError(f"source_location required when source_type={self.source_type}")
        return self
```

### Deployment-Mode Validation

```python
@app.post("/api/projects")
async def create_project(request: ProjectCreateRequest):
    # Security: Hosted mode cannot access user's local filesystem
    if is_hosted_mode() and request.source_type == SourceType.LOCAL_PATH:
        raise HTTPException(
            status_code=403,
            detail="source_type='local_path' not available in hosted mode"
        )

    # Generate workspace path (isolated sandbox)
    project_id = db.create_project(...)
    workspace_path = Path(WORKSPACE_ROOT) / str(project_id)

    # Initialize workspace based on source type
    if request.source_type == SourceType.GIT_REMOTE:
        git.clone(request.source_location, workspace_path, branch=request.source_branch)
    elif request.source_type == SourceType.LOCAL_PATH:
        shutil.copytree(request.source_location, workspace_path)
    elif request.source_type == SourceType.UPLOAD:
        # Handled via separate upload endpoint
        os.makedirs(workspace_path)
    else:  # empty
        os.makedirs(workspace_path)
        git.init(workspace_path)

    # Update workspace_path and git status
    db.update_project(project_id, {
        "workspace_path": str(workspace_path),
        "git_initialized": True
    })

    return ProjectResponse(...)
```

---

## Config JSON Structure

The `config` JSON field stores discovery state, PRD versioning, and tech stack:

```json
{
  "discovery": {
    "completed": false,
    "tech_stack": {
      "languages": ["python", "typescript"],
      "frameworks": ["fastapi", "react", "nextjs"],
      "package_managers": ["pip", "npm"],
      "structure": "monorepo"
    },
    "conventions": {
      "backend_path": "backend/",
      "frontend_path": "web-ui/",
      "test_framework": "pytest",
      "test_command": "pytest",
      "build_command": "npm run build"
    }
  },
  "prd": {
    "current_version": "v1",
    "last_generated": "2025-10-27T19:30:00Z",
    "generation_mode": "initial"
  }
}
```

### Discovery State

**Purpose**: Store what the AI learned about the project during setup/onboarding.

**Population**:
- Initial setup: Socratic Q&A fills in tech_stack and conventions
- Re-discovery: Can be triggered manually to update if project structure changes

**Usage**:
- Agent selection (choose frontend vs backend agent based on file location)
- Command execution (run correct test/build commands)
- PRD generation (understand project context)

### PRD Versioning

**Purpose**: Track PRD evolution over time.

**Versions**:
- `v1` - Initial PRD from project setup
- `v2+` - Regenerated/edited PRDs
- `current` - Pointer to active version

**Storage**: PRD content stored in `memory` table with `category='prd', key='v1'|'v2'|'current'`

---

## Project Lifecycle & Phase Gates

### Phase: Discovery

**State**: `phase='discovery', status='init'`

**Purpose**: Onboard the project, understand structure, generate initial PRD

**Workflow**:
1. Project created with minimal info
2. Socratic Q&A conversation:
   - "What are you building?" (PRD goals)
   - "What tech stack?" (Discovery tech_stack)
   - "What's the structure?" (Discovery conventions)
3. AI generates initial PRD from conversation
4. Populates `config.discovery` and `config.prd`
5. Transitions to Planning

**Dashboard behavior**: Show setup chat interface, hide task boards until PRD generated

### Phase: Planning

**State**: `phase='planning', status='planning'`

**Purpose**: Review PRD, generate tasks, prepare for execution

**Workflow**:
1. Display generated PRD
2. Allow editing/refinement
3. Generate tasks from PRD
4. User approves and starts execution
5. Transitions to Active

**Dashboard behavior**: Show PRD, task list, allow editing before start

### Phase: Active

**State**: `phase='active', status='running'`

**Purpose**: Execute tasks, build features

**Workflow**:
1. Multi-agent coordination executes tasks
2. Progress tracked in real-time
3. User can add new tasks/issues
4. Transitions to Review when scope complete

**Dashboard behavior**: Full dashboard - tasks, agents, progress, activity feed

### Phase: Review

**State**: `phase='review', status='completed'`

**Purpose**: Final review before marking complete

**Workflow**:
1. All tasks complete
2. Review generated code
3. Mark project complete or add follow-up work

**Dashboard behavior**: Summary view, analytics, option to reopen

### Phase: Complete

**State**: `phase='complete', status='completed'`

**Purpose**: Project archived/finished

**Dashboard behavior**: Read-only view, historical analytics

---

## Discovery + PRD Relationship

### For New Projects (90% overlap)

**Project Setup Flow** (combined Discovery + PRD):
```
1. Create project (name, description, source)
   ↓
2. Socratic conversation handles BOTH:
   - Discovery questions: "What's your tech stack? Monorepo structure?"
   - Requirements questions: "What features? Who are the users?"
   ↓
3. Generate initial PRD from conversation
   ↓
4. Populate config.discovery from same conversation
   ↓
5. Transition to Planning phase
```

**API**: `POST /api/projects/{id}/setup` - Full onboarding flow

### For Existing Projects (separate)

**PRD Edit/Regenerate Flow** (skips Discovery):
```
1. Project exists (discovery already complete)
   ↓
2. Trigger PRD regeneration
   ↓
3. Use existing config.discovery context
   ↓
4. Ask ONLY requirements questions (skip tech stack)
   ↓
5. Generate PRD v2
   ↓
6. Update config.prd.current_version
```

**API**: `POST /api/projects/{id}/prd/regenerate` - Skip discovery, use existing context

---

## Migration Strategy

### Existing Projects

**Decision**: Drop all existing test projects and start fresh.

**Rationale**:
- Current projects are test data
- Schema changes are significant
- Clean start easier than complex migration
- No production data to preserve

### Migration Steps

1. **Backup** (if any projects worth keeping):
   ```bash
   sqlite3 .codeframe/state.db ".dump projects" > projects_backup.sql
   ```

2. **Drop old schema**:
   ```sql
   DROP TABLE IF EXISTS projects;
   ```

3. **Create new schema** (run updated `database.py` initialization)

4. **Update API models**:
   - Remove `ProjectType` enum
   - Update `ProjectCreateRequest` model
   - Add deployment-mode validation

5. **Test**:
   - Create project via API with new schema
   - Verify workspace creation
   - Test all source types

---

## Implementation Checklist

### Phase 1: Schema & Models
- [ ] Update `projects` table schema in `database.py`
- [ ] Remove `ProjectType` enum from `models.py`
- [ ] Create new `ProjectCreateRequest` model
- [ ] Add `SourceType` enum
- [ ] Update `ProjectResponse` model

### Phase 2: API Endpoints
- [ ] Update `POST /api/projects` endpoint
- [ ] Add deployment-mode detection
- [ ] Add source-type validation
- [ ] Implement workspace creation logic
- [ ] Add git initialization for each source type

### Phase 3: Workspace Management
- [ ] Create workspace root directory structure
- [ ] Implement git clone for `git_remote`
- [ ] Implement copy for `local_path`
- [ ] Implement extract for `upload`
- [ ] Implement init for `empty`

### Phase 4: Discovery & PRD (Future)
- [ ] Design Socratic Q&A flow
- [ ] Build discovery chat interface
- [ ] Implement PRD generation
- [ ] Add PRD versioning to memory table
- [ ] Create setup endpoint
- [ ] Create PRD regenerate endpoint

### Phase 5: Dashboard Updates
- [ ] Add phase-based UI switching
- [ ] Show setup banner in discovery phase
- [ ] Implement discovery chat UI (future)
- [ ] Add PRD view/edit UI (future)

---

## Security Considerations

### Hosted SaaS Mode

**Restrictions**:
- ✅ `git_remote` - Safe (only network access)
- ✅ `upload` - Safe (user-provided files, sandboxed)
- ✅ `empty` - Safe (creates new directory)
- 🚫 `local_path` - **BLOCKED** (filesystem access risk)

**Validation**: API rejects `source_type='local_path'` with 403 Forbidden

### Self-Hosted Mode

**Permissions**: All source types allowed

**User responsibility**: Self-hosted users responsible for filesystem security

### Workspace Isolation

**All modes**: Code always copied/cloned into managed `workspace_path`

**Benefits**:
- Original source unchanged (if `local_path`)
- Isolated from other projects
- Safe to delete/recreate
- Git tracking independent of source

---

## Future Enhancements

### Discovery Agent
- Automatic tech stack detection via file analysis
- Framework-specific recommendations
- Code convention learning
- Best practices suggestions

### PRD Templates
- Pre-built PRD templates by project type
- Industry-specific templates (SaaS, mobile app, API service)
- Custom template creation

### Multi-Source Projects
- Link multiple git repos into one project
- Submodule support
- Monorepo workspace mapping

### Source Sync
- Keep workspace in sync with source
- Git pull updates
- Conflict resolution
- Change notifications

---

## Success Metrics

### Schema Flexibility
- ✅ Handles monorepos (Python + TypeScript)
- ✅ Works without knowing language upfront
- ✅ Supports both deployment modes
- ✅ Enables progressive discovery

### User Experience
- Minimal friction at project creation (2 required fields)
- Natural discovery through conversation
- Clear phase transitions
- Flexible source options

### Future-Proof
- Discovery feature buildable on this schema
- PRD versioning supported
- Tech stack evolution tracked
- Backward compatible additions possible

---

## References

- Current schema: `codeframe/persistence/database.py` (lines 47-54)
- Current API models: `codeframe/ui/models.py` (lines 11-40)
- Sprint 4 multi-agent coordination: Uses `depends_on` for task dependencies
- Memory table: Already supports `category='prd'` for PRD storage

---

**End of Design Document**
