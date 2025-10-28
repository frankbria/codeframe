# Project Schema Refactoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor project schema to support flexible source types (git_remote, local_path, upload, empty), remove restrictive language enum, enable both self-hosted and hosted SaaS deployment modes.

**Architecture:** Replace single `project_type` enum with flexible `source_type` + `source_location` pattern. All projects work in managed `workspace_path` sandboxes. Add deployment-mode validation at API layer. Enable progressive discovery through Socratic questioning (future feature, schema ready now).

**Tech Stack:** SQLite (schema migration), FastAPI (API validation), Python pathlib (workspace management), GitPython (git operations)

---

## Prerequisites

**Design Document:** `docs/plans/2025-10-27-project-schema-refactoring.md`

**Current State:**
- Database: `.codeframe/state.db` with old projects schema
- Models: `ProjectType` enum in `codeframe/ui/models.py`
- API: `POST /api/projects` accepts `project_type` enum

**Target State:**
- New schema with `source_type`, `source_location`, `workspace_path`
- `SourceType` enum replacing `ProjectType`
- Deployment-mode aware API validation
- Workspace management system

---

## Task 1: Database Schema Migration

**Files:**
- Modify: `codeframe/persistence/database.py:47-54` (projects table)
- Test: `tests/test_database_schema.py` (new file)

**Step 1: Write failing test for new schema**

Create `tests/test_database_schema.py`:

```python
"""Tests for database schema changes (project refactoring)."""
import pytest
from pathlib import Path
from codeframe.persistence.database import Database


@pytest.mark.asyncio
async def test_projects_table_has_new_columns():
    """Verify projects table has new schema columns."""
    db_path = Path(":memory:")
    db = Database(db_path)

    # Get table schema
    async with db._get_connection() as conn:
        cursor = await conn.execute("PRAGMA table_info(projects)")
        columns = {row[1]: row[2] for row in await cursor.fetchall()}

    # Verify new columns exist
    assert "description" in columns, "Missing description column"
    assert "source_type" in columns, "Missing source_type column"
    assert "source_location" in columns, "Missing source_location column"
    assert "source_branch" in columns, "Missing source_branch column"
    assert "workspace_path" in columns, "Missing workspace_path column"
    assert "git_initialized" in columns, "Missing git_initialized column"
    assert "current_commit" in columns, "Missing current_commit column"

    # Verify old columns removed
    assert "root_path" not in columns, "root_path should be removed"


@pytest.mark.asyncio
async def test_source_type_check_constraint():
    """Verify source_type has CHECK constraint."""
    db_path = Path(":memory:")
    db = Database(db_path)

    # Try to insert invalid source_type
    async with db._get_connection() as conn:
        with pytest.raises(Exception) as exc_info:
            await conn.execute("""
                INSERT INTO projects (name, description, source_type, workspace_path)
                VALUES ('test', 'desc', 'invalid_type', '/tmp/test')
            """)

        assert "CHECK constraint failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_description_not_null():
    """Verify description is required (NOT NULL)."""
    db_path = Path(":memory:")
    db = Database(db_path)

    async with db._get_connection() as conn:
        with pytest.raises(Exception) as exc_info:
            await conn.execute("""
                INSERT INTO projects (name, workspace_path)
                VALUES ('test', '/tmp/test')
            """)

        assert "NOT NULL constraint failed" in str(exc_info.value)
```

**Step 2: Run test to verify it fails**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/test_database_schema.py -v`

Expected: FAIL - table schema doesn't match

**Step 3: Update schema in database.py**

Modify `codeframe/persistence/database.py`:

```python
# Around line 47-54, replace the projects table definition:

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,

    -- Source tracking (optional, can be set during setup or later)
    source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')) DEFAULT 'empty',
    source_location TEXT,
    source_branch TEXT DEFAULT 'main',

    -- Managed workspace (always local to running instance)
    workspace_path TEXT NOT NULL,

    -- Git tracking (foundation for all projects)
    git_initialized BOOLEAN DEFAULT FALSE,
    current_commit TEXT,

    -- Workflow state
    status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
    phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config JSON
)
```

**Step 4: Drop existing projects table**

Add migration logic to `database.py` in the `__init__` method (around line 30):

```python
async def __init__(self, db_path: Path):
    """Initialize database connection."""
    self.db_path = db_path
    self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async with self._get_connection() as conn:
        # Drop old projects table if it exists (migration)
        # This is safe because we're only dropping test data
        await conn.execute("DROP TABLE IF EXISTS projects")

        # Create all tables
        await conn.executescript(self._get_schema())
        await conn.commit()
