# Sprint 10 Phase 4: Checkpoint API Endpoints

**Implementation Date**: 2025-11-23
**Tasks Completed**: T092, T093, T094, T095, T096, T097

## Summary

Added 5 FastAPI endpoints for project checkpoint management:

1. **GET /api/projects/{id}/checkpoints** - List all checkpoints for project (T092)
2. **POST /api/projects/{id}/checkpoints** - Create new checkpoint (T093)
3. **GET /api/projects/{id}/checkpoints/{cid}** - Get specific checkpoint (T094)
4. **DELETE /api/projects/{id}/checkpoints/{cid}** - Delete checkpoint and files (T095)
5. **POST /api/projects/{id}/checkpoints/{cid}/restore** - Restore checkpoint (T096, T097)

## Files Modified

### 1. `codeframe/ui/models.py`
Added 3 Pydantic models:
- `CheckpointCreateRequest` - Request for creating checkpoints
- `CheckpointResponse` - Response model for checkpoint data
- `RestoreCheckpointRequest` - Request for restoring checkpoints (with diff preview)

### 2. `codeframe/ui/server.py`
Added 5 endpoint handlers (lines 2593-3032):
- `list_checkpoints()` - GET endpoint
- `create_checkpoint()` - POST endpoint
- `get_checkpoint()` - GET endpoint
- `delete_checkpoint()` - DELETE endpoint
- `restore_checkpoint()` - POST endpoint

## API Design

### Request/Response Models

```python
# Create checkpoint request
{
    "name": str,              # Required, max 100 chars
    "description": str,       # Optional, max 500 chars
    "trigger": str            # Default: "manual"
}

# Checkpoint response
{
    "id": int,
    "project_id": int,
    "name": str,
    "description": str | null,
    "trigger": str,
    "git_commit": str,
    "database_backup_path": str,
    "context_snapshot_path": str,
    "metadata": {
        "project_id": int,
        "phase": str,
        "tasks_completed": int,
        "tasks_total": int,
        "agents_active": list[str],
        "last_task_completed": str | null,
        "context_items_count": int,
        "total_cost_usd": float
    },
    "created_at": str  # ISO 8601
}

# Restore checkpoint request
{
    "confirm_restore": bool  # False = show diff, True = restore
}
```

## HTTP Status Codes

| Endpoint | Success | Error Codes |
|----------|---------|-------------|
| GET /checkpoints | 200 | 404 (project not found) |
| POST /checkpoints | 201 | 404 (project not found), 500 (creation failed) |
| GET /checkpoints/{id} | 200 | 404 (project/checkpoint not found) |
| DELETE /checkpoints/{id} | 204 | 404 (project/checkpoint not found), 500 (deletion failed) |
| POST /checkpoints/{id}/restore | 200 (diff), 202 (restore) | 404 (not found), 500 (restore failed) |

## Integration Points

### CheckpointManager
All endpoints use `CheckpointManager` from `codeframe/lib/checkpoint_manager.py`:

```python
class CheckpointManager:
    async def create_checkpoint(name: str, description: Optional[str] = None) -> Checkpoint
    async def list_checkpoints() -> List[Checkpoint]
    async def restore_checkpoint(checkpoint_id: int, confirm: bool = False) -> Dict[str, Any]
```

### Database Methods
Database operations via `Database` class:

```python
def get_checkpoints(project_id: int) -> List[Checkpoint]
def get_checkpoint_by_id(checkpoint_id: int) -> Optional[Checkpoint]
def save_checkpoint(...) -> int
# DELETE via raw SQL in endpoint
```

## Testing with cURL

### 1. List Checkpoints (T092)

```bash
curl -X GET "http://localhost:8080/api/projects/1/checkpoints" \
  -H "Content-Type: application/json"
```

