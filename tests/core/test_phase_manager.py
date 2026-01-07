"""Unit tests for PhaseManager class.

Tests phase transition validation, execution, and phase requirements.
Following TDD principles - these tests are written before the implementation.
"""

import pytest
from pathlib import Path

from codeframe.persistence.database import Database
from codeframe.core.phase_manager import (
    PhaseManager,
    VALID_TRANSITIONS,
    PHASE_STEPS,
)
from codeframe.core.models import ProjectPhase
from tests.conftest import setup_test_user


class TestPhaseManagerCanTransition:
    """Tests for can_transition() validation method."""

    def test_discovery_to_planning_valid(self):
        """Discovery can transition to planning."""
        assert PhaseManager.can_transition("discovery", "planning") is True

    def test_planning_to_active_valid(self):
        """Planning can transition to active."""
        assert PhaseManager.can_transition("planning", "active") is True

    def test_planning_to_discovery_valid(self):
        """Planning can go back to discovery."""
        assert PhaseManager.can_transition("planning", "discovery") is True

    def test_active_to_review_valid(self):
        """Active can transition to review."""
        assert PhaseManager.can_transition("active", "review") is True

    def test_active_to_planning_valid(self):
        """Active can go back to planning."""
        assert PhaseManager.can_transition("active", "planning") is True

    def test_review_to_complete_valid(self):
        """Review can transition to complete."""
        assert PhaseManager.can_transition("review", "complete") is True

    def test_review_to_active_valid(self):
        """Review can go back to active."""
        assert PhaseManager.can_transition("review", "active") is True

    def test_discovery_to_active_invalid(self):
        """Discovery cannot skip directly to active."""
        assert PhaseManager.can_transition("discovery", "active") is False

    def test_discovery_to_review_invalid(self):
        """Discovery cannot skip to review."""
        assert PhaseManager.can_transition("discovery", "review") is False

    def test_complete_to_discovery_invalid(self):
        """Complete cannot go back to discovery."""
        assert PhaseManager.can_transition("complete", "discovery") is False

    def test_unknown_from_phase(self):
        """Unknown from_phase returns False."""
        assert PhaseManager.can_transition("unknown", "planning") is False

    def test_unknown_to_phase(self):
        """Unknown to_phase returns False."""
        assert PhaseManager.can_transition("discovery", "unknown") is False

    def test_same_phase_invalid(self):
        """Cannot transition to same phase."""
        assert PhaseManager.can_transition("discovery", "discovery") is False


class TestPhaseManagerTransition:
    """Tests for transition() execution method."""

    def test_transition_success(self, temp_db_path: Path):
        """Successful phase transition updates database."""
        db = Database(temp_db_path)
        db.initialize()
        setup_test_user(db, user_id=1)

        # Create project in discovery phase
        project_id = db.create_project(
            user_id=1,
            name="Test Project",
            description="Test",
            phase="discovery",
        )

        # Transition to planning
        PhaseManager.transition(project_id, "planning", db)

        # Verify phase updated
        project = db.get_project(project_id)
        assert project["phase"] == "planning"

    def test_transition_invalid_raises_400(self, temp_db_path: Path):
        """Invalid transition raises HTTPException with 400 status."""
        from fastapi import HTTPException

        db = Database(temp_db_path)
        db.initialize()
        setup_test_user(db, user_id=1)

        project_id = db.create_project(
            user_id=1,
            name="Test Project",
            description="Test",
            phase="discovery",
        )

        # Try invalid transition (discovery -> review)
        with pytest.raises(HTTPException) as exc_info:
            PhaseManager.transition(project_id, "review", db)

        assert exc_info.value.status_code == 400
        assert "Invalid phase transition" in str(exc_info.value.detail)

    def test_transition_nonexistent_project_raises_404(self, temp_db_path: Path):
        """Transition on non-existent project raises 404."""
        from fastapi import HTTPException

        db = Database(temp_db_path)
        db.initialize()

        with pytest.raises(HTTPException) as exc_info:
            PhaseManager.transition(99999, "planning", db)

        assert exc_info.value.status_code == 404

    def test_transition_chain(self, temp_db_path: Path):
        """Test full phase transition chain from discovery to complete."""
        db = Database(temp_db_path)
        db.initialize()
        setup_test_user(db, user_id=1)

        project_id = db.create_project(
            user_id=1,
            name="Test Project",
            description="Test",
            phase="discovery",
        )

        # Walk through the full lifecycle
        transitions = ["planning", "active", "review", "complete"]

        for target_phase in transitions:
            PhaseManager.transition(project_id, target_phase, db)
            project = db.get_project(project_id)
            assert project["phase"] == target_phase


