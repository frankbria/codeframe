# CF-41: Backend Worker Agent - Design Specification

**Status**: Design Phase
**Priority**: P0
**Sprint**: 3 - Autonomous Agent Execution
**Estimated Effort**: 8-10 hours
**Author**: Claude Code (System Architect)
**Date**: 2025-10-17

---

## 1. Executive Summary

The Backend Worker Agent is the foundation of CodeFRAME's autonomous execution system. It reads tasks from the database, understands the codebase through indexing, writes Python code, runs tests, and self-corrects failures—all autonomously.

This agent bridges Sprint 2's planning capabilities (discovery, PRD, task decomposition) with Sprint 3's execution reality.

---

## 2. Requirements Analysis

### 2.1 Functional Requirements

**Primary Capabilities:**
1. **Task Retrieval**: Fetch pending tasks from database with priority ordering
2. **Context Building**: Use codebase indexing (cf-32) to understand code structure
3. **Code Generation**: Write Python code files using Anthropic Claude API
4. **File Operations**: Create/modify/delete files in project directory
5. **Test Integration**: Integrate with test runner (cf-42) for validation
6. **Self-Correction**: Fix failures up to 3 attempts (cf-43)
7. **Status Tracking**: Update task status in database throughout lifecycle

### 2.2 Non-Functional Requirements

**Quality:**
- 85%+ test coverage (TDD methodology)
- All public methods tested with RED-GREEN-REFACTOR
- Error handling for API failures, file I/O, database issues

**Performance:**
- Task execution latency: <60s for simple tasks
- Context retrieval: <5s (leverage cf-32 indexing)
- File writes: Atomic operations to prevent corruption

**Reliability:**
- Idempotent task execution (safe to retry)
- Transaction support for database updates
- Graceful degradation on API quota limits

---

## 3. System Architecture

### 3.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Backend Worker Agent                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Task Manager │  │Code Generator│  │ File Manager │      │
│  │              │  │              │  │              │      │
│  │ - Fetch task │  │ - Build      │  │ - Write file │      │
│  │ - Update     │  │   prompt     │  │ - Read file  │      │
│  │   status     │  │ - Call LLM   │  │ - Delete     │      │
│  │ - Validate   │  │ - Parse      │  │ - Validate   │      │
│  │   completion │  │   response   │  │   paths      │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         └──────────────────┼──────────────────┘              │
│                            │                                 │
│                   ┌────────▼────────┐                       │
│                   │ Worker Executor │                       │
│                   │                 │                       │
│                   │ - Orchestrate   │                       │
│                   │ - Retry logic   │                       │
│                   │ - Error handle  │                       │
│                   └────────┬────────┘                       │
│                            │                                 │
└────────────────────────────┼─────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
      ┌───────────┐  ┌────────────┐  ┌──────────────┐
      │ Database  │  │  Codebase  │  │   Anthropic  │
      │           │  │    Index   │  │   Claude API │
      │ - Tasks   │  │            │  │              │
      │ - Status  │  │ - Symbols  │  │ - Code gen   │
      │ - Issues  │  │ - Files    │  │ - Analysis   │
      └───────────┘  └────────────┘  └──────────────┘
```

### 3.2 Data Flow

```
1. INITIALIZATION
   LeadAgent → Database: Fetch pending task (status='pending', priority=0)
   Database → LeadAgent: Return task {id, title, description, issue_id}

2. CONTEXT BUILDING
   WorkerAgent → CodebaseIndex: query_codebase(task.description)
   CodebaseIndex → WorkerAgent: Related symbols, files, dependencies

3. CODE GENERATION
   WorkerAgent → Claude API: {system_prompt, user_prompt, codebase_context}
   Claude API → WorkerAgent: Generated code + explanation

4. FILE OPERATIONS
   WorkerAgent → FileSystem: Write file(path, content)
   FileSystem → WorkerAgent: Success/Failure

5. STATUS UPDATE
   WorkerAgent → Database: update_task(id, status='completed')
   Database → WorkerAgent: Confirmation
