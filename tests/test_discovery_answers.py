"""Tests for answer capture and structuring in Socratic discovery.

This module implements comprehensive tests for the answer capture system
following TDD (Test-Driven Development) principles.
"""

import pytest
from codeframe.discovery.answers import AnswerCapture


class TestAnswerCaptureBasics:
    """Test basic answer capture functionality."""

    def test_capture_single_answer(self):
        """Test capturing a single answer with question ID."""
        capture = AnswerCapture()

        result = capture.capture_answer(
            question_id="q1",
            answer_text="Authentication for a SaaS app"
        )

        assert result is True
        assert "q1" in capture.answers
        assert capture.answers["q1"]["text"] == "Authentication for a SaaS app"

    def test_capture_multiple_answers(self):
        """Test capturing multiple answers from different questions."""
        capture = AnswerCapture()

        capture.capture_answer("q1", "User authentication system")
        capture.capture_answer("q2", "Developers and end users")
        capture.capture_answer("q3", "Must use PostgreSQL and Redis")

        assert len(capture.answers) == 3
        assert all(qid in capture.answers for qid in ["q1", "q2", "q3"])

    def test_update_existing_answer(self):
        """Test updating an existing answer overwrites previous value."""
        capture = AnswerCapture()

        capture.capture_answer("q1", "Initial answer")
        capture.capture_answer("q1", "Updated answer")

        assert capture.answers["q1"]["text"] == "Updated answer"

    def test_empty_answer_text(self):
        """Test handling of empty answer text."""
        capture = AnswerCapture()

        result = capture.capture_answer("q1", "")

        assert result is True
        assert capture.answers["q1"]["text"] == ""


class TestFeatureExtraction:
    """Test feature extraction from natural language answers."""

    def test_extract_comma_separated_features(self):
        """Test extracting features from comma-separated list."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "login, signup, password reset")

        features = capture.extract_features(capture.answers)

        assert "login" in features
        assert "signup" in features
        assert "password reset" in features

    def test_extract_features_from_sentence(self):
        """Test extracting features from natural sentence."""
        capture = AnswerCapture()
        capture.capture_answer(
            "q1",
            "The system needs authentication, authorization, and user profile management"
        )

        features = capture.extract_features(capture.answers)

        assert "authentication" in features
        assert "authorization" in features
        assert "user profile management" in features

    def test_extract_features_with_action_verbs(self):
        """Test extracting features that start with action verbs."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Users can login, logout, and reset passwords")

        features = capture.extract_features(capture.answers)

        assert any("login" in f for f in features)
        assert any("logout" in f for f in features)
        assert any("reset" in f.lower() and "password" in f.lower() for f in features)

    def test_extract_features_from_multiple_answers(self):
        """Test extracting features from multiple question answers."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Authentication system")
        capture.capture_answer("q2", "User dashboard and reporting")

        features = capture.extract_features(capture.answers)

        assert len(features) >= 2
        assert any("authentication" in f.lower() for f in features)
        assert any("dashboard" in f.lower() for f in features)


class TestUserExtraction:
    """Test user/persona extraction from answers."""

    def test_extract_simple_users(self):
        """Test extracting simple user types."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "developers and end users")

        users = capture.extract_users(capture.answers)

        assert "developers" in users
        assert "end users" in users

    def test_extract_users_with_roles(self):
        """Test extracting users with specific roles."""
        capture = AnswerCapture()
        capture.capture_answer(
            "q1",
            "The system is for administrators, content creators, and viewers"
        )

        users = capture.extract_users(capture.answers)

        assert "administrators" in users
        assert "content creators" in users
        assert "viewers" in users

    def test_extract_users_from_personas(self):
        """Test extracting users from persona descriptions."""
        capture = AnswerCapture()
        capture.capture_answer(
            "q1",
            "Primary users are software engineers. Secondary users include project managers."
        )

        users = capture.extract_users(capture.answers)

        assert any("engineer" in u.lower() for u in users)
        assert any("manager" in u.lower() for u in users)

    def test_extract_no_users(self):
        """Test when no users are mentioned in answers."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Authentication with JWT tokens")

        users = capture.extract_users(capture.answers)

        assert isinstance(users, list)
        assert len(users) == 0


class TestConstraintExtraction:
    """Test constraint extraction from answers."""

    def test_extract_technology_constraints(self):
        """Test extracting technology constraints."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Must use PostgreSQL and Redis")

        constraints = capture.extract_constraints(capture.answers)

        assert "database" in constraints or "technology" in constraints
        assert any("PostgreSQL" in str(v) for v in constraints.values())
        assert any("Redis" in str(v) for v in constraints.values())

    def test_extract_performance_constraints(self):
        """Test extracting performance-related constraints."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Response time must be under 200ms")

        constraints = capture.extract_constraints(capture.answers)

        assert "performance" in constraints or "response_time" in constraints

    def test_extract_security_constraints(self):
        """Test extracting security constraints."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Must comply with GDPR and use encrypted storage")

        constraints = capture.extract_constraints(capture.answers)

        assert "security" in constraints or "compliance" in constraints

    def test_extract_multiple_constraint_types(self):
        """Test extracting multiple types of constraints."""
        capture = AnswerCapture()
        capture.capture_answer(
            "q1",
            "Use PostgreSQL database, must be GDPR compliant, response under 100ms"
        )

        constraints = capture.extract_constraints(capture.answers)

        assert len(constraints) >= 2


