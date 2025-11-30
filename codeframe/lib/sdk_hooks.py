"""SDK Tool Hooks for CodeFRAME (SDK Migration Task 2.1a).

This module provides pre-tool and post-tool hooks for the Claude Agent SDK,
enabling quality gates and metrics tracking at the tool execution level.

Pre-tool hooks:
    - Block writes to protected files (.env, credentials, secrets)
    - Block dangerous bash commands (rm -rf /, fork bombs, etc.)
    - Validate tool inputs for safety

Post-tool hooks:
    - Record metrics after tool usage (Write, Bash)
    - Trigger quality checks after file writes
    - Track token usage and costs

Architecture:
    Hooks integrate with the SDK's hook system via HookMatcher and async hook functions.
    Each hook receives HookInput, tool_use_id, and HookContext and returns HookJSONOutput.

Known Issues:
    - SDK hooks have reliability concerns (GitHub #193, #213)
    - Fallback validation is performed in WorkerAgent.complete_task() for redundancy
    - Hooks are "best effort" defense-in-depth, not primary security layer

Usage:
    >>> from codeframe.lib.sdk_hooks import build_codeframe_hooks
    >>> from codeframe.persistence.database import Database
    >>> from codeframe.lib.metrics_tracker import MetricsTracker
    >>> from codeframe.lib.quality_gates import QualityGates
    >>>
    >>> db = Database("state.db")
    >>> tracker = MetricsTracker(db=db)
    >>> gates = QualityGates(db=db, project_id=1, project_root=Path("/app"))
    >>>
    >>> hooks = build_codeframe_hooks(db=db, metrics_tracker=tracker, quality_gates=gates)
    >>> # Use in ClaudeAgentOptions: hooks=hooks

See Also:
    - specs/sdk-migration/plan.md: Complete SDK migration plan
    - codeframe.lib.quality_gates: Quality gate enforcement
    - codeframe.lib.metrics_tracker: Token usage and cost tracking
"""

import logging
import re
from typing import Dict, Any, Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from claude_agent_sdk import HookMatcher, HookInput, HookContext, HookJSONOutput
    SDK_AVAILABLE = True
except ImportError:
    # Type stubs for when SDK is not installed (testing environments)
    HookInput = Dict[str, Any]
    HookContext = Any
    HookJSONOutput = Dict[str, Any]
    SDK_AVAILABLE = False
    logger.warning("claude-agent-sdk not available - hooks will not function")


# ============================================================================
# Protected File Patterns and Dangerous Commands
# ============================================================================

# Protected file patterns that should never be written to
PROTECTED_FILE_PATTERNS = [
    r"\.env$",
    r"\.env\..*$",  # .env.local, .env.production, etc.
    r"credentials\.json$",
    r"secrets\.ya?ml$",
    r"\.git/",  # Git internals
    r"\.pem$",  # Private keys
    r"\.key$",  # Private keys
    r"id_rsa$",  # SSH keys
    r"id_dsa$",
    r"\.p12$",  # PKCS#12 certificates
    r"\.pfx$",
    r"password.*",
    r"secret.*",
    r"token.*",
]

# Dangerous bash command patterns
DANGEROUS_BASH_PATTERNS = [
    r"rm\s+-rf\s+/",  # Delete root filesystem
    r":\(\)\{\s*:\|:\&\s*\};:",  # Fork bomb
    r"dd\s+if=/dev/zero\s+of=/dev/",  # Disk wipe
    r"mkfs\.",  # Format filesystem
    r">/dev/sd",  # Write to disk devices
    r"chmod\s+-R\s+777\s+/",  # Open all permissions
    r"chown\s+-R.*\s+/",  # Change ownership of root
]


# ============================================================================
# Pre-Tool Hook Factory
# ============================================================================

def create_quality_gate_pre_hook() -> Callable:
    """Create a pre-tool hook for quality gate enforcement.

    This hook blocks unsafe operations before they are executed:
    - Writes to protected files (.env, credentials, secrets)
    - Dangerous bash commands (rm -rf /, fork bombs, etc.)

    Returns:
        Async hook function compatible with SDK PreToolUse hook

    Example:
        >>> pre_hook = create_quality_gate_pre_hook()
        >>> # Use in HookMatcher: HookMatcher(matcher=None, hooks=[pre_hook])
    """

    async def quality_gate_pre_hook(
        input_data: HookInput,
        tool_use_id: Optional[str],
        context: HookContext,
    ) -> HookJSONOutput:
        """Block unsafe tool operations before execution.

        Args:
            input_data: Hook input containing tool_name and tool_input
            tool_use_id: Unique ID for this tool use (optional)
            context: Hook context with session information

        Returns:
            HookJSONOutput with permissionDecision="deny" if unsafe, {} if safe
        """
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Check Write tool for protected files
        if tool_name == "Write":
            file_path = tool_input.get("file_path", "")
            for pattern in PROTECTED_FILE_PATTERNS:
                if re.search(pattern, file_path, re.IGNORECASE):
                    logger.warning(
                        f"Blocked Write to protected file: {file_path} (pattern: {pattern})"
                    )
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                f"Cannot write to protected file: {file_path}. "
                                f"This file contains sensitive data (matched pattern: {pattern}). "
                                f"Please choose a different file or get human approval."
                            ),
                        }
                    }

        # Check Bash tool for dangerous commands
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            for pattern in DANGEROUS_BASH_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    logger.warning(
                        f"Blocked dangerous Bash command: {command} (pattern: {pattern})"
                    )
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": (
                                f"Blocked dangerous command: {command}. "
                                f"This command matched a dangerous pattern ({pattern}) and could "
                                f"cause system damage. Please use a safer alternative."
                            ),
                        }
                    }

        # Allow safe operations
        return {}

    return quality_gate_pre_hook