**Expected Response (200 OK)**:
```json
{
  "checkpoints": [
    {
      "id": 1,
      "project_id": 1,
      "name": "Before refactor",
      "description": "Safety checkpoint",
      "trigger": "manual",
      "git_commit": "a1b2c3d4e5f6...",
      "database_backup_path": "/path/to/checkpoint-001-db.sqlite",
      "context_snapshot_path": "/path/to/checkpoint-001-context.json",
      "metadata": {
        "project_id": 1,
        "phase": "active",
        "tasks_completed": 15,
        "tasks_total": 40,
        "agents_active": ["backend-001", "frontend-001"],
        "last_task_completed": "Implement JWT authentication",
        "context_items_count": 50,
        "total_cost_usd": 2.45
      },
      "created_at": "2025-11-23T10:30:00Z"
    }
  ]
}
```

### 2. Create Checkpoint (T093)

```bash
curl -X POST "http://localhost:8080/api/projects/1/checkpoints" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Before refactor",
    "description": "Safety checkpoint before major refactoring",
    "trigger": "manual"
  }'
```

**Expected Response (201 Created)**:
```json
{
  "id": 2,
  "project_id": 1,
  "name": "Before refactor",
  "description": "Safety checkpoint before major refactoring",
  "trigger": "manual",
  "git_commit": "a1b2c3d4e5f6789...",
  "database_backup_path": "/path/to/checkpoint-002-db.sqlite",
  "context_snapshot_path": "/path/to/checkpoint-002-context.json",
  "metadata": {
    "project_id": 1,
    "phase": "active",
    "tasks_completed": 15,
    "tasks_total": 40,
    "agents_active": ["backend-001"],
    "last_task_completed": "Add user authentication",
    "context_items_count": 50,
    "total_cost_usd": 2.45
  },
  "created_at": "2025-11-23T10:35:00Z"
}
```

### 3. Get Specific Checkpoint (T094)

```bash
curl -X GET "http://localhost:8080/api/projects/1/checkpoints/2" \
  -H "Content-Type: application/json"
```

**Expected Response (200 OK)**: Same as create response

### 4. Delete Checkpoint (T095)

```bash
curl -X DELETE "http://localhost:8080/api/projects/1/checkpoints/2" \
  -H "Content-Type: application/json"
```

**Expected Response (204 No Content)**: Empty body

### 5. Restore Checkpoint - Show Diff (T096)

```bash
curl -X POST "http://localhost:8080/api/projects/1/checkpoints/1/restore" \
  -H "Content-Type: application/json" \
  -d '{
    "confirm_restore": false
  }'
```

**Expected Response (200 OK)**:
```json
{
  "checkpoint_name": "Before refactor",
  "diff": "diff --git a/codeframe/agents/worker.py b/codeframe/agents/worker.py\nindex abc123..def456 100644\n--- a/codeframe/agents/worker.py\n+++ b/codeframe/agents/worker.py\n@@ -10,7 +10,7 @@ class WorkerAgent:\n     def __init__(self):\n-        self.status = 'idle'\n+        self.status = 'active'\n"
}
```

### 6. Restore Checkpoint - Confirm Restore (T097)

```bash
curl -X POST "http://localhost:8080/api/projects/1/checkpoints/1/restore" \
  -H "Content-Type: application/json" \
  -d '{
    "confirm_restore": true
  }'
```

**Expected Response (202 Accepted)**:
```json
{
  "success": true,
  "checkpoint_name": "Before refactor",
  "git_commit": "a1b2c3d4e5f6789...",
  "items_restored": 50
}
```

## Error Handling Examples

### 404 - Project Not Found
```bash
curl -X GET "http://localhost:8080/api/projects/9999/checkpoints"
```

**Response (404)**:
```json
{
  "detail": "Project 9999 not found"
}
```

### 404 - Checkpoint Not Found
```bash
curl -X GET "http://localhost:8080/api/projects/1/checkpoints/9999"
```

**Response (404)**:
```json
{
  "detail": "Checkpoint 9999 not found"
}
```

### 404 - Checkpoint Doesn't Belong to Project
```bash
# Checkpoint 1 belongs to project 2, but we're accessing via project 1
curl -X GET "http://localhost:8080/api/projects/1/checkpoints/1"
```

