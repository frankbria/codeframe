# ReAct Agent Architecture Plan

**Date**: 2026-02-07
**Status**: Draft
**Scope**: Replace Plan-and-Execute with ReAct loop for CodeFRAME's agent execution system

---

## 1. Architecture Overview

### What Changes

CodeFRAME's agent execution currently uses a **Plan-and-Execute** pattern:

```
PRD → Tasks → [Plan all steps upfront] → [Execute steps sequentially] → [Verify at end]
```

This is a known anti-pattern. Plans become stale as soon as step 1 produces unexpected output. The agent generates whole files without seeing what prior steps actually produced, leading to cross-file inconsistency, config overwrites, and ineffective self-correction.

The new architecture uses a **ReAct (Reason + Act) loop**:

```
PRD → Tasks → [Think: what should I do next?]
                       ↓
              [Act: call a tool (read, edit, create, search, run)]
                       ↓
              [Observe: what happened?]
                       ↓
              [Decide: task complete? keep going? stuck?]
                       ↓
              [Loop back to Think]
```

The LLM decides what to do at every step based on the current state of the codebase, not a predetermined plan. This is how Claude Code, SWE-agent, Warp, and every top SWE-bench performer works.

### What Stays the Same

| Module | Status | Notes |
|--------|--------|-------|
| `codeframe/core/workspace.py` | Unchanged | Workspace model is stable |
| `codeframe/core/tasks.py` | Unchanged | Task model is stable |
| `codeframe/core/gates.py` | Unchanged | Gate system works well |
| `codeframe/core/blockers.py` | Unchanged | Blocker system works well |
| `codeframe/core/events.py` | Unchanged | Event emission is stable |
| `codeframe/core/state_machine.py` | Unchanged | Status transitions are stable |
| `codeframe/core/runtime.py` | Minor change | Support new agent type via flag |
| `codeframe/core/context.py` | Minor change | Initial context loading still used, JIT retrieval added |
| `codeframe/core/streaming.py` | Unchanged | SSE streaming works |
| `codeframe/core/fix_tracker.py` | Reused | Escalation logic still valuable |
| `codeframe/core/quick_fixes.py` | Reused | Pattern-based fixes still valuable |
| `codeframe/adapters/llm/base.py` | Unchanged | Already has Tool/ToolCall/ToolResult types |
| `codeframe/adapters/llm/anthropic.py` | Minor change | Ensure tool-use response handling works |
| `codeframe/cli/app.py` | Minor change | Add `--engine react` flag |

### What's New

| Module | Purpose |
|--------|---------|
| `codeframe/core/react_agent.py` | ReAct loop agent (replaces `Agent.run()` logic) |
| `codeframe/core/tools.py` | Tool definitions and execution dispatch |
| `codeframe/core/editor.py` | Search-replace file editor with fuzzy matching |

### What's Modified

| Module | Changes |
|--------|---------|
| `codeframe/core/agent.py` | Kept for backward compatibility; new code goes in `react_agent.py` |
| `codeframe/core/executor.py` | Refactored: tool implementations extracted, whole-file generation kept for `create_file` |
| `codeframe/core/planner.py` | Made optional; used only for lightweight "intent preview" before ReAct loop |

### High-Level Flow

```
cf work start <task-id> --execute [--engine react]
    │
    ├── runtime.start_task_run()
    │
    └── runtime.execute_agent()
            │
            ├── Load initial context (task, PRD, file tree, preferences)
            ├── Build system prompt (base + task + project layers)
            ├── Initialize conversation: [system, user: "Execute this task"]
            │
            └── REACT LOOP (max 30 iterations):
                ├── llm.complete(messages, tools=AGENT_TOOLS)
                │
                ├── If response has tool_calls:
                │   ├── Execute each tool call
                │   ├── Auto-verify after file edits (ruff check)
                │   ├── Append tool results to conversation
                │   └── Continue loop
                │
                ├── If response has text only (end_turn):
                │   ├── Agent is done → run final verification
                │   └── Exit loop
                │
                ├── If blocker detected:
                │   ├── Create blocker in DB
                │   └── Exit loop with BLOCKED status
                │
                └── Token budget check → compact if needed
```

---

## 2. The Agent Loop

### ReAct Loop Implementation

