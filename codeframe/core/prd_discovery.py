"""PRD Discovery Session management for CodeFRAME v2.

This module provides AI-native Socratic discovery for PRD generation.
The AI drives the entire discovery process - generating context-sensitive
questions, validating answer adequacy, and determining when sufficient
information has been gathered.

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

from codeframe.adapters.llm.anthropic import AnthropicProvider
from codeframe.adapters.llm.base import Purpose
from codeframe.core import blockers, prd
from codeframe.core.workspace import Workspace, get_db_connection

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class DiscoveryError(Exception):
    """Base exception for discovery errors."""

    pass


class NoApiKeyError(DiscoveryError):
    """Raised when no API key is available for AI-driven discovery."""

    pass


class ValidationError(DiscoveryError):
    """Raised when answer validation fails."""

    pass


class IncompleteSessionError(DiscoveryError):
    """Raised when trying to generate PRD from incomplete session."""

    pass


class SessionState(str, Enum):
    """State of a discovery session."""

    IDLE = "idle"
    DISCOVERING = "discovering"
    PAUSED = "paused"
    COMPLETED = "completed"


# Categories that should be covered for a complete PRD
DISCOVERY_CATEGORIES = [
    "problem",      # What problem does this solve?
    "users",        # Who are the target users?
    "features",     # What are the core capabilities?
    "constraints",  # What limitations exist?
    "tech_stack",   # What technologies are preferred?
]

# System prompt for the discovery AI
DISCOVERY_SYSTEM_PROMPT = """You are an expert product manager conducting Socratic discovery to gather requirements for a software project. Your goal is to ask thoughtful, context-sensitive questions that help clarify the project vision.

## Your Role
- Ask ONE clear, specific question at a time
- Build on previous answers to go deeper
- Be conversational but professional
- Focus on understanding the "why" behind requirements

## Categories to Cover
You need to gather enough information in these areas:
1. **Problem**: What problem does this solve? Why does it matter? Who feels the pain?
2. **Users**: Who are the target users? What are their roles and needs?
3. **Features**: What are the core capabilities? What's the MVP vs nice-to-have?
4. **Constraints**: Technical limitations? Timeline? Budget? Compliance requirements?
5. **Tech Stack**: Preferred technologies? Existing systems to integrate with?

## Scoring Guidelines
For each category, mentally score completeness from 0-100:
- 0-30: Not mentioned or too vague
- 30-60: Basic understanding but missing details
- 60-80: Good understanding, minor gaps
- 80-100: Clear, specific, actionable

## When to Stop
Stop asking questions when:
- All categories score 60+ AND total average is 70+
- OR user has provided enough for a focused MVP PRD
- OR diminishing returns (user is repeating themselves)

Apply a "question tax" - only ask if the answer will meaningfully improve the PRD.
Don't ask about edge cases, future phases, or nice-to-haves unless core is unclear."""

QUESTION_GENERATION_PROMPT = """Based on the conversation so far, generate the next discovery question.

## Previous Q&A
{qa_history}

## Current Coverage Assessment
{coverage_assessment}

## Instructions
1. Identify the biggest gap in understanding
2. Generate ONE focused question that addresses that gap
3. Make it specific to what the user has already shared
4. Don't repeat questions already asked

If you believe we have enough information (all categories adequately covered), respond with:
DISCOVERY_COMPLETE

Otherwise, respond with just the question text, nothing else."""

ANSWER_VALIDATION_PROMPT = """Evaluate whether this answer adequately addresses the question.

Question: {question}
Answer: {answer}

## Evaluation Criteria
1. **Relevance**: Does it actually answer what was asked?
2. **Specificity**: Is it concrete enough to act on?
3. **Completeness**: Does it fully address the question or leave major gaps?

## Response Format
Respond with a JSON object:
{{
    "adequate": true/false,
    "reason": "brief explanation",
    "follow_up": "optional follow-up question if answer is inadequate but not rejectable"
}}

Be lenient - accept answers that provide useful information even if not perfect.
Only mark inadequate if the answer is truly unhelpful (off-topic, too vague to use, or dismissive)."""

