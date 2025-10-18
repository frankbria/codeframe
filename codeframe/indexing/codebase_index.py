"""Codebase indexing for structural awareness.

This module provides the main CodebaseIndex class that coordinates
parsing of multiple files and provides query capabilities.
"""

import re
from pathlib import Path
from typing import List, Optional

from .models import Symbol, SymbolType
from .parsers.python_parser import PythonParser
from .parsers.typescript_parser import TypeScriptParser


class CodebaseIndex:
    """Index codebase structure for agent queries."""

    def __init__(self, project_root: str):
        """Initialize the codebase index.

        Args:
            project_root: Path to the project root directory
        """
        self.project_root = Path(project_root)
        self.symbols: List[Symbol] = []
        self.python_parser = PythonParser()
        self.ts_parser = TypeScriptParser()

    def build(self, file_patterns: Optional[List[str]] = None):
        """Build index by parsing all source files.

        Args:
            file_patterns: Glob patterns for files to index.
                          Default: ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]
        """
        if file_patterns is None:
            file_patterns = ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx"]

        self.symbols = []

        for pattern in file_patterns:
            for file_path in self.project_root.glob(pattern):
                if file_path.is_file():
                    self._parse_file(file_path)

    def _parse_file(self, file_path: Path):
        """Parse a single file and add its symbols to the index.

        Args:
            file_path: Path to the file to parse
        """
        suffix = file_path.suffix.lower()

        if suffix == ".py":
            symbols = self.python_parser.parse_file(file_path)
            self.symbols.extend(symbols)
        elif suffix in [".ts", ".tsx", ".js", ".jsx"]:
            symbols = self.ts_parser.parse_file(file_path)
            self.symbols.extend(symbols)

    def find_symbols(
        self,
        name: str,
        symbol_type: Optional[SymbolType] = None,
        language: Optional[str] = None,
    ) -> List[Symbol]:
        """Find symbols by name, optionally filter by type and language.

        Args:
            name: Symbol name to search for
            symbol_type: Optional filter by symbol type
            language: Optional filter by programming language

        Returns:
            List of matching symbols
        """
        results = [s for s in self.symbols if s.name == name]

        if symbol_type is not None:
            results = [s for s in results if s.type == symbol_type]

        if language is not None:
            results = [s for s in results if s.language == language]

        return results

    def get_file_symbols(self, file_path: str) -> List[Symbol]:
        """Get all symbols defined in a specific file.

        Args:
            file_path: Path to the file

        Returns:
            List of symbols in the file
        """
        # Normalize paths for comparison
        file_path_normalized = str(Path(file_path).resolve())
        results = []

        for symbol in self.symbols:
            symbol_path_normalized = str(Path(symbol.file_path).resolve())
            if symbol_path_normalized == file_path_normalized:
                results.append(symbol)

        return results

    def search_pattern(self, pattern: str) -> List[Symbol]:
        """Search for symbols matching a regex pattern.

        Args:
            pattern: Regular expression pattern to match symbol names

        Returns:
            List of symbols with names matching the pattern
        """
        try:
            regex = re.compile(pattern)
            return [s for s in self.symbols if regex.search(s.name)]
        except re.error:
            return []

    def to_dict(self) -> dict:
        """Export index as dictionary for serialization.

        Returns:
            Dictionary with index data and statistics
        """
        file_paths = set(s.file_path for s in self.symbols)

        return {
            "symbols": [s.to_dict() for s in self.symbols],
            "symbol_count": len(self.symbols),
            "file_count": len(file_paths),
        }
