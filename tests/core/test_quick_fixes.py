"""Tests for pattern-based quick fixes."""

import pytest
from pathlib import Path

from codeframe.core.quick_fixes import (
    find_quick_fix,
    apply_quick_fix,
    detect_package_manager,
    match_module_not_found,
    match_import_error,
    match_name_error,
    match_syntax_error,
    match_indentation_error,
    QuickFix,
    FixType,
    STDLIB_MODULES,
    PACKAGE_ALIASES,
)


class TestModuleNotFoundMatching:
    """Tests for ModuleNotFoundError pattern matching."""

    def test_matches_module_not_found_error(self):
        """Should match ModuleNotFoundError."""
        error = "ModuleNotFoundError: No module named 'requests'"
        fix = match_module_not_found(error)

        assert fix is not None
        assert fix.fix_type == FixType.INSTALL_PACKAGE
        assert "requests" in fix.command or "requests" in fix.description

    def test_matches_import_error_no_module(self):
        """Should match ImportError with 'No module named'."""
        error = "ImportError: No module named 'flask'"
        fix = match_module_not_found(error)

        assert fix is not None
        assert "flask" in fix.command or "flask" in fix.description

    def test_ignores_stdlib_modules(self):
        """Should not try to install standard library modules."""
        error = "ModuleNotFoundError: No module named 'os'"
        fix = match_module_not_found(error)

        assert fix is None

    def test_handles_submodules(self):
        """Should install top-level package for submodule errors."""
        error = "ModuleNotFoundError: No module named 'requests.auth'"
        fix = match_module_not_found(error)

        assert fix is not None
        # Should install 'requests', not 'requests.auth'
        assert "requests" in fix.command or "requests" in fix.description

    def test_uses_package_aliases(self):
        """Should use correct package name for aliased modules."""
        error = "ModuleNotFoundError: No module named 'PIL'"
        fix = match_module_not_found(error)

        assert fix is not None
        # PIL installs as Pillow
        assert "Pillow" in fix.description or "Pillow" in fix.command


class TestImportErrorMatching:
    """Tests for ImportError pattern matching."""

    def test_matches_cannot_import_name(self):
        """Should match 'cannot import name' errors."""
        error = "ImportError: cannot import name 'Foo' from 'bar'"
        fix = match_import_error(error)

        assert fix is not None
        assert fix.fix_type == FixType.ADD_IMPORT
        assert "Foo" in fix.insert_content
        assert "bar" in fix.insert_content


class TestNameErrorMatching:
    """Tests for NameError pattern matching."""

    def test_matches_name_not_defined(self):
        """Should match 'name is not defined' errors."""
        error = "NameError: name 'Optional' is not defined"
        fix = match_name_error(error)

        assert fix is not None
        assert fix.fix_type == FixType.ADD_IMPORT
        assert "Optional" in fix.insert_content
        assert "typing" in fix.insert_content

    def test_handles_dataclass(self):
        """Should suggest dataclass import."""
        error = "NameError: name 'dataclass' is not defined"
        fix = match_name_error(error)

        assert fix is not None
        assert "dataclass" in fix.insert_content
        assert "dataclasses" in fix.insert_content

    def test_handles_path(self):
        """Should suggest Path import."""
        error = "NameError: name 'Path' is not defined"
        fix = match_name_error(error)

        assert fix is not None
        assert "Path" in fix.insert_content
        assert "pathlib" in fix.insert_content


class TestSyntaxErrorMatching:
    """Tests for SyntaxError pattern matching."""

    def test_matches_missing_colon_in_def(self):
        """Should detect missing colon after def."""
        error = "SyntaxError: expected ':' at line 5"
        file_content = """def foo()
    pass
"""
        # Note: We need to be on line 1 for this example
        error_with_line = "SyntaxError: expected ':' at line 1"
        fix = match_syntax_error(error_with_line, file_content)

        assert fix is not None
        assert fix.fix_type == FixType.FIX_SYNTAX


class TestIndentationErrorMatching:
    """Tests for IndentationError pattern matching."""

    def test_matches_mixed_tabs_spaces(self):
        """Should detect mixed tabs and spaces."""
        error = "IndentationError: inconsistent use of tabs and spaces at line 1"
        file_content = "\t    mixed_indent"
        fix = match_indentation_error(error, file_content)

        assert fix is not None
        assert fix.fix_type == FixType.FIX_INDENTATION


