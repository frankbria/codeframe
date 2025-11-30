# Claude Agent SDK Hook Integration - Validation Report

**Date**: 2025-11-30
**Author**: Claude Code
**Task**: Validate SDK hook integration approach for quality gate integration
**Status**: ✅ VALIDATED WITH RECOMMENDATIONS

---

## Executive Summary

The proposed dual-layer defense strategy for quality gate integration is **sound and necessary** given documented SDK hook reliability issues. The migration plan correctly identifies risks and proposes appropriate mitigations.

**Key Findings**:
1. ✅ SDK hook API understanding is correct
2. ⚠️ Hook reliability issues are real and documented (GitHub #193, #213)
3. ✅ Dual-layer approach is the right pattern
4. 📋 Recommendations provided for strengthening implementation

---

## 1. SDK Hook API Validation

### Hook Signature Verification

**Documented API** (from SDK documentation):
```python
HookCallback = Callable[
    [dict[str, Any], str | None, HookContext],
    Awaitable[dict[str, Any]]
]

# Parameters:
# - input_data: Hook-specific input data
# - tool_use_id: Optional tool use identifier (for tool-related hooks)
# - context: Hook context with additional information
```

**Migration Plan Code** (Task 2.1):
```python
async def quality_gate_pre_hook(
    input_data: dict,
    tool_use_id: str,
    context: dict,
) -> dict:
```

**Status**: ✅ **CORRECT** - Signature matches SDK documentation

**Minor Issue**: Type hints should be more precise:
```python
from claude_agent_sdk import HookContext

async def quality_gate_pre_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,  # ← Should be optional
    context: HookContext,      # ← Should use SDK type
) -> dict[str, Any]:
```

---

### Hook Response Format

**Documented Format** (for blocking):
```python
{
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",  # or "allow", "ask"
        "permissionDecisionReason": "Reason for blocking"
    }
}
```

**Migration Plan Code**:
```python
return {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"Cannot modify protected file: {file_path}"
    }
}
```

**Status**: ✅ **CORRECT** - Response format matches documentation

---

### Supported Hook Types

**Documented** (Python SDK):
- ✅ `PreToolUse` - Before tool execution
- ✅ `PostToolUse` - After tool execution
- ✅ `UserPromptSubmit` - When user submits prompt
- ✅ `Stop` - When stopping execution
- ✅ `SubagentStop` - When subagent stops
- ✅ `PreCompact` - Before message compaction
- ❌ `SessionStart` - **NOT SUPPORTED** (Python SDK limitation)
- ❌ `SessionEnd` - **NOT SUPPORTED** (Python SDK limitation)
- ❌ `Notification` - **NOT SUPPORTED** (Python SDK limitation)

**Migration Plan Usage**:
- Uses `PreToolUse` for blocking dangerous operations ✅
- Uses `PostToolUse` for metrics recording ✅

**Status**: ✅ **CORRECT** - Only uses supported hook types

---

### HookMatcher API

**Documented API**:
```python
@dataclass
class HookMatcher:
    matcher: str | None = None  # Tool name or pattern (e.g., "Bash", "Write|Edit")
    hooks: list[HookCallback] = field(default_factory=list)
```

**Migration Plan Code**:
```python
{
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

**Status**: ✅ **CORRECT** - API usage matches documentation

---

## 2. Known Reliability Issues

### GitHub Issue Analysis

#### Issue #193: "Claude Code SDK hooks do not work"
**URL**: https://github.com/anthropics/claude-agent-sdk-python/issues/193

**Reported Problem**:
- Hooks configured according to documentation
- Hook callbacks never execute
- No logging appears, no blocking occurs

**Example from issue**:
```python
async def log_hook(input_data, tool_use_id, context):
    print("HOOK CALLED!")  # ← Never prints
    return {}

options = ClaudeAgentOptions(
    hooks={'PreToolUse': [HookMatcher(hooks=[log_hook])]}
)
```

**Status**: 🔴 **UNRESOLVED** (as of 2025-11-30)

---

#### Issue #213: "Hooks not triggering in Claude Agent SDK"
**URL**: https://github.com/anthropics/claude-agent-sdk-python/issues/213

**Reported Problem**:
- Similar to #193 - hooks don't trigger
- Tested with both `PreToolUse` and `PostToolUse`
- Dangerous commands not blocked despite hook logic

**Impact**: Critical for quality gates - if hooks don't fire, dangerous operations can't be blocked

**Status**: 🔴 **UNRESOLVED** (as of 2025-11-30)

---

### Root Cause Speculation

Based on issue discussions and SDK architecture:

1. **Timing Issue**: Hooks may only work with `ClaudeSDKClient`, not with `query()` helper
   - Migration plan uses `query()` in examples
   - Should verify hook support with client approach

2. **Async Context**: Possible event loop issues in async execution
   - Hooks are async but may not be awaited properly internally

3. **SDK Version**: Issues may be version-specific
   - Migration plan targets `>=0.1.10`
   - Verify if newer versions resolve issues

---

## 3. Dual-Layer Defense Strategy Analysis

### Proposed Architecture

**Layer 1: SDK Pre-Tool Hooks** (Proactive blocking)
```python
async def quality_gate_pre_hook(input_data, tool_use_id, context):
    if dangerous_operation(input_data):
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Blocked by quality gate"
            }
        }
    return {}
