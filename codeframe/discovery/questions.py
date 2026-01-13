"""Discovery Question Framework for Socratic requirements gathering.

This module provides a structured approach to discovering project requirements
through progressive questioning organized by category.

Note: As of the Socratic Discovery enhancement, this framework now serves as:
1. A FALLBACK mechanism when AI question generation fails
2. A VALIDATION layer to ensure all required categories are covered
3. A COMPLETION DETECTOR using is_discovery_complete()

AI-powered questions are generated dynamically by LeadAgent._generate_next_discovery_question()
with full conversation context. The static questions defined here are preserved
for fallback scenarios and backward compatibility.

See docs/discovery-socratic-methodology.md for full architecture details.
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Question categories in order of importance
QUESTION_CATEGORIES = ["problem", "users", "features", "constraints", "tech_stack"]

# Minimum answer length to be considered substantive
MIN_ANSWER_LENGTH = 5

# Invalid answer patterns
INVALID_ANSWERS = {"n/a", "na", "none", "idk"}


class DiscoveryQuestionFramework:
    """Framework for managing discovery questions and tracking progress.

    Organizes questions by category and manages progression through the
    discovery process based on user responses.

    Attributes:
        categories: List of question categories in order
        context: Dictionary of question IDs to user answers
    """

    def __init__(self):
        """Initialize the discovery question framework."""
        self.categories = QUESTION_CATEGORIES
        self.context: Dict[str, str] = {}
        self._questions: Optional[List[Dict[str, Any]]] = None
        logger.debug("Initialized DiscoveryQuestionFramework")

    def _create_question(
        self, question_id: str, category: str, text: str, importance: str = "required"
    ) -> Dict[str, Any]:
        """Create a question dictionary with consistent structure.

        Args:
            question_id: Unique identifier for the question
            category: Category this question belongs to
            text: The question text to ask the user
            importance: Either 'required' or 'optional'

        Returns:
            Question dictionary with all required fields
        """
        return {
            "id": question_id,
            "category": category,
            "text": text,
            "importance": importance,
        }

    def generate_questions(self) -> List[Dict[str, Any]]:
        """Generate all discovery questions organized by category.

        Questions are organized into five categories: problem, users, features,
        constraints, and tech_stack. Required questions are placed before optional
        ones to prioritize essential information gathering.

        Returns:
            List of question dictionaries with id, category, text, and importance

        Example:
            >>> framework = DiscoveryQuestionFramework()
            >>> questions = framework.generate_questions()
            >>> len(questions)
            10
            >>> questions[0]["category"]
            'problem'
        """
        if self._questions is not None:
            return self._questions

        questions = []

        # Problem category questions
        questions.extend(
            [
                self._create_question(
                    "problem_1", "problem", "What problem does this application solve?", "required"
                ),
                self._create_question(
                    "problem_2",
                    "problem",
                    "Why does this problem need to be solved now?",
                    "optional",
                ),
            ]
        )

        # Users category questions
        questions.extend(
            [
                self._create_question(
                    "users_1", "users", "Who are the primary users of this application?", "required"
                ),
                self._create_question(
                    "users_2", "users", "What is the expected number of users?", "optional"
                ),
            ]
        )

        # Features category questions
        questions.extend(
            [
                self._create_question(
                    "features_1",
                    "features",
                    "What are the core features you need? (Please list the top 3)",
                    "required",
                ),
                self._create_question(
                    "features_2",
                    "features",
                    "Are there any nice-to-have features for future iterations?",
                    "optional",
                ),
            ]
        )

        # Constraints category questions
        questions.extend(
            [
                self._create_question(
                    "constraints_1",
                    "constraints",
                    "Are there any technical constraints we should be aware of?",
                    "required",
                ),
                self._create_question(
                    "constraints_2",
                    "constraints",
                    "What is the timeline for this project?",
                    "optional",
                ),
            ]
        )

        # Tech stack category questions
        questions.extend(
            [
                self._create_question(
                    "tech_stack_1",
                    "tech_stack",
                    "Do you have a preferred tech stack or programming language?",
                    "required",
                ),
                self._create_question(
                    "tech_stack_2",
                    "tech_stack",
                    "Are there any existing systems this needs to integrate with?",
                    "optional",
                ),
            ]
        )

        # Sort questions: required first, then optional, maintaining category order
        required_questions = [q for q in questions if q["importance"] == "required"]
        optional_questions = [q for q in questions if q["importance"] == "optional"]

        self._questions = required_questions + optional_questions
        logger.debug(f"Generated {len(self._questions)} questions")
        return self._questions

    def get_next_question(self, context: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Get the next unanswered question based on current context.

        The method prioritizes required questions before optional ones, ensuring
        that essential information is gathered first. Once all required questions
        are answered, optional questions are presented.

        Args:
            context: Dictionary mapping question IDs to user answers

        Returns:
            Next question to ask, or None if all questions are answered

        Example:
            >>> framework = DiscoveryQuestionFramework()
            >>> next_q = framework.get_next_question(context={})
            >>> next_q["importance"]
            'required'
        """
        questions = self.generate_questions()

        # First, try to find next unanswered required question
        for question in questions:
            if question["id"] not in context and question["importance"] == "required":
                logger.debug(f"Next question: {question['id']} (required)")
                return question

        # If all required questions answered, return next optional
        for question in questions:
            if question["id"] not in context and question["importance"] == "optional":
                logger.debug(f"Next question: {question['id']} (optional)")
                return question

        logger.debug("No more questions to ask")
        return None

    def _is_answer_valid(self, answer: str) -> bool:
        """Check if an answer is substantive and valid.

        Args:
            answer: The user's answer text

        Returns:
            True if answer is valid and substantive, False otherwise
        """
        answer = answer.strip()
        return len(answer) >= MIN_ANSWER_LENGTH and answer.lower() not in INVALID_ANSWERS

    def is_discovery_complete(self, answers: Dict[str, str]) -> bool:
        """Check if discovery phase is complete.

        Discovery is complete when all required questions have been answered
        with substantive responses. Answers must be longer than the minimum
        length and not match invalid patterns (e.g., "N/A", "idk").

        Args:
            answers: Dictionary mapping question IDs to user answers

        Returns:
            True if discovery is complete, False otherwise

        Example:
            >>> framework = DiscoveryQuestionFramework()
            >>> framework.is_discovery_complete({})
            False
            >>> questions = framework.generate_questions()
            >>> required = {q["id"]: "Valid answer" for q in questions if q["importance"] == "required"}
            >>> framework.is_discovery_complete(required)
            True
        """
        if not answers:
            logger.debug("Discovery incomplete: no answers provided")
            return False

        questions = self.generate_questions()
        required_questions = [q for q in questions if q["importance"] == "required"]

        # Check all required questions are answered with valid responses
        for question in required_questions:
            if question["id"] not in answers:
                logger.debug(f"Discovery incomplete: missing answer for {question['id']}")
                return False

            # Validate answer quality
            if not self._is_answer_valid(answers[question["id"]]):
                logger.debug(f"Discovery incomplete: invalid answer for {question['id']}")
                return False

        logger.info(f"Discovery complete: {len(required_questions)} required questions answered")
        return True