COVERAGE_ASSESSMENT_PROMPT = """Assess the current coverage of discovery categories based on the conversation.

## Conversation History
{qa_history}

## Categories to Assess
1. problem - Understanding of the problem being solved
2. users - Knowledge of target users and their needs
3. features - Clarity on core capabilities needed
4. constraints - Awareness of limitations and requirements
5. tech_stack - Understanding of technology preferences

## Response Format
Respond with a JSON object:
{{
    "scores": {{
        "problem": 0-100,
        "users": 0-100,
        "features": 0-100,
        "constraints": 0-100,
        "tech_stack": 0-100
    }},
    "average": 0-100,
    "weakest_category": "category_name",
    "ready_for_prd": true/false,
    "reasoning": "brief explanation of readiness assessment"
}}"""

PRD_GENERATION_PROMPT = """Generate a Product Requirements Document based on the discovery conversation.

## Discovery Conversation
{qa_history}

## PRD Format
Generate a markdown PRD with these sections:

# [Project Title - infer from conversation]

## Overview
A clear problem statement and vision (2-3 sentences).

## Target Users
Who will use this and what are their key needs.

## Core Features
Numbered list of MVP features with brief descriptions.

## Technical Requirements
Technology stack, integrations, and technical constraints.

## Constraints & Considerations
Timeline, budget, compliance, or other limitations.

## Success Criteria
How we'll know if this project succeeds (measurable where possible).

## Out of Scope (MVP)
What we're explicitly NOT building in the first version.

---

Keep it concise but complete. Focus on actionable requirements.
This PRD should be sufficient to generate development tasks."""