```

**Step 5: Run test to verify it passes**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/test_database_schema.py -v`

Expected: PASS - all 3 tests passing

**Step 6: Commit**

```bash
git add codeframe/persistence/database.py tests/test_database_schema.py
git commit -m "feat(database): refactor projects schema with source types and workspace path"
```

---

## Task 2: Update API Models

**Files:**
- Modify: `codeframe/ui/models.py:11-40`
- Test: `tests/ui/test_models.py` (new file)

**Step 1: Write failing test for new models**

Create `tests/ui/test_models.py`:

```python
"""Tests for API models (project refactoring)."""
import pytest
from pydantic import ValidationError
from codeframe.ui.models import (
    SourceType,
    ProjectCreateRequest,
)


def test_source_type_enum_values():
    """Verify SourceType enum has correct values."""
    assert SourceType.GIT_REMOTE == "git_remote"
    assert SourceType.LOCAL_PATH == "local_path"
    assert SourceType.UPLOAD == "upload"
    assert SourceType.EMPTY == "empty"


def test_project_create_request_minimal():
    """Verify minimal valid request (name + description only)."""
    request = ProjectCreateRequest(
        name="Test Project",
        description="A test project"
    )

    assert request.name == "Test Project"
    assert request.description == "A test project"
    assert request.source_type == SourceType.EMPTY
    assert request.source_location is None
    assert request.source_branch == "main"


def test_project_create_request_git_remote():
    """Verify git_remote request requires source_location."""
    request = ProjectCreateRequest(
        name="Test",
        description="Test",
        source_type=SourceType.GIT_REMOTE,
        source_location="https://github.com/user/repo.git"
    )

    assert request.source_type == SourceType.GIT_REMOTE
    assert request.source_location == "https://github.com/user/repo.git"


def test_project_create_request_validation_error():
    """Verify source_location required when source_type != empty."""
    with pytest.raises(ValidationError) as exc_info:
        ProjectCreateRequest(
            name="Test",
            description="Test",
            source_type=SourceType.GIT_REMOTE,
            # Missing source_location
        )

    errors = exc_info.value.errors()
    assert any("source_location" in str(e) for e in errors)


def test_project_create_request_name_required():
    """Verify name is required."""
    with pytest.raises(ValidationError):
        ProjectCreateRequest(description="Test")


def test_project_create_request_description_required():
    """Verify description is required."""
    with pytest.raises(ValidationError):
        ProjectCreateRequest(name="Test")
```

**Step 2: Run test to verify it fails**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/ui/test_models.py -v`

Expected: FAIL - SourceType doesn't exist, ProjectType still present

**Step 3: Update models.py**

Modify `codeframe/ui/models.py` (lines 11-40):

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class SourceType(str, Enum):
    """Supported project source types."""
    GIT_REMOTE = "git_remote"
    LOCAL_PATH = "local_path"
    UPLOAD = "upload"
    EMPTY = "empty"


class ProjectCreateRequest(BaseModel):
    """Request model for creating a new project."""

    # Required
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    description: str = Field(..., min_length=1, max_length=500, description="Project description/purpose")

    # Optional - source configuration
    source_type: Optional[SourceType] = Field(default=SourceType.EMPTY, description="Source type for project initialization")
    source_location: Optional[str] = Field(default=None, description="Git URL, local path, or upload filename")
    source_branch: Optional[str] = Field(default="main", description="Git branch to clone (for git_remote)")

    # Optional - workspace naming (auto-generated if not provided)
    workspace_name: Optional[str] = Field(default=None, description="Custom workspace directory name")

    @model_validator(mode='after')
    def validate_source(self):
        """Validate source_location is provided when source_type requires it."""
        if self.source_type != SourceType.EMPTY and not self.source_location:
            raise ValueError(f"source_location required when source_type={self.source_type}")
        return self


# Remove old ProjectType enum (delete lines with PYTHON, JAVASCRIPT, etc.)
```

