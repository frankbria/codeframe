"""PRD Discovery Session management for CodeFRAME v2.

This module provides headless, CLI-native Socratic discovery for PRD generation.
It reuses the existing DiscoveryQuestionFramework and AnswerCapture classes
while providing a session-based interface suitable for CLI interaction.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from codeframe.core import blockers, prd
from codeframe.core.workspace import Workspace, get_db_connection
from codeframe.discovery.answers import AnswerCapture
from codeframe.discovery.questions import (
    QUESTION_CATEGORIES,
    DiscoveryQuestionFramework,
    MIN_ANSWER_LENGTH,
    INVALID_ANSWERS,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ValidationError(Exception):
    """Raised when answer validation fails."""

    pass


class IncompleteSessionError(Exception):
    """Raised when trying to generate PRD from incomplete session."""

    pass


class SessionState(str, Enum):
    """State of a discovery session."""

    IDLE = "idle"
    DISCOVERING = "discovering"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass
class PrdDiscoverySession:
    """Manages an interactive PRD discovery session.

    Orchestrates question flow using DiscoveryQuestionFramework,
    captures and validates answers, stores state in workspace database,
    and generates PRD from collected answers.

    Attributes:
        workspace: The workspace this session belongs to
        api_key: Optional API key for AI-powered questions
        session_id: Unique session identifier
        state: Current session state
    """

    workspace: Workspace
    api_key: Optional[str] = None
    session_id: Optional[str] = field(default=None, init=False)
    state: SessionState = field(default=SessionState.IDLE, init=False)
    _framework: DiscoveryQuestionFramework = field(default=None, init=False)
    _answer_capture: AnswerCapture = field(default=None, init=False)
    _answers: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _llm_provider: Any = field(default=None, init=False)
    _blocker_id: Optional[str] = field(default=None, init=False)

    def __post_init__(self):
        """Initialize components."""
        self._framework = DiscoveryQuestionFramework()
        self._answer_capture = AnswerCapture()

        # Initialize LLM provider if API key available
        if self.api_key or os.getenv("ANTHROPIC_API_KEY"):
            try:
                from codeframe.adapters.llm.anthropic import AnthropicProvider

                key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
                self._llm_provider = AnthropicProvider(api_key=key)
            except ImportError:
                logger.warning("AnthropicProvider not available, using static questions")
                self._llm_provider = None
            except Exception as e:
                logger.warning(f"Failed to initialize LLM provider: {e}")
                self._llm_provider = None

    @property
    def answered_count(self) -> int:
        """Number of questions answered."""
        return len(self._answers)

    def start_discovery(self) -> None:
        """Start a new discovery session.

        Creates a session record in the database and sets state to DISCOVERING.
        """
        self.session_id = str(uuid.uuid4())
        self.state = SessionState.DISCOVERING
        self._answers = {}

        # Ensure schema exists and save initial session
        _ensure_discovery_schema(self.workspace)
        self._save_session()

        logger.info(f"Started discovery session {self.session_id}")

    def load_session(self, session_id: str) -> None:
        """Load an existing session from database.

        Args:
            session_id: Session ID to load

        Raises:
            ValueError: If session not found
        """
        conn = get_db_connection(self.workspace)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, state, answers, blocker_id
            FROM discovery_sessions
            WHERE id = ? AND workspace_id = ?
            """,
            (session_id, self.workspace.id),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Session not found: {session_id}")

        self.session_id = row[0]
        self.state = SessionState(row[1])
        self._answers = json.loads(row[2]) if row[2] else {}
        self._blocker_id = row[3]

        # Sync answers with answer capture
        for qid, data in self._answers.items():
            self._answer_capture.capture_answer(qid, data.get("text", ""))

        logger.info(f"Loaded session {session_id} with {len(self._answers)} answers")

    def get_current_question(self) -> Optional[dict[str, Any]]:
        """Get the next unanswered question.

        Returns question dict with id, category, text, importance.
        Uses AI for follow-up questions if LLM provider available,
        otherwise falls back to static questions.

        Returns:
            Question dict or None if all questions answered
        """
        # Build context from already-answered questions
        context = {qid: data.get("text", "") for qid, data in self._answers.items()}

        # Get next question from framework
        question = self._framework.get_next_question(context)

        if question is None:
            return None

        # If we have LLM provider and have some context, try AI question
        if self._llm_provider and len(self._answers) > 0:
            try:
                ai_question = self._generate_ai_question(question, context)
                if ai_question:
                    # Return AI question but keep same ID for tracking
                    return {
                        **question,
                        "text": ai_question,
                        "ai_generated": True,
                    }
            except Exception as e:
                logger.warning(f"AI question generation failed, using static: {e}")

        return question

    def _generate_ai_question(
        self, base_question: dict[str, Any], context: dict[str, str]
    ) -> Optional[str]:
        """Generate an AI-powered follow-up question.

        Args:
            base_question: The base question from framework
            context: Previously answered questions

        Returns:
            AI-generated question text or None
        """
        if not self._llm_provider:
            return None

        from codeframe.adapters.llm.base import Purpose

        # Build prompt with context
        context_str = "\n".join(
            f"Q: {qid}\nA: {text}" for qid, text in context.items()
        )

        system = (
            "You are helping gather requirements for a software project. "
            "Based on the user's previous answers, generate a thoughtful follow-up question "
            "for the category specified. Be specific and help clarify requirements."
        )

        prompt = f"""Previous answers:
{context_str}

Current category: {base_question['category']}
Base question: {base_question['text']}

Generate a more specific, context-aware follow-up question that builds on what the user has shared.
Only output the question text, nothing else."""

        try:
            response = self._llm_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                purpose=Purpose.GENERATION,
                system=system,
                max_tokens=200,
                temperature=0.7,
            )
            return response.content.strip()
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            return None

    def submit_answer(self, answer_text: str) -> None:
        """Submit an answer to the current question.

        Validates the answer, saves it, and advances to next question.

        Args:
            answer_text: User's answer

        Raises:
            ValidationError: If answer is invalid
            ValueError: If no current question
        """
        answer_text = answer_text.strip()

        # Validate answer - check invalid patterns first (more specific error)
        if answer_text.lower() in INVALID_ANSWERS:
            raise ValidationError(
                "Please provide a substantive answer (not 'n/a', 'idk', etc.)"
            )

        if len(answer_text) < MIN_ANSWER_LENGTH:
            raise ValidationError(
                f"Answer too short (minimum {MIN_ANSWER_LENGTH} characters)"
            )

        # Get current question
        context = {qid: data.get("text", "") for qid, data in self._answers.items()}
        question = self._framework.get_next_question(context)

        if question is None:
            raise ValueError("No current question to answer")

        # Store answer
        self._answers[question["id"]] = {
            "text": answer_text,
            "question_text": question["text"],
            "category": question["category"],
            "timestamp": _utc_now().isoformat(),
        }

        # Also capture in AnswerCapture for extraction
        self._answer_capture.capture_answer(question["id"], answer_text)

        # Save to database
        self._save_session()

        logger.info(f"Answer submitted for {question['id']}")

    def is_complete(self) -> bool:
        """Check if all required questions have been answered.

        Returns:
            True if discovery is complete
        """
        context = {qid: data.get("text", "") for qid, data in self._answers.items()}
        return self._framework.is_discovery_complete(context)

    def get_progress(self) -> dict[str, Any]:
        """Get discovery progress statistics.

        Returns:
            Dict with answered, required_total, optional_total, percentage
        """
        questions = self._framework.generate_questions()
        required_questions = [q for q in questions if q["importance"] == "required"]
        optional_questions = [q for q in questions if q["importance"] == "optional"]

        required_answered = sum(
            1 for q in required_questions if q["id"] in self._answers
        )

        percentage = (
            int(required_answered / len(required_questions) * 100)
            if required_questions
            else 0
        )

        return {
            "answered": required_answered,
            "required_total": len(required_questions),
            "optional_total": len(optional_questions),
            "percentage": percentage,
            "categories_complete": self._get_completed_categories(),
        }

    def _get_completed_categories(self) -> list[str]:
        """Get list of fully answered categories."""
        completed = []
        questions = self._framework.generate_questions()

        for category in QUESTION_CATEGORIES:
            category_required = [
                q
                for q in questions
                if q["category"] == category and q["importance"] == "required"
            ]
            if all(q["id"] in self._answers for q in category_required):
                completed.append(category)

        return completed

    def pause_discovery(self, reason: str) -> str:
        """Pause the discovery session.

        Creates a blocker for later resume.

        Args:
            reason: Reason for pausing

        Returns:
            Blocker ID for resume
        """
        self.state = SessionState.PAUSED

        # Create blocker with session info
        question = (
            f"Discovery session paused: {reason}\n"
            f"Session ID: {self.session_id}\n"
            f"Progress: {self.answered_count} questions answered"
        )

        blocker = blockers.create(
            self.workspace, question=question, task_id=None  # Session-level blocker
        )
        self._blocker_id = blocker.id
        self._save_session()

        logger.info(f"Session paused with blocker {blocker.id}")
        return blocker.id

    def resume_discovery(self, blocker_id: str) -> None:
        """Resume discovery from a blocker.

        Args:
            blocker_id: Blocker ID to resume from

        Raises:
            ValueError: If blocker not found or not a discovery blocker
        """
        blocker = blockers.get(self.workspace, blocker_id)
        if not blocker:
            raise ValueError(f"Blocker not found: {blocker_id}")

        if "discovery" not in blocker.question.lower():
            raise ValueError("Blocker is not a discovery session blocker")

        # Extract session ID from blocker question
        lines = blocker.question.split("\n")
        session_id = None
        for line in lines:
            if "Session ID:" in line:
                session_id = line.split("Session ID:")[-1].strip()
                break

        if not session_id:
            raise ValueError("Could not find session ID in blocker")

        # Load the session
        self.load_session(session_id)
        self.state = SessionState.DISCOVERING
        self._save_session()

        logger.info(f"Resumed session {session_id} from blocker {blocker_id}")

    def generate_prd(self) -> prd.PrdRecord:
        """Generate PRD from discovery answers.

        Extracts structured data from answers and builds PRD markdown.

        Returns:
            Created PrdRecord

        Raises:
            IncompleteSessionError: If required questions not answered
        """
        if not self.is_complete():
            raise IncompleteSessionError(
                "Cannot generate PRD: not all required questions answered"
            )

        # Get structured data from answers
        structured = self._answer_capture.get_structured_data()

        # Build PRD content
        content = self._build_prd_content(structured)

        # Extract title from problem answer
        title = self._extract_title()

        # Store PRD
        record = prd.store(
            self.workspace,
            content=content,
            title=title,
            metadata={
                "source": "discovery",
                "session_id": self.session_id,
                "generated_at": _utc_now().isoformat(),
            },
        )

        # Update session state
        self.state = SessionState.COMPLETED
        self._save_session()

        logger.info(f"Generated PRD {record.id} from session {self.session_id}")
        return record

    def _extract_title(self) -> str:
        """Extract project title from answers."""
        # Try to find a title in problem answers
        for qid, data in self._answers.items():
            if "problem" in qid:
                text = data.get("text", "")
                # Take first sentence or first 50 chars
                if "." in text[:100]:
                    return text.split(".")[0].strip()[:60]
                return text[:50].strip() + "..."

        return "Untitled Project"

    def _build_prd_content(self, structured: dict[str, Any]) -> str:
        """Build PRD markdown from structured data.

        Args:
            structured: Data from AnswerCapture.get_structured_data()

        Returns:
            PRD markdown content
        """
        lines = []

        # Title
        title = self._extract_title()
        lines.append(f"# {title}")
        lines.append("")

        # Overview section
        lines.append("## Overview")
        lines.append("")
        problem_answers = [
            data["text"]
            for qid, data in self._answers.items()
            if data.get("category") == "problem"
        ]
        if problem_answers:
            lines.append(problem_answers[0])
        lines.append("")

        # User Stories section
        lines.append("## User Stories")
        lines.append("")
        users = structured.get("users", [])
        features = structured.get("features", [])

        if users and features:
            for user in users[:3]:  # Limit to 3 user types
                for feature in features[:3]:  # 3 features per user
                    lines.append(f"- As a **{user}**, I want to {feature.lower()}")
            lines.append("")
        elif users:
            for user in users:
                lines.append(f"- **{user}**: Primary user of the system")
            lines.append("")
        else:
            user_answers = [
                data["text"]
                for qid, data in self._answers.items()
                if data.get("category") == "users"
            ]
            for answer in user_answers:
                lines.append(f"- {answer}")
            lines.append("")

        # Technical Requirements section
        lines.append("## Technical Requirements")
        lines.append("")
        tech_answers = [
            data["text"]
            for qid, data in self._answers.items()
            if data.get("category") == "tech_stack"
        ]
        for answer in tech_answers:
            lines.append(f"- {answer}")
        lines.append("")

        # Constraints section
        lines.append("## Constraints")
        lines.append("")
        constraints = structured.get("constraints", {})
        if constraints:
            for key, value in constraints.items():
                if isinstance(value, list):
                    lines.append(f"- **{key.title()}**: {', '.join(value)}")
                else:
                    lines.append(f"- **{key.title()}**: {value}")
        else:
            constraint_answers = [
                data["text"]
                for qid, data in self._answers.items()
                if data.get("category") == "constraints"
            ]
            for answer in constraint_answers:
                lines.append(f"- {answer}")
        lines.append("")

        # Features section (extracted)
        lines.append("## Core Features")
        lines.append("")
        if features:
            for i, feature in enumerate(features, 1):
                lines.append(f"{i}. {feature}")
        else:
            feature_answers = [
                data["text"]
                for qid, data in self._answers.items()
                if data.get("category") == "features"
            ]
            for answer in feature_answers:
                lines.append(f"- {answer}")
        lines.append("")

        # Acceptance Criteria
        lines.append("## Acceptance Criteria")
        lines.append("")
        if features:
            for feature in features[:5]:
                lines.append(f"- [ ] {feature} is implemented and tested")
        else:
            lines.append("- [ ] All core features implemented")
            lines.append("- [ ] All constraints satisfied")
            lines.append("- [ ] User acceptance testing complete")
        lines.append("")

        return "\n".join(lines)

    def _save_session(self) -> None:
        """Save session state to database."""
        conn = get_db_connection(self.workspace)
        cursor = conn.cursor()

        now = _utc_now().isoformat()
        answers_json = json.dumps(self._answers)

        cursor.execute(
            """
            INSERT OR REPLACE INTO discovery_sessions
                (id, workspace_id, state, answers, blocker_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM discovery_sessions WHERE id = ?), ?),
                    ?)
            """,
            (
                self.session_id,
                self.workspace.id,
                self.state.value,
                answers_json,
                self._blocker_id,
                self.session_id,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()


def _ensure_discovery_schema(workspace: Workspace) -> None:
    """Ensure discovery_sessions table exists.

    Args:
        workspace: Workspace to update
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discovery_sessions (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'idle',
            answers TEXT DEFAULT '{}',
            blocker_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            FOREIGN KEY (blocker_id) REFERENCES blockers(id),
            CHECK (state IN ('idle', 'discovering', 'paused', 'completed'))
        )
    """)

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_discovery_sessions_workspace "
        "ON discovery_sessions(workspace_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_discovery_sessions_state "
        "ON discovery_sessions(state)"
    )

    conn.commit()
    conn.close()


def get_active_session(workspace: Workspace) -> Optional[PrdDiscoverySession]:
    """Get the most recent active (non-completed) discovery session.

    Args:
        workspace: Workspace to query

    Returns:
        PrdDiscoverySession if found, None otherwise
    """
    _ensure_discovery_schema(workspace)

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id FROM discovery_sessions
        WHERE workspace_id = ? AND state != 'completed'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (workspace.id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    session = PrdDiscoverySession(workspace)
    session.load_session(row[0])
    return session