class TestStructuredDataGeneration:
    """Test generation of structured data for PRD."""

    def test_get_structured_data_basic(self):
        """Test basic structured data generation."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Authentication for a SaaS app")
        capture.capture_answer("q2", "Developers")

        data = capture.get_structured_data()

        assert isinstance(data, dict)
        assert "features" in data
        assert "users" in data
        assert "constraints" in data

    def test_get_structured_data_with_confidence(self):
        """Test structured data includes confidence scores."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "login, signup, password reset")

        data = capture.get_structured_data()

        assert "confidence" in data
        assert isinstance(data["confidence"], dict)

    def test_structured_data_example_case(self):
        """Test the example from requirements."""
        capture = AnswerCapture()
        capture.capture_answer(
            "q1",
            "Authentication for a SaaS app. Users are developers."
        )

        data = capture.get_structured_data()

        # Should extract problem, domain, and users
        assert any("authentication" in str(v).lower() for v in data.values() if isinstance(v, (str, list)))
        assert any("saas" in str(v).lower() for v in data.values() if isinstance(v, (str, list)))
        assert any("developer" in str(u).lower() for u in data.get("users", []))

    def test_structured_data_empty_capture(self):
        """Test structured data generation with no answers."""
        capture = AnswerCapture()

        data = capture.get_structured_data()

        assert isinstance(data, dict)
        assert data["features"] == []
        assert data["users"] == []
        assert data["constraints"] == {}

    def test_structured_data_preserves_raw_answers(self):
        """Test that structured data includes raw answer text."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Test answer")

        data = capture.get_structured_data()

        assert "raw_answers" in data
        assert "q1" in data["raw_answers"]
        assert data["raw_answers"]["q1"] == "Test answer"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_special_characters_in_answers(self):
        """Test handling special characters in answers."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Features: login & signup, user@domain.com")

        features = capture.extract_features(capture.answers)

        assert len(features) > 0

    def test_very_long_answer_text(self):
        """Test handling very long answer text."""
        capture = AnswerCapture()
        long_text = "authentication " * 100

        result = capture.capture_answer("q1", long_text)

        assert result is True

    def test_unicode_characters(self):
        """Test handling unicode characters."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "Users: 开发者 and développeurs")

        users = capture.extract_users(capture.answers)

        assert isinstance(users, list)

    def test_case_insensitive_extraction(self):
        """Test that extraction is case-insensitive."""
        capture = AnswerCapture()
        capture.capture_answer("q1", "AUTHENTICATION and Authorization")

        features = capture.extract_features(capture.answers)

        # Should normalize case
        assert len(features) >= 2