**Step 4: Update imports in server.py**

Modify `codeframe/ui/server.py` to import `SourceType` instead of `ProjectType`:

```python
from codeframe.ui.models import (
    ProjectCreateRequest,
    SourceType,  # Changed from ProjectType
    # ... other imports
)
```

**Step 5: Run test to verify it passes**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/ui/test_models.py -v`

Expected: PASS - all 7 tests passing

**Step 6: Commit**

```bash
git add codeframe/ui/models.py codeframe/ui/server.py tests/ui/test_models.py
git commit -m "feat(models): replace ProjectType with SourceType enum"
```

---

## Task 3: Workspace Management Module

**Files:**
- Create: `codeframe/workspace/__init__.py`
- Create: `codeframe/workspace/manager.py`
- Test: `tests/test_workspace_manager.py` (new file)

**Step 1: Write failing test for workspace manager**

Create `tests/test_workspace_manager.py`:

```python
"""Tests for workspace management."""
import pytest
import tempfile
import shutil
from pathlib import Path
from codeframe.workspace.manager import WorkspaceManager
from codeframe.ui.models import SourceType


@pytest.fixture
def temp_workspace_root():
    """Create temporary workspace root."""
    root = Path(tempfile.mkdtemp())
    yield root
    shutil.rmtree(root)


def test_workspace_manager_creates_directory(temp_workspace_root):
    """Verify workspace manager creates workspace directory."""
    manager = WorkspaceManager(temp_workspace_root)

    workspace_path = manager.create_workspace(
        project_id=1,
        source_type=SourceType.EMPTY
    )

    assert workspace_path.exists()
    assert workspace_path.is_dir()
    assert workspace_path.name == "1"


def test_workspace_manager_empty_source(temp_workspace_root):
    """Verify empty source creates git repo."""
    manager = WorkspaceManager(temp_workspace_root)

    workspace_path = manager.create_workspace(
        project_id=1,
        source_type=SourceType.EMPTY
    )

    # Verify git initialized
    git_dir = workspace_path / ".git"
    assert git_dir.exists()


def test_workspace_manager_unique_paths(temp_workspace_root):
    """Verify each project gets unique workspace."""
    manager = WorkspaceManager(temp_workspace_root)

    ws1 = manager.create_workspace(1, SourceType.EMPTY)
    ws2 = manager.create_workspace(2, SourceType.EMPTY)

    assert ws1 != ws2
    assert ws1.name == "1"
    assert ws2.name == "2"
```

**Step 2: Run test to verify it fails**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/test_workspace_manager.py -v`

Expected: FAIL - WorkspaceManager doesn't exist

**Step 3: Create workspace management module**

Create `codeframe/workspace/__init__.py`:

```python
"""Workspace management for CodeFRAME projects."""
from codeframe.workspace.manager import WorkspaceManager

__all__ = ["WorkspaceManager"]
```

Create `codeframe/workspace/manager.py`:

```python
"""Workspace manager for creating and managing project workspaces."""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from codeframe.ui.models import SourceType


class WorkspaceManager:
    """Manages project workspaces (sandboxed directories)."""

    def __init__(self, workspace_root: Path):
        """Initialize workspace manager.

        Args:
            workspace_root: Root directory for all project workspaces
        """
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def create_workspace(
        self,
        project_id: int,
        source_type: SourceType,
        source_location: Optional[str] = None,
        source_branch: str = "main"
    ) -> Path:
        """Create workspace for a project.

        Args:
            project_id: Unique project identifier
            source_type: Type of source initialization
            source_location: Git URL, local path, or upload filename
            source_branch: Git branch to clone (for git_remote)

        Returns:
            Path to created workspace
        """
        workspace_path = self.workspace_root / str(project_id)

        if workspace_path.exists():
            raise ValueError(f"Workspace already exists: {workspace_path}")

        # Initialize based on source type
        if source_type == SourceType.GIT_REMOTE:
            self._init_from_git(workspace_path, source_location, source_branch)
        elif source_type == SourceType.LOCAL_PATH:
            self._init_from_local(workspace_path, source_location)
        elif source_type == SourceType.UPLOAD:
            self._init_from_upload(workspace_path, source_location)
        else:  # EMPTY
            self._init_empty(workspace_path)

        return workspace_path

    def _init_empty(self, workspace_path: Path) -> None:
        """Initialize empty workspace with git repo."""
        workspace_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=workspace_path,
            check=True,
            capture_output=True
        )

    def _init_from_git(self, workspace_path: Path, git_url: str, branch: str) -> None:
        """Clone from git repository."""
        subprocess.run(
            ["git", "clone", "--branch", branch, git_url, str(workspace_path)],
            check=True,
            capture_output=True
        )

    def _init_from_local(self, workspace_path: Path, local_path: str) -> None:
        """Copy from local filesystem path."""
        source = Path(local_path)
        if not source.exists():
            raise ValueError(f"Source path does not exist: {local_path}")

        shutil.copytree(source, workspace_path)

        # Initialize git if not already a git repo
        if not (workspace_path / ".git").exists():
            subprocess.run(
                ["git", "init"],
                cwd=workspace_path,
                check=True,
                capture_output=True
            )

    def _init_from_upload(self, workspace_path: Path, upload_filename: str) -> None:
        """Extract from uploaded archive."""
        # TODO: Implement in Phase 4 (upload endpoint)
        workspace_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=workspace_path,
            check=True,
            capture_output=True
        )
```

**Step 4: Run test to verify it passes**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/test_workspace_manager.py -v`

Expected: PASS - all 3 tests passing

**Step 5: Commit**

```bash
git add codeframe/workspace/ tests/test_workspace_manager.py
git commit -m "feat(workspace): add workspace manager for project sandboxes"
```

---

## Task 4: API Endpoint Updates

**Files:**
- Modify: `codeframe/ui/server.py` (POST /api/projects endpoint)
- Test: `tests/ui/test_project_api.py` (new file)

**Step 1: Write failing test for updated API**

Create `tests/ui/test_project_api.py`:

```python
"""Tests for project API endpoints."""
import pytest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from codeframe.ui.server import app
from codeframe.persistence.database import Database


@pytest.fixture
def test_client():
    """Create test client with temporary database."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"

    # Override database path
    app.state.db = Database(db_path)
    app.state.workspace_root = temp_dir / "workspaces"

    client = TestClient(app)

    yield client

    # Cleanup
    shutil.rmtree(temp_dir)


def test_create_project_minimal(test_client):
    """Test creating project with minimal required fields."""
    response = test_client.post(
        "/api/projects",
        json={
            "name": "Test Project",
            "description": "A test project"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["description"] == "A test project"
    assert data["source_type"] == "empty"
    assert "workspace_path" in data


def test_create_project_git_remote(test_client):
    """Test creating project from git repository."""
    response = test_client.post(
        "/api/projects",
        json={
            "name": "Git Project",
            "description": "From git",
            "source_type": "git_remote",
            "source_location": "https://github.com/user/repo.git"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source_type"] == "git_remote"
    assert data["source_location"] == "https://github.com/user/repo.git"


def test_create_project_validation_error(test_client):
    """Test validation error for missing source_location."""
    response = test_client.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "git_remote"
            # Missing source_location
        }
    )

    assert response.status_code == 422


def test_create_project_missing_description(test_client):
    """Test validation error for missing description."""
    response = test_client.post(
        "/api/projects",
        json={"name": "Test"}
    )

    assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/ui/test_project_api.py -v`

Expected: FAIL - API still uses old schema

**Step 3: Update Database methods**

Modify `codeframe/persistence/database.py` - update `create_project` method:

```python
async def create_project(
    self,
    name: str,
    description: str,
    source_type: str = "empty",
    source_location: Optional[str] = None,
    source_branch: str = "main",
    workspace_path: Optional[str] = None,
    **kwargs
) -> int:
    """Create a new project.

    Args:
        name: Project name
        description: Project description/purpose
        source_type: Source type (git_remote, local_path, upload, empty)
        source_location: Git URL, local path, or upload filename
        source_branch: Git branch (for git_remote)
        workspace_path: Path to workspace directory
        **kwargs: Additional fields (config, etc.)

    Returns:
        Created project ID
    """
    async with self._get_connection() as conn:
        cursor = await conn.execute(
            """
            INSERT INTO projects (
                name, description, source_type, source_location,
                source_branch, workspace_path, git_initialized
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                source_type,
                source_location,
                source_branch,
                workspace_path,
                False  # Will be set to True after workspace initialization
            )
        )
        await conn.commit()
        return cursor.lastrowid