class TestPackageManagerDetection:
    """Tests for package manager detection."""

    def test_detects_uv_from_lock(self, tmp_path):
        """Should detect uv from uv.lock."""
        (tmp_path / "uv.lock").touch()
        pm = detect_package_manager(tmp_path)
        assert "uv" in pm

    def test_detects_npm(self, tmp_path):
        """Should detect npm from package-lock.json."""
        (tmp_path / "package-lock.json").touch()
        pm = detect_package_manager(tmp_path)
        assert "npm" in pm

    def test_detects_yarn(self, tmp_path):
        """Should detect yarn from yarn.lock."""
        (tmp_path / "yarn.lock").touch()
        pm = detect_package_manager(tmp_path)
        assert "yarn" in pm

    def test_detects_pnpm(self, tmp_path):
        """Should detect pnpm from pnpm-lock.yaml."""
        (tmp_path / "pnpm-lock.yaml").touch()
        pm = detect_package_manager(tmp_path)
        assert "pnpm" in pm

    def test_detects_poetry(self, tmp_path):
        """Should detect poetry from poetry.lock."""
        (tmp_path / "poetry.lock").touch()
        pm = detect_package_manager(tmp_path)
        assert "poetry" in pm

    def test_default_to_pip(self, tmp_path):
        """Should default to pip when nothing detected."""
        pm = detect_package_manager(tmp_path)
        assert "pip" in pm


class TestFindQuickFix:
    """Tests for find_quick_fix integration function."""

    def test_finds_module_fix(self, tmp_path):
        """Should find fix for module errors."""
        error = "ModuleNotFoundError: No module named 'fastapi'"
        fix = find_quick_fix(error, repo_path=tmp_path)

        assert fix is not None
        assert fix.fix_type == FixType.INSTALL_PACKAGE

    def test_returns_none_for_unknown_errors(self, tmp_path):
        """Should return None for unrecognized errors."""
        error = "Some random error that doesn't match patterns"
        fix = find_quick_fix(error, repo_path=tmp_path)

        assert fix is None


class TestApplyQuickFix:
    """Tests for applying quick fixes."""

    def test_apply_install_package_dry_run(self, tmp_path):
        """Should report what would be run in dry_run mode."""
        fix = QuickFix(
            fix_type=FixType.INSTALL_PACKAGE,
            description="Install requests",
            command="pip install requests",
        )

        success, msg = apply_quick_fix(fix, tmp_path, dry_run=True)

        assert success is True
        assert "Would run" in msg

    def test_apply_add_import(self, tmp_path):
        """Should add import to file."""
        test_file = tmp_path / "main.py"
        test_file.write_text("print('hello')\n")

        fix = QuickFix(
            fix_type=FixType.ADD_IMPORT,
            description="Add Optional import",
            file_path=str(test_file),
            insert_line=1,
            insert_content="from typing import Optional\n",
        )

        success, msg = apply_quick_fix(fix, tmp_path, dry_run=False)

        assert success is True
        content = test_file.read_text()
        assert "from typing import Optional" in content
        # Should be at the top
        assert content.startswith("from typing import Optional")

    def test_apply_fix_syntax(self, tmp_path):
        """Should fix syntax errors."""
        test_file = tmp_path / "main.py"
        test_file.write_text("def foo()\n    pass\n")

        fix = QuickFix(
            fix_type=FixType.FIX_SYNTAX,
            description="Add missing colon",
            file_path=str(test_file),
            old_content="def foo()",
            new_content="def foo():",
        )

        success, msg = apply_quick_fix(fix, tmp_path, dry_run=False)

        assert success is True
        content = test_file.read_text()
        assert "def foo():" in content

    def test_apply_fails_if_old_content_not_found(self, tmp_path):
        """Should fail if old_content not in file."""
        test_file = tmp_path / "main.py"
        test_file.write_text("completely different content\n")

        fix = QuickFix(
            fix_type=FixType.FIX_SYNTAX,
            description="Fix something",
            file_path=str(test_file),
            old_content="content that doesn't exist",
            new_content="new content",
        )

        success, msg = apply_quick_fix(fix, tmp_path, dry_run=False)

        assert success is False
        assert "not found" in msg.lower()

    def test_apply_fails_if_file_missing(self, tmp_path):
        """Should fail gracefully if file doesn't exist."""
        fix = QuickFix(
            fix_type=FixType.FIX_SYNTAX,
            description="Fix something",
            file_path=str(tmp_path / "nonexistent.py"),
            old_content="old",
            new_content="new",
        )

        success, msg = apply_quick_fix(fix, tmp_path, dry_run=False)

        assert success is False


class TestStdlibModules:
    """Tests for standard library module detection."""

    def test_common_stdlib_in_list(self):
        """Common stdlib modules should be in the list."""
        common = ["os", "sys", "re", "json", "datetime", "pathlib", "typing"]
        for mod in common:
            assert mod in STDLIB_MODULES, f"{mod} should be in STDLIB_MODULES"


class TestPackageAliases:
    """Tests for package name aliases."""

    def test_common_aliases(self):
        """Common aliases should be defined."""
        assert PACKAGE_ALIASES.get("PIL") == "Pillow"
        assert PACKAGE_ALIASES.get("cv2") == "opencv-python"
        assert PACKAGE_ALIASES.get("sklearn") == "scikit-learn"
        assert PACKAGE_ALIASES.get("yaml") == "pyyaml"
