"""Unit tests for TokenCounter class.

Tests cover:
- Basic token counting functionality
- Cache mechanism and performance
- Batch processing
- Context aggregation
- Error handling and edge cases
"""

from codeframe.lib.token_counter import TokenCounter


class TestTokenCounterBasics:
    """Test basic token counting functionality."""

    def test_init_default(self):
        """Test default initialization with caching enabled."""
        counter = TokenCounter()
        assert counter.cache_enabled is True
        assert counter._cache == {}

    def test_init_cache_disabled(self):
        """Test initialization with caching disabled."""
        counter = TokenCounter(cache_enabled=False)
        assert counter.cache_enabled is False
        assert counter._cache == {}

    def test_count_tokens_simple(self):
        """Test counting tokens in a simple string."""
        counter = TokenCounter()
        count = counter.count_tokens("Hello, world!")
        assert isinstance(count, int)
        assert count > 0

    def test_count_tokens_empty_string(self):
        """Test counting tokens in an empty string."""
        counter = TokenCounter()
        count = counter.count_tokens("")
        assert count == 0

    def test_count_tokens_whitespace_only(self):
        """Test counting tokens in whitespace-only string."""
        counter = TokenCounter()
        count = counter.count_tokens("   \n\t  ")
        # Whitespace should still count as tokens
        assert count >= 0


class TestTokenCounterCache:
    """Test caching mechanism."""

    def test_cache_hit(self):
        """Test that identical content uses cache."""
        counter = TokenCounter(cache_enabled=True)
        content = "This is a test sentence."

        # First call should populate cache
        count1 = counter.count_tokens(content)
        cache_size_after_first = counter.get_cache_stats()["cache_size"]

        # Second call should use cache
        count2 = counter.count_tokens(content)
        cache_size_after_second = counter.get_cache_stats()["cache_size"]

        assert count1 == count2
        assert cache_size_after_first == cache_size_after_second

    def test_cache_miss(self):
        """Test that different content creates new cache entries."""
        counter = TokenCounter(cache_enabled=True)

        count1 = counter.count_tokens("First sentence.")
        count2 = counter.count_tokens("Second sentence.")

        stats = counter.get_cache_stats()
        assert stats["cache_size"] == 2

    def test_cache_disabled_no_storage(self):
        """Test that cache is not used when disabled."""
        counter = TokenCounter(cache_enabled=False)

        counter.count_tokens("Test content")
        counter.count_tokens("Test content")

        stats = counter.get_cache_stats()
        assert stats["cache_size"] == 0

    def test_clear_cache(self):
        """Test cache clearing functionality."""
        counter = TokenCounter(cache_enabled=True)

        counter.count_tokens("First")
        counter.count_tokens("Second")
        assert counter.get_cache_stats()["cache_size"] == 2

        counter.clear_cache()
        assert counter.get_cache_stats()["cache_size"] == 0

    def test_cache_consistency(self):
        """Test that cached counts are accurate."""
        counter = TokenCounter(cache_enabled=True)
        content = "Consistent content for testing"

        # Get count with cache
        count_cached = counter.count_tokens(content)

        # Clear cache and get fresh count
        counter.clear_cache()
        count_fresh = counter.count_tokens(content)

        assert count_cached == count_fresh


class TestTokenCounterBatch:
    """Test batch processing functionality."""

    def test_batch_empty_list(self):
        """Test batch counting with empty list."""
        counter = TokenCounter()
        counts = counter.count_tokens_batch([])
        assert counts == []

    def test_batch_single_item(self):
        """Test batch counting with single item."""
        counter = TokenCounter()
        counts = counter.count_tokens_batch(["Hello world"])
        assert len(counts) == 1
        assert counts[0] > 0

    def test_batch_multiple_items(self):
        """Test batch counting with multiple items."""
        counter = TokenCounter()
        contents = ["First item", "Second item", "Third item"]
        counts = counter.count_tokens_batch(contents)

        assert len(counts) == 3
        assert all(isinstance(c, int) for c in counts)
        assert all(c > 0 for c in counts)

    def test_batch_with_duplicates(self):
        """Test batch counting with duplicate content."""
        counter = TokenCounter(cache_enabled=True)
        contents = ["Same content", "Different content", "Same content"]
        counts = counter.count_tokens_batch(contents)

        # Duplicate items should have same count
        assert counts[0] == counts[2]
        # Cache should be used for duplicate
        assert counter.get_cache_stats()["cache_size"] == 2

    def test_batch_with_empty_strings(self):
        """Test batch counting with some empty strings."""
        counter = TokenCounter()
        contents = ["Content", "", "More content"]
        counts = counter.count_tokens_batch(contents)

        assert len(counts) == 3
        assert counts[0] > 0
        assert counts[1] == 0
        assert counts[2] > 0

    def test_batch_preserves_order(self):
        """Test that batch results maintain input order."""
        counter = TokenCounter()
        contents = ["Short", "A much longer sentence", "Medium length"]
        counts = counter.count_tokens_batch(contents)

        # Verify order is preserved by checking each individually
        for content, batch_count in zip(contents, counts):
            individual_count = counter.count_tokens(content)
            assert batch_count == individual_count