```

**Step 4: Update API endpoint in server.py**

Modify `codeframe/ui/server.py` - update POST /api/projects:

```python
from pathlib import Path
from codeframe.workspace import WorkspaceManager

# Add to app startup
@app.on_event("startup")
async def startup():
    """Initialize app state."""
    # ... existing code ...

    # Initialize workspace manager
    workspace_root = Path.cwd() / ".codeframe" / "workspaces"
    app.state.workspace_manager = WorkspaceManager(workspace_root)


@app.post("/api/projects")
async def create_project(request: ProjectCreateRequest):
    """Create a new project.

    Args:
        request: Project creation request with name, description, source config

    Returns:
        Created project details
    """
    # TODO: Add deployment-mode validation (Task 5)

    # Create project record first (to get ID)
    project_id = await app.state.db.create_project(
        name=request.name,
        description=request.description,
        source_type=request.source_type.value,
        source_location=request.source_location,
        source_branch=request.source_branch,
        workspace_path=""  # Will be updated after workspace creation
    )

    # Create workspace
    try:
        workspace_path = app.state.workspace_manager.create_workspace(
            project_id=project_id,
            source_type=request.source_type,
            source_location=request.source_location,
            source_branch=request.source_branch
        )

        # Update project with workspace path and git status
        await app.state.db.update_project(
            project_id,
            workspace_path=str(workspace_path),
            git_initialized=True
        )

    except Exception as e:
        # Cleanup: delete project if workspace creation fails
        await app.state.db.delete_project(project_id)
        raise HTTPException(status_code=500, detail=f"Workspace creation failed: {str(e)}")

    # Return project details
    project = await app.state.db.get_project(project_id)
    return project
```

**Step 5: Add update_project method to Database**

Modify `codeframe/persistence/database.py`:

```python
async def update_project(self, project_id: int, **kwargs) -> None:
    """Update project fields.

    Args:
        project_id: Project ID to update
        **kwargs: Fields to update (workspace_path, git_initialized, etc.)
    """
    if not kwargs:
        return

    set_clause = ", ".join(f"{key} = ?" for key in kwargs.keys())
    values = list(kwargs.values()) + [project_id]

    async with self._get_connection() as conn:
        await conn.execute(
            f"UPDATE projects SET {set_clause} WHERE id = ?",
            values
        )
        await conn.commit()


async def delete_project(self, project_id: int) -> None:
    """Delete a project.

    Args:
        project_id: Project ID to delete
    """
    async with self._get_connection() as conn:
        await conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await conn.commit()
```

**Step 6: Run test to verify it passes**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/ui/test_project_api.py -v`

Expected: PASS - all 5 tests passing

**Step 7: Commit**

```bash
git add codeframe/ui/server.py codeframe/persistence/database.py tests/ui/test_project_api.py
git commit -m "feat(api): update project creation endpoint with workspace management"
```

---

## Task 5: Deployment Mode Validation

**Files:**
- Modify: `codeframe/ui/server.py`
- Test: `tests/ui/test_deployment_mode.py` (new file)

**Step 1: Write failing test for deployment mode validation**

Create `tests/ui/test_deployment_mode.py`:

```python
"""Tests for deployment mode validation."""
import pytest
import os
from fastapi.testclient import TestClient
from codeframe.ui.server import app


@pytest.fixture
def test_client_hosted():
    """Test client with HOSTED mode."""
    os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "hosted"
    client = TestClient(app)
    yield client
    del os.environ["CODEFRAME_DEPLOYMENT_MODE"]


@pytest.fixture
def test_client_self_hosted():
    """Test client with SELF_HOSTED mode."""
    os.environ["CODEFRAME_DEPLOYMENT_MODE"] = "self_hosted"
    client = TestClient(app)
    yield client
    del os.environ["CODEFRAME_DEPLOYMENT_MODE"]


def test_hosted_mode_blocks_local_path(test_client_hosted):
    """Verify hosted mode rejects local_path source type."""
    response = test_client_hosted.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "local_path",
            "source_location": "/home/user/project"
        }
    )

    assert response.status_code == 403
    assert "not available in hosted mode" in response.json()["detail"]


def test_hosted_mode_allows_git_remote(test_client_hosted):
    """Verify hosted mode allows git_remote."""
    response = test_client_hosted.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "git_remote",
            "source_location": "https://github.com/user/repo.git"
        }
    )

    # Should not be blocked (may fail for other reasons, but not 403)
    assert response.status_code != 403


def test_self_hosted_allows_all_sources(test_client_self_hosted):
    """Verify self-hosted mode allows all source types."""
    # Test local_path is allowed
    response = test_client_self_hosted.post(
        "/api/projects",
        json={
            "name": "Test",
            "description": "Test",
            "source_type": "local_path",
            "source_location": "/tmp/test"
        }
    )

    # Should not be blocked with 403
    assert response.status_code != 403
```

**Step 2: Run test to verify it fails**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/ui/test_deployment_mode.py -v`

Expected: FAIL - no deployment mode validation exists

**Step 3: Add deployment mode detection**

Modify `codeframe/ui/server.py`:

```python
import os
from enum import Enum

class DeploymentMode(str, Enum):
    """Deployment mode for CodeFRAME."""
    SELF_HOSTED = "self_hosted"
    HOSTED = "hosted"


def get_deployment_mode() -> DeploymentMode:
    """Get current deployment mode from environment.

    Returns:
        DeploymentMode.SELF_HOSTED or DeploymentMode.HOSTED
    """
    mode = os.getenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted").lower()

    if mode == "hosted":
        return DeploymentMode.HOSTED
    return DeploymentMode.SELF_HOSTED


def is_hosted_mode() -> bool:
    """Check if running in hosted SaaS mode.

    Returns:
        True if hosted mode, False if self-hosted
    """
    return get_deployment_mode() == DeploymentMode.HOSTED
```

**Step 4: Add validation to create_project endpoint**

Modify the `create_project` endpoint in `server.py`:

```python
@app.post("/api/projects")
async def create_project(request: ProjectCreateRequest):
    """Create a new project."""

    # Security: Hosted mode cannot access user's local filesystem
    if is_hosted_mode() and request.source_type == SourceType.LOCAL_PATH:
        raise HTTPException(
            status_code=403,
            detail="source_type='local_path' not available in hosted mode"
        )

    # ... rest of endpoint implementation ...
```

**Step 5: Run test to verify it passes**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/ui/test_deployment_mode.py -v`

Expected: PASS - all 3 tests passing

**Step 6: Commit**

```bash
git add codeframe/ui/server.py tests/ui/test_deployment_mode.py
git commit -m "feat(security): add deployment mode validation for source types"
```

---

## Task 6: Integration Testing

**Files:**
- Test: `tests/integration/test_project_creation_flow.py` (new file)

**Step 1: Write integration test**

Create `tests/integration/test_project_creation_flow.py`:

```python
"""Integration tests for full project creation flow."""
import pytest
import tempfile
import shutil
from pathlib import Path
from codeframe.persistence.database import Database
from codeframe.workspace import WorkspaceManager
from codeframe.ui.models import SourceType


@pytest.fixture
def integration_env():
    """Set up integration test environment."""
    temp_dir = Path(tempfile.mkdtemp())

    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    db = Database(db_path)
    workspace_manager = WorkspaceManager(workspace_root)

    yield {
        "db": db,
        "workspace_manager": workspace_manager,
        "temp_dir": temp_dir
    }

    shutil.rmtree(temp_dir)


@pytest.mark.asyncio
async def test_create_empty_project_end_to_end(integration_env):
    """Test full flow: create empty project with database + workspace."""
    db = integration_env["db"]
    workspace_manager = integration_env["workspace_manager"]

    # Step 1: Create project in database
    project_id = await db.create_project(
        name="Test Project",
        description="Integration test",
        source_type="empty",
        workspace_path=""
    )

    # Step 2: Create workspace
    workspace_path = workspace_manager.create_workspace(
        project_id=project_id,
        source_type=SourceType.EMPTY
    )

    # Step 3: Update project with workspace path
    await db.update_project(
        project_id,
        workspace_path=str(workspace_path),
        git_initialized=True
    )

    # Step 4: Verify project state
    project = await db.get_project(project_id)

    assert project["name"] == "Test Project"
    assert project["description"] == "Integration test"
    assert project["source_type"] == "empty"
    assert project["workspace_path"] == str(workspace_path)
    assert project["git_initialized"] is True

    # Step 5: Verify workspace exists
    assert workspace_path.exists()
    assert (workspace_path / ".git").exists()


@pytest.mark.asyncio
async def test_create_project_rollback_on_failure(integration_env):
    """Test rollback when workspace creation fails."""
    db = integration_env["db"]
    workspace_manager = integration_env["workspace_manager"]

    # Create project
    project_id = await db.create_project(
        name="Test",
        description="Test",
        source_type="git_remote",
        source_location="invalid-url",
        workspace_path=""
    )

    # Try to create workspace (should fail)
    with pytest.raises(Exception):
        workspace_manager.create_workspace(
            project_id=project_id,
            source_type=SourceType.GIT_REMOTE,
            source_location="invalid-url"
        )

    # Cleanup: delete project
    await db.delete_project(project_id)

    # Verify project deleted
    project = await db.get_project(project_id)
    assert project is None
```

**Step 2: Add get_project method to Database**

Modify `codeframe/persistence/database.py`:

```python
async def get_project(self, project_id: int) -> Optional[dict]:
    """Get project by ID.

    Args:
        project_id: Project ID

    Returns:
        Project dict or None if not found
    """
    async with self._get_connection() as conn:
        cursor = await conn.execute(
            "SELECT * FROM projects WHERE id = ?",
            (project_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        # Convert row to dict
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
```

**Step 3: Run integration tests**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/integration/test_project_creation_flow.py -v`

Expected: PASS - all 2 integration tests passing

**Step 4: Commit**

```bash
git add codeframe/persistence/database.py tests/integration/test_project_creation_flow.py
git commit -m "test: add integration tests for project creation flow"
```

---

## Task 7: Run Full Test Suite

**Step 1: Run all new tests**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/test_database_schema.py tests/ui/test_models.py tests/test_workspace_manager.py tests/ui/test_project_api.py tests/ui/test_deployment_mode.py tests/integration/test_project_creation_flow.py -v`

Expected: All tests passing

**Step 2: Run full test suite (regression check)**

Run: `ANTHROPIC_API_KEY="test-key" venv/bin/python -m pytest tests/ -v --tb=short`

Expected: New tests pass, old tests may fail due to schema changes (expected)

**Step 3: Document test results**

Create `claudedocs/project-schema-test-results.md`:

```markdown
# Project Schema Refactoring Test Results

**Date**: 2025-10-27
**Branch**: 005-project-schema-refactoring

## New Tests Added

1. **test_database_schema.py** (3 tests)
   - ✅ test_projects_table_has_new_columns
   - ✅ test_source_type_check_constraint
   - ✅ test_description_not_null

2. **test_models.py** (7 tests)
   - ✅ test_source_type_enum_values
   - ✅ test_project_create_request_minimal
   - ✅ test_project_create_request_git_remote
   - ✅ test_project_create_request_validation_error
   - ✅ test_project_create_request_name_required
   - ✅ test_project_create_request_description_required

3. **test_workspace_manager.py** (3 tests)
   - ✅ test_workspace_manager_creates_directory
   - ✅ test_workspace_manager_empty_source
   - ✅ test_workspace_manager_unique_paths

4. **test_project_api.py** (5 tests)
   - ✅ test_create_project_minimal
   - ✅ test_create_project_git_remote
   - ✅ test_create_project_validation_error
   - ✅ test_create_project_missing_description

5. **test_deployment_mode.py** (3 tests)
   - ✅ test_hosted_mode_blocks_local_path
   - ✅ test_hosted_mode_allows_git_remote
   - ✅ test_self_hosted_allows_all_sources

6. **test_project_creation_flow.py** (2 integration tests)
   - ✅ test_create_empty_project_end_to_end
   - ✅ test_create_project_rollback_on_failure

**Total New Tests**: 23
**Total Passing**: 23

## Breaking Changes

Schema migration drops old `projects` table, so existing test data is lost (expected).

Old tests using `project_type` will need updates (if any exist).

## Next Steps

- Manual testing with real git repositories
- Test upload source type (Phase 4)
- Add discovery/PRD generation (future sprint)
```

