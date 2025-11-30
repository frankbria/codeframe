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
    from claude_agent_sdk import query, ClaudeAgentOptions

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
            logger.warning(
                "Claude Agent SDK not available, falling back to AnthropicProvider"
            )
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

            return await asyncio.to_thread(self._fallback.send_message, conversation)

        # SDK path - extract last user message
        last_message = conversation[-1]["content"]

        # Collect streamed response
        full_content = []
        usage_info = {"input_tokens": 0, "output_tokens": 0}
        stop_reason = None

        async for message in query(prompt=last_message, options=self._options):
            if hasattr(message, "content"):
                full_content.append(str(message.content))
            if hasattr(message, "usage"):
                usage_info["input_tokens"] = getattr(message.usage, "input_tokens", 0)
                usage_info["output_tokens"] = getattr(message.usage, "output_tokens", 0)
            if hasattr(message, "stop_reason"):
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
            raise RuntimeError(
                "Streaming requires SDK - not available in fallback mode"
            )

        async for message in query(prompt=prompt, options=self._options):
            yield message
