"""#1116 — the agent event bridge collapsed everything into one type.

The classifier was a substring test:

    AGENT_STEP_STARTED if "started" in event_type else AGENT_STEP_COMPLETED

So a skipped file, a failed step and a completed step all arrived as
AGENT_STEP_COMPLETED. One run produced 192 identical console lines, and three
consecutive lines for the same path in the same second were three different
underlying events. Worse than noise: a *failure* was reported as a completion,
and `cf work diagnose` / the event log are the documented way to understand a
failed run.
"""

import pytest

from codeframe.core.events import EventType
from codeframe.core.runtime import _agent_event_to_event_type

pytestmark = pytest.mark.v2


class TestTheOutcomesAreDistinguished:
    """AC: distinct EventTypes, not a two-way substring test."""

    def test_a_skipped_step_is_not_a_completed_step(self):
        assert _agent_event_to_event_type("step_skipped") != _agent_event_to_event_type(
            "step_completed"
        )

    def test_a_failed_step_is_not_a_completed_step(self):
        """The worst case: a failure reported as a success."""
        assert _agent_event_to_event_type("step_failed") != _agent_event_to_event_type(
            "step_completed"
        )

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("step_started", EventType.AGENT_STEP_STARTED),
            ("step_completed", EventType.AGENT_STEP_COMPLETED),
            ("step_skipped", EventType.AGENT_STEP_SKIPPED),
            ("step_failed", EventType.AGENT_STEP_FAILED),
        ],
    )
    def test_the_four_step_outcomes(self, name, expected):
        assert _agent_event_to_event_type(name) == expected

    @pytest.mark.parametrize(
        "name,expected",
        [
            # The whole agent vocabulary, from the adapters and react_agent.
            ("agent_started", EventType.AGENT_STEP_STARTED),
            ("planning_started", EventType.AGENT_STEP_STARTED),
            ("verification_started", EventType.AGENT_STEP_STARTED),
            ("self_correction_started", EventType.AGENT_STEP_STARTED),
            ("agent_completed", EventType.AGENT_STEP_COMPLETED),
            ("planning_completed", EventType.AGENT_STEP_COMPLETED),
            ("iterations_completed", EventType.AGENT_STEP_COMPLETED),
            ("already_completed", EventType.AGENT_STEP_COMPLETED),
            ("self_correction_completed", EventType.AGENT_STEP_COMPLETED),
            ("agent_failed", EventType.AGENT_STEP_FAILED),
            ("execution_failed", EventType.AGENT_STEP_FAILED),
            ("verification_failed", EventType.AGENT_STEP_FAILED),
            ("self_correction_failed", EventType.AGENT_STEP_FAILED),
            ("stall_failed", EventType.AGENT_STEP_FAILED),
            ("blocker_created", EventType.BLOCKER_CREATED),
            ("escalation_blocker_created", EventType.BLOCKER_CREATED),
        ],
    )
    def test_every_known_agent_event_name(self, name, expected):
        assert _agent_event_to_event_type(name) == expected

    def test_no_known_failure_event_reads_as_completed(self):
        """The regression in one assertion."""
        for name in (
            "step_failed",
            "execution_failed",
            "verification_failed",
            "self_correction_failed",
            "stall_failed",
            "agent_failed",
        ):
            assert _agent_event_to_event_type(name) != EventType.AGENT_STEP_COMPLETED


class TestUnknownEventsArePassedThrough:
    """AC: unmapped types get a distinct type, not AGENT_STEP_COMPLETED."""

    @pytest.mark.parametrize("name", ["something_new", "", "weird", "tool_invoked"])
    def test_unmapped_names_get_agent_event(self, name):
        assert _agent_event_to_event_type(name) == EventType.AGENT_EVENT

    def test_an_unknown_event_is_never_silently_a_completion(self):
        assert (
            _agent_event_to_event_type("a_brand_new_thing")
            != EventType.AGENT_STEP_COMPLETED
        )

    def test_case_is_not_significant(self):
        assert _agent_event_to_event_type("STEP_SKIPPED") == EventType.AGENT_STEP_SKIPPED


class TestTheConsoleShowsTheRealType:
    """AC: the console line shows the actual agent event type.

    It was in the payload as `agent_event` all along but the printer's key
    whitelist did not include it, so the terminal could not tell the three
    same-path lines apart.
    """

    def test_agent_event_is_printed(self, capsys):
        from datetime import datetime, timezone

        from codeframe.core.events import Event, print_event

        print_event(
            Event(
                id=1,
                workspace_id="ws",
                event_type=EventType.AGENT_STEP_SKIPPED,
                payload={
                    "agent_event": "step_skipped",
                    "path": "todo_api/database.py",
                    "status": "SKIPPED",
                },
                created_at=datetime.now(timezone.utc),
            )
        )
        out = capsys.readouterr().out
        assert "step_skipped" in out
        assert "todo_api/database.py" in out