class TestPhaseManagerGetPhaseRequirements:
    """Tests for get_phase_requirements() method."""

    def test_discovery_requirements(self):
        """Get discovery phase requirements."""
        reqs = PhaseManager.get_phase_requirements("discovery")

        assert reqs["phase"] == "discovery"
        assert reqs["steps"]["total"] == 4
        assert reqs["steps"]["description"] == "Discovery Phase"
        assert "planning" in reqs["valid_next_phases"]

    def test_planning_requirements(self):
        """Get planning phase requirements."""
        reqs = PhaseManager.get_phase_requirements("planning")

        assert reqs["phase"] == "planning"
        assert reqs["steps"]["total"] == 4
        assert "active" in reqs["valid_next_phases"]
        assert "discovery" in reqs["valid_next_phases"]

    def test_active_requirements(self):
        """Get active phase requirements."""
        reqs = PhaseManager.get_phase_requirements("active")

        assert reqs["phase"] == "active"
        assert reqs["steps"]["total"] == 5
        assert reqs["steps"]["description"] == "Development Phase"

    def test_review_requirements(self):
        """Get review phase requirements."""
        reqs = PhaseManager.get_phase_requirements("review")

        assert reqs["phase"] == "review"
        assert reqs["steps"]["total"] == 3
        assert "complete" in reqs["valid_next_phases"]
        assert "active" in reqs["valid_next_phases"]

    def test_complete_requirements(self):
        """Get complete phase requirements."""
        reqs = PhaseManager.get_phase_requirements("complete")

        assert reqs["phase"] == "complete"
        assert reqs["steps"]["total"] == 1
        assert reqs["steps"]["description"] == "Complete"

    def test_invalid_phase_raises_error(self):
        """Invalid phase raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            PhaseManager.get_phase_requirements("invalid_phase")

        assert "Unknown phase" in str(exc_info.value)


class TestPhaseConfigurationCompleteness:
    """Tests to ensure phase configuration is complete."""

    def test_all_project_phases_have_transitions(self):
        """All ProjectPhase enum values should be in VALID_TRANSITIONS."""
        for phase in ProjectPhase:
            assert phase.value in VALID_TRANSITIONS, f"Missing transitions for {phase.value}"

    def test_all_project_phases_have_steps(self):
        """All ProjectPhase enum values should be in PHASE_STEPS."""
        for phase in ProjectPhase:
            assert phase.value in PHASE_STEPS, f"Missing steps for {phase.value}"

    def test_phase_steps_have_required_keys(self):
        """Each phase step config has total and description."""
        for phase, steps in PHASE_STEPS.items():
            assert "total" in steps, f"Missing 'total' for {phase}"
            assert "description" in steps, f"Missing 'description' for {phase}"
            assert isinstance(steps["total"], int), f"'total' should be int for {phase}"
            assert isinstance(steps["description"], str), f"'description' should be str for {phase}"

    def test_valid_transitions_reference_valid_phases(self):
        """All phases in VALID_TRANSITIONS reference valid phases."""
        all_phases = set(VALID_TRANSITIONS.keys())

        for from_phase, to_phases in VALID_TRANSITIONS.items():
            for to_phase in to_phases:
                # All target phases should also be defined (except potentially 'shipped')
                if to_phase not in all_phases:
                    # Allow 'shipped' as a terminal state not yet in enum
                    assert to_phase in ["shipped"], (
                        f"Unknown target phase '{to_phase}' from '{from_phase}'"
                    )
