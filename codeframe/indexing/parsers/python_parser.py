"""Python code parser using tree-sitter.

This module provides functionality to parse Python source files and extract
code symbols such as classes, functions, and methods.
"""

from pathlib import Path
from typing import List

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

from ..models import Symbol, SymbolType


class PythonParser:
    """Parse Python files and extract symbols using tree-sitter."""

    def __init__(self):
        """Initialize the Python parser with tree-sitter."""
        self.language = Language(tspython.language())
        self.parser = Parser(self.language)

    def parse_file(self, file_path: Path) -> List[Symbol]:
        """Parse a Python file and return all symbols.

        Args:
            file_path: Path to the Python file to parse

        Returns:
            List of Symbol objects found in the file
        """
        try:
            source_code = file_path.read_bytes()
        except Exception:
            # Handle file read errors gracefully
            return []

        if not source_code:
            return []

        try:
            tree = self.parser.parse(source_code)
        except Exception:
            # Handle parse errors gracefully
            return []

        symbols = []

        # Extract all symbols from the parse tree
        symbols.extend(self._extract_classes(tree.root_node, source_code, str(file_path)))
        symbols.extend(self._extract_functions(tree.root_node, source_code, str(file_path)))

        return symbols

    def _extract_classes(
        self, node, source_code: bytes, file_path: str, parent: str = None
    ) -> List[Symbol]:
        """Extract class definitions from the parse tree.

        Args:
            node: Tree-sitter node to search
            source_code: Source code bytes
            file_path: Path to the file being parsed
            parent: Parent class name for nested classes

        Returns:
            List of class symbols and their methods
        """
        symbols = []

        # Find all class definitions
        for child in node.children:
            if child.type == "class_definition":
                # Get class name
                class_name_node = child.child_by_field_name("name")
                if class_name_node:
                    class_name = source_code[
                        class_name_node.start_byte : class_name_node.end_byte
                    ].decode("utf-8")

                    # Create class symbol
                    class_symbol = Symbol(
                        name=class_name,
                        type=SymbolType.CLASS,
                        file_path=file_path,
                        line_number=child.start_point[0] + 1,  # tree-sitter is 0-indexed
                        language="python",
                        parent=parent,
                    )
                    symbols.append(class_symbol)

                    # Extract methods from this class
                    class_body = child.child_by_field_name("body")
                    if class_body:
                        symbols.extend(
                            self._extract_methods(class_body, class_name, source_code, file_path)
                        )

                        # Recursively extract nested classes
                        symbols.extend(
                            self._extract_classes(class_body, source_code, file_path, class_name)
                        )

            # Recursively search in other nodes (but not in function bodies)
            elif child.type not in ["function_definition", "class_definition"]:
                symbols.extend(self._extract_classes(child, source_code, file_path, parent))

        return symbols

    def _extract_functions(self, node, source_code: bytes, file_path: str) -> List[Symbol]:
        """Extract top-level function definitions.

        Args:
            node: Tree-sitter node to search
            source_code: Source code bytes
            file_path: Path to the file being parsed

        Returns:
            List of function symbols
        """
        symbols = []

        # Find all top-level function definitions (not methods inside classes)
        for child in node.children:
            if child.type == "function_definition":
                func_name_node = child.child_by_field_name("name")
                if func_name_node:
                    func_name = source_code[
                        func_name_node.start_byte : func_name_node.end_byte
                    ].decode("utf-8")

                    func_symbol = Symbol(
                        name=func_name,
                        type=SymbolType.FUNCTION,
                        file_path=file_path,
                        line_number=child.start_point[0] + 1,
                        language="python",
                    )
                    symbols.append(func_symbol)

            elif child.type == "decorated_definition":
                # Handle decorated functions at module level
                definition_node = None
                for subchild in child.children:
                    if subchild.type == "function_definition":
                        definition_node = subchild
                        break

                if definition_node:
                    func_name_node = definition_node.child_by_field_name("name")
                    if func_name_node:
                        func_name = source_code[
                            func_name_node.start_byte : func_name_node.end_byte
                        ].decode("utf-8")

                        func_symbol = Symbol(
                            name=func_name,
                            type=SymbolType.FUNCTION,
                            file_path=file_path,
                            line_number=definition_node.start_point[0] + 1,
                            language="python",
                        )
                        symbols.append(func_symbol)

            # Recursively search module-level nodes, but don't go into class or function bodies
            elif child.type not in ["class_definition"]:
                if child.type == "module":
                    symbols.extend(self._extract_functions(child, source_code, file_path))

        return symbols

    def _extract_methods(
        self, class_body_node, class_name: str, source_code: bytes, file_path: str
    ) -> List[Symbol]:
        """Extract method definitions from a class body.

        Args:
            class_body_node: Tree-sitter node representing class body
            class_name: Name of the parent class
            source_code: Source code bytes
            file_path: Path to the file being parsed

        Returns:
            List of method symbols
        """
        symbols = []

        for child in class_body_node.children:
            # Handle both decorated and undecorated functions
            if child.type == "function_definition":
                method_name_node = child.child_by_field_name("name")
                if method_name_node:
                    method_name = source_code[
                        method_name_node.start_byte : method_name_node.end_byte
                    ].decode("utf-8")

                    method_symbol = Symbol(
                        name=method_name,
                        type=SymbolType.METHOD,
                        file_path=file_path,
                        line_number=child.start_point[0] + 1,
                        language="python",
                        parent=class_name,
                    )
                    symbols.append(method_symbol)

            elif child.type == "decorated_definition":
                # Handle decorated methods
                definition_node = None
                for subchild in child.children:
                    if subchild.type == "function_definition":
                        definition_node = subchild
                        break

                if definition_node:
                    method_name_node = definition_node.child_by_field_name("name")
                    if method_name_node:
                        method_name = source_code[
                            method_name_node.start_byte : method_name_node.end_byte
                        ].decode("utf-8")

                        method_symbol = Symbol(
                            name=method_name,
                            type=SymbolType.METHOD,
                            file_path=file_path,
                            line_number=definition_node.start_point[0] + 1,
                            language="python",
                            parent=class_name,
                        )
                        symbols.append(method_symbol)

        return symbols