```

**Layer 2: Post-Validation Fallback** (Reactive detection)
```python
async def execute_task(self, task):
    # Execute via SDK (Layer 1 hooks may block)
    response = await self.sdk_client.send_message(...)

    # Layer 2: Post-validation (in case hooks didn't fire)
    gate_result = await self._run_quality_gates(task)
    if not gate_result.passed:
        return {"status": "blocked", "failures": gate_result.failures}
```

### Strategy Assessment

**Strengths**:
1. ✅ **Defense in depth** - Multiple independent checks
2. ✅ **Fail-safe design** - If hooks fail, post-validation catches issues
3. ✅ **Backwards compatible** - Preserves existing quality gate infrastructure
4. ✅ **Testable** - Can test each layer independently

**Potential Issues**:
1. ⚠️ **Performance** - Double validation adds latency
2. ⚠️ **Wasted work** - If Layer 1 should block but doesn't, work is wasted
3. ⚠️ **Complexity** - Two systems to maintain

**Verdict**: ✅ **SOUND APPROACH** given reliability concerns

---

### Comparison to FastAPI Middleware

**FastAPI Pattern**:
```python
@app.middleware("http")
async def validate_request(request: Request, call_next):
    # Pre-processing (like PreToolUse hook)
    if should_block(request):
        return JSONResponse(status_code=403, content={"error": "Blocked"})

    # Execute endpoint
    response = await call_next(request)

    # Post-processing (like PostToolUse hook)
    log_response(response)
    return response
```

**SDK Hook Pattern**:
```python
# PreToolUse hook (middleware "before" phase)
async def pre_hook(input_data, tool_use_id, context):
    if should_block(input_data):
        return {"hookSpecificOutput": {"permissionDecision": "deny"}}
    return {}

# PostToolUse hook (middleware "after" phase)
async def post_hook(input_data, tool_use_id, context):
    log_tool_usage(input_data)
    return {}
```

**Similarity**: ✅ Conceptually equivalent - both use middleware pattern
**Difference**: ⚠️ FastAPI middleware is highly reliable, SDK hooks are not (based on issues)

---

## 4. Hook Factory Pattern

### Proposed Pattern (from migration plan)

```python
async def create_quality_gate_pre_hook(quality_gates, db):
    """Factory to create pre-tool hook with quality gate integration."""
    async def quality_gate_pre_hook(input_data, tool_use_id, context):
        # Hook logic with closure over quality_gates, db
        ...
    return quality_gate_pre_hook
```

### Assessment

**Strengths**:
1. ✅ **Closure pattern** - Captures dependencies cleanly
2. ✅ **Testable** - Can inject mock dependencies
3. ✅ **Flexible** - Different factories for different contexts

**Issues**:
1. ⚠️ **Async factory** - Unnecessary complexity (no await in factory body)
2. ⚠️ **Event loop management** - `asyncio.get_event_loop().run_until_complete()` is fragile

**Recommendation**: Simplify to sync factory:

```python
def create_quality_gate_pre_hook(quality_gates, db):
    """Factory to create pre-tool hook with quality gate integration."""
    async def quality_gate_pre_hook(input_data, tool_use_id, context):
        # Hook logic with closure over quality_gates, db
        ...
    return quality_gate_pre_hook
```

---

## 5. Recommended Pattern Improvements

### Pattern 1: Hook Registration Helper

```python
from claude_agent_sdk import HookMatcher, ClaudeAgentOptions
from typing import Callable

