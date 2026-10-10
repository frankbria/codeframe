"""PRD discovery is bounded (#1443).

A session used to end only when the model said so (``DISCOVERY_COMPLETE`` or
``ready_for_prd``). A model that never said so asked 30+ near-duplicate
questions with coverage stuck at 75-81%. These tests drive a fake provider that
never declares completion and pin each stop rule that now ends the session.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.workspace import Workspace, create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


def _coverage_json(average: int, scores: dict | None = None) -> str:
    scores = scores or {
        "problem": 90,
        "users": 85,
        "features": 80,
        "constraints": 40,
        "tech_stack": 30,
    }
    return json.dumps(
        {
            "scores": scores,
            "average": average,
            "weakest_category": "tech_stack",
            "ready_for_prd": False,
            "reasoning": "still gaps",
        }
    )


class FakeProvider:
    """Routes each call by its prompt; never declares discovery complete.

    ``coverage`` is a list of replies for successive coverage assessments (the
    last one repeats); ``questions`` likewise for question generation.
    """

    def __init__(self, coverage: list[str], questions: list[str] | None = None):
        self.coverage = list(coverage)
        self.questions = list(questions) if questions else None
        self.question_prompts: list[str] = []
        self.prd_prompts: list[str] = []
        self._n = 0

    @staticmethod
    def _next(queue: list[str]) -> str:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def complete(self, messages, **_kwargs):
        prompt = messages[0]["content"]
        response = MagicMock()
        response.input_tokens = 1
        response.output_tokens = 1
        if prompt.startswith("Assess the current coverage"):
            response.content = self._next(self.coverage)
        elif prompt.startswith("Evaluate whether this answer"):
            response.content = '{"adequate": true, "reason": "ok"}'
        elif prompt.startswith("Based on the conversation so far"):
            self.question_prompts.append(prompt)
            if self.questions is not None:
                response.content = self._next(self.questions)
            else:
                self._n += 1
                # Distinct vocabulary per question so the duplicate guard stays quiet.
                topics = [
                    "deployment region", "billing currency", "audit retention",
                    "offline mode", "localisation scope", "accessibility level",
                    "import formats", "export cadence", "notification channels",
                    "admin roles", "backup policy", "latency budget", "browser matrix",
                    "mobile platforms", "pricing tiers",
                ]
                response.content = f"What about the {topics[self._n % len(topics)]}?"
        elif "Product Requirements Document" in prompt:
            self.prd_prompts.append(prompt)
            response.content = "# Todo API\n\n## Overview\nA todo API."
        else:
            response.content = "What are you building?"
        return response


def _session(workspace: Workspace, provider: FakeProvider, **kwargs):
    from codeframe.core.prd_discovery import PrdDiscoverySession

    with patch("codeframe.core.prd_discovery.AnthropicProvider", return_value=provider):
        session = PrdDiscoverySession(workspace, api_key="test-key", **kwargs)
    session.start_discovery()
    return session


def _answer_until_complete(session, limit: int = 50) -> int:
    asked = 0
    while not session.is_complete() and asked < limit:
        result = session.submit_answer(f"answer number {asked}")
        assert result["accepted"]
        asked += 1
    return asked


class TestQuestionCap:
    def test_rising_coverage_stops_at_the_cap(self, workspace):
        # Coverage keeps rising (so no plateau), the model never says ready.
        provider = FakeProvider([_coverage_json(a) for a in range(20, 100, 6)])
        session = _session(workspace, provider, max_questions=4)

        assert _answer_until_complete(session) == 4
        assert session.is_complete()
        assert session.get_current_question() is None

    def test_default_cap_is_ten(self, workspace):
        provider = FakeProvider([_coverage_json(a) for a in range(5, 100, 6)])
        session = _session(workspace, provider)

        assert _answer_until_complete(session) == 10

    def test_cap_comes_from_workspace_config(self, workspace):
        config = Path(workspace.repo_path) / ".codeframe" / "config.yaml"
        config.write_text("discovery_max_questions: 3\n")
        provider = FakeProvider([_coverage_json(a) for a in range(20, 100, 6)])
        session = _session(workspace, provider)

        assert _answer_until_complete(session) == 3

    @pytest.mark.parametrize("bad", ["0", "-2", "true", "'seven'"])
    def test_invalid_config_value_falls_back_to_default(self, workspace, bad):
        config = Path(workspace.repo_path) / ".codeframe" / "config.yaml"
        config.write_text(f"discovery_max_questions: {bad}\n")
        provider = FakeProvider([_coverage_json(a) for a in range(5, 100, 6)])
        session = _session(workspace, provider)

        assert session.get_progress()["max_questions"] == 10

    def test_explicit_cap_beats_config(self, workspace):
        config = Path(workspace.repo_path) / ".codeframe" / "config.yaml"
        config.write_text("discovery_max_questions: 3\n")
        provider = FakeProvider([_coverage_json(a) for a in range(20, 100, 6)])
        session = _session(workspace, provider, max_questions=5)

        assert _answer_until_complete(session) == 5

    def test_cap_survives_a_reload(self, workspace):
        """The web UI reloads the session on every answer; the count must hold.

        A reload has no ``max_questions`` argument, so the server's cap is the
        workspace config's.
        """
        from codeframe.core.prd_discovery import process_discovery_answer

        config = Path(workspace.repo_path) / ".codeframe" / "config.yaml"
        config.write_text("discovery_max_questions: 3\n")
        provider = FakeProvider([_coverage_json(a) for a in range(20, 100, 6)])
        session = _session(workspace, provider)
        session_id = session.session_id

        with patch("codeframe.core.prd_discovery.AnthropicProvider", return_value=provider):
            results = [
                process_discovery_answer(workspace, session_id, f"a{i}", api_key="k")
                for i in range(3)
            ]
        assert [r["is_complete"] for r in results] == [False, False, True]

    def test_capped_session_generates_a_prd_listing_uncovered_areas(self, workspace):
        provider = FakeProvider([_coverage_json(a) for a in range(20, 100, 6)])
        session = _session(workspace, provider, max_questions=2)
        _answer_until_complete(session)

        record = session.generate_prd()

        assert record.title == "Todo API"
        prompt = provider.prd_prompts[-1]
        assert "Open Questions" in prompt
        # constraints (40) and tech_stack (30) are below the coverage bar.
        assert "constraints" in prompt and "tech_stack" in prompt
        assert "problem" not in prompt.split("Open Questions", 1)[1]


class TestPlateau:
    def test_flat_noisy_coverage_stops_on_plateau_not_at_cap(self, workspace):
        # The live run's shape: 75-81% wobbling for 20+ answers.
        series = [60, 75, 78, 76, 80, 78, 81, 79, 77, 81, 80, 78]
        provider = FakeProvider([_coverage_json(a) for a in series])
        session = _session(workspace, provider, max_questions=10)

        asked = _answer_until_complete(session)

        assert session.is_complete()
        assert asked < 10
        # Running max: 78 after answer 3, 80 after answer 6 — a gain of 2 over
        # the last three answers, under the 5-point bar.
        assert asked == 6

    def test_rising_coverage_does_not_plateau(self, workspace):
        provider = FakeProvider([_coverage_json(a) for a in range(10, 100, 6)])
        session = _session(workspace, provider, max_questions=8)

        assert _answer_until_complete(session) == 8

    def test_progress_percentage_is_monotonic(self, workspace):
        provider = FakeProvider([_coverage_json(a) for a in [40, 70, 55, 90]])
        session = _session(workspace, provider, max_questions=10)

        seen = []
        for i in range(4):
            session.submit_answer(f"a{i}")
            seen.append(session.get_progress()["percentage"])
        assert seen == [40, 70, 70, 90]


class TestLegacySessions:
    def test_session_saved_before_1443_keeps_its_progress(self, workspace):
        """Pre-#1443 rows have no per-answer scores, only the last assessment."""
        from codeframe.core.prd_discovery import get_session
        from codeframe.core.workspace import get_db_connection

        provider = FakeProvider([_coverage_json(a) for a in range(20, 100, 6)])
        session = _session(workspace, provider)
        legacy = [{"question": f"q{i}", "answer": f"a{i}", "timestamp": "t"} for i in range(3)]
        conn = get_db_connection(workspace)
        conn.execute(
            "UPDATE discovery_sessions SET qa_history = ?, coverage = ? WHERE id = ?",
            (json.dumps(legacy), _coverage_json(75), session.session_id),
        )
        conn.commit()
        conn.close()

        with patch("codeframe.core.prd_discovery.AnthropicProvider", return_value=provider):
            loaded = get_session(workspace, session.session_id, api_key="k")

        assert loaded.get_progress()["percentage"] == 75


