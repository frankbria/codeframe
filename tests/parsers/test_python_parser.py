"""Tests for Python code parser.

Following TDD methodology - these tests are written BEFORE implementation.
"""

import tempfile
from pathlib import Path

import pytest

from codeframe.indexing.models import Symbol, SymbolType
from codeframe.indexing.parsers.python_parser import PythonParser


class TestPythonParser:
    """Test PythonParser functionality."""

    @pytest.fixture
    def parser(self):
        """Create a PythonParser instance."""
        return PythonParser()

    @pytest.fixture
    def temp_file(self):
        """Create a temporary Python file for testing."""
        temp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        yield Path(temp.name)
        # Cleanup
        Path(temp.name).unlink(missing_ok=True)

    def test_parse_empty_file(self, parser, temp_file):
        """Test parsing an empty Python file."""
        temp_file.write_text("")
        symbols = parser.parse_file(temp_file)
        assert symbols == []

    def test_parse_simple_class(self, parser, temp_file):
        """Test parsing a simple Python class."""
        code = """class User:
    pass
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        assert len(symbols) == 1
        assert symbols[0].name == "User"
        assert symbols[0].type == SymbolType.CLASS
        assert symbols[0].line_number == 1
        assert symbols[0].language == "python"
        assert symbols[0].file_path == str(temp_file)

    def test_parse_class_with_methods(self, parser, temp_file):
        """Test parsing a class with methods."""
        code = """class User:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello, {self.name}"
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Should find 1 class + 2 methods = 3 symbols
        assert len(symbols) == 3

        class_sym = [s for s in symbols if s.type == SymbolType.CLASS][0]
        assert class_sym.name == "User"
        assert class_sym.line_number == 1

        methods = [s for s in symbols if s.type == SymbolType.METHOD]
        assert len(methods) == 2

        method_names = {m.name for m in methods}
        assert method_names == {"__init__", "greet"}

        # Check that methods have parent set
        for method in methods:
            assert method.parent == "User"
            assert method.language == "python"

    def test_parse_multiple_classes(self, parser, temp_file):
        """Test parsing multiple classes in one file."""
        code = """class User:
    pass

class Admin:
    pass

class Guest:
    pass
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        assert len(symbols) == 3

        class_names = {s.name for s in symbols if s.type == SymbolType.CLASS}
        assert class_names == {"User", "Admin", "Guest"}

    def test_parse_top_level_function(self, parser, temp_file):
        """Test parsing top-level functions."""
        code = """def get_user(user_id):
    return User.get(user_id)

def save_user(user):
    user.save()
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        assert len(symbols) == 2

        func_names = {s.name for s in symbols if s.type == SymbolType.FUNCTION}
        assert func_names == {"get_user", "save_user"}

        for symbol in symbols:
            assert symbol.type == SymbolType.FUNCTION
            assert symbol.parent is None
            assert symbol.language == "python"

    def test_parse_mixed_classes_and_functions(self, parser, temp_file):
        """Test parsing file with both classes and functions."""
        code = """def helper_function():
    pass

class User:
    def save(self):
        pass

def another_helper():
    pass
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # 2 functions + 1 class + 1 method = 4 symbols
        assert len(symbols) == 4

        functions = [s for s in symbols if s.type == SymbolType.FUNCTION]
        assert len(functions) == 2
        assert {f.name for f in functions} == {"helper_function", "another_helper"}

        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "User"

        methods = [s for s in symbols if s.type == SymbolType.METHOD]
        assert len(methods) == 1
        assert methods[0].name == "save"
        assert methods[0].parent == "User"

    def test_parse_nested_classes(self, parser, temp_file):
        """Test parsing nested classes."""
        code = """class Outer:
    class Inner:
        def inner_method(self):
            pass

    def outer_method(self):
        pass
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Should find: Outer class, Inner class, inner_method, outer_method
        assert len(symbols) >= 2  # At minimum, both classes

        outer_classes = [s for s in symbols if s.name == "Outer" and s.type == SymbolType.CLASS]
        assert len(outer_classes) == 1

        # Inner class should exist
        inner_classes = [s for s in symbols if s.name == "Inner" and s.type == SymbolType.CLASS]
        assert len(inner_classes) == 1

    def test_parse_class_with_docstring(self, parser, temp_file):
        """Test parsing class with docstring."""
        code = '''class User:
    """A user model."""

    def __init__(self):
        """Initialize user."""
        pass
'''
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Should find class and method
        assert len(symbols) >= 1

        class_sym = [s for s in symbols if s.type == SymbolType.CLASS][0]
        assert class_sym.name == "User"

    def test_parse_function_with_decorators(self, parser, temp_file):
        """Test parsing functions with decorators."""
        code = """@property
def name(self):
    return self._name

@staticmethod
def create():
    return User()
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Should find both functions
        assert len(symbols) == 2

        func_names = {s.name for s in symbols}
        assert "name" in func_names
        assert "create" in func_names

    def test_parse_file_with_imports(self, parser, temp_file):
        """Test parsing file with import statements."""
        code = """import os
from typing import List

class User:
    pass
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Should only find the class, not imports
        class_symbols = [s for s in symbols if s.type == SymbolType.CLASS]
        assert len(class_symbols) == 1
        assert class_symbols[0].name == "User"

    def test_parse_async_functions(self, parser, temp_file):
        """Test parsing async functions."""
        code = """async def fetch_user(user_id):
    return await db.get(user_id)

class UserService:
    async def save(self, user):
        await db.save(user)
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Should find: 1 async function, 1 class, 1 async method
        functions = [s for s in symbols if s.type == SymbolType.FUNCTION]
        assert len(functions) == 1
        assert functions[0].name == "fetch_user"

        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        assert len(classes) == 1

        methods = [s for s in symbols if s.type == SymbolType.METHOD]
        assert len(methods) == 1
        assert methods[0].name == "save"

    def test_parse_class_variables(self, parser, temp_file):
        """Test parsing class-level variables."""
        code = """class Config:
    DEBUG = True
    PORT = 8000
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Should find at least the class
        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "Config"

    def test_parse_syntax_error_file(self, parser, temp_file):
        """Test parsing file with syntax errors - should not crash."""
        code = """class User:
    def broken method():  # syntax error
        pass
"""
        temp_file.write_text(code)

        # Should handle gracefully, possibly returning partial results
        symbols = parser.parse_file(temp_file)
        # At minimum, should not crash
        assert isinstance(symbols, list)

    def test_line_numbers_are_accurate(self, parser, temp_file):
        """Test that line numbers are accurately reported."""
        code = """# Comment line 1
# Comment line 2

def first_function():  # line 4
    pass

class MyClass:  # line 7
    def method_one(self):  # line 8
        pass

    def method_two(self):  # line 11
        pass
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        # Find specific symbols and check line numbers
        first_func = [s for s in symbols if s.name == "first_function"][0]
        assert first_func.line_number == 4

        my_class = [s for s in symbols if s.name == "MyClass" and s.type == SymbolType.CLASS][0]
        assert my_class.line_number == 7

        method_one = [s for s in symbols if s.name == "method_one"][0]
        assert method_one.line_number == 8

        method_two = [s for s in symbols if s.name == "method_two"][0]
        assert method_two.line_number == 11

    def test_parser_preserves_file_path(self, parser, temp_file):
        """Test that parser preserves the file path in symbols."""
        code = """class User:
    pass
"""
        temp_file.write_text(code)
        symbols = parser.parse_file(temp_file)

        assert len(symbols) == 1
        assert symbols[0].file_path == str(temp_file)
