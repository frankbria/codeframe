"""Core data models for codebase indexing.

This module defines the fundamental data structures used to represent
code symbols discovered during codebase indexing.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SymbolType(Enum):
    """Types of code symbols that can be indexed."""

    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    INTERFACE = "interface"  # TypeScript
    TYPE = "type"  # TypeScript type alias


@dataclass
class Symbol:
    """Represents a code symbol in the codebase.

    Attributes:
        name: The name of the symbol (e.g., "User", "get_user", "authenticate")
        type: The type of symbol (class, function, method, etc.)
        file_path: Absolute or relative path to the file containing the symbol
        line_number: Line number where the symbol is defined
        language: Programming language (e.g., 'python', 'typescript', 'javascript')
        signature: Optional function/method signature (e.g., "def get_user(user_id: int) -> User")
        parent: Optional parent symbol name (e.g., class name for methods)
    """

    name: str
    type: SymbolType
    file_path: str
    line_number: int
    language: str
    signature: Optional[str] = None
    parent: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert symbol to dictionary for JSON serialization.

        Returns:
            Dictionary with symbol attributes, with SymbolType converted to string value.
        """
        return {
            "name": self.name,
            "type": self.type.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "language": self.language,
            "signature": self.signature,
            "parent": self.parent,
        }
