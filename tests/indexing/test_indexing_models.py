"""Tests for codebase indexing models.

Following TDD methodology - these tests are written BEFORE implementation.
"""

from codeframe.indexing.models import Symbol, SymbolType


class TestSymbolType:
    """Test SymbolType enum."""

    def test_symbol_type_values(self):
        """Test that all expected symbol types exist."""
        assert SymbolType.CLASS.value == "class"
        assert SymbolType.FUNCTION.value == "function"
        assert SymbolType.METHOD.value == "method"
        assert SymbolType.VARIABLE.value == "variable"
        assert SymbolType.INTERFACE.value == "interface"
        assert SymbolType.TYPE.value == "type"

    def test_symbol_type_enum_members(self):
        """Test that all expected enum members exist."""
        expected_members = {"CLASS", "FUNCTION", "METHOD", "VARIABLE", "INTERFACE", "TYPE"}
        actual_members = {member.name for member in SymbolType}
        assert actual_members == expected_members


class TestSymbol:
    """Test Symbol dataclass."""

    def test_symbol_creation_minimal(self):
        """Test creating a symbol with minimal required fields."""
        symbol = Symbol(
            name="User",
            type=SymbolType.CLASS,
            file_path="/home/project/models.py",
            line_number=10,
            language="python",
        )

        assert symbol.name == "User"
        assert symbol.type == SymbolType.CLASS
        assert symbol.file_path == "/home/project/models.py"
        assert symbol.line_number == 10
        assert symbol.language == "python"
        assert symbol.signature is None
        assert symbol.parent is None

    def test_symbol_creation_with_signature(self):
        """Test creating a function symbol with signature."""
        symbol = Symbol(
            name="get_user",
            type=SymbolType.FUNCTION,
            file_path="/home/project/api.py",
            line_number=25,
            language="python",
            signature="def get_user(user_id: int) -> User",
        )

        assert symbol.name == "get_user"
        assert symbol.signature == "def get_user(user_id: int) -> User"

    def test_symbol_creation_with_parent(self):
        """Test creating a method symbol with parent class."""
        symbol = Symbol(
            name="save",
            type=SymbolType.METHOD,
            file_path="/home/project/models.py",
            line_number=45,
            language="python",
            signature="def save(self) -> None",
            parent="User",
        )

        assert symbol.name == "save"
        assert symbol.parent == "User"
        assert symbol.type == SymbolType.METHOD

    def test_symbol_to_dict_minimal(self):
        """Test converting minimal symbol to dictionary."""
        symbol = Symbol(
            name="count",
            type=SymbolType.VARIABLE,
            file_path="/home/project/config.py",
            line_number=5,
            language="python",
        )

        result = symbol.to_dict()

        assert isinstance(result, dict)
        assert result["name"] == "count"
        assert result["type"] == "variable"
        assert result["file_path"] == "/home/project/config.py"
        assert result["line_number"] == 5
        assert result["language"] == "python"
        assert result["signature"] is None
        assert result["parent"] is None

    def test_symbol_to_dict_complete(self):
        """Test converting complete symbol to dictionary."""
        symbol = Symbol(
            name="authenticate",
            type=SymbolType.METHOD,
            file_path="/home/project/auth.py",
            line_number=100,
            language="typescript",
            signature="async authenticate(token: string): Promise<User>",
            parent="AuthService",
        )

        result = symbol.to_dict()

        assert result["name"] == "authenticate"
        assert result["type"] == "method"
        assert result["file_path"] == "/home/project/auth.py"
        assert result["line_number"] == 100
        assert result["language"] == "typescript"
        assert result["signature"] == "async authenticate(token: string): Promise<User>"
        assert result["parent"] == "AuthService"

    def test_symbol_equality(self):
        """Test that symbols with same attributes are equal."""
        symbol1 = Symbol(
            name="User",
            type=SymbolType.CLASS,
            file_path="/home/project/models.py",
            line_number=10,
            language="python",
        )

        symbol2 = Symbol(
            name="User",
            type=SymbolType.CLASS,
            file_path="/home/project/models.py",
            line_number=10,
            language="python",
        )

        assert symbol1 == symbol2

    def test_symbol_inequality_different_name(self):
        """Test that symbols with different names are not equal."""
        symbol1 = Symbol(
            name="User",
            type=SymbolType.CLASS,
            file_path="/home/project/models.py",
            line_number=10,
            language="python",
        )

        symbol2 = Symbol(
            name="Admin",
            type=SymbolType.CLASS,
            file_path="/home/project/models.py",
            line_number=10,
            language="python",
        )

        assert symbol1 != symbol2

    def test_symbol_inequality_different_line(self):
        """Test that symbols at different lines are not equal."""
        symbol1 = Symbol(
            name="User",
            type=SymbolType.CLASS,
            file_path="/home/project/models.py",
            line_number=10,
            language="python",
        )

        symbol2 = Symbol(
            name="User",
            type=SymbolType.CLASS,
            file_path="/home/project/models.py",
            line_number=20,
            language="python",
        )

        assert symbol1 != symbol2