The core loop lives in `codeframe/core/react_agent.py`:

```python
class ReactAgent:
    """ReAct-based agent that uses tool-use loop instead of upfront planning."""

    MAX_ITERATIONS = 30          # Hard cap on loop iterations
    SELF_CORRECTION_CAP = 5      # Max retries for same error
    COMPACT_THRESHOLD = 0.85     # Compact when context is 85% full

    def run(self, task_id: str) -> AgentState:
        # 1. Load context
        context = self._load_initial_context(task_id)

        # 2. Build system prompt
        system_prompt = self._build_system_prompt(context)

        # 3. Build initial user message
        messages = [{"role": "user", "content": self._build_task_message(context)}]

        # 4. ReAct loop
        iteration = 0
        while iteration < self.MAX_ITERATIONS:
            iteration += 1

            # Call LLM with tools
            response = self.llm.complete(
                messages=messages,
                purpose=Purpose.EXECUTION,
                tools=AGENT_TOOLS,
                system=system_prompt,
                max_tokens=16384,
                temperature=0.0,
            )

            # Handle text-only response (agent thinks it's done)
            if not response.has_tool_calls:
                messages.append({"role": "assistant", "content": response.content})
                break

            # Handle tool calls
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls,
            })

            tool_results = []
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call, context)
                tool_results.append(result)

                # Auto-verify after file modifications
                if tool_call.name in ("edit_file", "create_file"):
                    lint_result = self._run_lint_check()
                    if lint_result and not lint_result.passed:
                        # Inject lint errors as additional context
                        result.content += f"\n\nLINT ERRORS:\n{lint_result.get_error_summary()}"

            messages.append({
                "role": "user",
                "tool_results": tool_results,
            })

            # Token budget management
            if self._should_compact(messages):
                messages = self._compact_messages(messages)

        # 5. Final verification
        return self._finalize(messages, context)
```

### How the Agent Decides What to Do Next

The agent does NOT use an explicit decision tree. The LLM itself decides the next action based on:

1. **System prompt**: Tells it the available tools and when to use them
2. **Conversation history**: All previous tool calls and their results
3. **Task description**: What needs to be accomplished
4. **Observed state**: File contents it has read, test results it has seen

This is the fundamental insight from the research: the model is the planner. Explicit planning is overhead that adds brittleness.

### How It Handles Multi-File Tasks

Example task: "Build a task tracker CLI with add, list, and complete commands"

The agent would naturally:

1. **Think**: "I need to create a CLI app. Let me check what exists first."
2. **Act**: `list_files(path=".")` -- sees the project structure
3. **Think**: "This is a new project. I'll start with the main module."
4. **Act**: `create_file(path="task_tracker.py", content="...")` -- creates main file
5. **Act**: `run_command(command="python task_tracker.py --help")` -- tests it works
6. **Observe**: Sees the help output or error
7. **Think**: "Help works. Now I need to add the 'add' command."
8. **Act**: `edit_file(path="task_tracker.py", edits=[...])` -- adds functionality
9. **Act**: `run_command(command="python task_tracker.py add 'Buy groceries'")` -- tests
10. **Continue** until all features work

Each step builds on observed reality, not assumptions. If step 5 reveals an import error, the agent sees it immediately and fixes it in step 6.

### Termination Conditions

The loop terminates when any of these is true:

| Condition | Status | How Detected |
|-----------|--------|--------------|
| LLM returns text without tool calls | COMPLETED | `not response.has_tool_calls` |
| Hard iteration limit reached (30) | FAILED | `iteration >= MAX_ITERATIONS` |
| Final verification passes | COMPLETED | `gates.run()` all pass |
| Final verification fails after retries | FAILED | Self-correction cap exceeded |
| Blocker detected | BLOCKED | Agent creates blocker via tool or pattern match |
| Unrecoverable error | FAILED | Exception in tool execution |

### How It Handles Edge Cases

**Agent loops on the same error**: The `FixAttemptTracker` (already in codebase) detects when the agent retries the same fix. After 3 attempts on the same error signature, it escalates to a blocker.

**Agent tries to do too much**: The 30-iteration hard cap prevents runaway execution. For typical tasks (3-15 files), this is more than enough.

