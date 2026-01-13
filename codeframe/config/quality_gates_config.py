"""Configuration for Quality Gates task classification.

This module provides configuration options for controlling how quality gates
are applied based on task classification.

Environment Variables:
    QUALITY_GATES_ENABLE_TASK_CLASSIFICATION: Enable/disable task classification (default: true)
    QUALITY_GATES_STRICT_MODE: Run all gates regardless of task type (default: false)

Usage:
    >>> from codeframe.config.quality_gates_config import get_quality_gates_config
    >>> config = get_quality_gates_config()
    >>> if config.enable_task_classification:
    ...     # Use task classification logic
    ...     pass
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from codeframe.core.models import QualityGateType


@dataclass
class QualityGatesConfig:
    """Configuration for quality gates task classification.

    Attributes:
        enable_task_classification: Whether to use task classification for gate selection.
            When enabled, tasks are classified and only applicable gates are run.
            When disabled, all gates run for all tasks (legacy behavior).
        strict_mode: When True, runs all gates regardless of task classification.
            This is useful for ensuring comprehensive quality checks on all tasks.
        custom_category_rules: Optional override for default category-to-gates mapping.
            Keys are category names (e.g., "design"), values are lists of gate types.
    """

    enable_task_classification: bool = True
    strict_mode: bool = False
    custom_category_rules: Optional[Dict[str, List[str]]] = None

    def should_use_task_classification(self) -> bool:
        """Determine if task classification should be used.

        Returns True if task classification is enabled AND strict mode is disabled.

        Returns:
            bool: True if task classification should be applied
        """
        return self.enable_task_classification and not self.strict_mode

    def get_custom_gates_for_category(self, category: str) -> Optional[List[QualityGateType]]:
        """Get custom gate list for a category if defined.

        Args:
            category: Task category name (e.g., "design", "code_implementation")

        Returns:
            List of QualityGateType if custom rules exist for category, None otherwise
        """
        if not self.custom_category_rules:
            return None

        gate_names = self.custom_category_rules.get(category)
        if gate_names is None:
            return None

        # Convert string names to QualityGateType enum values
        gates = []
        for name in gate_names:
            try:
                gates.append(QualityGateType(name))
            except ValueError:
                # Invalid gate name, skip it
                pass

        return gates if gates else None


def _parse_bool_env(key: str, default: bool) -> bool:
    """Parse boolean environment variable.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Parsed boolean value
    """
    value = os.environ.get(key, "").lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    return default


# Singleton config instance
_config: Optional[QualityGatesConfig] = None


def get_quality_gates_config() -> QualityGatesConfig:
    """Get the quality gates configuration.

    Configuration is loaded from environment variables on first call and cached.

    Environment Variables:
        QUALITY_GATES_ENABLE_TASK_CLASSIFICATION: Enable task classification (default: true)
        QUALITY_GATES_STRICT_MODE: Run all gates regardless of task type (default: false)

    Returns:
        QualityGatesConfig instance
    """
    global _config

    if _config is None:
        _config = QualityGatesConfig(
            enable_task_classification=_parse_bool_env(
                "QUALITY_GATES_ENABLE_TASK_CLASSIFICATION", True
            ),
            strict_mode=_parse_bool_env("QUALITY_GATES_STRICT_MODE", False),
        )

    return _config


def reset_config() -> None:
    """Reset the cached configuration.

    Useful for testing when environment variables change.
    """
    global _config
    _config = None
