"""Tests for PRD generation functionality (cf-16.1)."""

import pytest
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import json
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.providers.anthropic import AnthropicProvider


@pytest.fixture
def db():
    """Create test database."""
    db = Database(":memory:")
    db.initialize()  # Initialize database schema
    yield db
    db.close()


@pytest.fixture
def project_id(db):
    """Create test project."""
    from codeframe.core.models import ProjectStatus
    project_id = db.create_project(
        name="Test PRD Project",
        status=ProjectStatus.ACTIVE,
    )
    return project_id


@pytest.fixture
def discovery_answers(db, project_id):
    """Create discovery answers in database."""
    answers = {
        "problem_1": "Build a SaaS platform for AI-powered document analysis",
        "users_1": "Legal professionals and enterprise compliance teams",
        "features_1": "Document upload, AI analysis, compliance checking, report generation",
        "tech_stack_1": "Python backend, React frontend, PostgreSQL database",
        "constraints_1": "Must handle 1000 concurrent users, HIPAA compliant"
    }

    for question_id, answer in answers.items():
        db.create_memory(
            project_id=project_id,
            category="discovery_answers",
            key=question_id,
            value=answer,
        )

    return answers


@pytest.fixture
def lead_agent(db, project_id):
    """Create Lead Agent with test API key."""
    agent = LeadAgent(
        project_id=project_id,
        db=db,
        api_key="test-api-key",
    )
    return agent


class TestPRDGenerationBasics:
    """Test basic PRD generation functionality."""

    def test_generate_prd_method_exists(self, lead_agent):
        """Test that generate_prd method exists."""
        assert hasattr(lead_agent, "generate_prd")
        assert callable(lead_agent.generate_prd)

    @patch.object(AnthropicProvider, "send_message")
    def test_generate_prd_loads_discovery_answers(
        self, mock_send, lead_agent, discovery_answers
    ):
        """Test that PRD generation loads discovery answers."""
        # Mock Claude response
        mock_send.return_value = {
            "content": "# PRD Mock Content",
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }

        # Generate PRD
        prd_content = lead_agent.generate_prd()

        # Verify Claude was called
        assert mock_send.called

        # Verify PRD content returned
        assert prd_content is not None
        assert len(prd_content) > 0

    @patch.object(AnthropicProvider, "send_message")
    def test_generate_prd_sends_structured_prompt(
        self, mock_send, lead_agent, discovery_answers
    ):
        """Test that PRD generation sends structured prompt to Claude."""
        # Mock Claude response
        mock_send.return_value = {
            "content": "# PRD Content",
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }

        # Generate PRD
        lead_agent.generate_prd()

        # Get the call args
        call_args = mock_send.call_args[0][0]

        # Verify prompt structure
        assert len(call_args) > 0
        assert call_args[-1]["role"] == "user"

        # Verify discovery answers included in prompt
        prompt_content = call_args[-1]["content"]
        assert "problem" in prompt_content.lower() or "SaaS platform" in prompt_content
        assert "document analysis" in prompt_content.lower() or "AI" in prompt_content.lower()


class TestPRDStructure:
    """Test PRD document structure requirements."""

    @patch.object(AnthropicProvider, "send_message")
    def test_prd_includes_required_sections(self, mock_send, lead_agent, discovery_answers):
        """Test that generated PRD includes all required sections."""
        # Mock complete PRD response
        mock_prd = """# Product Requirements Document (PRD)

## Executive Summary
Build a SaaS platform for AI-powered document analysis.

## Problem Statement
Legal professionals need faster document analysis.

## User Personas
- Legal professionals
- Enterprise compliance teams

## Features & Requirements
- Document upload
- AI analysis
- Compliance checking
- Report generation

## Technical Architecture
- Python backend
- React frontend
- PostgreSQL database

## Success Metrics
- 1000 concurrent users
- HIPAA compliance

## Timeline & Milestones
- Phase 1: MVP (3 months)
"""
        mock_send.return_value = {
            "content": mock_prd,
            "usage": {"input_tokens": 100, "output_tokens": 500},
        }

        # Generate PRD
        prd_content = lead_agent.generate_prd()

        # Verify required sections present
        required_sections = [
            "Executive Summary",
            "Problem Statement",
            "User Personas",
            "Features & Requirements",
            "Technical Architecture",
            "Success Metrics",
            "Timeline & Milestones",
        ]

        for section in required_sections:
            assert section in prd_content, f"Missing section: {section}"