**Agent goes off-track**: The system prompt explicitly constrains behavior: "Implement exactly what the task describes. Do not add features, refactor code, or make improvements beyond what was asked."

---

## 3. Tool Design

### Tool Set (7 Tools)

The tool set is intentionally minimal. Research shows that fewer tools = higher accuracy (Vercel removed 80% of tools and saw 3.5x improvement).

#### 3.1 `read_file`

**Purpose**: Read file contents. Always read before editing.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Relative path from workspace root"
    },
    "start_line": {
      "type": "integer",
      "description": "Start line (1-based, optional)"
    },
    "end_line": {
      "type": "integer",
      "description": "End line (1-based, optional)"
    }
  },
  "required": ["path"]
}
```

**Output**: File content with line context. If file is large (>500 lines), shows first/last 50 lines with a summary. Supports line ranges for targeted reading.

**Maps to**: `context.py` file loading logic, with line-range support added.

**Safety**: Path traversal check via `_is_path_safe()` (already in `agent.py`).

#### 3.2 `edit_file`

**Purpose**: Make targeted changes to existing files using search-replace blocks.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Relative path from workspace root"
    },
    "edits": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "search": {
            "type": "string",
            "description": "Exact text to find in the file"
          },
          "replace": {
            "type": "string",
            "description": "Text to replace it with"
          }
        },
        "required": ["search", "replace"]
      },
      "description": "List of search-replace operations to apply in order"
    }
  },
  "required": ["path", "edits"]
}
```

**Output**: Success with a unified diff preview, or failure with the actual file content near the expected match location (so the LLM can retry with correct content).

**Error feedback format** (critical for self-correction):
```
EDIT FAILED: No match found for search block in task_tracker.py.
The file contains these similar lines near the expected location:
  Line 42: def add_task(self, title: str, priority: int = 0):
  Line 43:     """Add a new task."""
  Line 44:     self.tasks.append(Task(title=title, priority=priority))
Please retry with the actual content from the file.
```

**Maps to**: New `editor.py` module (see Section 3.8).

#### 3.3 `create_file`

**Purpose**: Create a new file with specified content. For genuinely new files only.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Relative path from workspace root"
    },
    "content": {
      "type": "string",
      "description": "Complete file content"
    }
  },
  "required": ["path", "content"]
}
```

**Output**: Success or failure. If file already exists, returns error suggesting `edit_file` instead.

**Maps to**: `executor.py:_execute_file_create()` logic, simplified.

**Note**: Whole-file generation is appropriate for new files. Search-replace only applies to editing existing files.

#### 3.4 `search_codebase`

**Purpose**: Search for patterns across the codebase. Uses regex, not semantic search.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "pattern": {
      "type": "string",
      "description": "Regex pattern to search for"
    },
    "file_glob": {
      "type": "string",
      "description": "Glob pattern to filter files (e.g., '*.py', 'src/**/*.ts')"
    },
    "max_results": {
      "type": "integer",
      "description": "Maximum results to return (default: 20)"
    }
  },
  "required": ["pattern"]
}
```

**Output**: Matching lines with file paths and line numbers. Truncated to `max_results`.

**Maps to**: New implementation using `subprocess.run(["grep", "-rn", ...])` or Python `re` over file tree from `context.py`.

**Why regex, not semantic**: Anthropic chose regex search (grep) over vector/semantic search for Claude Code. Code search needs precision, not fuzzy relevance. Regex is deterministic, fast, and the agent can construct precise patterns.

#### 3.5 `list_files`

**Purpose**: List files in a directory or matching a pattern.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Directory to list (default: workspace root)"
    },
    "pattern": {
      "type": "string",
      "description": "Glob pattern to filter (e.g., '**/*.py')"
    },
    "max_depth": {
      "type": "integer",
      "description": "Maximum directory depth (default: 3)"
    }
  }
}
```

**Output**: File listing with sizes. Respects ignore patterns from `context.py:DEFAULT_IGNORE_PATTERNS`.

**Maps to**: `context.py:ContextLoader._scan_file_tree()`.

#### 3.6 `run_command`

**Purpose**: Execute a shell command in the workspace.

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "Shell command to execute"
    },
    "timeout": {
      "type": "integer",
      "description": "Timeout in seconds (default: 60, max: 300)"
    }
  },
  "required": ["command"]
}
```