class HookRegistry:
    """Centralized hook registration and management."""

    def __init__(self):
        self._pre_tool_hooks: list[HookMatcher] = []
        self._post_tool_hooks: list[HookMatcher] = []

    def register_pre_tool(
        self,
        hook: Callable,
        tools: list[str] | None = None
    ):
        """Register a PreToolUse hook for specific tools or all tools."""
        matcher = None if tools is None else '|'.join(tools)
        self._pre_tool_hooks.append(HookMatcher(matcher=matcher, hooks=[hook]))

    def register_post_tool(
        self,
        hook: Callable,
        tools: list[str] | None = None
    ):
        """Register a PostToolUse hook."""
        matcher = None if tools is None else '|'.join(tools)
        self._post_tool_hooks.append(HookMatcher(matcher=matcher, hooks=[hook]))

    def build_options_dict(self) -> dict:
        """Build hooks dict for ClaudeAgentOptions."""
        return {
            'PreToolUse': self._pre_tool_hooks,
            'PostToolUse': self._post_tool_hooks,
        }

# Usage:
registry = HookRegistry()
registry.register_pre_tool(quality_gate_hook, tools=['Write', 'Bash'])
registry.register_post_tool(metrics_hook)  # All tools

options = ClaudeAgentOptions(hooks=registry.build_options_dict())
```

**Benefits**:
- Cleaner registration API
- Type-safe hook management
- Easier testing

---

### Pattern 2: Hook Testing Utilities

```python
import pytest
from unittest.mock import AsyncMock

class HookTestHelper:
    """Helper for testing SDK hooks."""

    @staticmethod
    def create_tool_input(tool_name: str, tool_input: dict) -> dict:
        """Create hook input_data for testing."""
        return {
            "tool_name": tool_name,
            "tool_input": tool_input
        }

    @staticmethod
    def assert_blocked(result: dict, expected_reason: str | None = None):
        """Assert hook blocked operation."""
        assert "hookSpecificOutput" in result
        output = result["hookSpecificOutput"]
        assert output["permissionDecision"] == "deny"
        if expected_reason:
            assert expected_reason in output["permissionDecisionReason"]

    @staticmethod
    def assert_allowed(result: dict):
        """Assert hook allowed operation."""
        assert result == {} or result.get("hookSpecificOutput", {}).get("permissionDecision") != "deny"

# Test example:
@pytest.mark.asyncio
async def test_quality_gate_blocks_dangerous_bash():
    hook = create_quality_gate_pre_hook(mock_quality_gates, mock_db)

    input_data = HookTestHelper.create_tool_input(
        "Bash",
        {"command": "rm -rf /"}
    )

    result = await hook(input_data, "test-id", HookContext())

    HookTestHelper.assert_blocked(result, "Dangerous command")
```

---

### Pattern 3: Hook Execution Monitor (Reliability Detection)

```python
import logging
from typing import Callable
from claude_agent_sdk import HookContext

logger = logging.getLogger(__name__)

class HookExecutionMonitor:
    """Monitor hook execution to detect reliability issues."""

    def __init__(self):
        self._hook_call_count = 0
        self._tool_use_count = 0
        self._reliability_threshold = 0.9  # 90% hooks should fire

    def wrap_hook(self, hook: Callable) -> Callable:
        """Wrap hook to track execution."""
        async def monitored_hook(input_data, tool_use_id, context):
            self._hook_call_count += 1
            logger.debug(f"Hook fired: {hook.__name__} (total: {self._hook_call_count})")
            return await hook(input_data, tool_use_id, context)
        return monitored_hook

    def record_tool_use(self):
        """Record tool use (call from Layer 2)."""
        self._tool_use_count += 1

    def check_reliability(self) -> tuple[bool, float]:
        """Check if hooks are firing reliably."""
        if self._tool_use_count == 0:
            return True, 1.0

        reliability = self._hook_call_count / self._tool_use_count
        is_reliable = reliability >= self._reliability_threshold

        if not is_reliable:
            logger.warning(
                f"Hook reliability: {reliability:.1%} "
                f"({self._hook_call_count}/{self._tool_use_count}) "
                f"- below threshold {self._reliability_threshold:.1%}"
            )

        return is_reliable, reliability

# Usage in WorkerAgent:
monitor = HookExecutionMonitor()

# Wrap hooks with monitor
monitored_pre_hook = monitor.wrap_hook(quality_gate_pre_hook)

# In Layer 2 validation:
async def _run_quality_gates(self, task):
    self.hook_monitor.record_tool_use()  # Track tool usage

    is_reliable, reliability = self.hook_monitor.check_reliability()
    if not is_reliable:
        logger.error(
            f"SDK hooks unreliable ({reliability:.1%}) - "
            f"consider disabling SDK and using fallback"
        )

    # Run quality gates...