# ============================================================================
# Post-Tool Hook Factory
# ============================================================================

def create_metrics_post_hook(
    db: Any,
    metrics_tracker: Optional[Any] = None,
) -> Callable:
    """Create a post-tool hook for metrics tracking.

    This hook records metrics after tool execution:
    - Records Write and Bash tool usage
    - Logs tool execution time
    - Can be extended to trigger quality checks

    Args:
        db: Database instance for storing metrics
        metrics_tracker: MetricsTracker instance (optional, created if None)

    Returns:
        Async hook function compatible with SDK PostToolUse hook

    Example:
        >>> from codeframe.lib.metrics_tracker import MetricsTracker
        >>> tracker = MetricsTracker(db=db)
        >>> post_hook = create_metrics_post_hook(db=db, metrics_tracker=tracker)
    """
    # Lazy import to avoid circular dependencies
    if metrics_tracker is None:
        from codeframe.lib.metrics_tracker import MetricsTracker
        metrics_tracker = MetricsTracker(db=db)

    async def metrics_post_hook(
        input_data: HookInput,
        tool_use_id: Optional[str],
        context: HookContext,
    ) -> HookJSONOutput:
        """Record metrics after tool execution.

        Args:
            input_data: Hook input containing tool_name, tool_input, tool_response
            tool_use_id: Unique ID for this tool use (optional)
            context: Hook context with session information

        Returns:
            HookJSONOutput (empty dict, doesn't modify tool behavior)
        """
        tool_name = input_data.get("tool_name", "")
        tool_response = input_data.get("tool_response", "")

        # Log tool usage
        logger.info(f"Tool executed: {tool_name} (tool_use_id={tool_use_id})")

        # Record metrics for specific tools
        if tool_name in ["Write", "Bash"]:
            # TODO: Extend this to record tool-specific metrics in database
            # For now, just log the usage
            logger.debug(f"{tool_name} tool executed successfully")

            # Check for errors in tool response
            if "error" in str(tool_response).lower():
                logger.warning(f"{tool_name} tool encountered error: {tool_response}")

        # Future: Trigger quality checks after Write operations
        # if tool_name == "Write":
        #     # Could trigger linting, type checking, etc.
        #     pass

        return {}

    return metrics_post_hook


# ============================================================================
# Hook Builder
# ============================================================================

def build_codeframe_hooks(
    db: Any,
    metrics_tracker: Optional[Any] = None,
    quality_gates: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build CodeFRAME hooks dictionary for SDK integration.

    Creates a complete hooks configuration for ClaudeAgentOptions, including:
    - PreToolUse hooks for safety validation
    - PostToolUse hooks for metrics tracking

    Args:
        db: Database instance
        metrics_tracker: MetricsTracker instance (optional)
        quality_gates: QualityGates instance (optional, reserved for future use)

    Returns:
        Dictionary compatible with SDK ClaudeAgentOptions.hooks format

    Example:
        >>> hooks = build_codeframe_hooks(db=db, metrics_tracker=tracker)
        >>> options = ClaudeAgentOptions(
        ...     allowed_tools=["Read", "Write", "Bash"],
        ...     hooks=hooks
        ... )

    Note:
        This function requires claude-agent-sdk to be installed. If not available,
        it returns an empty dict and logs a warning.
    """
    if not SDK_AVAILABLE:
        logger.warning(
            "claude-agent-sdk not available - returning empty hooks dict. "
            "Install with: uv add claude-agent-sdk"
        )
        return {}

    # Create hook functions
    pre_hook = create_quality_gate_pre_hook()
    post_hook = create_metrics_post_hook(db=db, metrics_tracker=metrics_tracker)

    # Build hooks dictionary using HookMatcher
    # matcher=None applies to all tools
    try:
        hooks_dict = {
            "PreToolUse": [
                HookMatcher(matcher=None, hooks=[pre_hook])
            ],
            "PostToolUse": [
                HookMatcher(matcher=None, hooks=[post_hook])
            ],
        }
        logger.info("Built CodeFRAME hooks: PreToolUse (safety), PostToolUse (metrics)")
        return hooks_dict
    except Exception as e:
        logger.error(f"Failed to build hooks: {e}")
        return {}


# ============================================================================
# Fallback Validation (for hook reliability issues)
# ============================================================================

def validate_tool_safety_fallback(tool_name: str, tool_input: Dict[str, Any]) -> Optional[str]:
    """Fallback validation when SDK hooks fail.

    This provides redundant safety checks that can be called directly from
    WorkerAgent.complete_task() or other locations to ensure safety even
    if SDK hooks have reliability issues.

    Args:
        tool_name: Name of the tool being executed
        tool_input: Tool input parameters

    Returns:
        None if safe, error message string if unsafe

    Example:
        >>> error = validate_tool_safety_fallback("Write", {"file_path": ".env"})
        >>> if error:
        ...     print(f"Validation failed: {error}")
        Validation failed: Cannot write to protected file: .env

    Note:
        This is used as a fallback due to known SDK hook reliability issues:
        - GitHub #193: Hooks not always triggered
        - GitHub #213: Hook errors not propagated correctly
    """
    # Check Write tool
    if tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        for pattern in PROTECTED_FILE_PATTERNS:
            if re.search(pattern, file_path, re.IGNORECASE):
                return f"Cannot write to protected file: {file_path} (matched pattern: {pattern})"

    # Check Bash tool
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        for pattern in DANGEROUS_BASH_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Blocked dangerous command: {command} (matched pattern: {pattern})"

    return None