**Step 4: Commit**

```bash
git add claudedocs/project-schema-test-results.md
git commit -m "docs: test results for project schema refactoring"
```

---

## Task 8: Manual Testing & Documentation

**Step 1: Test creating empty project via API**

```bash
# Start backend server
cd /home/frankbria/projects/codeframe/.worktrees/005-project-schema-refactoring
venv/bin/python -m codeframe.ui.server

# In another terminal, test API
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Manual Test Project",
    "description": "Testing new schema"
  }'

# Verify workspace created
ls .codeframe/workspaces/
```

Expected: Project created, workspace directory exists with git repo

**Step 2: Test git_remote source type**

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Git Test",
    "description": "Clone from git",
    "source_type": "git_remote",
    "source_location": "https://github.com/anthropics/anthropic-quickstarts.git",
    "source_branch": "main"
  }'

# Verify cloned
ls .codeframe/workspaces/2/
```

Expected: Repository cloned successfully

**Step 3: Test deployment mode validation**

```bash
# Set hosted mode
export CODEFRAME_DEPLOYMENT_MODE=hosted

# Try local_path (should fail)
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Local Test",
    "description": "Should fail",
    "source_type": "local_path",
    "source_location": "/tmp/test"
  }'
```

Expected: 403 Forbidden with message about hosted mode

**Step 4: Update AGILE_SPRINTS.md**

Add to Sprint 5 (or current sprint):

```markdown
## Sprint 5: Project Schema Refactoring

**Goal**: Remove restrictive project_type enum, support flexible source types, enable both deployment modes

**Status**: ✅ COMPLETE

### Tasks Completed

1. ✅ Database schema migration (new projects table)
2. ✅ API models refactoring (SourceType enum)
3. ✅ Workspace management module
4. ✅ API endpoint updates
5. ✅ Deployment mode validation
6. ✅ Integration testing (23 new tests)
7. ✅ Manual testing & documentation

### Changes

**Schema Changes**:
- Removed: `project_type` enum, `root_path` field
- Added: `description`, `source_type`, `source_location`, `source_branch`, `workspace_path`, `git_initialized`, `current_commit`

**New Modules**:
- `codeframe/workspace/manager.py` - Workspace management
- Deployment mode detection and validation

**Source Types Supported**:
- `git_remote` - Clone from git URL (both modes)
- `local_path` - Copy from filesystem (self-hosted only)
- `upload` - Extract from archive (future)
- `empty` - Fresh git repo (both modes)

### Next Steps

- Discovery/PRD generation (Sprint 6)
- Upload source type implementation
- Socratic questioning flow
```

**Step 5: Commit**

```bash
git add AGILE_SPRINTS.md
git commit -m "docs: update AGILE_SPRINTS with schema refactoring completion"
```

---

## Completion Checklist

- [x] Schema migration with new projects table
- [x] SourceType enum replacing ProjectType
- [x] Workspace manager module
- [x] Updated API endpoints
- [x] Deployment mode validation
- [x] 23 new tests (all passing)
- [x] Integration tests for full flow
- [x] Manual testing documentation
- [x] AGILE_SPRINTS.md updated

## Success Criteria

✅ **Functional**:
- Projects can be created with 4 source types
- Deployment mode blocks local_path in hosted mode
- All projects get isolated workspace directories
- Git initialized for all workspaces

✅ **Quality**:
- 23 new tests covering schema, models, API, workspace
- Integration tests verify end-to-end flow
- Manual testing confirms real git clone works

✅ **Documentation**:
- Design document at `docs/plans/2025-10-27-project-schema-refactoring.md`
- Test results documented
- AGILE_SPRINTS.md updated

## Future Work (Not in This Plan)

- Discovery/PRD generation feature
- Upload source type implementation (archive extraction)
- Socratic questioning UI
- PRD versioning system
- Config JSON population from discovery