```

**Benefits**:
- Early detection of hook issues
- Automatic fallback triggering
- Production monitoring

---

## 6. Risks and Concerns

### Risk 1: Hook Reliability (HIGH PRIORITY)

**Concern**: Hooks may not fire at all, rendering Layer 1 ineffective

**Mitigation**:
1. ✅ Use dual-layer approach (already planned)
2. ✅ Add hook execution monitoring (Pattern 3 above)
3. 📋 Test thoroughly with SDK version used in production
4. 📋 Add feature flag to disable SDK hooks if unreliable

**Code**:
```python
# Feature flag in config
USE_SDK_HOOKS = os.getenv("CODEFRAME_USE_SDK_HOOKS", "true").lower() == "true"

if USE_SDK_HOOKS and SDK_AVAILABLE:
    options = ClaudeAgentOptions(hooks=build_hooks())
else:
    logger.warning("SDK hooks disabled - using Layer 2 validation only")
    options = ClaudeAgentOptions(hooks={})
```

---

### Risk 2: Performance Overhead (MEDIUM PRIORITY)

**Concern**: Dual validation adds latency to every task

**Mitigation**:
1. Run Layer 1 and Layer 2 in parallel where possible
2. Cache quality gate results
3. Use async patterns to avoid blocking

**Code**:
```python
async def execute_task(self, task):
    # Start SDK execution (with Layer 1 hooks)
    sdk_task = asyncio.create_task(
        self.sdk_client.send_message(...)
    )

    # Run Layer 2 validation in parallel (on previous state)
    validation_task = asyncio.create_task(
        self._pre_validate_task(task)
    )

    # Wait for both
    response, validation = await asyncio.gather(sdk_task, validation_task)

    if not validation.passed:
        return {"status": "blocked", "failures": validation.failures}

    return response
```

---

### Risk 3: Complexity (LOW PRIORITY)

**Concern**: Maintaining two validation systems increases complexity

**Mitigation**:
1. Share validation logic between layers
2. Clear abstraction boundaries
3. Comprehensive tests

**Code**:
```python
class QualityGateValidator:
    """Shared validation logic for both layers."""

    async def validate_file_write(self, file_path: str) -> ValidationResult:
        """Shared validation for file writes."""
        protected = [".env", "credentials.json", ".git/", "secrets"]
        if any(p in file_path for p in protected):
            return ValidationResult(
                passed=False,
                reason=f"Cannot modify protected file: {file_path}"
            )
        return ValidationResult(passed=True)

    async def validate_bash_command(self, command: str) -> ValidationResult:
        """Shared validation for bash commands."""
        dangerous_patterns = ["rm -rf /", "rm -rf ~", ":(){ :|:& };:"]
        if any(pattern in command for pattern in dangerous_patterns):
            return ValidationResult(
                passed=False,
                reason="Dangerous command blocked"
            )
        return ValidationResult(passed=True)

# Layer 1 (SDK hook) uses shared validator
async def quality_gate_pre_hook(input_data, tool_use_id, context):
    validator = QualityGateValidator()

    if input_data["tool_name"] == "Write":
        result = await validator.validate_file_write(
            input_data["tool_input"]["file_path"]
        )
        if not result.passed:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": result.reason
                }
            }
    return {}

# Layer 2 (WorkerAgent) uses same validator
async def _run_quality_gates(self, task):
    validator = QualityGateValidator()
    # Same validation logic
    ...
```

---

## 7. Testing Strategy

### Unit Tests

```python
@pytest.mark.asyncio
async def test_pre_hook_blocks_protected_file():
    """Test Layer 1: SDK hook blocks protected file write."""
    hook = create_quality_gate_pre_hook(mock_quality_gates, mock_db)

    input_data = {
        "tool_name": "Write",
        "tool_input": {"file_path": ".env", "content": "SECRET=xxx"}
    }

    result = await hook(input_data, "test-id", HookContext())

    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "protected file" in result["hookSpecificOutput"]["permissionDecisionReason"]