class TestUnparseableAssessment:
    def test_garbage_once_keeps_prior_coverage(self, workspace):
        provider = FakeProvider(
            [_coverage_json(50), "Sure! Here is my assessment of the", _coverage_json(70)]
        )
        session = _session(workspace, provider, max_questions=10)

        session.submit_answer("first")
        session.submit_answer("second")  # assessment is garbage

        assert session.get_progress()["percentage"] == 50
        assert session._coverage["average"] == 50
        # The next question was generated against the last good assessment,
        # not "Not yet assessed" — which invited from-the-top questions.
        assert "Not yet assessed" not in provider.question_prompts[-1]
        assert '"average": 50' in provider.question_prompts[-1]

    def test_prose_wrapped_json_is_still_read(self, workspace):
        wrapped = "Here is the assessment:\n```json\n" + _coverage_json(64) + "\n```\nHope it helps."
        provider = FakeProvider([wrapped])
        session = _session(workspace, provider, max_questions=10)

        session.submit_answer("first")

        assert session._coverage["average"] == 64

    def test_repeated_failures_end_discovery(self, workspace):
        provider = FakeProvider([_coverage_json(30), "nope"])
        session = _session(workspace, provider, max_questions=10)

        asked = _answer_until_complete(session)

        # One good assessment, then three failures: no rise over three answers
        # is a plateau, so repeated failures end discovery without a rule of
        # their own.
        assert asked == 4
        assert session.is_complete()


