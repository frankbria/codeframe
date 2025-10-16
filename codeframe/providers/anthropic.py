"""Anthropic API provider for Claude integration."""

import logging
from typing import List, Dict, Any, Optional

try:
    import anthropic
    from anthropic import (
        Anthropic,
        AuthenticationError,
        RateLimitError,
        APIConnectionError,
    )
except ImportError:
    raise ImportError(
        "anthropic package not found. Install with: pip install anthropic"
    )


logger = logging.getLogger(__name__)


class AnthropicProvider:
    """Provider for Anthropic's Claude API.

    Handles message sending, error handling, and token usage tracking
    for Claude conversations.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (required)
            model: Claude model to use (default: claude-sonnet-4-20250514)

        Raises:
            ValueError: If API key is missing or empty
        """
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required for Lead Agent.\n"
                "Get your API key at: https://console.anthropic.com/\n"
                "Then add it to your .env file or pass it to the constructor."
            )

        self.api_key = api_key
        self.model = model
        self.client = Anthropic(api_key=api_key)

        logger.info(f"Initialized AnthropicProvider with model: {model}")

    def send_message(
        self,
        conversation: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Send message to Claude API.

        Args:
            conversation: List of message dicts with 'role' and 'content' keys
                         Roles must be 'user' or 'assistant'

        Returns:
            Dictionary containing:
                - content: Assistant's response text
                - stop_reason: Why the response ended
                - usage: Token usage statistics

        Raises:
            ValueError: If conversation is empty or has invalid roles
            AuthenticationError: If API key is invalid
            RateLimitError: If rate limit is exceeded
            APIConnectionError: If connection fails
            TimeoutError: If request times out
        """
        # Validate conversation
        if not conversation:
            raise ValueError("Conversation cannot be empty")

        # Validate message roles
        for msg in conversation:
            if msg.get("role") not in ["user", "assistant"]:
                raise ValueError(
                    f"Invalid message role: {msg.get('role')}. "
                    "Must be 'user' or 'assistant'"
                )

        try:
            # Send request to Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=conversation,
            )

            # Extract response content
            content = response.content[0].text if response.content else ""

            # Build response dictionary
            result = {
                "content": content,
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                },
            }

            logger.info(
                f"Claude API response - Input tokens: {result['usage']['input_tokens']}, "
                f"Output tokens: {result['usage']['output_tokens']}"
            )

            return result

        except AuthenticationError as e:
            logger.error(f"Authentication error: {e}")
            raise

        except RateLimitError as e:
            logger.error(f"Rate limit exceeded: {e}")
            raise

        except APIConnectionError as e:
            logger.error(f"API connection error: {e}")
            raise

        except TimeoutError as e:
            logger.error(f"Request timeout: {e}")
            raise

        except Exception as e:
            logger.error(f"Unexpected error sending message to Claude: {e}")
            raise