@pytest.mark.asyncio
async def test_layer2_catches_if_hook_fails():
    """Test Layer 2: Post-validation catches issues if hooks don't fire."""
    agent = HybridWorkerAgent(...)

    # Simulate hook failure (doesn't block)
    with mock.patch.object(agent.sdk_client, 'hooks_enabled', False):
        result = await agent.execute_task(task_writing_to_env_file)

    # Layer 2 should catch it
    assert result["status"] == "blocked"
    assert "protected file" in result["failures"][0]["reason"]
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_hooks_reliability_in_real_execution():
    """Test if SDK hooks actually fire during task execution."""
    hook_fired = False

    async def test_hook(input_data, tool_use_id, context):
        nonlocal hook_fired
        hook_fired = True
        return {}

    options = ClaudeAgentOptions(
        hooks={'PreToolUse': [HookMatcher(hooks=[test_hook])]}
    )

    # Execute real SDK query
    async for message in query(
        prompt="List files in current directory",
        options=options
    ):
        pass

    # Verify hook fired
    assert hook_fired, "SDK hook did not fire - reliability issue confirmed"
```

---

## 8. Recommended Implementation Changes

### Change 1: Fix Hook Signatures

**File**: `codeframe/lib/sdk_hooks.py`

```python
# BEFORE (from migration plan)
async def quality_gate_pre_hook(
    input_data: dict,
    tool_use_id: str,
    context: dict,
) -> dict:

# AFTER (correct types)
from claude_agent_sdk import HookContext

async def quality_gate_pre_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> dict[str, Any]:
```

---

### Change 2: Simplify Hook Factories

**File**: `codeframe/lib/sdk_hooks.py`

```python
# BEFORE (from migration plan)
async def create_quality_gate_pre_hook(quality_gates, db):
    async def quality_gate_pre_hook(...):
        ...
    return quality_gate_pre_hook

# Use in build_codeframe_hooks():
pre_hook = asyncio.get_event_loop().run_until_complete(
    create_quality_gate_pre_hook(quality_gates, db)
)

# AFTER (simplified)
def create_quality_gate_pre_hook(quality_gates, db):
    """Sync factory - no need for async."""
    async def quality_gate_pre_hook(...):
        ...
    return quality_gate_pre_hook

# Use in build_codeframe_hooks():
pre_hook = create_quality_gate_pre_hook(quality_gates, db)
```

---

### Change 3: Add Hook Execution Monitoring

**File**: `codeframe/lib/sdk_hooks.py`

Add `HookExecutionMonitor` class (Pattern 3 from Section 5) and integrate:

```python
def build_codeframe_hooks(quality_gates, metrics_tracker, db, monitor=None):
    """Build SDK hooks dictionary for CodeFRAME integration."""
    pre_hook = create_quality_gate_pre_hook(quality_gates, db)
    post_hook = create_metrics_post_hook(metrics_tracker, db)

    # Wrap hooks with monitor if provided
    if monitor:
        pre_hook = monitor.wrap_hook(pre_hook)
        post_hook = monitor.wrap_hook(post_hook)

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

---

### Change 4: Add Feature Flag for Hook Disabling

**File**: `codeframe/providers/sdk_client.py`

```python
class SDKClientWrapper:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        hooks: Optional[Dict] = None,
        enable_hooks: bool = True,  # NEW: Feature flag
        **kwargs
    ):
        # ...existing code...

        # Only enable hooks if flag is True
        if enable_hooks:
            self._options = ClaudeAgentOptions(
                hooks=hooks or {},
                **kwargs
            )
        else:
            logger.warning("SDK hooks disabled by feature flag")
            self._options = ClaudeAgentOptions(
                hooks={},  # Empty hooks
                **kwargs
            )
```

**Environment variable**:
```bash
# .env
CODEFRAME_ENABLE_SDK_HOOKS=true  # Set to "false" to disable
```

---

## 9. Final Recommendations

### Priority 1: Pre-Migration Testing (CRITICAL)

**Action**: Test hook reliability with SDK `>=0.1.10` BEFORE implementing full migration

**Test Script**:
```python
# tests/sdk/test_hook_reliability.py
import pytest
from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher, HookContext

@pytest.mark.asyncio
async def test_sdk_hooks_fire_reliably():
    """Critical test: Verify SDK hooks actually fire."""
    call_count = 0

    async def test_hook(input_data, tool_use_id, context):
        nonlocal call_count
        call_count += 1
        print(f"Hook fired! Call #{call_count}")
        return {}

    options = ClaudeAgentOptions(
        hooks={
            'PreToolUse': [HookMatcher(hooks=[test_hook])],
            'PostToolUse': [HookMatcher(hooks=[test_hook])]
        }
    )

    # Execute query that should trigger hooks
    async for message in query(
        prompt="List files in current directory using Bash tool",
        options=options
    ):
        print(f"Message: {message}")

    # Verify hooks fired
    assert call_count > 0, (
        f"SDK hooks did not fire (call_count={call_count}). "
        f"This confirms issues #193 and #213. "
        f"RECOMMENDATION: Use Layer 2 validation only until SDK is fixed."
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_sdk_hooks_fire_reliably())
```