@dataclass
class PrdDiscoverySession:
    """Manages an AI-driven PRD discovery session.

    The AI drives the entire discovery process:
    - Generates context-sensitive questions based on conversation history
    - Validates answer adequacy (not just length/pattern)
    - Determines when sufficient information has been gathered
    - Generates the final PRD

    Attributes:
        workspace: The workspace this session belongs to
        api_key: API key for LLM provider (required)
        session_id: Unique session identifier
        state: Current session state
    """

    workspace: Workspace
    api_key: Optional[str] = None
    session_id: Optional[str] = field(default=None, init=False)
    state: SessionState = field(default=SessionState.IDLE, init=False)
    _llm_provider: Any = field(default=None, init=False)
    _qa_history: list[dict[str, str]] = field(default_factory=list, init=False)
    _current_question: Optional[str] = field(default=None, init=False)
    _coverage: Optional[dict[str, Any]] = field(default=None, init=False)
    _blocker_id: Optional[str] = field(default=None, init=False)
    _is_complete: bool = field(default=False, init=False)

    def __post_init__(self):
        """Initialize the LLM provider."""
        key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise NoApiKeyError(
                "ANTHROPIC_API_KEY is required for AI-driven discovery. "
                "Set the environment variable or pass api_key parameter."
            )

        self._llm_provider = AnthropicProvider(api_key=key)

    @property
    def answered_count(self) -> int:
        """Number of questions answered."""
        return len(self._qa_history)

    def start_discovery(self) -> None:
        """Start a new discovery session.

        Creates a session record and generates the first question.
        """
        self.session_id = str(uuid.uuid4())
        self.state = SessionState.DISCOVERING
        self._qa_history = []
        self._is_complete = False

        # Ensure schema exists and save initial session
        _ensure_discovery_schema(self.workspace)
        self._save_session()

        # Generate first question and persist it
        self._current_question = self._generate_opening_question()
        self._save_session()

        logger.info(f"Started discovery session {self.session_id}")

    def _generate_opening_question(self) -> str:
        """Generate the opening question for discovery."""

        prompt = """You're starting a new product discovery session.
Generate an opening question that invites the user to describe their project idea.
Be warm and encouraging. Just output the question, nothing else."""

        response = self._llm_provider.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.GENERATION,
            system=DISCOVERY_SYSTEM_PROMPT,
            max_tokens=200,
            temperature=0.7,
        )
        return response.content.strip()

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
            SELECT id, state, qa_history, current_question, coverage, blocker_id, is_complete
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
        self._qa_history = json.loads(row[2]) if row[2] else []
        self._current_question = row[3]
        self._coverage = json.loads(row[4]) if row[4] else None
        self._blocker_id = row[5]
        self._is_complete = bool(row[6]) if row[6] is not None else False

        logger.info(f"Loaded session {session_id} with {len(self._qa_history)} Q&A pairs")

    def get_current_question(self) -> Optional[dict[str, Any]]:
        """Get the current question to display.

        Returns:
            Question dict with 'text' and 'question_number', or None if complete
        """
        if self._is_complete:
            return None

        if self._current_question:
            return {
                "text": self._current_question,
                "question_number": len(self._qa_history) + 1,
            }

        return None

    def submit_answer(self, answer_text: str) -> dict[str, Any]:
        """Submit an answer and get validation result.

        The AI validates the answer for adequacy. If adequate, generates
        the next question (or marks discovery complete).

        Args:
            answer_text: User's answer

        Returns:
            Dict with 'accepted', 'feedback', and optionally 'follow_up'

        Raises:
            ValidationError: If answer is empty
        """
        answer_text = answer_text.strip()

        if not answer_text:
            raise ValidationError("Please provide an answer.")

        # Validate with AI
        validation = self._validate_answer(self._current_question, answer_text)

        if not validation["adequate"]:
            # Answer not adequate - provide feedback
            if validation.get("follow_up"):
                # Replace current question with follow-up
                self._current_question = validation["follow_up"]
                self._save_session()
                return {
                    "accepted": False,
                    "feedback": validation["reason"],
                    "follow_up": validation["follow_up"],
                }
            else:
                return {
                    "accepted": False,
                    "feedback": validation["reason"],
                }

        # Answer accepted - store it
        self._qa_history.append({
            "question": self._current_question,
            "answer": answer_text,
            "timestamp": _utc_now().isoformat(),
        })

        # Check coverage and generate next question
        self._update_coverage()
        next_question = self._generate_next_question()

        # Complete when AI signals done OR coverage assessment says ready
        if next_question == "DISCOVERY_COMPLETE" or self._coverage_is_sufficient():
            self._is_complete = True
            self._current_question = None
        else:
            self._current_question = next_question

        self._save_session()

        return {
            "accepted": True,
            "feedback": "Answer recorded.",
            "coverage": self._coverage,
        }

    def _validate_answer(self, question: str, answer: str) -> dict[str, Any]:
        """Use AI to validate if answer adequately addresses the question."""

        prompt = ANSWER_VALIDATION_PROMPT.format(
            question=question,
            answer=answer,
        )

        response = self._llm_provider.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.GENERATION,
            max_tokens=300,
            temperature=0.3,
        )

        try:
            # Parse JSON response
            content = response.content.strip()
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except json.JSONDecodeError:
            # If AI doesn't return valid JSON, be lenient and accept
            logger.warning(f"Could not parse validation response: {response.content}")
            return {"adequate": True, "reason": "Accepted"}

    def _update_coverage(self) -> None:
        """Update the coverage assessment based on conversation history."""

        qa_history = self._format_qa_history()

        prompt = COVERAGE_ASSESSMENT_PROMPT.format(qa_history=qa_history)

        response = self._llm_provider.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.GENERATION,
            max_tokens=500,
            temperature=0.3,
        )

        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            self._coverage = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse coverage response: {response.content}")
            self._coverage = None

    def _coverage_is_sufficient(self) -> bool:
        """Check if coverage is sufficient to generate PRD.

        Relies on AI assessment - if a comprehensive answer covers all
        categories (e.g., pasting a full PRD), discovery can complete quickly.
        """
        if not self._coverage:
            return False
        return self._coverage.get("ready_for_prd", False)

    def _generate_next_question(self) -> str:
        """Generate the next discovery question based on context."""

        qa_history = self._format_qa_history()
        coverage_str = json.dumps(self._coverage, indent=2) if self._coverage else "Not yet assessed"

        prompt = QUESTION_GENERATION_PROMPT.format(
            qa_history=qa_history,
            coverage_assessment=coverage_str,
        )

        response = self._llm_provider.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.GENERATION,
            system=DISCOVERY_SYSTEM_PROMPT,
            max_tokens=300,
            temperature=0.7,
        )

        return response.content.strip()

    def _format_qa_history(self) -> str:
        """Format Q&A history for prompts."""
        if not self._qa_history:
            return "(No questions answered yet)"

        lines = []
        for i, qa in enumerate(self._qa_history, 1):
            lines.append(f"Q{i}: {qa['question']}")
            lines.append(f"A{i}: {qa['answer']}")
            lines.append("")
        return "\n".join(lines)

    def is_complete(self) -> bool:
        """Check if discovery is complete.

        Returns:
            True if AI has determined sufficient information gathered
        """
        return self._is_complete

    def get_progress(self) -> dict[str, Any]:
        """Get discovery progress statistics.

        Returns:
            Dict with coverage scores and completion status
        """
        return {
            "answered": len(self._qa_history),
            "coverage": self._coverage or {},
            "is_complete": self._is_complete,
            "percentage": self._coverage.get("average", 0) if self._coverage else 0,
        }

    def pause_discovery(self, reason: str) -> str:
        """Pause the discovery session.

        Creates a blocker for later resume.

        Args:
            reason: Reason for pausing

        Returns:
            Blocker ID for resume
        """
        self.state = SessionState.PAUSED

        question = (
            f"Discovery session paused: {reason}\n"
            f"Session ID: {self.session_id}\n"
            f"Progress: {len(self._qa_history)} questions answered"
        )

        blocker = blockers.create(
            self.workspace, question=question, task_id=None
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
        """Generate PRD from discovery conversation.

        Uses AI to synthesize the conversation into a structured PRD.

        Returns:
            Created PrdRecord

        Raises:
            IncompleteSessionError: If discovery not complete
        """
        if not self._is_complete and not self._coverage_is_sufficient():
            raise IncompleteSessionError(
                "Cannot generate PRD: discovery not complete. "
                f"Current coverage: {self._coverage}"
            )


        qa_history = self._format_qa_history()

        prompt = PRD_GENERATION_PROMPT.format(qa_history=qa_history)

        response = self._llm_provider.complete(
            messages=[{"role": "user", "content": prompt}],
            purpose=Purpose.PLANNING,  # Use stronger model for PRD generation
            max_tokens=4000,
            temperature=0.5,
        )

        content = response.content.strip()

        # Extract title from PRD content
        title = self._extract_title_from_prd(content)

        # Store PRD
        record = prd.store(
            self.workspace,
            content=content,
            title=title,
            metadata={
                "source": "ai_discovery",
                "session_id": self.session_id,
                "questions_asked": len(self._qa_history),
                "coverage": self._coverage,
                "generated_at": _utc_now().isoformat(),
            },
        )

        # Update session state
        self.state = SessionState.COMPLETED
        self._save_session()

        logger.info(f"Generated PRD {record.id} from session {self.session_id}")
        return record

    def _extract_title_from_prd(self, content: str) -> str:
        """Extract project title from generated PRD content."""
        import re

        # Try to find H1 heading
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Remove any trailing punctuation or brackets
            title = re.sub(r"[\[\]()]", "", title).strip()
            return title[:100]  # Limit length

        return "Untitled Project"

    def _save_session(self) -> None:
        """Save session state to database."""
        conn = get_db_connection(self.workspace)
        cursor = conn.cursor()

        now = _utc_now().isoformat()
        qa_history_json = json.dumps(self._qa_history)
        coverage_json = json.dumps(self._coverage) if self._coverage else None

        cursor.execute(
            """
            INSERT OR REPLACE INTO discovery_sessions
                (id, workspace_id, state, qa_history, current_question,
                 coverage, blocker_id, is_complete, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM discovery_sessions WHERE id = ?), ?),
                    ?)
            """,
            (
                self.session_id,
                self.workspace.id,
                self.state.value,
                qa_history_json,
                self._current_question,
                coverage_json,
                self._blocker_id,
                1 if self._is_complete else 0,
                self.session_id,
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()


def _ensure_discovery_schema(workspace: Workspace) -> None:
    """Ensure discovery_sessions table exists with updated schema.

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
            qa_history TEXT DEFAULT '[]',
            current_question TEXT,
            coverage TEXT,
            blocker_id TEXT,
            is_complete INTEGER DEFAULT 0,
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
        PrdDiscoverySession if found, None if no active session exists

    Raises:
        NoApiKeyError: If session exists but ANTHROPIC_API_KEY is not set
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

    # Need API key to load session
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning(
            "Cannot load discovery session %s: ANTHROPIC_API_KEY environment "
            "variable is not set. Set the API key to resume this session.",
            row[0],
        )
        raise NoApiKeyError(
            "ANTHROPIC_API_KEY is required to load discovery session. "
            "Set the environment variable to resume."
        )

    session = PrdDiscoverySession(workspace, api_key=api_key)
    session.load_session(row[0])
    return session