**Output**: stdout, stderr, exit code. Output truncated to 4000 chars (first 2000 + last 2000 if longer).

**Maps to**: `executor.py:_execute_shell_command()` with existing safety checks (`_is_dangerous_command()`).

**Safety layers**:
1. Dangerous command regex check (already in `executor.py`)
2. Command parsed via `shlex.split()` when possible
3. Timeout enforcement
4. Output truncation to prevent context flooding
5. Working directory locked to workspace

#### 3.7 `run_tests`

**Purpose**: Run the project's test suite (or a subset).

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "test_path": {
      "type": "string",
      "description": "Specific test file or directory (optional)"
    },
    "verbose": {
      "type": "boolean",
      "description": "Show full test output (default: false)"
    }
  }
}
```

**Output**: Test summary (passed/failed/errors). On failure, shows first failing test with its output.

**Maps to**: `gates.py:_run_pytest()` and `_run_npm_test()`.

**Why separate from `run_command`**: Focused output. `run_tests` only shows the first failing test and its traceback, not the entire test suite output. This keeps the context window clean.

### 3.8 Search-Replace Editor (`codeframe/core/editor.py`)

The editor implements a matching fallback chain for reliability:

```python
class SearchReplaceEditor:
    """Applies search-replace edits to files with fuzzy matching fallback."""

    def apply_edits(self, file_path: Path, edits: list[Edit]) -> EditResult:
        """Apply a list of search-replace edits to a file.

        Each edit is tried with a fallback chain:
        1. Exact match
        2. Whitespace-normalized match (collapse spaces/tabs)
        3. Indentation-agnostic match (strip leading whitespace)
        4. Fuzzy match (Levenshtein similarity > 0.85)
        5. Fail with context (show actual file content near expected location)
        """
        content = file_path.read_text()
        original = content

        for edit in edits:
            content, match_info = self._apply_single_edit(content, edit)
            if not match_info.matched:
                # Return error with context for LLM retry
                return EditResult(
                    success=False,
                    error=self._format_match_error(content, edit, match_info),
                )

        # Write the modified content
        file_path.write_text(content)

        # Generate diff for the response
        diff = self._generate_diff(original, content, file_path.name)

        return EditResult(success=True, diff=diff)
```

**Key rules** (enforced in the tool, not just the prompt):
- Never include line numbers in search blocks (LLMs hallucinate them)
- Preserve original indentation in replacements
- Support multiple edits in a single call (reduces round trips)
- Always diff against actual file state, not cached/assumed state

### Tool-to-Module Mapping Summary

| Tool | Implementation Module | Existing Code Reused |
|------|----------------------|---------------------|
| `read_file` | `tools.py` → `context.py` | File loading, path safety |
| `edit_file` | `tools.py` → `editor.py` | New module |
| `create_file` | `tools.py` → file ops | `executor.py` create logic |
| `search_codebase` | `tools.py` → grep | New, simple implementation |
| `list_files` | `tools.py` → `context.py` | `_scan_file_tree()` |
| `run_command` | `tools.py` → `executor.py` | `_execute_shell_command()` |
| `run_tests` | `tools.py` → `gates.py` | `_run_pytest()`, `_run_npm_test()` |

---

## 4. Context Management

### Initial Context Loading

When the agent starts, it loads:

1. **Task metadata**: Title, description, status (from `tasks.py`)
2. **PRD content**: If associated (from `prd.py`, truncated to ~5000 chars)
3. **File tree**: Repository structure listing (from `context.py`, lightweight)
4. **Preferences**: AGENTS.md / CLAUDE.md content (from `agents_config.py`)
5. **Tech stack**: Detected or configured (from `workspace.py`)
6. **Answered blockers**: Previous Q&A context (from `blockers.py`)

This goes into the **system prompt**, not the conversation. Total initial context target: ~10-15K tokens.

### Just-in-Time Retrieval

Unlike the current architecture which pre-loads file contents into context, the ReAct agent retrieves files on demand via tools:

```
Current approach:
  Load context → Score relevance → Pre-load top 5 files → Send all to LLM

New approach:
  Load lightweight context (file tree only) → LLM decides which files to read → read_file tool
