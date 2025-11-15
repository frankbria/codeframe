"""
Comprehensive Test Template - Reference for AI Agents

This module provides examples of all major test patterns used in the codeframe
project. AI agents should reference these patterns when writing new tests.

PATTERN COVERAGE MATRIX:
┌──────────────────────────────────────────────────────────────────────────┐
│ Pattern             │ Use When                    │ Example Class        │
├─────────────────────┼─────────────────────────────┼────────────────────── ┤
│ Traditional Unit    │ Known inputs/outputs        │ TestTraditionalUnit  │
│ Parametrized        │ Same logic, many cases      │ TestParametrized     │
│ Property-Based      │ Testing invariants/laws     │ TestPropertyBased    │
│ Fixtures            │ Reusable test setup         │ TestFixtureUsage     │
│ Integration         │ Multi-component workflows   │ TestIntegration      │
│ Async               │ Testing async functions     │ TestAsyncPatterns    │
└──────────────────────────────────────────────────────────────────────────┘

KEY PRINCIPLES:
1. Test behavior, not implementation
2. One assertion per test (when possible)
3. Clear, descriptive test names
4. Arrange-Act-Assert pattern
5. Independent tests (no shared state)
"""

import pytest
from hypothesis import given, strategies as st


# ============================================================================
# Helper Functions (Functions Under Test)
# ============================================================================


def reverse_string(s: str) -> str:
    """Reverse a string."""
    return s[::-1]


