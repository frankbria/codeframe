"""Tests for TypeScript/JavaScript code parser.

Following TDD methodology - these tests are written BEFORE implementation.
"""

import tempfile
from pathlib import Path

import pytest

from codeframe.indexing.models import Symbol, SymbolType
from codeframe.indexing.parsers.typescript_parser import TypeScriptParser


class TestTypeScriptParser:
    """Test TypeScriptParser functionality."""

    @pytest.fixture
    def parser(self):
        """Create a TypeScriptParser instance."""
        return TypeScriptParser()

    @pytest.fixture
    def temp_ts_file(self):
        """Create a temporary TypeScript file for testing."""
        temp = tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False)
        yield Path(temp.name)
        Path(temp.name).unlink(missing_ok=True)

    @pytest.fixture
    def temp_js_file(self):
        """Create a temporary JavaScript file for testing."""
        temp = tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False)
        yield Path(temp.name)
        Path(temp.name).unlink(missing_ok=True)

    def test_parse_empty_file(self, parser, temp_ts_file):
        """Test parsing an empty TypeScript file."""
        temp_ts_file.write_text("")
        symbols = parser.parse_file(temp_ts_file)
        assert symbols == []

    def test_parse_simple_class(self, parser, temp_ts_file):
        """Test parsing a simple TypeScript class."""
        code = """class User {
}
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        assert len(symbols) == 1
        assert symbols[0].name == "User"
        assert symbols[0].type == SymbolType.CLASS
        assert symbols[0].line_number == 1
        assert symbols[0].language == "typescript"

    def test_parse_class_with_methods(self, parser, temp_ts_file):
        """Test parsing a TypeScript class with methods."""
        code = """class UserService {
  constructor(private db: Database) {}

  async getUser(id: string): Promise<User> {
    return await this.db.get(id);
  }

  saveUser(user: User): void {
    this.db.save(user);
  }
}
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        # Should find 1 class + 3 methods (constructor, getUser, saveUser)
        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "UserService"

        methods = [s for s in symbols if s.type == SymbolType.METHOD]
        assert len(methods) == 3

        method_names = {m.name for m in methods}
        assert "constructor" in method_names
        assert "getUser" in method_names
        assert "saveUser" in method_names

        # Check that methods have parent set
        for method in methods:
            assert method.parent == "UserService"
            assert method.language == "typescript"

    def test_parse_interface(self, parser, temp_ts_file):
        """Test parsing TypeScript interface."""
        code = """interface User {
  id: string;
  name: string;
  email: string;
}
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        assert len(symbols) == 1
        assert symbols[0].name == "User"
        assert symbols[0].type == SymbolType.INTERFACE
        assert symbols[0].language == "typescript"

    def test_parse_type_alias(self, parser, temp_ts_file):
        """Test parsing TypeScript type alias."""
        code = """type UserId = string;

type UserRole = 'admin' | 'user' | 'guest';
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        assert len(symbols) == 2

        type_names = {s.name for s in symbols if s.type == SymbolType.TYPE}
        assert type_names == {"UserId", "UserRole"}

    def test_parse_function(self, parser, temp_ts_file):
        """Test parsing TypeScript functions."""
        code = """function getUserById(id: string): User {
  return users.find(u => u.id === id);
}

async function fetchUser(id: string): Promise<User> {
  return await api.get(`/users/${id}`);
}
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        assert len(symbols) == 2

        func_names = {s.name for s in symbols if s.type == SymbolType.FUNCTION}
        assert func_names == {"getUserById", "fetchUser"}

        for symbol in symbols:
            assert symbol.type == SymbolType.FUNCTION
            assert symbol.parent is None

    def test_parse_arrow_function(self, parser, temp_ts_file):
        """Test parsing arrow functions."""
        code = """const getUser = (id: string): User => {
  return users.find(u => u.id === id);
};

const saveUser = async (user: User): Promise<void> => {
  await db.save(user);
};
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        # Arrow functions assigned to const should be detected
        func_names = {s.name for s in symbols if s.type == SymbolType.FUNCTION}
        assert "getUser" in func_names or "saveUser" in func_names

    def test_parse_react_component(self, parser, temp_ts_file):
        """Test parsing React component function."""
        code = """export function UserProfile({ user }: { user: User }) {
  return <div>{user.name}</div>;
}

export const Avatar = ({ url }: { url: string }) => {
  return <img src={url} />;
};
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        # Should detect the component functions
        func_names = {s.name for s in symbols if s.type == SymbolType.FUNCTION}
        assert "UserProfile" in func_names

    def test_parse_exported_class(self, parser, temp_ts_file):
        """Test parsing exported classes."""
        code = """export class UserService {
  getUser() {
    return null;
  }
}

export default class AdminService {
  getAdmin() {
    return null;
  }
}
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        class_names = {c.name for c in classes}
        assert "UserService" in class_names
        assert "AdminService" in class_names

    def test_parse_javascript_file(self, parser, temp_js_file):
        """Test parsing JavaScript (.js) file."""
        code = """class User {
  constructor(name) {
    this.name = name;
  }

  greet() {
    return `Hello, ${this.name}`;
  }
}

function createUser(name) {
  return new User(name);
}
"""
        temp_js_file.write_text(code)
        symbols = parser.parse_file(temp_js_file)

        # Should detect class and function
        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "User"
        assert classes[0].language == "javascript"

        functions = [s for s in symbols if s.type == SymbolType.FUNCTION]
        assert len(functions) >= 1
        func_names = {f.name for f in functions}
        assert "createUser" in func_names

    def test_parse_mixed_interfaces_and_classes(self, parser, temp_ts_file):
        """Test parsing file with both interfaces and classes."""
        code = """interface IUser {
  id: string;
  name: string;
}

class User implements IUser {
  constructor(public id: string, public name: string) {}
}

type UserData = Partial<IUser>;
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        interfaces = [s for s in symbols if s.type == SymbolType.INTERFACE]
        assert len(interfaces) == 1
        assert interfaces[0].name == "IUser"

        classes = [s for s in symbols if s.type == SymbolType.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "User"

        types = [s for s in symbols if s.type == SymbolType.TYPE]
        assert len(types) == 1
        assert types[0].name == "UserData"

    def test_line_numbers_are_accurate(self, parser, temp_ts_file):
        """Test that line numbers are accurately reported."""
        code = """// Comment line 1
// Comment line 2

function firstFunction() {  // line 4
  return true;
}

class MyClass {  // line 8
  methodOne() {  // line 9
    return 1;
  }

  methodTwo() {  // line 13
    return 2;
  }
}

interface MyInterface {  // line 18
  prop: string;
}
"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        first_func = [s for s in symbols if s.name == "firstFunction"][0]
        assert first_func.line_number == 4

        my_class = [s for s in symbols if s.name == "MyClass" and s.type == SymbolType.CLASS][0]
        assert my_class.line_number == 8

        my_interface = [s for s in symbols if s.name == "MyInterface"][0]
        assert my_interface.line_number == 18

    def test_parser_preserves_file_path(self, parser, temp_ts_file):
        """Test that parser preserves the file path in symbols."""
        code = """class User {}"""
        temp_ts_file.write_text(code)
        symbols = parser.parse_file(temp_ts_file)

        assert len(symbols) == 1
        assert symbols[0].file_path == str(temp_ts_file)