class TestNearDuplicateGuard:
    def test_near_duplicate_question_is_not_asked_twice(self, workspace):
        q = "What would you need to see from teammates to trust the list?"
        dup = "What would you need to see from your teammates to trust this list?"
        fresh = "Which database should store the todos?"
        provider = FakeProvider(
            [_coverage_json(a) for a in range(10, 100, 6)],
            questions=[q, dup, fresh, "Who deploys it and where does it run?"],
        )
        session = _session(workspace, provider, max_questions=10)

        session.submit_answer("first")
        assert session.get_current_question()["text"] == q
        session.submit_answer("second")

        assert session.get_current_question()["text"] == fresh
        # The regeneration named the duplicate so the model can steer away.
        assert dup in provider.question_prompts[-1]

    @pytest.mark.parametrize(
        "earlier, later",
        [
            ("What is the target platform?", "What is the target audience?"),
            ("Who are the primary users of this app?", "Who are the primary competitors of this app?"),
        ],
    )
    def test_same_template_different_topic_is_not_a_duplicate(self, earlier, later):
        """Short questions share their stopwords; only content words count."""
        from codeframe.core.prd_discovery import _is_near_duplicate

        assert not _is_near_duplicate(later, [earlier])

    def test_persistent_duplicates_end_discovery(self, workspace):
        q = "What would you need to see from teammates to trust the list?"
        provider = FakeProvider([_coverage_json(a) for a in range(10, 100, 6)], questions=[q])
        session = _session(workspace, provider, max_questions=10)

        session.submit_answer("first")
        assert session.get_current_question()["text"] == q
        session.submit_answer("second")

        assert session.is_complete()


class TestFinishNow:
    def test_finish_now_completes_and_generates(self, workspace):
        provider = FakeProvider([_coverage_json(40)])
        session = _session(workspace, provider, max_questions=10)
        session.submit_answer("a todo API for my team")

        session.finish_now()

        assert session.is_complete()
        assert session.generate_prd().title == "Todo API"

    def test_finish_now_needs_one_answer(self, workspace):
        from codeframe.core.prd_discovery import DiscoveryError

        provider = FakeProvider([_coverage_json(40)])
        session = _session(workspace, provider)

        with pytest.raises(DiscoveryError):
            session.finish_now()
        assert not session.is_complete()