def add_numbers(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def normalize_data(data: dict) -> dict:
    """Normalize dictionary keys to lowercase."""
    return {k.lower(): v for k, v in data.items()}


def calculate_discount(price: float, discount_percent: float) -> float:
    """Calculate final price after discount."""
    if not 0 <= discount_percent <= 100:
        raise ValueError("Discount must be between 0 and 100")
    return price * (1 - discount_percent / 100)


# ============================================================================
# Test Class 1: Traditional Unit Tests
# ============================================================================


class TestTraditionalUnitTests:
    """
    Traditional unit tests with specific known inputs and expected outputs.

    Use when: You have concrete test cases with known results.
    """

    def test_reverse_string_with_simple_input(self):
        """Test reversing a simple string."""
        # Arrange
        input_string = "hello"
        expected = "olleh"

        # Act
        result = reverse_string(input_string)

        # Assert
        assert result == expected

    def test_reverse_empty_string(self):
        """Test reversing an empty string returns empty string."""
        assert reverse_string("") == ""

    def test_add_positive_numbers(self):
        """Test adding two positive numbers."""
        assert add_numbers(5, 3) == 8

    def test_add_negative_numbers(self):
        """Test adding two negative numbers."""
        assert add_numbers(-5, -3) == -8

    def test_add_mixed_signs(self):
        """Test adding numbers with different signs."""
        assert add_numbers(10, -3) == 7

    def test_normalize_data_converts_keys_to_lowercase(self):
        """Test that normalize_data lowercases all keys."""
        input_data = {"Name": "Alice", "AGE": 30}
        result = normalize_data(input_data)

        assert result == {"name": "Alice", "age": 30}

    def test_calculate_discount_with_valid_percentage(self):
        """Test discount calculation with valid percentage."""
        price = 100.0
        discount = 20.0  # 20%

        result = calculate_discount(price, discount)

        assert result == 80.0

    def test_calculate_discount_raises_error_for_invalid_percentage(self):
        """Test that invalid discount percentage raises ValueError."""
        with pytest.raises(ValueError, match="Discount must be between 0 and 100"):
            calculate_discount(100.0, 150.0)


# ============================================================================
# Test Class 2: Parametrized Tests
# ============================================================================


class TestParametrizedTests:
    """
    Parametrized tests for testing the same logic with multiple inputs.

    Use when: You want to test the same function with many different inputs.
    """

    @pytest.mark.parametrize(
        "input_string,expected",
        [
            ("hello", "olleh"),
            ("world", "dlrow"),
            ("python", "nohtyp"),
            ("", ""),
            ("a", "a"),
            ("12345", "54321"),
        ],
    )
    def test_reverse_string_multiple_inputs(self, input_string, expected):
        """Test string reversal with multiple inputs."""
        assert reverse_string(input_string) == expected

    @pytest.mark.parametrize(
        "a,b,expected",
        [
            (0, 0, 0),
            (1, 1, 2),
            (10, 20, 30),
            (-5, 5, 0),
            (1.5, 2.5, 4.0),
        ],
    )
    def test_add_numbers_boundary_values(self, a, b, expected):
        """Test adding numbers with boundary values."""
        assert add_numbers(a, b) == expected

    @pytest.mark.parametrize(
        "price,discount,expected",
        [
            (100.0, 0.0, 100.0),  # No discount
            (100.0, 50.0, 50.0),  # 50% discount
            (100.0, 100.0, 0.0),  # 100% discount
            (50.0, 20.0, 40.0),  # 20% discount
        ],
    )
    def test_discount_calculation_edge_cases(self, price, discount, expected):
        """Test discount calculation with edge cases."""
        assert calculate_discount(price, discount) == pytest.approx(expected)


# ============================================================================
# Test Class 3: Property-Based Tests (Hypothesis)
# ============================================================================


class TestPropertyBasedTests:
    """
    Property-based tests using Hypothesis for generative testing.

    Use when: Testing invariants, laws, or properties that hold for all inputs.
    """

    @given(st.text())
    def test_reverse_is_idempotent(self, s):
        """Property: Reversing a string twice returns the original."""
        assert reverse_string(reverse_string(s)) == s

    @given(st.text())
    def test_reverse_preserves_length(self, s):
        """Property: Reversing preserves string length."""
        assert len(reverse_string(s)) == len(s)

    @given(
        st.floats(allow_nan=False, allow_infinity=False),
        st.floats(allow_nan=False, allow_infinity=False),
    )
    def test_addition_is_commutative(self, a, b):
        """Property: Addition is commutative (a + b == b + a)."""
        assert add_numbers(a, b) == pytest.approx(add_numbers(b, a))

    @given(st.dictionaries(st.text(min_size=1), st.integers()))
    def test_normalize_preserves_values(self, data):
        """Property: Normalization preserves dictionary values."""
        normalized = normalize_data(data)
        # Values should be unchanged
        for key, value in data.items():
            assert normalized[key.lower()] == value

    @given(st.floats(min_value=0, max_value=1000), st.floats(min_value=0, max_value=100))
    def test_discount_never_negative(self, price, discount):
        """Property: Discounted price is never negative."""
        result = calculate_discount(price, discount)
        assert result >= 0


# ============================================================================
# Test Class 4: Fixture Usage
# ============================================================================


@pytest.fixture
def sample_data():
    """Fixture providing sample dictionary data."""
    return {"Name": "Alice", "Email": "alice@example.com", "Age": 30}


@pytest.fixture
def temp_user_database(tmp_path):
    """Fixture creating a temporary user database file."""
    db_file = tmp_path / "users.txt"
    db_file.write_text("user1\nuser2\nuser3\n")
    return db_file


class TestFixtureUsage:
    """
    Tests demonstrating fixture usage for reusable setup.

    Use when: You need to set up test data or resources that are reused.
    """

    def test_normalize_with_fixture(self, sample_data):
        """Test normalization using fixture data."""
        result = normalize_data(sample_data)

        assert result["name"] == "Alice"
        assert result["email"] == "alice@example.com"
        assert result["age"] == 30

    def test_fixture_data_is_independent(self, sample_data):
        """Test that fixture data is fresh for each test."""
        # Modify the fixture data
        sample_data["Name"] = "Bob"

        # This should still be "Alice" in the next test
        assert sample_data["Name"] == "Bob"

    def test_temp_file_fixture(self, temp_user_database):
        """Test using a temporary file fixture."""
        content = temp_user_database.read_text()

        assert "user1" in content
        assert "user2" in content
        assert "user3" in content


# ============================================================================
# Test Class 5: Integration Patterns
# ============================================================================


@pytest.mark.integration
class TestIntegrationPatterns:
    """
    Integration tests that test multiple components together.

    Use when: Testing workflows that involve multiple functions or modules.
    """

    def test_multi_step_data_processing_workflow(self):
        """Test a workflow with multiple processing steps."""
        # Step 1: Prepare data
        raw_data = {"ITEM": "Widget", "PRICE": 100.0}

        # Step 2: Normalize
        normalized = normalize_data(raw_data)

        # Step 3: Apply discount
        final_price = calculate_discount(normalized["price"], 10.0)

        # Assert final result
        assert final_price == 90.0

    def test_error_propagation_across_functions(self):
        """Test that errors propagate correctly through a workflow."""
        raw_data = {"PRICE": 100.0}

        # Normalize
        normalized = normalize_data(raw_data)

        # This should raise an error due to invalid discount
        with pytest.raises(ValueError):
            calculate_discount(normalized["price"], 150.0)


# ============================================================================
# Test Class 6: Async Patterns
# ============================================================================


async def async_fetch_user(user_id: int) -> dict:
    """Simulated async function to fetch user data."""
    # Simulated async operation
    return {"id": user_id, "name": f"User{user_id}"}


async def async_process_batch(items: list) -> list:
    """Simulated async batch processing."""
    # Simulated async operation
    return [item * 2 for item in items]


@pytest.mark.asyncio
class TestAsyncPatterns:
    """
    Tests for async functions using pytest-asyncio.

    Use when: Testing async/await functions.
    """

    async def test_async_fetch_user(self):
        """Test async user fetching."""
        user = await async_fetch_user(123)

        assert user["id"] == 123
        assert user["name"] == "User123"

    async def test_async_batch_processing(self):
        """Test async batch processing."""
        items = [1, 2, 3, 4, 5]
        result = await async_process_batch(items)

        assert result == [2, 4, 6, 8, 10]

    async def test_async_error_handling(self):
        """Test error handling in async functions."""
        # This would test async error scenarios
        user = await async_fetch_user(0)
        assert user["id"] == 0


# ============================================================================
# Summary: When to Use Each Pattern
# ============================================================================

"""
PATTERN SELECTION GUIDE:

1. **Traditional Unit Tests** (TestTraditionalUnitTests)
   - Use for: Known input/output pairs
   - Example: Test that reverse("hello") == "olleh"

2. **Parametrized Tests** (TestParametrizedTests)
   - Use for: Same test logic with many inputs
   - Example: Test add_numbers with (1,1,2), (2,3,5), (10,20,30)

3. **Property-Based Tests** (TestPropertyBasedTests)
   - Use for: Testing invariants that should hold for all inputs
   - Example: reverse(reverse(s)) == s for any string s

4. **Fixtures** (TestFixtureUsage)
   - Use for: Reusable test data or setup/teardown
   - Example: Database connections, temp files, sample data

5. **Integration Tests** (TestIntegrationPatterns)
   - Use for: Multi-step workflows across components
   - Example: normalize() -> calculate_discount() workflow
   - Mark with: @pytest.mark.integration

6. **Async Tests** (TestAsyncPatterns)
   - Use for: Testing async/await functions
   - Example: API calls, database queries, concurrent operations
   - Mark with: @pytest.mark.asyncio

QUICK REFERENCE:
- Concrete case? → Traditional
- Many similar cases? → Parametrized
- Testing a law/property? → Property-based (Hypothesis)
- Need setup/teardown? → Fixtures
- Multi-component workflow? → Integration
- Async function? → Async patterns
"""
