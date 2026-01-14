# Database Repository Pattern Architecture

**Date**: 2025-12-22
**Status**: Implemented
**Version**: 1.0

## Overview

The CodeFRAME persistence layer has been refactored from a monolithic `Database` class (4,531 lines) into a modular repository architecture using the Repository pattern. This refactoring improves maintainability, testability, and code organization while maintaining 100% backward compatibility.

## Architecture

### Before: Monolithic Database Class

```text
database.py (4,531 lines)
├── Schema creation (600+ lines)
├── Project CRUD (300 lines)
├── Issue CRUD (350 lines)
├── Task CRUD (400 lines)
├── Agent management (350 lines)
├── Blocker management (300 lines)
├── Memory operations (200 lines)
├── Context management (250 lines)
├── Checkpoint operations (150 lines)
├── Git tracking (250 lines)
├── Test results (150 lines)
├── Lint results (200 lines)
├── Code reviews (150 lines)
├── Quality gates (200 lines)
├── Token usage (150 lines)
├── Correction attempts (150 lines)
├── Activity logs (200 lines)
└── Authentication (250 lines)
```

**Problems:**
- Difficult to review (4,500+ lines in one file)
- Hard to maintain (changes to one domain affect others)
- Testing complexity (all domains tested together)
- High cognitive load (need to understand entire file)
- Merge conflicts (multiple developers editing same file)

### After: Repository Pattern

```text
persistence/
├── database.py (301 lines) - Facade class
├── schema_manager.py (700 lines) - Schema creation
└── repositories/
    ├── base.py (247 lines) - BaseRepository
    ├── __init__.py - Exports
    ├── project_repository.py (303 lines)
    ├── issue_repository.py (368 lines)
    ├── task_repository.py (530 lines)
    ├── agent_repository.py (398 lines)
    ├── blocker_repository.py (310 lines)
    ├── memory_repository.py (181 lines)
    ├── context_repository.py (246 lines)
    ├── checkpoint_repository.py (130 lines)
    ├── git_repository.py (245 lines)
    ├── test_repository.py (142 lines)
    ├── lint_repository.py (203 lines)
    ├── review_repository.py (149 lines)
    ├── quality_repository.py (198 lines)
    ├── token_repository.py (151 lines)
    ├── correction_repository.py (147 lines)
    ├── activity_repository.py (197 lines)
    └── auth_repository.py (254 lines)
```

**Benefits:**
- ✅ **Reviewability**: Each repository is 150-530 lines (reviewable in one session)
- ✅ **Maintainability**: Changes to one domain isolated from others
- ✅ **Testability**: Repositories tested independently
- ✅ **Clarity**: Clear separation of concerns by domain
- ✅ **Extensibility**: Add new repositories without touching existing code
- ✅ **Parallel Development**: Multiple developers can work on different repositories

## Implementation Details

### BaseRepository

All repositories inherit from `BaseRepository` which provides:

- Sync and async connection management
- Common database utilities (`_execute`, `_fetchone`, `_fetchall`, `_commit`)
- Row-to-dict conversion helpers
- Datetime parsing/formatting utilities
- Last insert ID retrieval

```python
from codeframe.persistence.repositories.base import BaseRepository

class ProjectRepository(BaseRepository):
    def create_project(self, name: str, description: str, ...) -> int:
        cursor = self._execute(
            "INSERT INTO projects (...) VALUES (...)",
            (name, description, ...)
        )
        self._commit()
        return self._get_last_insert_id()
```

### Database Facade

The `Database` class now acts as a facade, delegating to repositories:

```python
class Database:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.conn = None
        self._async_conn = None

        # Repositories (initialized in initialize())
        self.projects = None
        self.issues = None
        self.tasks = None
        # ... etc

    def initialize(self) -> None:
        """Initialize database and all repositories."""
        self.conn = sqlite3.connect(str(self.db_path))

        # Create schema using SchemaManager
        schema_mgr = SchemaManager(self.conn)
        schema_mgr.create_schema()

        # Initialize all repositories
        self.projects = ProjectRepository(sync_conn=self.conn, database=self)
        self.issues = IssueRepository(sync_conn=self.conn, database=self)
        # ... etc

    def create_project(self, name: str, description: str, ...) -> int:
        """Delegate to ProjectRepository."""
        return self.projects.create_project(name, description, ...)
```

### Cross-Repository Operations

Repositories can call methods on other repositories through the `_database` reference:

```python
class ProjectRepository(BaseRepository):
    def get_project_stats(self, project_id: int) -> Dict[str, int]:
        """Get project statistics by querying TaskRepository."""
        tasks = self._database.tasks.get_project_tasks(project_id)
        return {
            "total_tasks": len(tasks),
            "completed": len([t for t in tasks if t.status == "completed"]),
            # ...
        }
```

## Migration Guide

### For Developers

**No changes required!** All existing code continues to work:

```python
# Before and After - same code
from codeframe.persistence.database import Database

db = Database("state.db")
db.initialize()

project_id = db.create_project(
    name="My Project",
    description="Test project"
)
```

### For Future Development

When adding new functionality:

1. **Identify the domain**: Which repository does this belong to?
2. **Add method to repository**: Implement in appropriate repository class
3. **Add delegation method**: Add delegating method to `Database` class if public API
4. **Write tests**: Test repository independently

Example - Adding a new project method:

```python
# 1. Add to ProjectRepository
class ProjectRepository(BaseRepository):
    def archive_project(self, project_id: int) -> None:
        """Archive a project."""
        self._execute(
            "UPDATE projects SET status = 'archived' WHERE id = ?",
            (project_id,)
        )
        self._commit()

# 2. Add delegation method to Database
class Database:
    def archive_project(self, project_id: int) -> None:
        """Archive a project."""
        return self.projects.archive_project(project_id)

# 3. Test independently
def test_archive_project():
    repo = ProjectRepository(sync_conn=conn)
    repo.archive_project(1)
    # assertions...
```

## Testing

All existing tests pass (71/71 - 100% pass rate):

```bash
# Core database tests
uv run pytest tests/persistence/test_database.py -v
# 40 tests passing

# API endpoint tests
uv run pytest tests/api/test_endpoints_database.py -v
# 23 tests passing

# Correction workflow tests
uv run pytest tests/persistence/test_correction_database.py -v
# 8 tests passing
```

## Performance Impact

**No performance degradation** - the refactoring is purely organizational:

- Same number of database queries
- Same query patterns
- Same connection management
- Delegation methods are simple pass-throughs (negligible overhead)

## File Organization

```text
codeframe/persistence/
├── database.py                    # Main facade (301 lines)
├── database.py.backup             # Original backup (4531 lines)
├── schema_manager.py              # Schema creation (700 lines)
└── repositories/
    ├── __init__.py                # Exports
    ├── base.py                    # BaseRepository (247 lines)
    ├── project_repository.py      # Projects (303 lines)
    ├── issue_repository.py        # Issues (368 lines)
    ├── task_repository.py         # Tasks (530 lines)
    ├── agent_repository.py        # Agents (398 lines)
    ├── blocker_repository.py      # Blockers (310 lines)
    ├── memory_repository.py       # Memory (181 lines)
    ├── context_repository.py      # Context (246 lines)
    ├── checkpoint_repository.py   # Checkpoints (130 lines)
    ├── git_repository.py          # Git tracking (245 lines)
    ├── test_repository.py         # Test results (142 lines)
    ├── lint_repository.py         # Lint results (203 lines)
    ├── review_repository.py       # Code reviews (149 lines)
    ├── quality_repository.py      # Quality gates (198 lines)
    ├── token_repository.py        # Token usage (151 lines)
    ├── correction_repository.py   # Corrections (147 lines)
    ├── activity_repository.py     # Activity logs (197 lines)
    └── auth_repository.py         # Auth (254 lines)
```

## Backward Compatibility

**100% backward compatible** - all existing imports and method signatures preserved:

✅ All `from codeframe.persistence.database import Database` imports work
✅ All `db.create_project(...)` method calls work
✅ All method signatures unchanged
✅ All helper methods (`_row_to_project`, etc.) work
✅ All async methods work
✅ All tests pass without modification

## Future Enhancements

Potential improvements for future consideration:

1. **Repository-specific tests**: Add focused unit tests for each repository
2. **Async repositories**: Create async-first repository variants for high-concurrency scenarios
3. **Repository interfaces**: Define abstract base classes for repository contracts
4. **Query builders**: Add fluent query builders for complex queries
5. **Caching layer**: Add repository-level caching for frequently accessed data

## References

- Original database.py: `/home/frankbria/projects/codeframe/codeframe/persistence/database.py.backup`
- Repository pattern: [Martin Fowler's Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- Pull Request: #147

## Approval

- ✅ All tests passing (71/71)
- ✅ Code review completed
- ✅ Documentation updated
- ✅ No breaking changes
- ✅ Ready for merge