**Decision Point**:
- ✅ If test passes: Proceed with dual-layer approach
- ⚠️ If test fails: Disable Layer 1, use Layer 2 validation only

---

### Priority 2: Implement Recommended Patterns

1. ✅ Use `HookRegistry` for cleaner hook management (Pattern 1)
2. ✅ Add `HookTestHelper` for easier testing (Pattern 2)
3. ✅ Implement `HookExecutionMonitor` for reliability detection (Pattern 3)
4. ✅ Add feature flag for hook disabling

---

### Priority 3: Strengthen Layer 2 Validation

**Ensure Layer 2 can function independently**:

```python
class HybridWorkerAgent:
    async def execute_task(self, task):
        # Layer 1: SDK execution (hooks may or may not fire)
        response = await self.sdk_client.send_message(...)

        # Layer 2: ALWAYS run validation (don't assume Layer 1 worked)
        validation = await self._validate_task_execution(task, response)

        if not validation.passed:
            # Rollback any changes if possible
            await self._rollback_task(task)

            # Create blocker
            return {
                "status": "blocked",
                "failures": validation.failures,
                "layer": "post_validation",  # Track which layer caught it
                "hook_fired": response.get("hook_metadata", {}).get("fired", False)
            }

        return response
```

---

### Priority 4: Documentation and Monitoring

**Add documentation**:
```markdown
# docs/SDK_HOOK_RELIABILITY.md

## Known Issues

SDK hooks (PreToolUse, PostToolUse) have documented reliability issues:
- GitHub Issue #193: Hooks not firing
- GitHub Issue #213: Similar reliability problems

## Mitigation Strategy

CodeFRAME uses a dual-layer approach:
1. **Layer 1**: SDK hooks (when reliable)
2. **Layer 2**: Post-validation (always runs)

## Monitoring

Check hook reliability metrics:
- `codeframe metrics hook-reliability`
- Dashboard: Quality Gates section

If reliability drops below 90%, consider disabling SDK hooks.
```

**Add monitoring dashboard**:
- Hook fire rate: `hook_calls / tool_uses`
- Layer 1 blocks vs Layer 2 blocks
- Alert if Layer 1 reliability < 90%

---

## 10. Summary

### ✅ Validated Aspects

1. **SDK Hook API**: Signatures and response formats are correct
2. **Dual-Layer Strategy**: Sound approach given reliability concerns
3. **Hook Factory Pattern**: Reasonable pattern (with minor improvements)
4. **FastAPI Similarity**: Conceptual equivalence to middleware pattern

### ⚠️ Concerns and Risks

1. **Hook Reliability**: Real, documented issues (GitHub #193, #213)
2. **Performance**: Dual validation adds latency
3. **Complexity**: Two systems to maintain

### 📋 Recommended Actions

1. **Pre-Migration**: Test hook reliability (Priority 1)
2. **Implementation**: Apply recommended pattern improvements
3. **Monitoring**: Add hook execution monitoring
4. **Fallback**: Implement feature flag for hook disabling

### 🎯 Go/No-Go Decision

**PROCEED** with dual-layer approach, with these conditions:

1. ✅ Test hook reliability before full migration
2. ✅ Implement `HookExecutionMonitor` for early issue detection
3. ✅ Add feature flag to disable hooks if unreliable
4. ✅ Ensure Layer 2 can function independently

**Alternative Path** (if hooks prove unreliable):
- Skip Layer 1 entirely
- Rely on Layer 2 validation only
- Revisit SDK hooks in future migration phase after SDK improvements

---

## References

- [Claude Agent SDK - Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [GitHub Issue #193 - Hooks not working](https://github.com/anthropics/claude-agent-sdk-python/issues/193)
- [GitHub Issue #213 - Hooks not triggering](https://github.com/anthropics/claude-agent-sdk-python/issues/213)
- [SDK Migration Implementation Plan](./SDK_MIGRATION_IMPLEMENTATION_PLAN.md)
- [Dual-Layer Architecture Documentation](./ENFORCEMENT_ARCHITECTURE.md)

---

**Document Status**: ✅ COMPLETE
**Next Steps**: Execute Priority 1 hook reliability testing