**Response (404)**:
```json
{
  "detail": "Checkpoint 1 does not belong to project 1"
}
```

### 500 - Checkpoint Creation Failed
```bash
curl -X POST "http://localhost:8080/api/projects/1/checkpoints" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test checkpoint"
  }'
```

**Response (500)** (if git fails):
```json
{
  "detail": "Checkpoint creation failed: Git commit failed: ..."
}
```

### 500 - Restore Failed (Missing Files)
```bash
curl -X POST "http://localhost:8080/api/projects/1/checkpoints/1/restore" \
  -H "Content-Type: application/json" \
  -d '{
    "confirm_restore": true
  }'
```

**Response (500)** (if backup files deleted):
```json
{
  "detail": "Checkpoint files missing: DB=/path/to/checkpoint-001-db.sqlite, Context=/path/to/checkpoint-001-context.json"
}
```

## Logging

All endpoints include comprehensive logging:

```python
# On checkpoint creation
logger.info(f"Created checkpoint {checkpoint.id} for project {project_id}: {checkpoint.name}")

# On checkpoint deletion
logger.info(f"Deleted checkpoint {checkpoint_id} for project {project_id}")
logger.debug(f"Deleted database backup: {db_backup_path}")
logger.debug(f"Deleted context snapshot: {context_snapshot_path}")

# On checkpoint restore
logger.info(f"Restored checkpoint {checkpoint_id} for project {project_id}")

# On errors
logger.error(f"Failed to create checkpoint for project {project_id}: {e}", exc_info=True)
logger.error(f"Failed to restore checkpoint {checkpoint_id}: {e}", exc_info=True)
```

## Security Considerations

1. **Project Ownership Validation**: All endpoints verify checkpoint belongs to specified project
2. **File Path Safety**: Uses `Path` objects to prevent directory traversal
3. **Database Transactions**: All database operations use proper transaction handling
4. **Error Sanitization**: Internal errors logged but sanitized messages returned to client

## Future Enhancements

Potential improvements for Phase 5+:

1. **Pagination**: Add `limit` and `offset` query params to list endpoint
2. **Filtering**: Add `trigger` and `date_range` filters to list endpoint
3. **WebSocket Events**: Broadcast checkpoint creation/deletion/restore events
4. **Async Restore**: Run restore in background task for large checkpoints
5. **Compression**: Compress database backups and context snapshots
6. **Retention Policy**: Auto-delete old checkpoints after N days
7. **Access Control**: Add user/role-based permissions for checkpoint operations

## Testing Checklist

- [ ] List checkpoints for valid project
- [ ] List checkpoints for non-existent project (404)
- [ ] Create checkpoint with valid data
- [ ] Create checkpoint with missing workspace (500)
- [ ] Get checkpoint by valid ID
- [ ] Get checkpoint by invalid ID (404)
- [ ] Get checkpoint from wrong project (404)
- [ ] Delete checkpoint by valid ID
- [ ] Delete checkpoint by invalid ID (404)
- [ ] Delete checkpoint with missing files (should succeed with warnings)
- [ ] Restore checkpoint with confirm=false (diff preview)
- [ ] Restore checkpoint with confirm=true (actual restore)
- [ ] Restore checkpoint with missing backup files (500)
- [ ] Restore checkpoint from wrong project (404)

## Implementation Notes

### Why 202 Accepted for Restore?
The restore endpoint returns 202 Accepted (not 200 OK) when `confirm_restore=true` because:
- Restore operations modify git state and database
- Operations may take several seconds for large projects
- Follows REST conventions for long-running operations
- Allows future migration to background task processing

### Why Separate Diff and Restore?
Two-phase restore (diff preview + confirm) prevents accidental data loss:
1. User requests restore with `confirm_restore=false`
2. API returns git diff showing what will change
3. User reviews diff and decides to proceed
4. User requests restore with `confirm_restore=true`
5. API performs actual restore

This matches the UX pattern used by git itself (`git diff` before `git checkout`).