```

**Advantages**:
- Agent only reads files it actually needs
- No wasted tokens on irrelevant files
- Agent can follow imports and references dynamically
- Works better for large codebases

### Token Budget Management

**Token tracking**: Estimate tokens for each message in the conversation history. Use the conservative estimate of `len(text) / 4`.

**Compaction strategy** (triggered at 85% of context window):

1. **Tool result clearing** (safest): Replace verbose tool results with summaries. A file read that returned 500 lines becomes "Read 500 lines from utils.py (functions: parse_config, validate_input, format_output)".

2. **Intermediate step removal**: Remove tool calls that didn't produce useful results (e.g., a `list_files` call that the agent didn't act on).

3. **Conversation summary**: Replace the oldest N messages with a summary: "Previously: created main.py with CLI structure, added add/list commands, fixed import error in utils.py. Current status: 3 files created, tests passing."

**What to preserve during compaction**:
- Architectural decisions made by the agent
- Unresolved errors or warnings
- File paths that were created/modified
- The most recent 5 tool call/result pairs

**What to discard**:
- Redundant file reads (if the agent read the same file twice)
- Successful tool outputs that were fully consumed
- Verbose test output after tests passed

### Handling Large Codebases

For repos with 1000+ files:

1. **File tree is summarized**: Show top-level directories with file counts, not individual files
2. **Search-first exploration**: Agent uses `search_codebase` to find relevant files, then `read_file` to examine them
3. **Follow-the-imports**: After reading a file, the agent can search for imports/references to discover related files
4. **Never pre-load**: No file content is loaded until the agent explicitly requests it

---

## 5. Verification Strategy

### When to Run Linters

**After every `edit_file` or `create_file` tool call**: Run `ruff check` on the modified file(s) only. This catches syntax errors, missing imports, and style issues immediately, before they compound.

Implementation: The tool execution handler auto-runs ruff and appends results to the tool output:

```python
def _execute_tool(self, tool_call: ToolCall, context: TaskContext) -> ToolResult:
    result = self._dispatch_tool(tool_call)

    # Auto-lint after file modifications
    if tool_call.name in ("edit_file", "create_file") and not result.is_error:
        lint = self._run_ruff_on_file(tool_call.input["path"])
        if lint.errors:
            result.content += f"\n\nLINT WARNINGS:\n{lint.format_errors()}"

    return result
```

The agent sees lint errors in the tool response and can fix them in the next iteration. No separate verification step needed.

### When to Run Tests

**Not after every change.** Tests are expensive and slow. Instead:

1. **Agent-initiated**: The agent calls `run_tests` when it thinks a feature is complete
2. **Final verification**: Gates run automatically when the agent signals completion (end_turn without tool calls)
3. **System prompt guidance**: Tell the agent to run tests after implementing each major feature, not after every line change

### Self-Correction Flow

```
Agent makes an edit
    │
    ├── Auto-lint runs (ruff)
    │   └── If errors: agent sees them in tool response → fixes in next iteration
    │
    ├── Agent runs tests (when ready)
    │   └── If failures: agent sees test output → analyzes → fixes
    │
    └── Final verification (all gates)
        ├── PASS → COMPLETED
        └── FAIL → self-correction (up to 3 attempts):
            ├── Try ruff --fix (existing _try_auto_fix)
            ├── Try pattern-based quick fixes (existing quick_fixes.py)
            ├── Check escalation threshold (existing fix_tracker.py)
            │   └── If exceeded → create blocker
            └── Agent gets error context, re-enters ReAct loop for 5 more iterations