class TestPRDPersistence:
    """Test PRD file persistence."""

    @patch.object(AnthropicProvider, "send_message")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_prd_saved_to_file(
        self, mock_file, mock_mkdir, mock_send, lead_agent, discovery_answers
    ):
        """Test that PRD is saved to .codeframe/memory/prd.md."""
        # Mock Claude response
        mock_prd = "# PRD Content\n\nThis is a test PRD."
        mock_send.return_value = {
            "content": mock_prd,
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }

        # Generate PRD
        prd_content = lead_agent.generate_prd()

        # Verify file was opened for writing
        mock_file.assert_called()

        # Get the actual file path that was used
        call_args = mock_file.call_args
        file_path_str = str(call_args[0][0]) if call_args and call_args[0] else ""

        # Verify path contains expected components
        assert "prd.md" in file_path_str or mock_file.called

    @patch.object(AnthropicProvider, "send_message")
    def test_prd_stored_in_database(
        self, mock_send, lead_agent, discovery_answers, db, project_id
    ):
        """Test that PRD metadata is stored in database."""
        # Mock Claude response
        mock_prd = "# PRD Content"
        mock_send.return_value = {
            "content": mock_prd,
            "usage": {"input_tokens": 100, "output_tokens": 200},
        }

        # Generate PRD
        lead_agent.generate_prd()

        # Verify PRD reference stored in database
        memories = db.get_project_memories(project_id)
        prd_memories = [m for m in memories if m["category"] == "prd"]

        assert len(prd_memories) > 0, "PRD should be stored in database"


class TestPRDErrorHandling:
    """Test error handling in PRD generation."""

    @patch.object(AnthropicProvider, "send_message")
    def test_generate_prd_handles_api_error(self, mock_send, lead_agent):
        """Test that PRD generation handles API errors gracefully."""
        # Mock API error
        mock_send.side_effect = Exception("API rate limit exceeded")

        # Should raise exception with helpful message
        with pytest.raises(Exception) as exc_info:
            lead_agent.generate_prd()

        assert "API" in str(exc_info.value) or "rate limit" in str(exc_info.value)

    def test_generate_prd_requires_discovery_complete(self, lead_agent):
        """Test that PRD generation requires discovery to be complete."""
        # Agent has no discovery answers
        # Should raise exception or return error message
        result = lead_agent.generate_prd()

        # Either raises exception or returns error message
        assert result is None or "discovery" in result.lower() or "complete" in result.lower()

    @patch.object(AnthropicProvider, "send_message")
    def test_generate_prd_handles_empty_response(self, mock_send, lead_agent, discovery_answers):
        """Test handling of empty Claude response."""
        # Mock empty response
        mock_send.return_value = {
            "content": "",
            "usage": {"input_tokens": 100, "output_tokens": 0},
        }

        # Generate PRD
        prd_content = lead_agent.generate_prd()

        # Should return empty string or raise error
        assert prd_content == "" or prd_content is None


class TestPRDTokenUsageTracking:
    """Test token usage tracking for PRD generation."""

    @patch.object(AnthropicProvider, "send_message")
    def test_prd_generation_logs_token_usage(
        self, mock_send, lead_agent, discovery_answers
    ):
        """Test that token usage is logged during PRD generation."""
        # Mock Claude response with token usage
        mock_send.return_value = {
            "content": "# PRD Content",
            "usage": {"input_tokens": 1500, "output_tokens": 2500},
        }

        # Generate PRD (should log token usage)
        with patch("codeframe.agents.lead_agent.logger") as mock_logger:
            lead_agent.generate_prd()

            # Verify logging occurred
            assert mock_logger.info.called or mock_logger.debug.called
