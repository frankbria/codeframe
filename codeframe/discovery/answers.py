"""Answer capture and structuring for Socratic discovery.

This module provides the AnswerCapture class for capturing user responses
during Socratic discovery sessions and extracting structured data for PRD generation.
"""

import re
from typing import Any


class AnswerCapture:
    """Captures and structures answers from Socratic discovery sessions.

    This class provides methods to capture user answers, extract features,
    users, and constraints, and generate structured data for PRD generation.

    Attributes:
        answers: Dictionary mapping question IDs to answer data
    """

    def __init__(self) -> None:
        """Initialize the AnswerCapture instance."""
        self.answers: dict[str, dict[str, Any]] = {}

    def capture_answer(self, question_id: str, answer_text: str) -> bool:
        """Capture an answer for a specific question.

        Args:
            question_id: Unique identifier for the question
            answer_text: User's answer text

        Returns:
            True if capture was successful
        """
        self.answers[question_id] = {
            "text": answer_text,
            "timestamp": None,  # Could add actual timestamp if needed
        }
        return True

    def extract_features(self, answers: dict[str, dict[str, Any]]) -> list[str]:
        """Extract features from captured answers.

        Parses natural language answers to identify features, capabilities,
        or functionalities mentioned by the user.

        Args:
            answers: Dictionary of captured answers

        Returns:
            List of extracted feature strings
        """
        features = []

        for answer_data in answers.values():
            text = answer_data.get("text", "")

            # Extract comma-separated items (handles "X, Y, and Z" pattern)
            if "," in text:
                # Split by comma and clean up
                parts = [part.strip() for part in text.split(",")]
                for part in parts:
                    # Remove "and" at the beginning
                    part = re.sub(r"^\s*and\s+", "", part, flags=re.IGNORECASE)
                    # Remove common prefixes/suffixes
                    cleaned = self._clean_feature_text(part)
                    if cleaned and len(cleaned) > 2:
                        features.append(cleaned)

            # Extract features with "and" conjunction (not already in comma list)
            elif " and " in text.lower():
                # Match patterns like "X and Y" with better context
                # Use word boundaries to capture full phrases
                pattern = r"\b([\w\s]+?)\s+and\s+([\w\s]+?)(?:\.|,|$|\s+(?:for|with|in|to)\b)"
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    for group in match.groups():
                        cleaned = self._clean_feature_text(group)
                        if cleaned and len(cleaned) > 2:
                            features.append(cleaned)

            # Extract features from action verbs (can login, can logout, etc.)
            action_patterns = [
                r"can\s+([\w\s]+?)(?:\.|,|and|$)",
                r"able to\s+([\w\s]+?)(?:\.|,|and|$)",
                r"needs?\s+([\w\s]+?)(?:\.|,|and|$)",
                r"requires?\s+([\w\s]+?)(?:\.|,|and|$)",
            ]
            for pattern in action_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    feature = match.group(1).strip()
                    cleaned = self._clean_feature_text(feature)
                    if cleaned and len(cleaned) > 2:
                        features.append(cleaned)

            # Extract single-word or multi-word features from key sentences
            # Look for key technical terms and phrases
            tech_patterns = [
                r"\b(authentication|authorization|login|logout|signup|sign\s*up|dashboard|"
                r"reporting|profile|settings|admin|user\s+profile(?:\s+management)?|"
                r"password\s+\w+|saas|app)\b"
            ]
            for pattern in tech_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    feature = match.group(1).strip()
                    cleaned = self._clean_feature_text(feature)
                    if cleaned and len(cleaned) > 2:
                        features.append(cleaned)

        # Remove duplicates while preserving order and normalize case
        seen = set()
        unique_features = []
        for feature in features:
            feature_lower = feature.lower()
            if feature_lower not in seen:
                seen.add(feature_lower)
                unique_features.append(feature)

        return unique_features

    def extract_users(self, answers: dict[str, dict[str, Any]]) -> list[str]:
        """Extract user types/personas from captured answers.

        Identifies different user types, roles, or personas mentioned
        in the answers.

        Args:
            answers: Dictionary of captured answers

        Returns:
            List of extracted user types
        """
        users = []

        for answer_data in answers.values():
            text = answer_data.get("text", "")

            # Common user/role patterns
            user_patterns = [
                # Direct mentions
                r"\b(developers?|engineers?|programmers?)\b",
                r"\b(end\s+users?|users?)\b",
                r"\b(administrators?|admins?)\b",
                r"\b(managers?|project\s+managers?)\b",
                r"\b(creators?|content\s+creators?)\b",
                r"\b(viewers?|readers?)\b",
                r"\b(clients?|customers?)\b",
                r"\b(team\s+members?)\b",
                # Role-based patterns
                r"for\s+(\w+(?:\s+\w+)?)\s+(?:and|,)",
                r"users?\s+are\s+(\w+(?:\s+\w+)?)",
                r"(?:primary|secondary)\s+users?\s+(?:are|include)\s+(\w+(?:\s+\w+)?)",
            ]

            for pattern in user_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    user = match.group(1) if len(match.groups()) > 0 else match.group(0)
                    user = user.strip()
                    # Clean up common articles and prepositions
                    user = re.sub(r"^(the|a|an)\s+", "", user, flags=re.IGNORECASE)
                    if user and len(user) > 2:
                        users.append(user)

            # Extract from lists with "and"
            if " and " in text:
                # Check for user context words before/after
                user_context_words = ["users", "for", "are", "include"]
                for word in user_context_words:
                    if word in text.lower():
                        pattern = r"(\w+(?:\s+\w+)?)\s+and\s+(\w+(?:\s+\w+)?)"
                        matches = re.finditer(pattern, text, re.IGNORECASE)
                        for match in matches:
                            for group in match.groups():
                                cleaned = group.strip()
                                cleaned = re.sub(
                                    r"^(the|a|an)\s+", "", cleaned, flags=re.IGNORECASE
                                )
                                if (
                                    cleaned
                                    and len(cleaned) > 2
                                    and not cleaned.lower() in ["system", "app"]
                                ):
                                    users.append(cleaned)
                        break

        # Remove duplicates while preserving order and normalize similar terms
        seen = set()
        unique_users = []
        for user in users:
            user_lower = user.lower()
            # Skip common non-user words
            if user_lower in ["system", "app", "application", "software"]:
                continue
            if user_lower not in seen:
                seen.add(user_lower)
                unique_users.append(user)

        return unique_users

    def extract_constraints(self, answers: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Extract technical and business constraints from answers.

        Identifies constraints related to technology, performance,
        security, compliance, etc.

        Args:
            answers: Dictionary of captured answers

        Returns:
            Dictionary of constraint types to constraint values
        """
        constraints: dict[str, Any] = {}

        for answer_data in answers.values():
            text = answer_data.get("text", "")

            # Technology constraints
            tech_patterns = [
                (r"\b(PostgreSQL|MySQL|MongoDB|Redis|SQLite)\b", "database"),
                (r"\b(React|Vue|Angular|Svelte)\b", "frontend"),
                (r"\b(Node\.js|Python|Ruby|Java|Go)\b", "backend"),
                (r"\b(AWS|Azure|GCP|Google Cloud)\b", "cloud"),
            ]

            for pattern, constraint_type in tech_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    tech = match.group(1)
                    if constraint_type not in constraints:
                        constraints[constraint_type] = []
                    if isinstance(constraints[constraint_type], list):
                        constraints[constraint_type].append(tech)
                    else:
                        constraints[constraint_type] = [constraints[constraint_type], tech]

            # Performance constraints
            perf_patterns = [
                r"response\s+time.*?(\d+)\s*ms",
                r"under\s+(\d+)\s*ms",
                r"latency.*?(\d+)\s*ms",
            ]

            for pattern in perf_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    constraints["performance"] = f"response_time_ms: {match.group(1)}"
                    break

            # Security/Compliance constraints
            security_patterns = [
                r"\b(GDPR|HIPAA|SOC2|PCI DSS)\b",
                r"\b(encrypted?|encryption)\b",
                r"\bcomply\s+with\s+(\w+)\b",
            ]

            security_items = []
            for pattern in security_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    security_items.append(match.group(0))

            if security_items:
                constraints["security"] = security_items

        # Flatten single-item lists for cleaner output
        for key, value in constraints.items():
            if isinstance(value, list) and len(value) == 1:
                constraints[key] = value[0]

        return constraints

    def get_structured_data(self) -> dict[str, Any]:
        """Generate structured data from all captured answers.

        Combines all extraction methods to produce a comprehensive
        structured representation suitable for PRD generation.

        Returns:
            Dictionary containing features, users, constraints, and metadata
        """
        features = self.extract_features(self.answers)
        users = self.extract_users(self.answers)
        constraints = self.extract_constraints(self.answers)

        # Calculate basic confidence scores
        confidence = {
            "features": 0.8 if features else 0.0,
            "users": 0.8 if users else 0.0,
            "constraints": 0.7 if constraints else 0.0,
        }

        # Extract raw answers for reference
        raw_answers = {qid: data.get("text", "") for qid, data in self.answers.items()}

        return {
            "features": features,
            "users": users,
            "constraints": constraints,
            "confidence": confidence,
            "raw_answers": raw_answers,
        }

    def _clean_feature_text(self, text: str) -> str:
        """Clean and normalize feature text.

        Args:
            text: Raw feature text

        Returns:
            Cleaned feature text
        """
        # Remove common prefixes and articles
        text = re.sub(r"^(the|a|an)\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(system|needs?|requires?)\s+", "", text, flags=re.IGNORECASE)

        # Remove trailing punctuation
        text = re.sub(r"[.,;:!?]+$", "", text)

        # Normalize whitespace
        text = " ".join(text.split())

        return text.strip()