```

### Escalation to Blockers

Blocker creation happens in two ways:

1. **Pattern-matched** (existing logic from `agent.py`):
   - Requirements ambiguity patterns → immediate blocker
   - Access/credentials patterns → immediate blocker
   - External service patterns → blocker after retry

2. **Threshold-based** (existing logic from `fix_tracker.py`):
   - Same error 3+ times → escalation blocker
   - Same file 3+ attempts → escalation blocker
   - Total failures > 5 → escalation blocker

3. **Agent-initiated** (new):
   - Agent's text response includes blocker indicators → create blocker
   - Agent explicitly states it cannot proceed without information

---

## 6. System Prompt Design

### Layered Prompt Structure

```
┌─────────────────────────────────────┐
│ Layer 1: BASE                       │  ← Always present
│ - Agent identity and role           │
│ - Available tools (auto-generated)  │
│ - Core constraints                  │
│ - Termination conditions            │
├─────────────────────────────────────┤
│ Layer 2: PROJECT                    │  ← Per-workspace
│ - AGENTS.md / CLAUDE.md content     │
│ - Tech stack description            │
│ - Repository structure summary      │
├─────────────────────────────────────┤
│ Layer 3: TASK                       │  ← Per-task
│ - Task title and description        │
│ - PRD content (if any)              │
│ - Previous blocker answers          │
└─────────────────────────────────────┘
```

### Layer 1: Base Prompt

```
You are CodeFRAME, an autonomous software engineering agent. You implement tasks by reading, writing, and testing code.

## How You Work

1. Read the task description and requirements
2. Explore the codebase to understand the current state
3. Make changes incrementally using the provided tools
4. Test your changes after each significant modification
5. Continue until the task is fully implemented and tests pass

## Rules

- ALWAYS read a file before editing it. Never assume file contents.
- Make small, targeted edits. Do not rewrite entire files when a few lines will do.
- Run tests after implementing each major feature, not after every line change.
- For NEW files, use create_file. For EXISTING files, use edit_file.
- Never use edit_file on a file you haven't read in this session.
- Keep solutions simple and focused. Do not add features, refactor code, or make improvements beyond what was asked.
- Implement a solution that works correctly for all valid inputs, not just test cases. Do not hard-code values.

## When You're Done

When the task is fully implemented and working, respond with a brief summary of what you did. Do not call any more tools.

## When You're Stuck

If you encounter a problem you genuinely cannot solve (conflicting requirements, missing credentials, unclear business logic), explain the problem clearly. Do NOT stop for trivial decisions like which library version to use or how to name a variable -- just pick the best option and proceed.

## Decision-Making Autonomy

You MUST make decisions autonomously about:
- Import organization and ordering
- Variable and function naming (following existing patterns)
- Error handling strategies
- Code organization within files
- Choice between equivalent implementations
- File handling (create vs edit based on whether file exists)
- Package versions (use latest stable)
- Configuration values (use sensible defaults)
```

### Layer 2: Project Context

```
## Project Preferences

{content of AGENTS.md or CLAUDE.md, if present}

## Technology Stack

{workspace.tech_stack or "Not specified -- detect from project files"}

## Repository Structure

{file tree summary from context loader -- directories and file counts, not individual files}
```

### Layer 3: Task Context

```
## Task

**Title**: {task.title}
**Description**: {task.description}

## Requirements (PRD)

{prd.content, truncated to 5000 chars}

## Previous Clarifications

