"""Phase management for project workflow.

This module provides the PhaseManager class for validating and controlling
phase transitions in the CodeFRAME workflow. It enforces valid transition
rules and provides phase metadata for the UI.
"""

from typing import Dict, List, Any

from fastapi import HTTPException

from codeframe.persistence.database import Database


# Valid phase transitions mapping
# Each phase maps to a list of phases it can transition to
VALID_TRANSITIONS: Dict[str, List[str]] = {
    "discovery": ["planning"],
    "planning": ["active", "discovery"],
    "active": ["review", "planning"],
    "review": ["complete", "active"],
    "complete": [],  # Terminal state (could transition to "shipped" in future)
}


# Phase step configurations
# Each phase has a total number of steps and a description
PHASE_STEPS: Dict[str, Dict[str, Any]] = {
    "discovery": {"total": 4, "description": "Discovery Phase"},
    "planning": {"total": 4, "description": "Planning Phase"},
    "active": {"total": 5, "description": "Development Phase"},
    "review": {"total": 3, "description": "Review Phase"},
    "complete": {"total": 1, "description": "Complete"},
}


class PhaseManager:
    """Manages project phase transitions and provides phase metadata.

    This class provides stateless validation and execution of phase transitions.
    All methods are static/class methods since phase logic doesn't require
    instance state.

    Phase Transition Rules:
        discovery → planning (forward only)
        planning → active, discovery (forward or back)
        active → review, planning (forward or back)
        review → complete, active (forward or back)
        complete → (terminal state)

    Example:
        >>> PhaseManager.can_transition("discovery", "planning")
        True
        >>> PhaseManager.can_transition("discovery", "active")
        False
    """

    @staticmethod
    def can_transition(from_phase: str, to_phase: str) -> bool:
        """Check if a phase transition is valid.

        This is a stateless validation method that doesn't require database
        access. It simply checks the VALID_TRANSITIONS configuration.

        Args:
            from_phase: Current phase name
            to_phase: Target phase name

        Returns:
            True if the transition is allowed, False otherwise

        Example:
            >>> PhaseManager.can_transition("planning", "active")
            True
            >>> PhaseManager.can_transition("discovery", "review")
            False
        """
        if from_phase not in VALID_TRANSITIONS:
            return False

        if from_phase == to_phase:
            return False

        return to_phase in VALID_TRANSITIONS[from_phase]

    @staticmethod
    def transition(project_id: int, to_phase: str, db: Database) -> None:
        """Execute a phase transition for a project.

        Validates the transition and updates the project's phase in the
        database if valid.

        Args:
            project_id: ID of the project to transition
            to_phase: Target phase name
            db: Database instance for persistence

        Raises:
            HTTPException: 404 if project not found
            HTTPException: 400 if transition is invalid

        Example:
            >>> db = Database("path/to/db")
            >>> PhaseManager.transition(1, "planning", db)  # discovery -> planning
        """
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=404,
                detail={"error": "Project not found", "project_id": project_id}
            )

        current_phase = project.get("phase", "discovery")

        if not PhaseManager.can_transition(current_phase, to_phase):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid phase transition from '{current_phase}' to '{to_phase}'"
            )

        # Update project phase
        db.update_project(project_id, {"phase": to_phase})

    @staticmethod
    def get_phase_requirements(phase: str) -> Dict[str, Any]:
        """Get requirements and metadata for a phase.

        Returns step configuration and valid transitions for the given phase.

        Args:
            phase: Phase name to get requirements for

        Returns:
            Dictionary with phase metadata:
                - phase: The phase name
                - steps: Dict with 'total' and 'description'
                - valid_next_phases: List of phases this can transition to

        Raises:
            ValueError: If phase is not recognized

        Example:
            >>> reqs = PhaseManager.get_phase_requirements("discovery")
            >>> reqs["steps"]["total"]
            4
        """
        if phase not in PHASE_STEPS:
            raise ValueError(f"Unknown phase: '{phase}'")

        if phase not in VALID_TRANSITIONS:
            raise ValueError(f"Unknown phase: '{phase}'")

        return {
            "phase": phase,
            "steps": PHASE_STEPS[phase],
            "valid_next_phases": VALID_TRANSITIONS[phase],
        }
