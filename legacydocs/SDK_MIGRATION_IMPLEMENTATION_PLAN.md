# Claude Agent SDK Migration - Implementation Plan

**Author**: Claude Code
**Date**: 2025-11-28
**Version**: 1.1
**Status**: READY FOR IMPLEMENTATION - All open questions resolved
**SDK Documentation**: [GitHub](https://github.com/anthropics/claude-agent-sdk-python) | [PyPI](https://pypi.org/project/claude-agent-sdk/)

---

## Executive Summary

This document provides a detailed implementation plan for migrating CodeFRAME to leverage the Claude Agent SDK, based on the recommendations in [SDK_OVERLAP_ANALYSIS.md](SDK_OVERLAP_ANALYSIS.md).

### Key Adjustments from Initial Analysis

During implementation planning, several findings required adjustments to the original recommendations:

| Finding | Original Assumption | Actual State | Impact |
|---------|---------------------|--------------|--------|
| Token Extraction | "Manual extraction needed refactoring" | Already uses `response.usage.input_tokens/output_tokens` pattern | **Simpler than expected** - minimal changes |
| Agent Definitions | "YAML → Markdown migration" | YAML includes maturity levels, error recovery, integration points | **More complex** - hybrid approach mandatory |
| API Patterns | "Single pattern to migrate" | Both sync (AnthropicProvider) AND async (AsyncAnthropic) | **Two migration paths needed** |
| Tool Framework | "Replace 500-700 lines" | Tools tightly integrated with quality gates, context management | **More careful extraction required** |

### Migration Complexity Assessment

| Phase | Original Estimate | Revised Estimate | Risk Level |
|-------|-------------------|------------------|------------|
| Phase 1: Foundation | 1-2 weeks | 1 week | Low |
| Phase 2: Tool Framework | 3-4 weeks | 3-4 weeks | Medium-High |
| Phase 3: Agent Pattern | 5-6 weeks | 4-6 weeks | Medium |
| Phase 4: Streaming | 7-8 weeks | 2-3 weeks | Low |
| Phase 5: Optimization | Ongoing | Ongoing | Low |

---

## Pre-Migration Requirements (RESOLVED)

All blocking questions have been answered through SDK documentation review.

### ✅ RESOLVED: SDK Package & Installation

**Package**: `claude-agent-sdk` (v0.1.10 as of Nov 2025)

```bash
pip install claude-agent-sdk
```

**Requirements**: Python 3.10+ (CodeFRAME uses 3.11+, compatible)

**Key imports**:
```python
from claude_agent_sdk import query, ClaudeSDKClient, ClaudeAgentOptions, HookMatcher
from claude_agent_sdk import create_sdk_mcp_server  # For custom tools
```

### ✅ RESOLVED: Async Support

**Answer**: The SDK is **fully async**. All operations use `async/await`.

```python
import anyio
from claude_agent_sdk import query

async def main():
    async for message in query(prompt="What is 2 + 2?"):
        print(message)

anyio.run(main)
```

**Impact**: CodeFRAME's async patterns (FrontendWorkerAgent, TestWorkerAgent) align well. The sync `AnthropicProvider` will need to be wrapped in the SDK client or converted to async.

### ✅ RESOLVED: Hook API Signatures

**PreToolUse Hook** - Called before tool execution:

```python
async def pre_tool_hook(input_data: dict, tool_use_id: str, context: dict) -> dict:
    """
    Args:
        input_data: {"tool_name": str, "tool_input": dict}
        tool_use_id: Unique identifier for this tool call
        context: Additional context from SDK

    Returns:
        {} to allow execution, or:
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Reason for blocking"
            }
        }
    """
    if input_data["tool_name"] == "Bash":
        command = input_data["tool_input"].get("command", "")
        if "rm -rf" in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Dangerous command blocked"
                }
            }
    return {}

# Registration
options = ClaudeAgentOptions(
    hooks={
        'PreToolUse': [HookMatcher(matcher='Bash', hooks=[pre_tool_hook])]
    }
)
```

**PostToolUse Hook** - Called after tool execution:

```python
async def post_tool_hook(input_data: dict, tool_use_id: str, context: dict) -> dict:
    """Same signature as PreToolUse, called after execution."""
    # Log tool usage, record metrics, etc.
    return {}
```

**Supported Hooks**: PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop, PreCompact

**Note**: SessionStart, SessionEnd, Notification hooks are NOT supported in Python SDK.

### ✅ RESOLVED: Subagent Spawning

**Two methods to define subagents**:

1. **Programmatic** (recommended for SDK applications):
```python
# Via agents parameter in query() options
async for message in query(
    prompt="Build a React component",
    agents=[
        {
            "name": "frontend-dev",
            "description": "React/TypeScript specialist",
            "tools": ["Read", "Write", "Bash"],
            "system_prompt": "You are a frontend developer..."
        }
    ]
):
    print(message)
```

2. **Filesystem-based**:
```markdown
<!-- .claude/agents/backend.md -->
---
name: Backend Developer
description: Python/FastAPI specialist
tools: [Read, Write, Bash, Grep]
---

You are a backend developer agent...
```

**Key constraints**:
- Subagents use the Task tool internally
- **Cannot spawn nested subagents** (prevents infinite recursion)
- Subagents maintain separate context from main agent
- Up to 10 concurrent subagents supported

**Impact on CodeFRAME**: The `agents` parameter approach aligns with our hybrid strategy - generate subagent configs from YAML at runtime.

---

## Phase 1: Foundation (Week 1)

### Overview
Low-risk, high-value changes that establish SDK integration patterns without disrupting existing functionality.

### Task 1.1: Add SDK Dependency

**Files to modify**: `pyproject.toml`

```toml
# Add to dependencies section (line ~25)
dependencies = [
    "anthropic>=0.18.0",  # Keep existing - SDK uses this internally
    "claude-agent-sdk>=0.1.10",  # Add SDK
    # ... rest unchanged
]
```

**Verification**:
```python
# Test import after installation
from claude_agent_sdk import query, ClaudeSDKClient, ClaudeAgentOptions
print("SDK imported successfully")
```

**Acceptance Criteria**:
- [ ] `pip install claude-agent-sdk>=0.1.10` succeeds
- [ ] `from claude_agent_sdk import query` works
- [ ] No conflicts with existing `anthropic>=0.18.0` package
- [ ] Tests still pass after adding dependency

**Estimated effort**: 1 hour
**Risk**: Very Low

---

### Task 1.2: Create SDK Integration Module

**New file**: `codeframe/providers/sdk_client.py`

**Purpose**: Abstract SDK interaction behind CodeFRAME interfaces, allowing gradual migration.

```python
"""SDK Integration Layer.

Provides CodeFRAME-compatible wrapper around Claude Agent SDK,
supporting gradual migration from direct Anthropic API usage.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
import logging
import os

# SDK imports (verified from documentation)
try:
    from claude_agent_sdk import (
        query,
        ClaudeSDKClient,
        ClaudeAgentOptions,
        HookMatcher,
    )
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

from codeframe.providers.anthropic import AnthropicProvider

logger = logging.getLogger(__name__)


class SDKClientWrapper:
    """Wrapper providing CodeFRAME-compatible interface to SDK.

    This class bridges the gap between CodeFRAME's existing patterns
    and the Claude Agent SDK, enabling incremental migration.

    The SDK requires ANTHROPIC_API_KEY environment variable to be set.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        cwd: Optional[str] = None,
        hooks: Optional[Dict] = None,
        permission_mode: str = "default",  # or "acceptEdits"
    ):
        # Ensure API key is in environment (SDK reads from env)
        if api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = api_key

        if not SDK_AVAILABLE:
            logger.warning("Claude Agent SDK not available, falling back to AnthropicProvider")
            self._use_sdk = False
            self._fallback = AnthropicProvider(api_key=api_key, model=model)
            self._options = None
            return

        self._use_sdk = True
        self._fallback = None

        # Build SDK options
        self._options = ClaudeAgentOptions(
            system_prompt=system_prompt or "",
            allowed_tools=allowed_tools or ["Read", "Write", "Bash", "Glob", "Grep"],
            max_turns=50,
            cwd=cwd or str(Path.cwd()),
            permission_mode=permission_mode,
            hooks=hooks or {},
        )

        logger.info(f"SDK client initialized (cwd={cwd}, tools={allowed_tools})")

    async def send_message(
        self,
        conversation: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Send message using SDK or fallback.

        Returns same format as AnthropicProvider.send_message() for compatibility.

        Note: SDK streams responses, so we collect all chunks into final response.
        """
        if not self._use_sdk:
            # Fallback to existing provider (sync, needs wrapper)
            import asyncio
            return await asyncio.to_thread(
                self._fallback.send_message, conversation
            )

        # SDK path - extract last user message
        last_message = conversation[-1]["content"]

        # Collect streamed response
        full_content = []
        usage_info = {"input_tokens": 0, "output_tokens": 0}
        stop_reason = None

        async for message in query(prompt=last_message, options=self._options):
            if hasattr(message, 'content'):
                full_content.append(str(message.content))
            if hasattr(message, 'usage'):
                usage_info["input_tokens"] = getattr(message.usage, 'input_tokens', 0)
                usage_info["output_tokens"] = getattr(message.usage, 'output_tokens', 0)
            if hasattr(message, 'stop_reason'):
                stop_reason = message.stop_reason

        return {
            "content": "".join(full_content),
            "stop_reason": stop_reason or "end_turn",
            "usage": usage_info,
        }

    async def send_message_streaming(
        self,
        prompt: str,
    ):
        """Send message and yield streaming responses.

        Yields SDK message objects for real-time processing.
        """
        if not self._use_sdk:
            raise RuntimeError("Streaming requires SDK - not available in fallback mode")

        async for message in query(prompt=prompt, options=self._options):
            yield message
```

**Acceptance Criteria**:
- [ ] Wrapper works with SDK when available
- [ ] Graceful fallback to AnthropicProvider when SDK unavailable
- [ ] Returns compatible response format
- [ ] Session ID captured for future use

**Estimated effort**: 4 hours
**Risk**: Low
**Dependencies**: Task 1.1

---

### Task 1.3: Token Tracking Enhancement

**Finding**: Current code already uses `response.usage.input_tokens/output_tokens` pattern. Minimal changes needed.

**Files to review**:
- `codeframe/providers/anthropic.py:101-107` - Already extracts tokens correctly
- `codeframe/lib/metrics_tracker.py` - No changes needed

**Changes required**:
1. Update `MetricsTracker.record_token_usage()` to accept optional `session_id`
2. Add `session_id` column to `token_usage` table (new migration)

**File to modify**: `codeframe/lib/metrics_tracker.py`

```python
# Add session_id parameter to record_token_usage()
async def record_token_usage(
    self,
    task_id: int,
    agent_id: str,
    project_id: int,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    call_type: str = "task_execution",
    session_id: Optional[str] = None,  # NEW: SDK session tracking
) -> None:
    # ... existing logic unchanged
```

**New migration file**: `codeframe/persistence/migrations/008_add_session_id.py`

```python
"""Add session_id column to token_usage table."""

async def upgrade(db):
    await db.execute("""
        ALTER TABLE token_usage
        ADD COLUMN session_id TEXT DEFAULT NULL
    """)

async def downgrade(db):
    # SQLite doesn't support DROP COLUMN easily
    pass
```

**Acceptance Criteria**:
- [ ] Session ID stored with token usage records
- [ ] Existing token tracking continues to work
- [ ] Migration applies cleanly

**Estimated effort**: 2 hours
**Risk**: Very Low

---

### Task 1.4: Session ID Storage Integration

**Files to modify**:
- `codeframe/core/session_manager.py`

**Changes**:
Add SDK session ID to session state for conversation resume capability.

```python
# session_state.json schema addition
{
    "last_session": { ... },
    "next_actions": [ ... ],
    "current_plan": "...",
    "active_blockers": [ ... ],
    "progress_pct": 68.5,
    "sdk_sessions": {  # NEW
        "lead_agent": "session_abc123",
        "backend-001": "session_def456",
    }
}
```

**Acceptance Criteria**:
- [ ] Session IDs stored per-agent
- [ ] Session IDs preserved across CLI restarts
- [ ] Compatible with existing session_state.json format

**Estimated effort**: 2 hours
**Risk**: Very Low

---

### Phase 1 Deliverables Summary

| Task | New Files | Modified Files | Lines Changed | Test Coverage |
|------|-----------|----------------|---------------|---------------|
| 1.1 SDK Dependency | - | `pyproject.toml` | ~2 | N/A |
| 1.2 SDK Integration Module | `providers/sdk_client.py` | - | ~80 | Unit tests |
| 1.3 Token Tracking | `migrations/008_*.py` | `metrics_tracker.py` | ~20 | Existing tests |
| 1.4 Session ID Storage | - | `session_manager.py` | ~15 | Unit tests |

**Total estimated effort**: 1 week
**Go/No-Go criteria**: All tasks complete, tests passing, SDK import verified

---

## Phase 2: Tool Framework Migration (Weeks 2-4)

### Overview
Replace manual tool execution with SDK's native tool framework while preserving quality gate integration.

### ARCHITECTURE DECISION REQUIRED

> **Critical Decision**: How to integrate SDK tools with CodeFRAME's quality gates?
>
> **Option A**: Pre-tool hooks
> - SDK's `PreToolUse` hook checks quality gates before tool execution
> - Pro: Clean integration
> - Con: May not have enough context to make decisions
>
> **Option B**: Wrapper tools
> - Create MCP tools that wrap quality checks + actual tool
> - Pro: Full control over execution
> - Con: More complex, duplicates SDK tools
>
> **Option C**: Post-tool validation
> - Let tools execute, validate results before committing
> - Pro: Simpler implementation
> - Con: Work may be wasted on failed validation
>
> **Recommendation**: Option A (Pre-tool hooks) with Option C fallback

---

### Task 2.1: Create CodeFRAME Tool Hooks

**New file**: `codeframe/lib/sdk_hooks.py`

```python
"""SDK Hook Implementations for CodeFRAME Integration.

These hooks integrate CodeFRAME's quality gates and metrics tracking
with the Claude Agent SDK's tool execution framework.

SDK Hook Signature (verified from documentation):
    async def hook(input_data: dict, tool_use_id: str, context: dict) -> dict

    input_data contains: {"tool_name": str, "tool_input": dict}

    Return {} to allow, or return blocking response:
    {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "Reason"
        }
    }
"""

from typing import Dict, Any, Optional
import logging

from claude_agent_sdk import HookMatcher

logger = logging.getLogger(__name__)


async def create_quality_gate_pre_hook(quality_gates, db):
    """Factory to create pre-tool hook with quality gate integration.

    Args:
        quality_gates: QualityGates instance
        db: Database connection for task status lookup

    Returns:
        Async hook function with correct SDK signature
    """
    async def quality_gate_pre_hook(
        input_data: dict,
        tool_use_id: str,
        context: dict,
    ) -> dict:
        """PreToolUse hook that blocks tools when quality gates fail.

        SDK calls this before every tool execution.
        """
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Check for protected files on Write operations
        if tool_name == "Write":
            file_path = tool_input.get("file_path", "")
            protected = [".env", "credentials.json", ".git/", "secrets"]
            if any(p in file_path for p in protected):
                logger.warning(f"Blocked write to protected file: {file_path}")
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Cannot modify protected file: {file_path}"
                    }
                }

        # Check for dangerous bash commands
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            dangerous_patterns = ["rm -rf /", "rm -rf ~", ":(){ :|:& };:", "dd if="]
            if any(pattern in command for pattern in dangerous_patterns):
                logger.warning(f"Blocked dangerous command: {command[:50]}...")
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "Dangerous command blocked by safety policy"
                    }
                }

        # Allow tool execution
        return {}

    return quality_gate_pre_hook


async def create_metrics_post_hook(metrics_tracker, db):
    """Factory to create post-tool hook for metrics tracking.

    Args:
        metrics_tracker: MetricsTracker instance
        db: Database connection

    Returns:
        Async hook function with correct SDK signature
    """
    async def metrics_post_hook(
        input_data: dict,
        tool_use_id: str,
        context: dict,
    ) -> dict:
        """PostToolUse hook that records tool usage metrics.

        SDK calls this after every tool execution.
        """
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Record tool usage for analytics
        logger.debug(f"Tool executed: {tool_name} (id={tool_use_id})")

        # If Write tool, trigger quality checks
        if tool_name == "Write":
            file_path = tool_input.get("file_path", "")
            logger.info(f"File written: {file_path} - quality check triggered")
            # Quality check logic would go here

        return {}

    return metrics_post_hook


def build_codeframe_hooks(quality_gates, metrics_tracker, db) -> dict:
    """Build SDK hooks dictionary for CodeFRAME integration.

    Returns hooks dict ready for ClaudeAgentOptions.

    Usage:
        hooks = build_codeframe_hooks(quality_gates, metrics_tracker, db)
        options = ClaudeAgentOptions(hooks=hooks, ...)
    """
    import asyncio

    # Create hook functions
    pre_hook = asyncio.get_event_loop().run_until_complete(
        create_quality_gate_pre_hook(quality_gates, db)
    )
    post_hook = asyncio.get_event_loop().run_until_complete(
        create_metrics_post_hook(metrics_tracker, db)
    )

    return {
        'PreToolUse': [
            HookMatcher(matcher='Write', hooks=[pre_hook]),
            HookMatcher(matcher='Bash', hooks=[pre_hook]),
        ],
        'PostToolUse': [
            HookMatcher(matcher='Write', hooks=[post_hook]),
            HookMatcher(matcher='Bash', hooks=[post_hook]),
        ],
    }
```

**Known Issue**: GitHub issues [#193](https://github.com/anthropics/claude-agent-sdk-python/issues/193) and [#213](https://github.com/anthropics/claude-agent-sdk-python/issues/213) report hooks not triggering in some cases. Test thoroughly and have fallback validation.

**Acceptance Criteria**:
- [ ] Pre-hook blocks tool execution for blocked tasks
- [ ] Pre-hook prevents modification of protected files
- [ ] Post-hook records metrics
- [ ] Post-hook triggers quality checks after writes

**Estimated effort**: 1 week
**Risk**: Medium - requires SDK hook API verification

---

### Task 2.2: Migrate File Operations

**Current implementation**: Direct `pathlib.Path` operations scattered across agents

**Target**: SDK's native `Read` and `Write` tools

**Files to modify**:
- `codeframe/agents/worker_agent.py`
- `codeframe/agents/backend_worker_agent.py`
- `codeframe/agents/frontend_worker_agent.py`

**Migration pattern**:

```python
# BEFORE (in agent code)
from pathlib import Path

async def _write_generated_code(self, file_path: str, content: str):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

# AFTER (SDK tool execution)
# File operations handled by SDK via tool calls
# Agent prompts include tool instructions, SDK executes

async def execute_task(self, task: Task):
    response = await self.sdk_client.query(
        f"Implement the following task:\n{task.description}\n\n"
        f"Use the Write tool to save your implementation."
    )
```

**Acceptance Criteria**:
- [ ] File operations use SDK tools
- [ ] Directory creation handled by SDK
- [ ] Atomic writes preserved
- [ ] Error handling maintained

**Estimated effort**: 1 week
**Risk**: Medium

---

### Task 2.3: Migrate Bash/Subprocess Operations

**Current implementation**: `subprocess.run()` in `TestRunner`, various agents

**Target**: SDK's native `Bash` tool

**Files to modify**:
- `codeframe/testing/test_runner.py`
- `codeframe/agents/test_worker_agent.py`

**ISSUE IDENTIFIED**: Current `TestRunner` parses pytest JSON output directly. SDK's Bash tool returns string output.

**Migration approach**:
1. Keep `TestRunner` for complex pytest orchestration
2. Expose simplified test execution via SDK Bash tool
3. Use SDK for simple commands (git, npm, ruff)

```python
# TestRunner stays for complex pytest workflows
class TestRunner:
    """Complex test orchestration - NOT migrated to SDK."""
    async def run_tests(self, ...):
        # Keep existing subprocess.run() logic
        # JSON parsing, result aggregation, etc.

# Simple commands migrate to SDK
# In agent prompts:
# "Run `ruff check {file}` to lint the code"
# SDK executes via Bash tool
```

**Acceptance Criteria**:
- [ ] Simple bash commands use SDK
- [ ] Complex pytest orchestration preserved
- [ ] Git operations work via SDK
- [ ] Output parsing maintained where needed

**Estimated effort**: 1 week
**Risk**: Medium - need to balance SDK simplicity with current functionality

---

### Task 2.4: Create Quality Gate MCP Tool

**Purpose**: Expose quality gates as MCP tool for SDK to invoke

**New file**: `codeframe/mcp/quality_gate_tool.py`

```python
"""MCP Tool exposing CodeFRAME Quality Gates.

Allows SDK-based agents to invoke quality gate checks.
"""

from typing import Dict, Any


async def run_quality_gates(
    task_id: int,
    project_id: int,
    checks: list = None,  # ["tests", "types", "coverage", "review"]
) -> Dict[str, Any]:
    """Run quality gate checks for a task.

    Args:
        task_id: Task to check
        project_id: Project context
        checks: Optional list of specific checks to run

    Returns:
        {
            "status": "passed" | "failed",
            "checks": {
                "tests": {"passed": True, "details": "..."},
                "types": {"passed": True, "details": "..."},
                "coverage": {"passed": True, "percentage": 87.5},
                "review": {"passed": True, "issues": []},
            },
            "blocking_failures": [...]
        }
    """
    # Implementation uses existing QualityGates class
    pass
```

**Acceptance Criteria**:
- [ ] Quality gates invocable as MCP tool
- [ ] Returns structured results
- [ ] Integrates with existing quality gate infrastructure

**Estimated effort**: 3 days
**Risk**: Low

---

### Phase 2 Deliverables Summary

| Task | New Files | Modified Files | Lines Changed | Dependencies |
|------|-----------|----------------|---------------|--------------|
| 2.1 Tool Hooks | `lib/sdk_hooks.py` | - | ~150 | Phase 1 |
| 2.2 File Operations | - | `agents/*.py` | ~200 | Task 2.1 |
| 2.3 Bash Operations | - | `testing/test_runner.py` | ~100 | Task 2.1 |
| 2.4 Quality Gate MCP | `mcp/quality_gate_tool.py` | - | ~80 | Task 2.1 |

**Total estimated effort**: 3 weeks
**Go/No-Go criteria**: All file/bash operations work, quality gates still block bad code

---

## Phase 3: Agent Pattern Migration (Weeks 5-8)

### Overview
Adopt SDK's subagent pattern while preserving CodeFRAME's unique features (maturity levels, project scoping).

### ARCHITECTURE DECISION REQUIRED

> **Critical Decision**: How to preserve maturity levels with SDK subagents?
>
> **Option A**: Maturity in system prompt
> - Different markdown files for each maturity level (backend-d1.md, backend-d2.md, etc.)
> - Pro: Clean SDK integration
> - Con: File proliferation (4 files per agent type)
>
> **Option B**: Dynamic prompt injection
> - Single markdown file, inject maturity instructions at runtime
> - Pro: Fewer files
> - Con: Less visible configuration
>
> **Option C**: Keep YAML + SDK hybrid
> - YAML for maturity/advanced config, SDK for execution
> - Pro: Preserves current configuration richness
> - Con: Two definition systems to maintain
>
> **Recommendation**: Option C (Hybrid) - YAML remains source of truth, generates SDK-compatible prompts

---

### Task 3.1: Create Subagent Markdown Generator

**Purpose**: Generate SDK-compatible markdown from YAML definitions

**New file**: `codeframe/agents/subagent_generator.py`

```python
"""Generate SDK subagent markdown from YAML definitions.

Preserves CodeFRAME's rich agent configurations while enabling
SDK subagent execution.
"""

from pathlib import Path
from typing import Optional
import logging

from codeframe.agents.definition_loader import AgentDefinitionLoader, AgentDefinition

logger = logging.getLogger(__name__)


class SubagentGenerator:
    """Generates SDK-compatible subagent markdown from YAML."""

    def __init__(self, definitions_dir: Path):
        self.loader = AgentDefinitionLoader()
        self.loader.load_definitions(definitions_dir)
        self.output_dir = Path(".claude/agents")

    def generate_all(self, maturity: str = "D2") -> None:
        """Generate markdown for all agent types at specified maturity."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        for agent_type in self.loader.list_available_types():
            self.generate_agent(agent_type, maturity)

    def generate_agent(self, agent_type: str, maturity: str = "D2") -> Path:
        """Generate markdown for a specific agent.

        Args:
            agent_type: Agent type name from YAML
            maturity: Maturity level (D1, D2, D3, D4)

        Returns:
            Path to generated markdown file
        """
        definition = self.loader.get_definition(agent_type)

        # Generate SDK-compatible markdown
        content = self._build_markdown(definition, maturity)

        output_path = self.output_dir / f"{agent_type}.md"
        output_path.write_text(content)

        logger.info(f"Generated subagent: {output_path}")
        return output_path

    def _build_markdown(self, definition: AgentDefinition, maturity: str) -> str:
        """Build SDK subagent markdown from definition."""
        # Get maturity-specific capabilities
        maturity_config = self._get_maturity_config(definition, maturity)

        # Build tool list from definition
        tools = self._map_tools_to_sdk(definition.tools)

        return f"""---
name: {definition.name}
description: {definition.description.strip().split(chr(10))[0]}
tools: {tools}
---

{definition.system_prompt}

## Maturity Level: {maturity}
{maturity_config.get('description', '')}

### Capabilities at this level:
{self._format_capabilities(maturity_config.get('capabilities', []))}

## Error Recovery
- Max correction attempts: {definition.constraints.get('max_correction_attempts', 3)}
- Escalation: Create blocker for manual intervention
"""

    def _get_maturity_config(self, definition: AgentDefinition, maturity: str) -> dict:
        """Extract maturity-specific configuration."""
        # Parse maturity_progression from definition
        for level in definition.raw.get('maturity_progression', []):
            if level.get('level') == maturity:
                return level
        return {}

    def _map_tools_to_sdk(self, yaml_tools: list) -> list:
        """Map YAML tool names to SDK tool names."""
        mapping = {
            'file_operations': ['Read', 'Write'],
            'anthropic_api': [],  # Implicit in SDK
            'codebase_index': ['Glob', 'Grep'],
            'test_runner': ['Bash'],
            'git_operations': ['Bash'],
            'database': [],  # CodeFRAME internal
        }

        sdk_tools = set()
        for tool in yaml_tools:
            sdk_tools.update(mapping.get(tool, []))

        return sorted(list(sdk_tools))

    def _format_capabilities(self, capabilities: list) -> str:
        """Format capability list for markdown."""
        return '\n'.join(f'- {cap}' for cap in capabilities)
```

**Acceptance Criteria**:
- [ ] Generates valid SDK markdown from YAML
- [ ] Includes maturity-specific instructions
- [ ] Maps tools correctly
- [ ] Output in `.claude/agents/` directory

**Estimated effort**: 1 week
**Risk**: Low

---

### Task 3.2: Hybrid Agent Wrapper

**Purpose**: Allow gradual migration - use SDK execution with CodeFRAME coordination

**New file**: `codeframe/agents/hybrid_worker.py`

```python
"""Hybrid Worker Agent.

Uses SDK for task execution while preserving CodeFRAME's
coordination, context management, and quality gates.
"""

from typing import Optional, Dict, Any
import logging

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.providers.sdk_client import SDKClientWrapper
from codeframe.lib.context_manager import ContextManager

logger = logging.getLogger(__name__)


class HybridWorkerAgent(WorkerAgent):
    """Worker agent using SDK for execution, CodeFRAME for coordination."""

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        project_id: int,
        db,
        sdk_client: SDKClientWrapper,
        context_manager: ContextManager,
        **kwargs
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=agent_type,
            project_id=project_id,
            db=db,
            **kwargs
        )
        self.sdk_client = sdk_client
        self.context_manager = context_manager

    async def execute_task(self, task) -> Dict[str, Any]:
        """Execute task using SDK with CodeFRAME coordination.

        1. Load context from tiered memory
        2. Build prompt with context
        3. Execute via SDK
        4. Save results to context
        5. Run quality gates
        6. Return result
        """
        # 1. Load context
        hot_context = await self.load_context(tier="hot")
        warm_context = await self.load_context(tier="warm", limit=20)

        # 2. Build prompt
        prompt = self._build_execution_prompt(task, hot_context, warm_context)

        # 3. Execute via SDK
        response = await self.sdk_client.send_message([
            {"role": "user", "content": prompt}
        ])

        # 4. Save to context
        await self.save_context_item(
            item_type="TASK_RESULT",
            content=f"Task {task.id}: {response['content'][:500]}..."
        )

        # 5. Quality gates (existing logic)
        gate_result = await self._run_quality_gates(task)
        if not gate_result.passed:
            return {"status": "blocked", "failures": gate_result.failures}

        # 6. Return result
        return {
            "status": "completed",
            "content": response["content"],
            "usage": response["usage"],
            "session_id": response.get("session_id"),
        }

    def _build_execution_prompt(self, task, hot_context, warm_context) -> str:
        """Build prompt with context and task."""
        context_str = "\n".join([
            f"[{item.item_type}] {item.content}"
            for item in hot_context + warm_context
        ])

        return f"""## Context
{context_str}

## Task
{task.title}

{task.description}

## Instructions
Complete this task using the available tools. Follow the coding standards
and patterns established in the codebase.
"""
```

**Acceptance Criteria**:
- [ ] HybridWorkerAgent extends WorkerAgent
- [ ] Uses SDK for execution
- [ ] Preserves context management
- [ ] Maintains quality gate integration

**Estimated effort**: 1 week
**Risk**: Medium

---

### Task 3.3: Update AgentPoolManager

**Files to modify**: `codeframe/agents/agent_pool_manager.py`

**Changes**:
- Add option to create HybridWorkerAgent vs traditional WorkerAgent
- Configure SDK client per agent
- Preserve existing pooling logic

**Acceptance Criteria**:
- [ ] Pool supports both agent types
- [ ] Feature flag for SDK vs traditional
- [ ] Existing tests continue to pass

**Estimated effort**: 3 days
**Risk**: Low

---

### Task 3.4: Update LeadAgent Coordination

**Files to modify**: `codeframe/agents/lead_agent.py`

**Changes**:
- Coordinate HybridWorkerAgents
- Handle SDK session resumption
- Preserve existing orchestration logic

**Acceptance Criteria**:
- [ ] LeadAgent works with hybrid agents
- [ ] Session IDs propagated correctly
- [ ] Multi-agent coordination preserved

**Estimated effort**: 1 week
**Risk**: Medium

---

### Phase 3 Deliverables Summary

| Task | New Files | Modified Files | Lines Changed |
|------|-----------|----------------|---------------|
| 3.1 Subagent Generator | `agents/subagent_generator.py` | - | ~150 |
| 3.2 Hybrid Worker | `agents/hybrid_worker.py` | - | ~120 |
| 3.3 Pool Manager | - | `agents/agent_pool_manager.py` | ~50 |
| 3.4 LeadAgent | - | `agents/lead_agent.py` | ~80 |

**Total estimated effort**: 4 weeks
**Go/No-Go criteria**: Agents execute via SDK, coordination preserved, maturity levels honored

---

## Phase 4: Streaming Integration (Weeks 9-10)

### Overview
Integrate SDK streaming for real-time Claude responses while preserving custom WebSocket events.

### Task 4.1: SDK Streaming Adapter

**New file**: `codeframe/ui/sdk_streaming.py`

```python
"""SDK Streaming to WebSocket Bridge.

Converts SDK streaming responses to CodeFRAME WebSocket format.
"""

from typing import AsyncIterator, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SDKStreamingBridge:
    """Bridges SDK streaming to CodeFRAME WebSocket broadcasts."""

    def __init__(self, connection_manager):
        self.connection_manager = connection_manager

    async def stream_response(
        self,
        sdk_stream: AsyncIterator,
        project_id: int,
        agent_id: str,
        task_id: int,
    ):
        """Stream SDK response to WebSocket clients.

        Args:
            sdk_stream: Async iterator from SDK
            project_id: Project context
            agent_id: Agent generating response
            task_id: Task being executed
        """
        full_content = []

        async for message in sdk_stream:
            if message.type == "assistant":
                # Emit partial update
                await self.connection_manager.broadcast({
                    "type": "agent_response_chunk",
                    "project_id": project_id,
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "content": message.content,
                    "is_final": False,
                })
                full_content.append(message.content)

            elif message.type == "tool_use":
                # Emit tool invocation event
                await self.connection_manager.broadcast({
                    "type": "tool_invoked",
                    "project_id": project_id,
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "tool_name": message.tool_name,
                    "tool_input": message.tool_input,
                })

        # Emit final message
        await self.connection_manager.broadcast({
            "type": "agent_response_complete",
            "project_id": project_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "content": "".join(full_content),
            "is_final": True,
        })
```

**Acceptance Criteria**:
- [ ] SDK stream converted to WebSocket events
- [ ] Tool invocations broadcast
- [ ] Final response assembled and broadcast

**Estimated effort**: 3 days
**Risk**: Low

---

### Task 4.2: Frontend Streaming Support

**Files to modify**: `web-ui/src/contexts/AgentStateContext.ts`

**Changes**:
- Add handlers for streaming event types
- Update UI for progressive content display

**Acceptance Criteria**:
- [ ] Frontend handles streaming events
- [ ] Progressive response display
- [ ] Tool invocation visibility

**Estimated effort**: 1 week
**Risk**: Low

---

### Phase 4 Deliverables Summary

| Task | New Files | Modified Files |
|------|-----------|----------------|
| 4.1 Streaming Bridge | `ui/sdk_streaming.py` | - |
| 4.2 Frontend Support | - | `web-ui/src/contexts/*.ts` |

**Total estimated effort**: 2 weeks
**Go/No-Go criteria**: Streaming works end-to-end, dashboard updates in real-time

---

## Phase 5: Optimization (Ongoing)

### Task 5.1: Context Compaction Fallback

**Purpose**: Use SDK compaction as backup when flash save is insufficient

**Files to modify**: `codeframe/lib/context_manager.py`

**Changes**:
- Add SDK compaction as fallback after flash save
- Trigger when token usage still too high after flash save

**Estimated effort**: 2 days

---

### Task 5.2: Expose Quality Gates as MCP Server

**Purpose**: Allow SDK users to invoke CodeFRAME quality gates

**New file**: `codeframe/mcp/codeframe_server.py`

```python
"""CodeFRAME MCP Server.

Exposes CodeFRAME capabilities as MCP tools for SDK integration.
"""

# Tools to expose:
# - run_quality_gates(task_id, project_id)
# - create_checkpoint(name, description)
# - restore_checkpoint(checkpoint_id)
# - get_context_stats(agent_id, project_id)
```

**Estimated effort**: 1 week

---

### Task 5.3: Monitor SDK Updates

**Ongoing activities**:
- Track SDK releases for new features
- Evaluate new tools for adoption
- Update integration as SDK evolves

---

## Resolved Questions

All previously open questions have been answered. See "Pre-Migration Requirements (RESOLVED)" section for details.

| ID | Question | Answer | Source |
|----|----------|--------|--------|
| OPEN-001 | SDK package name? | `pip install claude-agent-sdk` (v0.1.10+) | [PyPI](https://pypi.org/project/claude-agent-sdk/) |
| OPEN-002 | Async support? | **Yes** - fully async with `async for` streaming | [GitHub README](https://github.com/anthropics/claude-agent-sdk-python) |
| OPEN-003 | Hook signatures? | `async def hook(input_data, tool_use_id, context) -> dict` | [GitHub examples](https://github.com/anthropics/claude-agent-sdk-python) |
| OPEN-004 | Subagent spawning? | Via `agents` parameter in `query()` or `.claude/agents/*.md` files | [Subagents docs](https://docs.claude.com/en/docs/agent-sdk/subagents) |

### NEW: Known Limitations Discovered

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Hook issues (#193, #213) | Hooks may not trigger reliably | Add fallback post-validation |
| No nested subagents | Subagents can't spawn subagents | LeadAgent stays as orchestrator |
| No SessionStart hook | Can't hook session initialization | Use pre-query setup instead |
| Python 3.10+ required | Excludes Python 3.9 | CodeFRAME uses 3.11+, OK |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SDK API changes mid-migration | Medium | High | Abstract behind wrapper (Task 1.2) |
| Async compatibility issues | Medium | Medium | Maintain fallback to AnthropicProvider |
| Quality gate integration gaps | Low | High | Extensive testing, feature flag rollout |
| Performance degradation | Low | Medium | Benchmark before/after each phase |
| Feature loss (maturity levels) | Medium | Low | Hybrid approach preserves features |

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Lines of code | 25,771 | ~24,900 | `wc -l $(find codeframe -name "*.py")` |
| Tool execution code | ~700 lines | ~200 lines | Review agent files |
| Maintenance complexity | High | Medium | Subjective assessment |
| Test coverage | 88% | 88%+ | pytest-cov |
| Quality gate effectiveness | 100% | 100% | No bad code merged |

---

## Appendix A: File Change Summary

### New Files

| File | Phase | Purpose |
|------|-------|---------|
| `providers/sdk_client.py` | 1 | SDK wrapper |
| `lib/sdk_hooks.py` | 2 | Tool hooks |
| `mcp/quality_gate_tool.py` | 2 | MCP tool |
| `agents/subagent_generator.py` | 3 | Markdown generator |
| `agents/hybrid_worker.py` | 3 | Hybrid agent |
| `ui/sdk_streaming.py` | 4 | Streaming bridge |
| `mcp/codeframe_server.py` | 5 | MCP server |

### Modified Files

| File | Phases | Changes |
|------|--------|---------|
| `pyproject.toml` | 1 | Add SDK dependency |
| `lib/metrics_tracker.py` | 1 | Add session_id |
| `core/session_manager.py` | 1 | Store SDK sessions |
| `agents/worker_agent.py` | 2, 3 | Tool migration |
| `agents/agent_pool_manager.py` | 3 | Hybrid agent support |
| `agents/lead_agent.py` | 3 | Coordination updates |
| `lib/context_manager.py` | 5 | Compaction fallback |

---

## Appendix B: Testing Strategy

### Phase 1 Tests
- SDK import test
- Wrapper fallback test
- Token tracking with session_id
- Session storage test

### Phase 2 Tests
- Pre-hook blocking tests
- Post-hook metrics tests
- File operation tests
- Bash execution tests
- Quality gate MCP tests

### Phase 3 Tests
- Subagent generation tests
- Hybrid agent execution tests
- Pool manager tests
- Coordination tests

### Phase 4 Tests
- Streaming bridge tests
- WebSocket event tests
- Frontend integration tests

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-28 | Claude Code | Initial implementation plan |
| 1.1 | 2025-11-28 | Claude Code | Resolved all open questions with SDK documentation, updated code examples with verified API signatures, added known limitations |

## References

- [Claude Agent SDK - PyPI](https://pypi.org/project/claude-agent-sdk/)
- [Claude Agent SDK - GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [SDK Demos Repository](https://github.com/anthropics/claude-agent-sdk-demos)
- [Agent SDK Overview](https://docs.claude.com/en/api/agent-sdk/overview)
- [Subagents Documentation](https://docs.claude.com/en/docs/agent-sdk/subagents)