{answered blockers as Q&A pairs}
```

### How User Conventions Integrate

User conventions from AGENTS.md or CLAUDE.md are injected into Layer 2 verbatim. The system prompt tells the agent to check project preferences first before making decisions. This matches the existing `agents_config.py` pattern but moves the content into the system prompt instead of the planning prompt.

### How Task-Specific Instructions Work

Each task gets its own Layer 3 content. If a task has specific requirements in its description (e.g., "use SQLite for storage"), those appear in the task context and the agent follows them.

---

## 7. Migration Plan

### Phase A: Search-Replace Editor (Low Risk, Additive)

**Goal**: Add the `editor.py` module without changing any existing behavior.

**Files**:
- Create: `codeframe/core/editor.py`
- Create: `tests/core/test_editor.py`

**What**:
- Implement `SearchReplaceEditor` with fuzzy matching fallback chain
- Exact match → whitespace-normalized → indentation-agnostic → fuzzy (Levenshtein)
- Unit tests for each matching level and error formatting

**Risk**: None. Purely additive. No existing code changes.

**Dependencies**: None (standalone module).

### Phase B: Tool Definitions (Low Risk, Additive)

**Goal**: Define agent tools with schemas and connect them to existing modules.

**Files**:
- Create: `codeframe/core/tools.py`
- Create: `tests/core/test_tools.py`

**What**:
- Define `AGENT_TOOLS` list with all 7 tool schemas (as `Tool` objects from `adapters/llm/base.py`)
- Implement `execute_tool(tool_call: ToolCall, workspace: Workspace) -> ToolResult` dispatcher
- Each tool function wraps existing module code
- Unit tests for each tool

**Risk**: None. Purely additive. Existing code used read-only.

**Dependencies**: Phase A (editor.py for edit_file tool).

### Phase C: ReAct Loop Agent (Medium Risk, Core Change)

**Goal**: Implement the ReAct agent loop as a new class alongside the existing Agent.

**Files**:
- Create: `codeframe/core/react_agent.py`
- Create: `tests/core/test_react_agent.py`
- Modify: `codeframe/core/runtime.py` -- add engine selection
- Modify: `codeframe/cli/app.py` -- add `--engine` flag

**What**:
- Implement `ReactAgent` class with the ReAct loop
- Build system prompt from context
- Handle tool call/result conversation flow
- Integrate with existing `AgentState`, `AgentStatus`, events
- Add `engine` parameter to `runtime.execute_agent()`
- Default engine remains "plan" (existing Agent); "react" selects ReactAgent

**Backward Compatibility**:
- Existing `Agent` class untouched
- Default behavior unchanged (`--engine plan` is implicit default)
- All existing tests pass without modification
- `--engine react` opts into new behavior

**Risk**: Medium. New code path, but doesn't touch existing code. Risk is in the new implementation, not in regressions.

**Dependencies**: Phase B (tools.py).

### Phase D: Incremental Verification (Low Risk, Refinement)

**Goal**: Add auto-linting after file modifications in the ReAct loop.

**Files**:
- Modify: `codeframe/core/react_agent.py` -- add post-edit lint
- Modify: `codeframe/core/tools.py` -- lint integration in tool execution

**What**:
- After `edit_file` or `create_file` tool execution, run `ruff check` on the modified file
- Append lint results to the tool's response content
- Agent sees errors in context and can fix them in the next iteration

**Risk**: Low. Only affects the ReAct path.

**Dependencies**: Phase C.

### Phase E: Context Compaction (Low Risk, Refinement)

**Goal**: Token budget management for long-running tasks.

**Files**:
- Modify: `codeframe/core/react_agent.py` -- add compaction logic

**What**:
- Track estimated tokens in conversation history
- At 85% threshold, compact old messages
- Preserve recent tool calls, architectural decisions, error context
- Discard redundant reads, successful outputs

**Risk**: Low. Only affects the ReAct path. Compaction is conservative.

**Dependencies**: Phase C.

### Phase F: Default Switch (After Validation)

**Goal**: Make ReAct the default engine after it's proven in production.

**Files**:
- Modify: `codeframe/core/runtime.py` -- change default engine
- Modify: `codeframe/cli/app.py` -- update help text

**What**:
- Change default from "plan" to "react"
- Keep "plan" available as fallback
- Eventually deprecate "plan" engine

**Risk**: Medium. Changes default behavior. Gated on sufficient testing and user feedback.

**Dependencies**: Phases C-E complete and validated.

### Migration Timeline

```
Phase A: Editor          [standalone, can start immediately]
Phase B: Tools           [depends on A]
Phase C: ReAct Loop      [depends on B, this is the big one]
Phase D: Auto-Lint       [depends on C, quick follow-up]
Phase E: Compaction      [depends on C, can be deferred]
Phase F: Default Switch  [depends on C-E validated]
```

Phases A and B are safe to ship independently. Phase C is the core change. Phases D and E are refinements.

---

## 8. Critical Design Decision: New Project Generation

### The Problem

The research is dominated by SWE-bench analysis, which is about **editing existing code to fix bugs**. CodeFRAME's primary use case is **PRD to working code** -- generating new projects from scratch.

Key differences:

| Dimension | Bug Fixing (SWE-bench) | New Project (CodeFRAME) |
|-----------|----------------------|------------------------|
| Files involved | 1-3 existing files | 5-30+ new files |
| Edit type | Surgical patches | Whole-file creation |
| Context available | Full existing codebase | PRD only, empty repo |
| Success criteria | Specific test passes | All requirements met |
| Error recovery | Fix the patch | Fix the generated code |

### How ReAct Handles New Projects

ReAct works equally well for generation. The agent simply uses `create_file` instead of `edit_file`:

1. Agent reads the PRD (in system prompt)
2. Agent creates the first file (e.g., `main.py` with basic structure)
3. Agent tests it (`run_command: python main.py --help`)
4. Agent creates the next file, imports from the first
5. Agent tests the integration
6. Agent continues until all PRD requirements are implemented

The key advantage over Plan-and-Execute: each file is created **after** the agent has seen what the previous files actually contain. No cross-file inconsistency because the agent reads before it writes.

### Lightweight Intent Preview (Optional)

For user transparency, the agent can optionally produce a lightweight "intent preview" before starting work:

```
Before implementing, I'll outline my approach:

Files to create:
- main.py: CLI entry point with argparse
- models.py: Task data model with SQLite persistence
- commands.py: Add, list, complete command handlers
- tests/test_commands.py: Unit tests for each command

I'll start with the data model, then build commands on top, and add the CLI last.
```

This is NOT a rigid plan. It's a quick outline the agent generates in its first "think" step. The agent can deviate as it learns more during execution.

Implementation: The system prompt includes "Before making any changes, briefly outline the files you plan to create and their purposes." The agent's first text response serves as the preview. This requires no code changes -- it's just prompt engineering.

### File Creation Strategy

For new files, the agent uses `create_file` with complete content. This is appropriate because:
- There's no existing content to diff against
- Search-replace doesn't apply to empty files
- The agent can still read the created file afterward to verify its content

For files that grow during execution (e.g., adding new functions), the agent switches to `edit_file` after the initial creation. This prevents the whole-file overwrite problem.

### Cross-File Consistency for Generated Projects

The main risk with new project generation is inconsistency between files (e.g., `main.py` imports from `models.py`, but `models.py` doesn't export the expected symbol).

Mitigations:

1. **Read-before-import**: The system prompt says "before importing from a file you created, read it to verify the exports match what you expect."

2. **Test after each file**: Running `python -c "from models import Task"` after creating `models.py` catches import issues immediately.

3. **Incremental verification**: Auto-lint catches missing imports, undefined names, and syntax errors after every file creation.

4. **Small files**: The agent is instructed to create small, focused files. A 50-line file is far less likely to have internal inconsistencies than a 500-line file.

---

## Appendix A: Module Dependency Graph

```
react_agent.py
    ├── tools.py
    │   ├── editor.py (for edit_file)
    │   ├── context.py (for read_file, list_files)
    │   ├── executor.py (for run_command)
    │   └── gates.py (for run_tests)
    ├── context.py (for initial context loading)
    ├── fix_tracker.py (for escalation detection)
    ├── quick_fixes.py (for pattern-based auto-fixes)
    ├── blockers.py (for blocker creation)
    ├── events.py (for event emission)
    └── adapters/llm/base.py (for LLM calls with tool-use)
```

## Appendix B: Conversation Message Format

Each turn in the conversation follows the Anthropic API message format:

```python
# User message (initial)
{"role": "user", "content": "Execute this task: ..."}

# Assistant message (with tool calls)
{
    "role": "assistant",
    "content": "I'll start by reading the existing code.",  # thinking text
    "tool_calls": [
        {"id": "tc_1", "name": "read_file", "input": {"path": "main.py"}}
    ]
}

# User message (tool results)
{
    "role": "user",
    "tool_results": [
        {"tool_call_id": "tc_1", "content": "# main.py\nimport sys\n..."}
    ]
}

# Assistant message (next action)
{
    "role": "assistant",
    "content": "I see the main module. I need to add the CLI parser.",
    "tool_calls": [
        {"id": "tc_2", "name": "edit_file", "input": {"path": "main.py", "edits": [...]}}
    ]
}
```

## Appendix C: Configuration

```python
# Environment variables for ReactAgent tuning
CODEFRAME_REACT_MAX_ITERATIONS = 30          # Hard cap on loop iterations
CODEFRAME_REACT_SELF_CORRECTION_CAP = 5      # Max retries for same error
CODEFRAME_REACT_COMPACT_THRESHOLD = 0.85     # Compact at 85% context usage
CODEFRAME_REACT_AUTO_LINT = true             # Auto-run ruff after edits
CODEFRAME_REACT_MAX_OUTPUT_CHARS = 4000      # Truncate tool output
```

These are configurable but have sensible defaults that should rarely need changing.
