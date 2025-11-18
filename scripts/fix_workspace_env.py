#!/usr/bin/env python3
"""Add WORKSPACE_ROOT environment variable to tests that reload server."""

import re
from pathlib import Path


def fix_workspace_env(content: str) -> str:
    """Add WORKSPACE_ROOT to tests that set DATABASE_PATH."""

    # Pattern: Find where DATABASE_PATH is set, add WORKSPACE_ROOT right after
    pattern = r'(os\.environ\["DATABASE_PATH"\] = str\(temp_db_path\))'

    def add_workspace_root(match):
        original = match.group(1)
        return f"""{original}

        # Set temporary workspace root to avoid collisions
        workspace_root = temp_db_path.parent / "workspaces"
        os.environ["WORKSPACE_ROOT"] = str(workspace_root)"""

    # Only apply if WORKSPACE_ROOT not already set
    if 'WORKSPACE_ROOT' not in content:
        content = re.sub(pattern, add_workspace_root, content)

    return content


def main():
    """Fix workspace environment in all API test files."""
    api_test_dir = Path("tests/api")

    fixed_count = 0

    for test_file in api_test_dir.glob("test_*.py"):
        original_content = test_file.read_text()

        # Only fix if it sets DATABASE_PATH
        if 'os.environ["DATABASE_PATH"]' in original_content:
            fixed_content = fix_workspace_env(original_content)

            if original_content != fixed_content:
                test_file.write_text(fixed_content)
                print(f"✅ Fixed: {test_file}")
                fixed_count += 1
            else:
                print(f"⏭️  Skipped (already has WORKSPACE_ROOT): {test_file}")

    print(f"\n📊 Fixed {fixed_count} files")


if __name__ == "__main__":
    main()
