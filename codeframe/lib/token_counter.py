"""Token counting with tiktoken and caching.

This module provides efficient token counting for LLM context management using
OpenAI's tiktoken library. It includes:
- Content-based caching to avoid redundant encoding operations
- Batch processing for efficient multi-content counting
- Context aggregation for Virtual Project context items

The caching mechanism uses SHA-256 content hashing to ensure cache integrity
while maintaining high performance for repeated content.
"""

import hashlib
from typing import Dict, List

import tiktoken


class TokenCounter:
    """Token counting with tiktoken and caching.

    This class provides efficient token counting using OpenAI's tiktoken library
    with an optional caching layer. The cache uses content hashing to store
    token counts, eliminating redundant encoding operations for identical content.

    The counter is model-agnostic but defaults to GPT-4 encoding, which is
    compatible with Claude API token counting requirements.

    Attributes:
        cache_enabled: Whether caching is enabled for this instance.
        _cache: Internal cache mapping content hashes to token counts.
        _encoding: tiktoken encoding instance for token counting.

    Example:
        >>> counter = TokenCounter(cache_enabled=True)
        >>> count = counter.count_tokens("Hello, world!")
        >>> counts = counter.count_tokens_batch(["Hello", "world"])
        >>> total = counter.count_context_tokens([
        ...     {"content": "Task 1"},
        ...     {"content": "Task 2"}
        ... ])
    """

    def __init__(self, cache_enabled: bool = True, model: str = "gpt-4") -> None:
        """Initialize token counter with optional caching.

        Args:
            cache_enabled: Enable content-based caching. Defaults to True for
                performance optimization in Virtual Project context management.
            model: Model name for tiktoken encoding. Defaults to "gpt-4" which
                provides compatible token counting for Claude API.

        Raises:
            ValueError: If the specified model is not supported by tiktoken.
        """
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, int] = {}

        try:
            self._encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback to cl100k_base encoding (used by GPT-4 and GPT-3.5-turbo)
            self._encoding = tiktoken.get_encoding("cl100k_base")

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content for cache key.

        Args:
            content: Text content to hash.

        Returns:
            Hexadecimal SHA-256 hash string.
        """
        return hashlib.sha256(content.encode()).hexdigest()

    def count_tokens(self, content: str) -> int:
        """Count tokens in content with optional caching.

        If caching is enabled and the content has been counted before,
        returns the cached count. Otherwise, encodes the content and
        optionally caches the result.

        Args:
            content: Text content to count tokens for.

        Returns:
            Number of tokens in the content according to the tiktoken encoding.

        Example:
            >>> counter = TokenCounter()
            >>> count = counter.count_tokens("Hello, world!")
            >>> count
            4
        """
        if not content:
            return 0

        # Check cache if enabled
        if self.cache_enabled:
            content_hash = self._compute_hash(content)
            if content_hash in self._cache:
                return self._cache[content_hash]

        # Count tokens using tiktoken
        token_count = len(self._encoding.encode(content))

        # Store in cache if enabled
        if self.cache_enabled:
            self._cache[content_hash] = token_count

        return token_count

    def count_tokens_batch(self, contents: List[str]) -> List[int]:
        """Count tokens for multiple contents efficiently.

        Processes a batch of content strings and returns their token counts.
        Uses caching to avoid redundant encoding when the same content appears
        multiple times in the batch.

        Args:
            contents: List of text content strings to count.

        Returns:
            List of token counts in the same order as input contents.

        Example:
            >>> counter = TokenCounter()
            >>> counts = counter.count_tokens_batch([
            ...     "First item",
            ...     "Second item",
            ...     "First item"  # Duplicate, uses cache
            ... ])
            >>> counts
            [2, 2, 2]
        """
        if not contents:
            return []

        # Process each content item, leveraging cache through count_tokens
        return [self.count_tokens(content) for content in contents]

    def count_context_tokens(self, context_items: List[Dict[str, str]]) -> int:
        """Sum tokens across all context item contents.

        Aggregates token counts for a list of context items, typically from
        the Virtual Project context system. Each context item should have
        a "content" key.

        Args:
            context_items: List of dictionaries with "content" keys containing
                text to count. Other dictionary keys are ignored.

        Returns:
            Total token count across all context item contents.

        Example:
            >>> counter = TokenCounter()
            >>> items = [
            ...     {"content": "Task description", "tier": "hot"},
            ...     {"content": "Code snippet", "tier": "warm"}
            ... ]
            >>> total = counter.count_context_tokens(items)
            >>> total
            5
        """
        if not context_items:
            return 0

        # Extract content from each item and count in batch
        contents = [item.get("content", "") for item in context_items]
        counts = self.count_tokens_batch(contents)

        return sum(counts)

    def clear_cache(self) -> None:
        """Clear the token count cache.

        Useful for freeing memory when the cache grows large, or when
        you want to ensure fresh counts without cached values.
        """
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics for monitoring and debugging.

        Returns:
            Dictionary with cache statistics including size and hit rate.
        """
        return {
            "cache_size": len(self._cache),
            "cache_enabled": self.cache_enabled
        }
