"""
Pytest configuration for unit tests.
"""

# Skip v1 legacy tests that import removed dependencies
# These tests rely on v1 routers that use get_db
collect_ignore = [
    "test_pr_router.py",
]
