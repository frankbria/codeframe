"""Tests for CodebaseIndex.

Following TDD methodology - these tests are written BEFORE implementation.
"""

import tempfile
from pathlib import Path

import pytest

from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.indexing.models import SymbolType


class TestCodebaseIndex:
    """Test CodebaseIndex functionality."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory with sample files."""
        temp_dir = tempfile.mkdtemp()
        project_root = Path(temp_dir)

        # Create Python file
        (project_root / "models.py").write_text('''
class User:
    def save(self):
        pass

def get_user(user_id):
    return User()
''')

        # Create TypeScript file
        (project_root / "api.ts").write_text('''
interface UserData {
    id: string;
    name: string;
}

class ApiClient {
    async fetchUser(id: string): Promise<UserData> {
        return null;
    }
}

function createClient(): ApiClient {
    return new ApiClient();
}
''')

        yield project_root

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    def test_build_index(self, temp_project):
        """Test building index from project."""
        index = CodebaseIndex(str(temp_project))
        index.build()

        assert len(index.symbols) > 0

    def test_find_symbols_by_name(self, temp_project):
        """Test finding symbols by name."""
        index = CodebaseIndex(str(temp_project))
        index.build()

        # Find User class
        user_symbols = index.find_symbols("User")
        assert len(user_symbols) > 0
        assert any(s.name == "User" and s.type == SymbolType.CLASS for s in user_symbols)

    def test_find_symbols_by_type(self, temp_project):
        """Test filtering symbols by type."""
        index = CodebaseIndex(str(temp_project))
        index.build()

        # Find all interfaces
        interfaces = index.find_symbols("UserData", symbol_type=SymbolType.INTERFACE)
        assert len(interfaces) > 0
        assert all(s.type == SymbolType.INTERFACE for s in interfaces)

    def test_find_symbols_by_language(self, temp_project):
        """Test filtering symbols by language."""
        index = CodebaseIndex(str(temp_project))
        index.build()

        # Find Python symbols
        python_symbols = index.find_symbols("User", language="python")
        assert len(python_symbols) > 0
        assert all(s.language == "python" for s in python_symbols)

    def test_get_file_symbols(self, temp_project):
        """Test getting all symbols from a specific file."""
        index = CodebaseIndex(str(temp_project))
        index.build()

        models_file = str(temp_project / "models.py")
        symbols = index.get_file_symbols(models_file)

        # Should have User class, save method, and get_user function
        assert len(symbols) >= 2
        symbol_names = {s.name for s in symbols}
        assert "User" in symbol_names

    def test_search_pattern(self, temp_project):
        """Test searching with regex pattern."""
        index = CodebaseIndex(str(temp_project))
        index.build()

        # Search for anything containing "User"
        results = index.search_pattern(".*User.*")
        assert len(results) > 0

    def test_to_dict(self, temp_project):
        """Test exporting index to dictionary."""
        index = CodebaseIndex(str(temp_project))
        index.build()

        index_dict = index.to_dict()

        assert "symbols" in index_dict
        assert "file_count" in index_dict
        assert "symbol_count" in index_dict
        assert isinstance(index_dict["symbols"], list)

    def test_build_with_file_patterns(self, temp_project):
        """Test building index with specific file patterns."""
        index = CodebaseIndex(str(temp_project))

        # Only index Python files
        index.build(file_patterns=["**/*.py"])

        # Should only have Python symbols
        assert all(s.language == "python" for s in index.symbols)

    def test_empty_project(self):
        """Test handling empty project directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            index = CodebaseIndex(temp_dir)
            index.build()
            assert index.symbols == []
        finally:
            import shutil
            shutil.rmtree(temp_dir)