class TestTokenCounterContext:
    """Test context aggregation functionality."""

    def test_context_empty_list(self):
        """Test context counting with empty list."""
        counter = TokenCounter()
        total = counter.count_context_tokens([])
        assert total == 0

    def test_context_single_item(self):
        """Test context counting with single item."""
        counter = TokenCounter()
        items = [{"content": "Task description"}]
        total = counter.count_context_tokens(items)
        assert total > 0

    def test_context_multiple_items(self):
        """Test context counting with multiple items."""
        counter = TokenCounter()
        items = [
            {"content": "First task description"},
            {"content": "Second task description"},
            {"content": "Third task description"},
        ]
        total = counter.count_context_tokens(items)

        # Total should be sum of individual counts
        individual_sum = sum(counter.count_tokens(item["content"]) for item in items)
        assert total == individual_sum

    def test_context_missing_content_key(self):
        """Test context counting with missing content keys."""
        counter = TokenCounter()
        items = [
            {"content": "Valid content"},
            {"other_key": "No content key"},
            {"content": "More valid content"},
        ]
        total = counter.count_context_tokens(items)

        # Should handle missing keys gracefully (empty string = 0 tokens)
        expected = (
            counter.count_tokens("Valid content")
            + counter.count_tokens("")
            + counter.count_tokens("More valid content")
        )
        assert total == expected

    def test_context_with_metadata(self):
        """Test context counting ignores extra metadata."""
        counter = TokenCounter()
        items = [
            {"content": "Task content", "tier": "hot", "importance": 0.9, "extra_field": "ignored"},
            {"content": "More content", "tier": "warm"},
        ]
        total = counter.count_context_tokens(items)

        # Should only count content field
        expected = counter.count_tokens("Task content") + counter.count_tokens("More content")
        assert total == expected

    def test_context_empty_content(self):
        """Test context counting with empty content values."""
        counter = TokenCounter()
        items = [{"content": "Real content"}, {"content": ""}, {"content": "More real content"}]
        total = counter.count_context_tokens(items)

        expected = (
            counter.count_tokens("Real content") + 0 + counter.count_tokens("More real content")
        )
        assert total == expected


class TestTokenCounterEdgeCases:
    """Test edge cases and error handling."""

    def test_very_long_content(self):
        """Test counting tokens in very long content."""
        counter = TokenCounter()
        # Create a long string (10,000 words)
        long_content = " ".join(["word"] * 10000)
        count = counter.count_tokens(long_content)
        assert count > 0
        # Should handle large content without errors

    def test_unicode_content(self):
        """Test counting tokens with Unicode characters."""
        counter = TokenCounter()
        unicode_content = "Hello 世界 🌍 мир"
        count = counter.count_tokens(unicode_content)
        assert count > 0

    def test_special_characters(self):
        """Test counting tokens with special characters."""
        counter = TokenCounter()
        special_content = "!@#$%^&*()_+-={}[]|:;<>?,./~`"
        count = counter.count_tokens(special_content)
        assert count >= 0

    def test_code_content(self):
        """Test counting tokens in code."""
        counter = TokenCounter()
        code_content = """
        def example_function(x, y):
            return x + y
        """
        count = counter.count_tokens(code_content)
        assert count > 0

    def test_model_fallback(self):
        """Test fallback to default encoding for unknown model."""
        counter = TokenCounter(model="unknown-model-xyz")
        count = counter.count_tokens("Hello world")
        assert count > 0  # Should use fallback encoding

    def test_get_cache_stats_structure(self):
        """Test cache stats return correct structure."""
        counter = TokenCounter()
        stats = counter.get_cache_stats()

        assert "cache_size" in stats
        assert "cache_enabled" in stats
        assert isinstance(stats["cache_size"], int)
        assert isinstance(stats["cache_enabled"], bool)


class TestTokenCounterPerformance:
    """Test performance characteristics."""

    def test_batch_vs_individual_accuracy(self):
        """Verify batch and individual counting produce same results."""
        counter = TokenCounter()
        contents = [
            "Short text",
            "A much longer text with many more words to count",
            "Medium length text here",
        ]

        # Get batch counts
        batch_counts = counter.count_tokens_batch(contents)

        # Get individual counts
        individual_counts = [counter.count_tokens(c) for c in contents]

        assert batch_counts == individual_counts

    def test_cache_reuse(self):
        """Test that cache is actually reused for identical content."""
        counter = TokenCounter(cache_enabled=True)
        content = "Repeated content for cache testing"

        # Count multiple times
        counts = [counter.count_tokens(content) for _ in range(10)]

        # All counts should be identical
        assert all(c == counts[0] for c in counts)
        # Cache should only have one entry
        assert counter.get_cache_stats()["cache_size"] == 1

    def test_different_instances_independent_caches(self):
        """Test that different instances maintain independent caches."""
        counter1 = TokenCounter(cache_enabled=True)
        counter2 = TokenCounter(cache_enabled=True)

        counter1.count_tokens("Content 1")
        counter2.count_tokens("Content 2")

        assert counter1.get_cache_stats()["cache_size"] == 1
        assert counter2.get_cache_stats()["cache_size"] == 1
