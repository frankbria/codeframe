"""
Ultra-simple sanity test to verify pytest works.
"""

import pytest


def test_sanity():
    """Simplest possible test."""
    print("\n🎯 SANITY TEST: Starting...")
    assert 1 + 1 == 2
    print("🎯 SANITY TEST: Passed!")


@pytest.mark.asyncio
async def test_async_sanity():
    """Simplest async test."""
    print("\n🎯 ASYNC SANITY TEST: Starting...")
    import asyncio

    await asyncio.sleep(0.1)
    assert True
    print("🎯 ASYNC SANITY TEST: Passed!")
