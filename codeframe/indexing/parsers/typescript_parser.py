"""TypeScript/JavaScript code parser using tree-sitter.

This module provides functionality to parse TypeScript and JavaScript source files
and extract code symbols such as classes, functions, interfaces, and types.
"""

from pathlib import Path
from typing import List

from tree_sitter import Language, Parser
import tree_sitter_typescript as tstype
import tree_sitter_javascript as tsjs

from ..models import Symbol, SymbolType


class TypeScriptParser:
    """Parse TypeScript/JavaScript files and extract symbols using tree-sitter."""

    def __init__(self):
        """Initialize the TypeScript/JavaScript parser with tree-sitter."""
        # TypeScript parser
        self.ts_language = Language(tstype.language_typescript())
        self.ts_parser = Parser(self.ts_language)

        # JavaScript parser
        self.js_language = Language(tsjs.language())
        self.js_parser = Parser(self.js_language)

        # TSX parser (TypeScript + JSX)
        self.tsx_language = Language(tstype.language_tsx())
        self.tsx_parser = Parser(self.tsx_language)

    def parse_file(self, file_path: Path) -> List[Symbol]:
        """Parse a TypeScript/JavaScript file and return all symbols.

        Args:
            file_path: Path to the TypeScript/JavaScript file to parse

        Returns:
            List of Symbol objects found in the file
        """
        try:
            source_code = file_path.read_bytes()
        except Exception:
            return []

        if not source_code:
            return []

        # Determine parser based on file extension
        suffix = file_path.suffix.lower()
        if suffix == ".ts":
            parser = self.ts_parser
            language = "typescript"
        elif suffix == ".tsx":
            parser = self.tsx_parser
            language = "typescript"
        elif suffix in [".js", ".jsx"]:
            parser = self.js_parser
            language = "javascript"
        else:
            # Default to TypeScript
            parser = self.ts_parser
            language = "typescript"

        try:
            tree = parser.parse(source_code)
        except Exception:
            return []

        symbols = []

        # Extract all symbols from the parse tree
        symbols.extend(
            self._extract_interfaces(tree.root_node, source_code, str(file_path), language)
        )
        symbols.extend(
            self._extract_type_aliases(tree.root_node, source_code, str(file_path), language)
        )
        symbols.extend(self._extract_classes(tree.root_node, source_code, str(file_path), language))
        symbols.extend(
            self._extract_functions(tree.root_node, source_code, str(file_path), language)
        )

        return symbols

    def _extract_interfaces(
        self, node, source_code: bytes, file_path: str, language: str
    ) -> List[Symbol]:
        """Extract interface definitions."""
        symbols = []

        for child in node.children:
            if child.type == "interface_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    interface_name = source_code[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8"
                    )

                    interface_symbol = Symbol(
                        name=interface_name,
                        type=SymbolType.INTERFACE,
                        file_path=file_path,
                        line_number=child.start_point[0] + 1,
                        language=language,
                    )
                    symbols.append(interface_symbol)

            elif child.type == "export_statement":
                # Handle exported interfaces
                declaration = child.child_by_field_name("declaration")
                if declaration and declaration.type == "interface_declaration":
                    name_node = declaration.child_by_field_name("name")
                    if name_node:
                        interface_name = source_code[
                            name_node.start_byte : name_node.end_byte
                        ].decode("utf-8")

                        interface_symbol = Symbol(
                            name=interface_name,
                            type=SymbolType.INTERFACE,
                            file_path=file_path,
                            line_number=declaration.start_point[0] + 1,
                            language=language,
                        )
                        symbols.append(interface_symbol)

        return symbols

    def _extract_type_aliases(
        self, node, source_code: bytes, file_path: str, language: str
    ) -> List[Symbol]:
        """Extract type alias definitions."""
        symbols = []

        for child in node.children:
            if child.type == "type_alias_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    type_name = source_code[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8"
                    )

                    type_symbol = Symbol(
                        name=type_name,
                        type=SymbolType.TYPE,
                        file_path=file_path,
                        line_number=child.start_point[0] + 1,
                        language=language,
                    )
                    symbols.append(type_symbol)

            elif child.type == "export_statement":
                # Handle exported type aliases
                declaration = child.child_by_field_name("declaration")
                if declaration and declaration.type == "type_alias_declaration":
                    name_node = declaration.child_by_field_name("name")
                    if name_node:
                        type_name = source_code[name_node.start_byte : name_node.end_byte].decode(
                            "utf-8"
                        )

                        type_symbol = Symbol(
                            name=type_name,
                            type=SymbolType.TYPE,
                            file_path=file_path,
                            line_number=declaration.start_point[0] + 1,
                            language=language,
                        )
                        symbols.append(type_symbol)

        return symbols

    def _extract_classes(
        self, node, source_code: bytes, file_path: str, language: str
    ) -> List[Symbol]:
        """Extract class definitions."""
        symbols = []

        for child in node.children:
            class_node = None

            if child.type == "class_declaration":
                class_node = child

            elif child.type == "export_statement":
                declaration = child.child_by_field_name("declaration")
                if declaration:
                    if declaration.type == "class_declaration":
                        class_node = declaration
                    elif declaration.type == "class":
                        # Handle: export default class
                        class_node = declaration

            if class_node:
                name_node = class_node.child_by_field_name("name")
                if name_node:
                    class_name = source_code[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8"
                    )

                    class_symbol = Symbol(
                        name=class_name,
                        type=SymbolType.CLASS,
                        file_path=file_path,
                        line_number=class_node.start_point[0] + 1,
                        language=language,
                    )
                    symbols.append(class_symbol)

                    # Extract methods
                    class_body = class_node.child_by_field_name("body")
                    if class_body:
                        symbols.extend(
                            self._extract_methods(
                                class_body, class_name, source_code, file_path, language
                            )
                        )

        return symbols

    def _extract_methods(
        self, class_body_node, class_name: str, source_code: bytes, file_path: str, language: str
    ) -> List[Symbol]:
        """Extract method definitions from a class body."""
        symbols = []

        for child in class_body_node.children:
            method_node = None

            if child.type == "method_definition":
                method_node = child

            if method_node:
                name_node = method_node.child_by_field_name("name")
                if name_node:
                    method_name = source_code[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8"
                    )

                    method_symbol = Symbol(
                        name=method_name,
                        type=SymbolType.METHOD,
                        file_path=file_path,
                        line_number=method_node.start_point[0] + 1,
                        language=language,
                        parent=class_name,
                    )
                    symbols.append(method_symbol)

        return symbols

    def _extract_functions(
        self, node, source_code: bytes, file_path: str, language: str
    ) -> List[Symbol]:
        """Extract top-level function definitions."""
        symbols = []

        for child in node.children:
            function_node = None

            if child.type == "function_declaration":
                function_node = child

            elif child.type == "export_statement":
                declaration = child.child_by_field_name("declaration")
                if declaration:
                    if declaration.type == "function_declaration":
                        function_node = declaration
                    elif declaration.type == "function":
                        function_node = declaration

            elif child.type == "lexical_declaration":
                # Handle: const func = () => {}
                for declarator in child.children:
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        value_node = declarator.child_by_field_name("value")

                        if name_node and value_node:
                            if value_node.type in ["arrow_function", "function"]:
                                func_name = source_code[
                                    name_node.start_byte : name_node.end_byte
                                ].decode("utf-8")

                                func_symbol = Symbol(
                                    name=func_name,
                                    type=SymbolType.FUNCTION,
                                    file_path=file_path,
                                    line_number=value_node.start_point[0] + 1,
                                    language=language,
                                )
                                symbols.append(func_symbol)

            if function_node:
                name_node = function_node.child_by_field_name("name")
                if name_node:
                    func_name = source_code[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8"
                    )

                    func_symbol = Symbol(
                        name=func_name,
                        type=SymbolType.FUNCTION,
                        file_path=file_path,
                        line_number=function_node.start_point[0] + 1,
                        language=language,
                    )
                    symbols.append(func_symbol)

        return symbols
