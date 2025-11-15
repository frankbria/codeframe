"""Unit tests for token counting functionality (T048).

Tests the TokenCounter class methods:
- count_tokens for single item
- count_tokens_batch for multiple items
- Caching mechanism
- count_context_tokens for agent's context

Part of 007-context-management Phase 6 (US4 - Flash Save).
"""

import pytest
from codeframe.lib.token_counter import TokenCounter


class TestTokenCounting:
    """Unit tests for TokenCounter class."""

    def test_count_tokens_single_item(self):
        """Test that TokenCounter works for a single content string."""
        counter = TokenCounter()

        # Simple test content
        content = "This is a test message for token counting."

        # ACT: Count tokens
        token_count = counter.count_tokens(content)

        # ASSERT: Returns reasonable token count
        assert token_count > 0
        assert isinstance(token_count, int)
        # Typically ~8-12 tokens for this sentence
        assert 5 < token_count < 20

    def test_count_tokens_batch(self):
        """Test that batch counting works for multiple items."""
        counter = TokenCounter()

        # Create batch of contents
        contents = [
            "First message for batch counting.",
            "Second message with different content.",
            "Third message to test batch processing.",
        ]

        # ACT: Count tokens in batch
        token_counts = counter.count_tokens_batch(contents)

        # ASSERT: Returns list of token counts
        assert len(token_counts) == 3
        assert all(isinstance(count, int) for count in token_counts)
        assert all(count > 0 for count in token_counts)

        # Verify total is reasonable
        total_tokens = sum(token_counts)
        assert total_tokens > 10  # Should have at least some tokens

    def test_token_count_caching(self):
        """Test that same content returns cached count."""
        counter = TokenCounter()

        content = "This content will be counted twice to test caching."

        # First call (should calculate)
        count_1 = counter.count_tokens(content)

        # Second call (should use cache)
        count_2 = counter.count_tokens(content)

        # ASSERT: Same count returned
        assert count_1 == count_2

        # Verify cache was used (if counter exposes cache stats, check them)
        # For now, just verify consistency
        assert count_1 > 0

    def test_count_context_tokens_for_agent(self):
        """Test total token count across all context items for an agent."""
        counter = TokenCounter()

        # Create mock context items (list of dicts with 'content' field)
        context_items = [
            {"id": 1, "content": "Task description: Implement user authentication."},
            {"id": 2, "content": "Code snippet: def authenticate_user(): pass"},
            {"id": 3, "content": "Error: Invalid credentials provided by user."},
        ]

        # ACT: Count total tokens across all items
        total_tokens = counter.count_context_tokens(context_items)

        # ASSERT: Returns total token count
        assert total_tokens > 0
        assert isinstance(total_tokens, int)

        # Verify it's the sum of individual counts
        individual_counts = [counter.count_tokens(item["content"]) for item in context_items]
        expected_total = sum(individual_counts)
        assert total_tokens == expected_total

    def test_count_context_tokens_with_empty_list(self):
        """Test counting tokens with empty context list."""
        counter = TokenCounter()

        # Empty context
        context_items = []

        # ACT: Count tokens
        total_tokens = counter.count_context_tokens(context_items)

        # ASSERT: Returns 0 for empty list
        assert total_tokens == 0

    def test_count_context_tokens_with_large_content(self):
        """Test token counting with large content items."""
        counter = TokenCounter()

        # Create large content item (simulate PRD section)
        large_content = "This is a very long PRD section. " * 500  # ~3500 words

        context_items = [{"id": 1, "content": large_content}]

        # ACT: Count tokens
        total_tokens = counter.count_context_tokens(context_items)

        # ASSERT: Returns reasonable count for large content
        assert total_tokens > 100  # Should be substantial
        # Typically ~1.3 tokens per word, so expect ~4500+ tokens
        assert total_tokens > 1000
