"""Pattern-based quick fixes for common errors.

Fixes common errors without requiring LLM calls:
- ModuleNotFoundError → install package
- ImportError → add import statement
- NameError → add missing import
- SyntaxError → common syntax fixes
- IndentationError → fix indentation

This module is headless - no FastAPI or HTTP dependencies.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Callable


class FixType(str, Enum):
    """Type of fix to apply."""

    INSTALL_PACKAGE = "install_package"
    ADD_IMPORT = "add_import"
    FIX_SYNTAX = "fix_syntax"
    FIX_INDENTATION = "fix_indentation"
    ADD_MISSING_FILE = "add_missing_file"
    FIX_TYPE_HINT = "fix_type_hint"


@dataclass
class QuickFix:
    """A quick fix that can be applied without LLM.

    Attributes:
        fix_type: Category of fix
        description: Human-readable description
        command: Shell command to run (for INSTALL_PACKAGE)
        file_path: File to modify (for code fixes)
        old_content: Content to find/replace
        new_content: Replacement content
        insert_line: Line number to insert at (1-based)
        insert_content: Content to insert
    """

    fix_type: FixType
    description: str
    command: Optional[str] = None
    file_path: Optional[str] = None
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    insert_line: Optional[int] = None
    insert_content: Optional[str] = None


# Mapping from common import names to package names
# (when they differ, e.g., import PIL → pip install Pillow)
PACKAGE_ALIASES = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
}

# Common standard library modules (shouldn't be installed)
STDLIB_MODULES = {
    "os", "sys", "re", "json", "datetime", "time", "math", "random",
    "collections", "itertools", "functools", "typing", "pathlib",
    "subprocess", "threading", "multiprocessing", "asyncio", "contextlib",
    "dataclasses", "enum", "abc", "copy", "io", "tempfile", "shutil",
    "logging", "unittest", "argparse", "configparser", "hashlib", "hmac",
    "base64", "struct", "pickle", "sqlite3", "csv", "xml", "html",
    "http", "urllib", "email", "mimetypes", "socket", "ssl", "select",
    "signal", "platform", "getpass", "glob", "fnmatch", "textwrap",
    "string", "decimal", "fractions", "statistics", "secrets", "uuid",
}


def detect_package_manager(repo_path: Path) -> str:
    """Detect the package manager to use.

    Args:
        repo_path: Path to the repository

    Returns:
        Package manager command (uv, pip, npm, etc.)
    """
    # Check for Python package managers
    if (repo_path / "uv.lock").exists() or (repo_path / "pyproject.toml").exists():
        # Check if uv is being used
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            if "[tool.uv]" in content or "uv.lock" in content:
                return "uv pip install"
        return "uv pip install"  # Default to uv for Python

    if (repo_path / "requirements.txt").exists():
        return "pip install"

    if (repo_path / "Pipfile").exists():
        return "pipenv install"

    if (repo_path / "poetry.lock").exists():
        return "poetry add"

    # Check for Node.js package managers
    if (repo_path / "package-lock.json").exists():
        return "npm install"

    if (repo_path / "yarn.lock").exists():
        return "yarn add"

    if (repo_path / "pnpm-lock.yaml").exists():
        return "pnpm add"

    # Default to pip
    return "pip install"


def match_module_not_found(error: str) -> Optional[QuickFix]:
    """Match ModuleNotFoundError and generate install fix.

    Patterns:
        - ModuleNotFoundError: No module named 'X'
        - ImportError: No module named 'X'

    Args:
        error: Error message

    Returns:
        QuickFix if matched, None otherwise
    """
    patterns = [
        r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]",
        r"ImportError: No module named ['\"]([^'\"]+)['\"]",
        r"No module named ['\"]([^'\"]+)['\"]",
    ]

    for pattern in patterns:
        match = re.search(pattern, error, re.IGNORECASE)
        if match:
            module = match.group(1).split('.')[0]  # Get top-level module

            # Skip standard library modules
            if module in STDLIB_MODULES:
                return None

            # Get actual package name
            package = PACKAGE_ALIASES.get(module, module)

            return QuickFix(
                fix_type=FixType.INSTALL_PACKAGE,
                description=f"Install missing package: {package}",
                command=f"{{package_manager}} {package}",
            )

    return None


def match_import_error(error: str, file_content: Optional[str] = None) -> Optional[QuickFix]:
    """Match ImportError for specific name and suggest import.

    Patterns:
        - ImportError: cannot import name 'X' from 'Y'
        - cannot import name 'X' from 'Y'

    Args:
        error: Error message
        file_content: Content of the file with the error

    Returns:
        QuickFix if matched, None otherwise
    """
    pattern = r"cannot import name ['\"]([^'\"]+)['\"] from ['\"]([^'\"]+)['\"]"
    match = re.search(pattern, error, re.IGNORECASE)

    if match:
        name = match.group(1)
        module = match.group(2)

        return QuickFix(
            fix_type=FixType.ADD_IMPORT,
            description=f"Fix import: from {module} import {name}",
            insert_line=1,  # Insert at top of file
            insert_content=f"from {module} import {name}\n",
        )

    return None


def match_name_error(error: str, file_content: Optional[str] = None) -> Optional[QuickFix]:
    """Match NameError and suggest import if it's a known module/type.

    Patterns:
        - NameError: name 'X' is not defined
        - name 'X' is not defined

    Args:
        error: Error message
        file_content: Content of the file with the error

    Returns:
        QuickFix if matched, None otherwise
    """
    pattern = r"(?:NameError: )?name ['\"]([^'\"]+)['\"] is not defined"
    match = re.search(pattern, error, re.IGNORECASE)

    if match:
        name = match.group(1)

        # Common imports that cause NameError
        common_imports = {
            # Typing
            "Optional": "from typing import Optional",
            "List": "from typing import List",
            "Dict": "from typing import Dict",
            "Any": "from typing import Any",
            "Union": "from typing import Union",
            "Callable": "from typing import Callable",
            "TypeVar": "from typing import TypeVar",
            # Dataclasses
            "dataclass": "from dataclasses import dataclass",
            "field": "from dataclasses import field",
            # Enum
            "Enum": "from enum import Enum",
            # Path
            "Path": "from pathlib import Path",
            # Datetime
            "datetime": "from datetime import datetime",
            "timedelta": "from datetime import timedelta",
            "timezone": "from datetime import timezone",
            # JSON
            "json": "import json",
            # Re
            "re": "import re",
            # OS
            "os": "import os",
            # Sys
            "sys": "import sys",
        }

        if name in common_imports:
            return QuickFix(
                fix_type=FixType.ADD_IMPORT,
                description=f"Add missing import for {name}",
                insert_line=1,
                insert_content=common_imports[name] + "\n",
            )

    return None


def match_syntax_error(error: str, file_content: Optional[str] = None) -> Optional[QuickFix]:
    """Match common SyntaxError patterns and suggest fixes.

    Patterns handled:
        - Missing colon after def/class/if/for/while
        - Unclosed brackets/parentheses
        - Invalid syntax near common patterns

    Args:
        error: Error message
        file_content: Content of the file with the error

    Returns:
        QuickFix if matched, None otherwise
    """
    # Extract line number if present
    line_match = re.search(r'line (\d+)', error, re.IGNORECASE)
    line_num = int(line_match.group(1)) if line_match else None

    # Missing colon patterns
    if "expected ':'" in error.lower() or "SyntaxError: invalid syntax" in error:
        if file_content and line_num:
            lines = file_content.split('\n')
            if 0 < line_num <= len(lines):
                line = lines[line_num - 1]
                # Check if it's a def/class/if/for/while without colon
                if re.match(r'^\s*(def|class|if|elif|else|for|while|try|except|finally|with)\s+.+[^:]\s*$', line):
                    return QuickFix(
                        fix_type=FixType.FIX_SYNTAX,
                        description=f"Add missing colon at line {line_num}",
                        old_content=line,
                        new_content=line.rstrip() + ":",
                    )

    # f-string without f prefix
    if "unterminated string literal" in error.lower() or "invalid syntax" in error.lower():
        if file_content and line_num:
            lines = file_content.split('\n')
            if 0 < line_num <= len(lines):
                line = lines[line_num - 1]
                # Pattern to match string literals with optional prefix
                # Captures: (1) prefix like r/u/b/br/fr, (2) opening quote, (3) body, (4) closing quote
                string_pattern = r'([rRuUbBfF]*)(["\'])([^"\']*\{[^}]+\}[^"\']*)\2'
                match = re.search(string_pattern, line)
                if match:
                    prefix = match.group(1)
                    quote = match.group(2)
                    body = match.group(3)

                    # Skip if already has 'f' prefix
                    if 'f' in prefix.lower():
                        pass  # Already an f-string
                    # Skip byte strings - can't add 'f' to 'b'
                    elif 'b' in prefix.lower():
                        pass  # Byte string, can't be f-string
                    else:
                        # Add 'f' to prefix (before 'r' if present, e.g., 'r' -> 'rf')
                        if 'r' in prefix.lower():
                            # Keep the case of r, add f before it
                            new_prefix = 'f' + prefix
                        else:
                            new_prefix = 'f' + prefix
                        # Build the new string literal
                        old_literal = f"{prefix}{quote}{body}{quote}"
                        new_literal = f"{new_prefix}{quote}{body}{quote}"
                        new_line = line.replace(old_literal, new_literal, 1)
                        if new_line != line:
                            return QuickFix(
                                fix_type=FixType.FIX_SYNTAX,
                                description=f"Add f-string prefix at line {line_num}",
                                old_content=line,
                                new_content=new_line,
                            )

    return None


def match_indentation_error(error: str, file_content: Optional[str] = None) -> Optional[QuickFix]:
    """Match IndentationError and suggest fix.

    Args:
        error: Error message
        file_content: Content of the file with the error

    Returns:
        QuickFix if matched, None otherwise
    """
    if "IndentationError" not in error and "indentation" not in error.lower():
        return None

    line_match = re.search(r'line (\d+)', error, re.IGNORECASE)
    if not line_match or not file_content:
        return None

    line_num = int(line_match.group(1))
    lines = file_content.split('\n')

    if not (0 < line_num <= len(lines)):
        return None

    current_line = lines[line_num - 1]

    # Detect mixed tabs/spaces
    if '\t' in current_line and ' ' in current_line[:len(current_line) - len(current_line.lstrip())]:
        # Convert to consistent spaces
        leading = current_line[:len(current_line) - len(current_line.lstrip())]
        # Replace tabs with 4 spaces
        new_leading = leading.replace('\t', '    ')
        new_line = new_leading + current_line.lstrip()

        return QuickFix(
            fix_type=FixType.FIX_INDENTATION,
            description=f"Fix mixed indentation at line {line_num}",
            old_content=current_line,
            new_content=new_line,
        )

    # Unexpected indent - try to match previous line's indentation
    if "unexpected indent" in error.lower() and line_num > 1:
        prev_line = lines[line_num - 2]
        prev_indent = len(prev_line) - len(prev_line.lstrip())

        # If previous line ends with colon, add 4 spaces
        if prev_line.rstrip().endswith(':'):
            expected_indent = prev_indent + 4
        else:
            expected_indent = prev_indent

        new_line = ' ' * expected_indent + current_line.lstrip()

        return QuickFix(
            fix_type=FixType.FIX_INDENTATION,
            description=f"Fix unexpected indentation at line {line_num}",
            old_content=current_line,
            new_content=new_line,
        )

    return None


def match_type_error(error: str) -> Optional[QuickFix]:
    """Match TypeError for missing type hints.

    Args:
        error: Error message

    Returns:
        QuickFix if matched, None otherwise
    """
    # This is more complex and usually needs LLM help
    # But we can catch some simple cases
    return None


# All pattern matchers in order of precedence
PATTERN_MATCHERS: list[Callable] = [
    match_module_not_found,
    match_import_error,
    match_name_error,
    match_syntax_error,
    match_indentation_error,
    match_type_error,
]


def find_quick_fix(
    error: str,
    file_path: Optional[Path] = None,
    repo_path: Optional[Path] = None,
) -> Optional[QuickFix]:
    """Find a quick fix for an error without LLM.

    Args:
        error: Error message
        file_path: Path to the file with the error (if known)
        repo_path: Path to the repository root

    Returns:
        QuickFix if a pattern match is found, None otherwise
    """
    # Read file content if we have a path
    file_content = None
    if file_path and file_path.exists():
        try:
            file_content = file_path.read_text()
        except Exception:
            pass

    # Try each pattern matcher
    for matcher in PATTERN_MATCHERS:
        try:
            # Check if matcher accepts file_content
            import inspect
            sig = inspect.signature(matcher)
            if 'file_content' in sig.parameters:
                fix = matcher(error, file_content)
            else:
                fix = matcher(error)

            if fix:
                # Fill in package manager if needed
                if fix.command and "{package_manager}" in fix.command and repo_path:
                    pm = detect_package_manager(repo_path)
                    fix.command = fix.command.replace("{package_manager}", pm)

                # Set file path if we have it
                if file_path and not fix.file_path:
                    fix.file_path = str(file_path)

                return fix

        except Exception:
            continue

    return None


def apply_quick_fix(
    fix: QuickFix,
    repo_path: Path,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Apply a quick fix.

    Args:
        fix: The fix to apply
        repo_path: Repository root path
        dry_run: If True, don't make changes

    Returns:
        Tuple of (success, message)
    """
    try:
        if fix.fix_type == FixType.INSTALL_PACKAGE:
            if not fix.command:
                return False, "No install command specified"

            if dry_run:
                return True, f"Would run: {fix.command}"

            import subprocess
            result = subprocess.run(
                fix.command.split(),
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                return True, f"Installed package: {fix.command}"
            else:
                return False, f"Install failed: {result.stderr}"

        elif fix.fix_type in {FixType.ADD_IMPORT, FixType.FIX_SYNTAX, FixType.FIX_INDENTATION}:
            if not fix.file_path:
                return False, "No file path specified"

            file_path = repo_path / fix.file_path
            if not file_path.exists():
                return False, f"File not found: {fix.file_path}"

            content = file_path.read_text()

            if fix.old_content and fix.new_content:
                # Replace content
                if fix.old_content not in content:
                    return False, f"Content to replace not found in {fix.file_path}"

                if dry_run:
                    return True, f"Would replace in {fix.file_path}"

                new_content = content.replace(fix.old_content, fix.new_content, 1)
                file_path.write_text(new_content)
                return True, f"Fixed: {fix.description}"

            elif fix.insert_line and fix.insert_content:
                # Insert content at line
                lines = content.split('\n')
                insert_idx = max(0, fix.insert_line - 1)

                if dry_run:
                    return True, f"Would insert at line {fix.insert_line} in {fix.file_path}"

                lines.insert(insert_idx, fix.insert_content.rstrip('\n'))
                file_path.write_text('\n'.join(lines))
                return True, f"Inserted: {fix.description}"

        return False, "Unknown fix type or missing parameters"

    except Exception as e:
        return False, f"Error applying fix: {e}"
