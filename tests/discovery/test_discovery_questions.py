"""Tests for Discovery Question Framework.

Following TDD approach:
1. RED: Write failing tests
2. GREEN: Implement minimal code to pass
3. REFACTOR: Optimize for quality
"""

import pytest
from codeframe.discovery.questions import DiscoveryQuestionFramework


class TestDiscoveryQuestionFrameworkInitialization:
    """Test suite for framework initialization."""

    def test_framework_initializes_with_default_categories(self):
        """Framework should initialize with predefined question categories."""
        framework = DiscoveryQuestionFramework()

        expected_categories = ["problem", "users", "features", "constraints", "tech_stack"]
        assert framework.categories == expected_categories

    def test_framework_initializes_with_empty_context(self):
        """Framework should start with empty answer context."""
        framework = DiscoveryQuestionFramework()

        assert framework.context == {}
        assert len(framework.context) == 0


class TestQuestionGeneration:
    """Test suite for question generation functionality."""

    def test_generate_questions_returns_all_categories(self):
        """generate_questions should return questions for all categories."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        # Should have questions for each category
        categories_in_questions = {q["category"] for q in questions}
        assert "problem" in categories_in_questions
        assert "users" in categories_in_questions
        assert "features" in categories_in_questions
        assert "constraints" in categories_in_questions
        assert "tech_stack" in categories_in_questions

    def test_questions_have_required_fields(self):
        """Each question should have id, category, text, importance fields."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        for question in questions:
            assert "id" in question
            assert "category" in question
            assert "text" in question
            assert "importance" in question
            assert question["importance"] in ["required", "optional"]

    def test_problem_category_questions(self):
        """Problem category should have appropriate discovery questions."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        problem_questions = [q for q in questions if q["category"] == "problem"]
        assert len(problem_questions) > 0

        # Should have the main problem question
        problem_texts = [q["text"] for q in problem_questions]
        assert any("problem" in text.lower() and "solve" in text.lower() for text in problem_texts)


class TestContextAwareQuestionProgression:
    """Test suite for context-aware question generation."""

    def test_get_next_question_returns_first_required_question(self):
        """get_next_question should return first unanswered required question."""
        framework = DiscoveryQuestionFramework()

        next_question = framework.get_next_question(context={})

        assert next_question is not None
        assert next_question["importance"] == "required"
        assert next_question["category"] == "problem"

    def test_get_next_question_skips_answered_questions(self):
        """get_next_question should skip questions that have been answered."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        # Answer the first question
        first_question = questions[0]
        context = {first_question["id"]: "User's answer to first question"}

        next_question = framework.get_next_question(context=context)

        # Should not return the answered question
        assert next_question["id"] != first_question["id"]

    def test_get_next_question_returns_none_when_all_required_answered(self):
        """get_next_question returns None when all required questions answered."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        # Answer all required questions
        context = {}
        for q in questions:
            if q["importance"] == "required":
                context[q["id"]] = f"Answer to {q['id']}"

        next_question = framework.get_next_question(context=context)

        # Should return None or optional question
        if next_question is not None:
            assert next_question["importance"] == "optional"

    def test_get_next_question_with_follow_up_logic(self):
        """get_next_question should support follow-up questions based on answers."""
        framework = DiscoveryQuestionFramework()

        # Answer initial questions
        context = {"problem_1": "Building a web application", "users_1": "Developers and designers"}

        next_question = framework.get_next_question(context=context)

        # Should intelligently select next question
        assert next_question is not None
        assert "id" in next_question


class TestDiscoveryCompletionDetection:
    """Test suite for discovery completion logic."""

    def test_is_discovery_complete_false_when_no_answers(self):
        """is_discovery_complete should return False with no answers."""
        framework = DiscoveryQuestionFramework()

        is_complete = framework.is_discovery_complete(answers={})

        assert is_complete is False

    def test_is_discovery_complete_false_when_partial_answers(self):
        """is_discovery_complete should return False with partial answers."""
        framework = DiscoveryQuestionFramework()

        # Only answer some required questions
        answers = {"problem_1": "Building a web app", "users_1": "Developers"}

        is_complete = framework.is_discovery_complete(answers=answers)

        assert is_complete is False

    def test_is_discovery_complete_true_when_all_required_answered(self):
        """is_discovery_complete should return True when all required answered."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        # Answer all required questions
        answers = {}
        for q in questions:
            if q["importance"] == "required":
                answers[q["id"]] = f"Valid answer for {q['id']}"

        is_complete = framework.is_discovery_complete(answers=answers)

        assert is_complete is True

    def test_is_discovery_complete_validates_answer_quality(self):
        """is_discovery_complete should validate that answers are substantive."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        # Provide empty or too-short answers
        answers = {}
        for q in questions:
            if q["importance"] == "required":
                answers[q["id"]] = "N/A"  # Too short

        is_complete = framework.is_discovery_complete(answers=answers)

        # Should be False because answers are not substantive
        assert is_complete is False


class TestQuestionOrdering:
    """Test suite for question ordering and progression logic."""

    def test_questions_ordered_by_importance_and_category(self):
        """Questions should be ordered with required first, then by category."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        # Required questions should come first
        required_questions = [q for q in questions if q["importance"] == "required"]
        optional_questions = [q for q in questions if q["importance"] == "optional"]

        # Find index of last required and first optional
        if required_questions and optional_questions:
            last_required_idx = questions.index(required_questions[-1])
            first_optional_idx = questions.index(optional_questions[0])

            assert last_required_idx < first_optional_idx

    def test_get_next_question_returns_none_when_all_answered(self):
        """get_next_question should return None when all questions answered."""
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()

        # Answer all questions (both required and optional)
        context = {}
        for q in questions:
            context[q["id"]] = f"Valid answer for {q['id']}"

        next_question = framework.get_next_question(context=context)

        # Should return None when everything is answered
        assert next_question is None
