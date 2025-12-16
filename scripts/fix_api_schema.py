#!/usr/bin/env python3
"""Fix old API schema (project_name/project_type) to new schema (name/description)."""

import re
import sys
from pathlib import Path


def fix_api_schema(content: str) -> str:
    """Fix API schema in test file content."""

    # Pattern 1: Both project_name and project_type in one JSON object
    # Handles optional extra fields after project_type
    # {"project_name": "foo", "project_type": "python"}
    # {"project_name": "foo", "project_type": "python", "extra": "field"}
    # → {"name": "foo", "description": "Test project"}
    # → {"name": "foo", "description": "Test project", "extra": "field"}
    pattern1 = r'\{"project_name":\s*"([^"]+)",\s*"project_type":\s*"[^"]+"(,\s*[^}]+)?\}'

    def replace_pattern1(match):
        name = match.group(1)
        extra_fields = match.group(2) or ""
        return f'{{"name": "{name}", "description": "Test project"{extra_fields}}}'

    content = re.sub(pattern1, replace_pattern1, content)

    # Pattern 2: Only project_type (for testing missing name)
    # {"project_type": "python"}
    # → {"description": "Test project"}
    pattern2 = r'\{"project_type":\s*"[^"]+"\}'
    replacement2 = r'{"description": "Test project"}'
    content = re.sub(pattern2, replacement2, content)

    # Pattern 3: Only project_name (for testing defaults)
    # {"project_name": "foo"}
    # → {"name": "foo", "description": "Test project"}
    pattern3 = r'\{"project_name":\s*"([^"]+)"\}'
    replacement3 = r'{"name": "\1", "description": "Test project"}'
    content = re.sub(pattern3, replacement3, content)

    # Pattern 4: project_name with extra fields (including project_type in any position)
    # {"project_name": "foo", "other": "bar"}
    # {"project_name": "foo", "other": "bar", "project_type": "python"}
    # → {"name": "foo", "description": "Test project", "other": "bar"}
    pattern4 = r'\{"project_name":\s*"([^"]+)",\s*([^}]+)\}'

    def replace_with_desc(match):
        name = match.group(1)
        rest = match.group(2)
        # Remove project_type field if present (it's been replaced by description)
        rest = re.sub(r',?\s*"project_type":\s*"[^"]+"', '', rest)
        rest = re.sub(r'"project_type":\s*"[^"]+",?\s*', '', rest)
        # Clean up any leading/trailing commas
        rest = rest.strip().strip(',').strip()
        if rest:
            return f'{{"name": "{name}", "description": "Test project", {rest}}}'
        else:
            return f'{{"name": "{name}", "description": "Test project"}}'

    content = re.sub(pattern4, replace_with_desc, content)

    # Pattern 5: Empty project_name with project_type (and optional extra fields)
    # {"project_name": "", "project_type": "python"}
    # {"project_name": "", "project_type": "python", "extra": "field"}
    # → {"name": "", "description": "Test project"}
    # → {"name": "", "description": "Test project", "extra": "field"}
    pattern5 = r'\{"project_name":\s*"",\s*"project_type":\s*"[^"]+"(,\s*[^}]+)?\}'

    def replace_pattern5(match):
        extra_fields = match.group(1) or ""
        return f'{{"name": "", "description": "Test project"{extra_fields}}}'

    content = re.sub(pattern5, replace_pattern5, content)

    # Fix docstrings and comments mentioning project_name
    content = content.replace("missing project_name", "missing name")
    content = content.replace("empty project_name", "empty name")
    content = content.replace("duplicate project_name", "duplicate name")
    content = content.replace("Test that project_type", "Test that source_type")
    content = content.replace("invalid project_type", "invalid source_type")

    # Fix assertions checking project_name in responses
    content = re.sub(r'\["project_name"\]', r'["name"]', content)

    return content


def main():
    """Fix API schema in all test files."""
    files_to_fix = [
        "tests/api/test_project_creation_api.py",
        "tests/api/test_endpoints_database.py",
        "tests/persistence/test_database.py",
        "tests/conftest.py",
    ]

    fixed_count = 0

    for file_path_str in files_to_fix:
        file_path = Path(file_path_str)

        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            continue

        # Read original content
        original_content = file_path.read_text()

        # Fix schema
        fixed_content = fix_api_schema(original_content)

        # Check if changes were made
        if original_content != fixed_content:
            file_path.write_text(fixed_content)
            print(f"✅ Fixed: {file_path}")
            fixed_count += 1
        else:
            print(f"⏭️  Skipped (no changes): {file_path}")

    print(f"\n📊 Fixed {fixed_count} files")
    return 0 if fixed_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