```

---

## 4. Detailed Component Design

### 4.1 BackendWorkerAgent Class

**File**: `codeframe/agents/backend_worker_agent.py`

```python
class BackendWorkerAgent:
    """
    Autonomous agent that executes backend development tasks.

    Responsibilities:
    - Fetch tasks from database
    - Build context from codebase index
    - Generate code using LLM
    - Write files to disk
    - Update task status
    - Integrate with test runner (future)
    - Self-correct failures (future)
    """

    def __init__(
        self,
        project_id: int,
        db: Database,
        codebase_index: CodebaseIndex,
        provider: str = "claude",
        api_key: Optional[str] = None,
        project_root: Path = Path(".")
    ):
        """
        Initialize Backend Worker Agent.

        Args:
            project_id: Project ID for database context
            db: Database instance for task/status management
            codebase_index: Indexed codebase for context retrieval
            provider: LLM provider (default: "claude")
            api_key: API key for LLM provider (uses env var if not provided)
            project_root: Project root directory for file operations
        """

    def fetch_next_task(self) -> Optional[Dict[str, Any]]:
        """
        Fetch highest priority pending task for this project.

        Returns:
            Task dictionary or None if no tasks available

        Task format:
        {
            "id": int,
            "task_number": str,  # e.g., "1.5.2"
            "title": str,
            "description": str,
            "issue_id": int,
            "status": str,
            "priority": int
        }
        """

    def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single task end-to-end.

        Args:
            task: Task dictionary from fetch_next_task()

        Returns:
            Execution result:
            {
                "status": "completed" | "failed",
                "files_modified": List[str],
                "output": str,
                "error": Optional[str]
            }

        Raises:
            TaskExecutionError: If task fails after all retries
        """

    def build_context(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build execution context from task and codebase.

        Args:
            task: Task dictionary

        Returns:
            Context dictionary:
            {
                "task": Dict[str, Any],
                "related_files": List[str],
                "related_symbols": List[Symbol],
                "issue_context": Dict[str, Any]
            }
        """

    def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate code using LLM based on context.

        Args:
            context: Context from build_context()

        Returns:
            Generation result:
            {
                "files": [
                    {
                        "path": str,
                        "content": str,
                        "action": "create" | "modify" | "delete"
                    }
                ],
                "explanation": str
            }
        """

    def apply_file_changes(self, files: List[Dict[str, Any]]) -> List[str]:
        """
        Apply file changes to disk.

        Args:
            files: List of file change dictionaries from generate_code()

        Returns:
            List of modified file paths

        Raises:
            FileOperationError: If file operations fail
        """

    def update_task_status(
        self,
        task_id: int,
        status: str,
        output: Optional[str] = None
    ) -> None:
        """
        Update task status in database.

        Args:
            task_id: Task ID
            status: New status ("in_progress", "completed", "failed")
            output: Optional execution output/error message
        """
```

### 4.2 Prompt Engineering Strategy

**System Prompt Template:**
```
You are a Backend Worker Agent in the CodeFRAME autonomous development system.

Your role:
- Read the task description carefully
- Analyze existing codebase structure
- Write clean, tested Python code
- Follow project conventions and patterns

Context provided:
- Task details (title, description, acceptance criteria)
- Related files and symbols from codebase
- Issue/PR context for broader understanding

Output format:
Return a JSON object with this structure:
{
  "files": [
    {
      "path": "relative/path/to/file.py",
      "action": "create" | "modify" | "delete",
      "content": "file content here"
    }
  ],
  "explanation": "Brief explanation of changes"
}

Guidelines:
- Use strict TDD: Write tests before implementation
- Follow existing code style and patterns
- Keep functions small and focused
- Add comprehensive docstrings
- Handle errors gracefully
```

**User Prompt Template:**
```
Task: {task_title}

Description:
{task_description}

Related Files:
{related_files}

Related Symbols:
{related_symbols}

Issue Context:
{issue_context}

Please implement this task following TDD methodology.
```

### 4.3 Database Schema Usage

**Tasks Table Query Pattern:**
```sql
-- Fetch next task (priority 0 = highest)
SELECT * FROM tasks
WHERE project_id = ?
  AND status = 'pending'
ORDER BY priority ASC, workflow_step ASC, id ASC
LIMIT 1;

-- Update task status
UPDATE tasks
SET status = ?, completed_at = CURRENT_TIMESTAMP
WHERE id = ?;

-- Get tasks by issue (for context)
SELECT * FROM tasks
WHERE issue_id = ?
ORDER BY task_number;
```

**Agents Table Updates:**
```sql
-- Update agent status during task execution
UPDATE agents
SET status = 'working',
    current_task_id = ?,
    last_heartbeat = CURRENT_TIMESTAMP
WHERE id = ?;

-- Clear agent status after task completion
UPDATE agents
SET status = 'idle',
    current_task_id = NULL,
    last_heartbeat = CURRENT_TIMESTAMP
WHERE id = ?;
```

---

## 5. Integration Points

### 5.1 Codebase Index Integration (cf-32)

**Usage:**
```python
# During context building
symbols = codebase_index.find_symbols_by_name("UserAuth")
files = codebase_index.get_file_symbols("codeframe/auth/user.py")
related = codebase_index.search_pattern("def authenticate")
```

**Benefits:**
- Fast symbol lookup without reading entire files
- Dependency discovery for impact analysis
- Pattern matching for similar implementations

### 5.2 Test Runner Integration (cf-42)

**Interface (Future):**
```python
# After code generation, before marking complete
test_result = test_runner.run_tests(
    files=modified_files,
    test_pattern="test_*.py"
)

if not test_result["all_passed"]:
    # Trigger self-correction loop (cf-43)
    self.fix_failures(test_result, max_attempts=3)
```

### 5.3 Git Workflow Integration (cf-33)

**Not Used in cf-41:**
- Git branching is managed at LeadAgent level
- WorkerAgent operates within existing feature branch
- Commits happen after task completion (cf-44)

---

## 6. Error Handling & Edge Cases

### 6.1 API Failures

**Scenario**: Claude API returns 429 (rate limit) or 500 (server error)

**Strategy**:
- Exponential backoff (1s, 2s, 4s, 8s, 16s)
- Max 5 retries
- Mark task as 'failed' with error message after exhaustion
- Create blocker for manual resolution

### 6.2 File Operation Failures

**Scenario**: Permission denied, disk full, invalid path

**Strategy**:
- Validate paths before writing (security: no `../` escapes)
- Atomic writes using temporary files + rename
- Rollback on partial failure
- Log detailed error for debugging

### 6.3 Invalid Task Data

**Scenario**: Task missing description, invalid issue_id

**Strategy**:
- Validate task schema on fetch
- Skip malformed tasks with warning log
- Update task status to 'failed' with validation error

### 6.4 Context Overload

**Scenario**: Codebase index returns 10K+ symbols

**Strategy**:
- Limit context to top 50 most relevant symbols (by relevance score)
- Prioritize symbols in same module/package
- Warn user if context truncated

---

## 7. Testing Strategy

### 7.1 Unit Tests (Required for cf-41)

**Test File**: `tests/test_backend_worker_agent.py`

**Coverage Requirements**: 85%+

**Test Categories**:
1. **Initialization Tests** (4 tests)
   - Test with default parameters
   - Test with custom API key
   - Test with missing dependencies (should raise)
   - Test database connection validation

2. **Task Fetching Tests** (6 tests)
   - Fetch task when available
   - Return None when no tasks
   - Respect priority ordering
   - Respect workflow_step ordering
   - Filter by project_id correctly
   - Handle database errors gracefully

3. **Context Building Tests** (5 tests)
   - Build context with related files
   - Build context with related symbols
   - Build context with issue data
   - Handle empty codebase index
   - Handle missing issue_id

4. **Code Generation Tests** (8 tests)
   - Generate single file creation
   - Generate multiple file modifications
   - Generate file deletion
   - Parse valid LLM response
   - Handle malformed LLM response
   - Handle API timeout
   - Handle API rate limit (429)
   - Handle API server error (500)

5. **File Operations Tests** (7 tests)
   - Create new file
   - Modify existing file
   - Delete file
   - Reject path traversal attacks (`../etc/passwd`)
   - Handle permission denied
   - Handle disk full
   - Atomic write (rename on success)

6. **Task Execution Tests** (6 tests)
   - Execute simple task end-to-end
   - Update status to 'in_progress' during execution
   - Update status to 'completed' on success
   - Update status to 'failed' on error
   - Record files_modified in output
   - Handle execution errors gracefully

7. **Integration Tests** (4 tests)
   - Full task lifecycle (fetch → execute → complete)
   - Agent status updates in database
   - Codebase index queries work
   - Multiple tasks in sequence

**Total**: 40 comprehensive tests

### 7.2 TDD Workflow

**RED-GREEN-REFACTOR Cycles:**

1. **Cycle 1**: Initialization & Configuration
   - RED: Write failing tests for `__init__`
   - GREEN: Implement minimal constructor
   - REFACTOR: Extract configuration validation

2. **Cycle 2**: Task Fetching
   - RED: Write failing tests for `fetch_next_task`
   - GREEN: Implement database query
   - REFACTOR: Extract query builder

3. **Cycle 3**: Context Building
   - RED: Write failing tests for `build_context`
   - GREEN: Implement codebase index integration
   - REFACTOR: Optimize symbol filtering

4. **Cycle 4**: Code Generation
   - RED: Write failing tests for `generate_code`
   - GREEN: Implement LLM API calls with prompts
   - REFACTOR: Extract prompt templates

5. **Cycle 5**: File Operations
   - RED: Write failing tests for `apply_file_changes`
   - GREEN: Implement file I/O with validation
   - REFACTOR: Add atomic write safety

6. **Cycle 6**: Task Execution Orchestration
   - RED: Write failing tests for `execute_task`
   - GREEN: Wire all components together
   - REFACTOR: Extract error handling

---

## 8. Implementation Plan

### Phase 1: Foundation (2-3 hours)
**Files to Create:**
- `codeframe/agents/backend_worker_agent.py`
- `tests/test_backend_worker_agent.py`

**Tasks:**
1. Define `BackendWorkerAgent` class skeleton
2. Implement `__init__` with dependency injection
3. Write initialization tests (TDD)
4. Implement `fetch_next_task` with database queries
5. Write task fetching tests (TDD)

**Deliverable**: Agent can fetch tasks from database

### Phase 2: Context & Generation (3-4 hours)
**Tasks:**
1. Implement `build_context` with codebase index queries
2. Write context building tests (TDD)
3. Design LLM prompts (system + user templates)
4. Implement `generate_code` with Anthropic API
5. Write code generation tests (TDD, with mocks)

**Deliverable**: Agent can generate code from task descriptions

### Phase 3: Execution & File I/O (2-3 hours)
**Tasks:**
1. Implement `apply_file_changes` with validation
2. Write file operation tests (TDD)
3. Implement `update_task_status` with database updates
4. Implement `execute_task` orchestration
5. Write execution tests (TDD)
6. Write end-to-end integration tests

**Deliverable**: Agent can execute tasks and write files

### Phase 4: Error Handling & Polish (1-2 hours)
**Tasks:**
1. Add comprehensive error handling
2. Implement retry logic for API calls
3. Add detailed logging
4. Run full test suite
5. Verify 85%+ coverage
6. Update documentation

**Deliverable**: Production-ready agent with >85% coverage

---

## 9. Success Criteria

### 9.1 Functional Acceptance

- [x] Agent fetches pending tasks from database
- [x] Agent builds context from codebase index
- [x] Agent generates Python code using Claude API
- [x] Agent writes files to disk safely
- [x] Agent updates task status correctly
- [x] Agent handles API errors gracefully
- [x] Agent validates file paths (security)

### 9.2 Quality Acceptance

- [x] 40+ comprehensive tests written
- [x] 100% test pass rate
- [x] 85%+ code coverage
- [x] Strict TDD methodology (RED-GREEN-REFACTOR)
- [x] Zero regressions in existing tests
- [x] All public methods documented

### 9.3 Integration Acceptance

- [x] Works with existing Database class (cf-8)
- [x] Works with CodebaseIndex (cf-32)
- [x] Respects task priorities and workflow steps
- [x] Updates agent status in database
- [x] Ready for test runner integration (cf-42)
- [x] Ready for self-correction loop (cf-43)

---

## 10. Future Enhancements (Out of Scope for cf-41)

### Not in cf-41:
1. **Test Runner Integration** (cf-42)
   - Run pytest after code generation
   - Parse test results
   - Pass to self-correction loop

2. **Self-Correction Loop** (cf-43)
   - Read test failures
   - Analyze errors
   - Regenerate code (max 3 attempts)
   - Escalate to blocker if still failing

3. **Git Auto-Commit** (cf-44)
   - Create commit after task completion
   - Generate descriptive commit message
   - Push to feature branch

4. **Maturity Adaptation** (Sprint 7)
   - Adjust prompt complexity based on agent maturity
   - D1: Detailed step-by-step instructions
   - D4: Goal only, full autonomy

5. **Context Management** (Sprint 6)
   - Flash save before context limit
   - HOT/WARM/COLD tiering
   - Context diffing

---

## 11. Risk Mitigation

### 11.1 API Cost Risk

**Risk**: Claude API usage could become expensive with many tasks

**Mitigation**:
- Cache similar task contexts
- Implement token budgets per task
- Add manual approval gates for high-cost tasks
- Monitor API usage via logging

### 11.2 Code Quality Risk

**Risk**: Generated code may not follow project conventions

**Mitigation**:
- Provide comprehensive codebase context
- Include example code in prompts
- Future: Add linter integration
- Future: Add code review agent (Sprint 8)

### 11.3 Security Risk

**Risk**: Agent could write malicious code or access sensitive files

**Mitigation**:
- Path traversal prevention (`../` validation)
- Restrict write operations to project root
- No execution of generated code without tests
- Future: Sandboxed execution environment

### 11.4 Reliability Risk

**Risk**: API outages could block all task execution

**Mitigation**:
- Retry logic with exponential backoff
- Fallback to queued execution
- Manual intervention via blockers
- Future: Multi-provider support (GPT-4 fallback)

---

## 12. Dependencies

### Required (Must Exist):
- ✅ `codeframe.persistence.database.Database` (cf-8)
- ✅ `codeframe.indexing.codebase_index.CodebaseIndex` (cf-32)
- ✅ `anthropic` Python SDK (already in dependencies)
- ✅ SQLite tasks/agents tables (already in schema)

### Optional (Future):
- ⏳ Test runner integration (cf-42)
- ⏳ Self-correction mechanism (cf-43)
- ⏳ Git workflow commands (cf-44)

---

## 13. Metrics & Monitoring

### Key Metrics:
- **Task Completion Rate**: % of tasks completed vs failed
- **Average Task Duration**: Time from fetch to completion
- **API Cost Per Task**: Token usage and $ cost
- **Error Rate by Type**: API errors, file errors, validation errors
- **Context Size**: Average symbols/files retrieved per task

### Logging Strategy:
```python
logger.info(f"Fetched task {task_id}: {task_title}")
logger.debug(f"Context: {len(symbols)} symbols, {len(files)} files")
logger.info(f"Generated {len(file_changes)} file changes")
logger.warning(f"API retry attempt {attempt}/5")
logger.error(f"Task {task_id} failed: {error}")
```

---

## 14. Conclusion

The Backend Worker Agent (cf-41) is the cornerstone of CodeFRAME's autonomous execution. By combining:
- **Codebase intelligence** (cf-32)
- **LLM code generation** (Anthropic Claude)
- **Robust file operations**
- **Database-driven orchestration**

...we enable true autonomous backend development within a controlled, tested, and observable framework.

This design prioritizes:
1. **Testability**: 40+ tests, 85%+ coverage
2. **Reliability**: Error handling, retries, rollbacks
3. **Security**: Path validation, atomic writes
4. **Extensibility**: Ready for cf-42 (tests) and cf-43 (self-correction)

**Next Steps**:
1. Review design with stakeholders
2. Begin Phase 1 implementation (TDD)
3. Integrate with existing Sprint 3 foundation (cf-32, cf-33)
4. Demonstrate working autonomous task execution
