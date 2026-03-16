"""Tests for PRD stress test with recursive decomposition.

Tests the headless stress-test engine that powers `cf prd stress-test`.
All tests use mocked LLM responses to avoid actual API calls.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.workspace import Workspace, create_or_load_workspace
from codeframe.core import prd as prd_module


pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def sample_prd() -> str:
    """A minimal PRD for testing decomposition."""
    return """# Invoice SaaS

## Overview
A SaaS platform for creating and managing invoices.

## Core Features
1. User Authentication - users can register and log in
2. Invoice Management - CRUD operations for invoices
3. PDF Export - generate PDF invoices

## Technical Requirements
Python, FastAPI, PostgreSQL
"""


@pytest.fixture
def mock_provider():
    """Create a mock LLM provider with predictable responses."""
    mock = MagicMock()

    def complete_side_effect(
        messages, purpose=None, system=None, max_tokens=None, temperature=None
    ):
        content = messages[0]["content"] if messages else ""
        response = MagicMock()

        # Goal extraction
        if "high-level deliverable goals" in (system or "").lower():
            response.content = json.dumps([
                "User Authentication",
                "Invoice Management",
                "PDF Export",
            ])
        # Classification — route based on the Goal: line in the message
        elif "classify" in (system or "").lower():
            # Extract the goal title from "Goal: <title>" line
            goal_line = ""
            for line in content.splitlines():
                if line.startswith("Goal: "):
                    goal_line = line[6:].strip()
                    break

            if "Authentication" in goal_line:
                response.content = json.dumps({
                    "classification": "ambiguous",
                    "ambiguity_label": "AUTH SCOPE",
                    "questions": [
                        "Email/password or OAuth?",
                        "JWT or server sessions?",
                    ],
                    "recommendation": "Add Authentication Requirements section",
                    "complexity_hint": "Medium",
                })
            elif goal_line == "Invoice Management":
                response.content = json.dumps({
                    "classification": "composite",
                    "children": [
                        {"title": "Invoice CRUD", "description": "Create, read, update, delete invoices"},
                        {"title": "Invoice Status Machine", "description": "Draft/Sent/Paid transitions"},
                    ],
                    "complexity_hint": "Medium",
                })
            else:
                response.content = json.dumps({
                    "classification": "atomic",
                    "complexity_hint": "Low",
                })
        # Ambiguity resolution
        elif "update the prd" in (system or "").lower():
            response.content = "# Invoice SaaS (Updated)\n\n## Authentication\nEmail/password with JWT sessions."
        else:
            response.content = json.dumps({"classification": "atomic", "complexity_hint": "Low"})

        return response

    mock.complete.side_effect = complete_side_effect
    return mock


# --- Model Tests ---


class TestClassificationEnum:
    def test_classification_values(self):
        from codeframe.core.prd_stress_test import Classification

        assert Classification.ATOMIC == "atomic"
        assert Classification.COMPOSITE == "composite"
        assert Classification.AMBIGUOUS == "ambiguous"


class TestDecompositionNode:
    def test_create_leaf_node(self):
        from codeframe.core.prd_stress_test import DecompositionNode, Classification

        node = DecompositionNode(
            id="node-1",
            title="PDF Export",
            description="Generate PDF invoices",
            classification=Classification.ATOMIC,
            children=[],
            lineage=[],
            depth=0,
            complexity_hint="Low",
        )
        assert node.title == "PDF Export"
        assert node.classification == Classification.ATOMIC
        assert node.children == []

    def test_create_composite_node_with_children(self):
        from codeframe.core.prd_stress_test import DecompositionNode, Classification

        child = DecompositionNode(
            id="child-1", title="Sub", description="Sub task",
            classification=Classification.ATOMIC, children=[], lineage=["Parent"],
            depth=1, complexity_hint="Low",
        )
        parent = DecompositionNode(
            id="parent-1", title="Parent", description="Parent task",
            classification=Classification.COMPOSITE, children=[child], lineage=[],
            depth=0, complexity_hint="Medium",
        )
        assert len(parent.children) == 1
        assert parent.children[0].lineage == ["Parent"]


class TestAmbiguity:
    def test_create_ambiguity(self):
        from codeframe.core.prd_stress_test import Ambiguity

        amb = Ambiguity(
            id="amb-1",
            label="AUTH SCOPE",
            source_node_title="User Authentication",
            questions=["Email/password or OAuth?"],
            recommendation="Add auth section to PRD",
        )
        assert amb.label == "AUTH SCOPE"
        assert amb.resolved_answer is None

    def test_resolve_ambiguity(self):
        from codeframe.core.prd_stress_test import Ambiguity

        amb = Ambiguity(
            id="amb-1", label="AUTH SCOPE",
            source_node_title="User Authentication",
            questions=["Email/password or OAuth?"],
            recommendation="Add auth section",
        )
        amb.resolved_answer = "Email/password with JWT"
        assert amb.resolved_answer == "Email/password with JWT"


# --- Core Function Tests ---


class TestExtractGoals:
    def test_extracts_goals_from_prd(self, sample_prd, mock_provider):
        from codeframe.core.prd_stress_test import extract_goals

        goals = extract_goals(sample_prd, mock_provider)
        assert goals == ["User Authentication", "Invoice Management", "PDF Export"]
        mock_provider.complete.assert_called_once()

    def test_empty_prd_returns_empty(self, mock_provider):
        from codeframe.core.prd_stress_test import extract_goals

        mock_provider.complete.side_effect = None
        resp = MagicMock()
        resp.content = json.dumps([])
        mock_provider.complete.return_value = resp

        goals = extract_goals("", mock_provider)
        assert goals == []


class TestClassifyAndDecompose:
    def test_atomic_classification(self, mock_provider):
        from codeframe.core.prd_stress_test import classify_and_decompose, Classification

        cls, children, ambiguity, hint = classify_and_decompose(
            "PDF Export", "Generate PDF invoices", [], "prd content", 0, mock_provider,
        )
        assert cls == Classification.ATOMIC
        assert children == []
        assert ambiguity is None
        assert hint == "Low"

    def test_composite_classification(self, mock_provider):
        from codeframe.core.prd_stress_test import classify_and_decompose, Classification

        cls, children, ambiguity, hint = classify_and_decompose(
            "Invoice Management", "CRUD + status", [], "prd content", 0, mock_provider,
        )
        assert cls == Classification.COMPOSITE
        assert len(children) == 2
        assert children[0]["title"] == "Invoice CRUD"
        assert ambiguity is None

    def test_ambiguous_classification(self, mock_provider):
        from codeframe.core.prd_stress_test import classify_and_decompose, Classification

        cls, children, ambiguity, hint = classify_and_decompose(
            "User Authentication", "users can register and log in", [], "prd content", 0, mock_provider,
        )
        assert cls == Classification.AMBIGUOUS
        assert ambiguity is not None
        assert ambiguity.label == "AUTH SCOPE"
        assert len(ambiguity.questions) == 2


class TestRecursiveDecompose:
    def test_atomic_returns_leaf(self, mock_provider):
        from codeframe.core.prd_stress_test import recursive_decompose, Classification

        node = recursive_decompose(
            "PDF Export", "Generate PDF invoices", [], "prd", 0, 3, [], mock_provider,
        )
        assert node.classification == Classification.ATOMIC
        assert node.children == []

    def test_composite_recurses(self, mock_provider):
        from codeframe.core.prd_stress_test import recursive_decompose, Classification

        node = recursive_decompose(
            "Invoice Management", "CRUD + status", [], "prd", 0, 3, [], mock_provider,
        )
        assert node.classification == Classification.COMPOSITE
        assert len(node.children) == 2
        # Children should be atomic (leaf nodes)
        for child in node.children:
            assert child.classification == Classification.ATOMIC

    def test_ambiguous_collects_ambiguity(self, mock_provider):
        from codeframe.core.prd_stress_test import recursive_decompose

        ambiguities = []
        node = recursive_decompose(
            "User Authentication", "users register and log in",
            [], "prd", 0, 3, ambiguities, mock_provider,
        )
        assert len(ambiguities) == 1
        assert ambiguities[0].label == "AUTH SCOPE"

    def test_max_depth_forces_atomic(self, mock_provider):
        from codeframe.core.prd_stress_test import recursive_decompose, Classification

        # At depth == max_depth, should return atomic regardless
        node = recursive_decompose(
            "Something Composite", "desc", [], "prd", 3, 3, [], mock_provider,
        )
        assert node.classification == Classification.ATOMIC
        # Should NOT have called the provider (forced leaf)
        # The provider may have been called for other things, so just check the node


class TestRenderTechSpec:
    def test_renders_markdown(self, mock_provider):
        from codeframe.core.prd_stress_test import (
            DecompositionNode, Classification, render_tech_spec,
        )

        tree = [
            DecompositionNode(
                id="1", title="PDF Export", description="Generate PDFs",
                classification=Classification.ATOMIC, children=[], lineage=[],
                depth=0, complexity_hint="Low",
            ),
        ]
        spec = render_tech_spec(tree, [])
        assert "PDF Export" in spec
        assert "Low" in spec

    def test_ambiguous_node_shows_clarification(self, mock_provider):
        from codeframe.core.prd_stress_test import (
            DecompositionNode, Classification, Ambiguity, render_tech_spec,
        )

        amb = Ambiguity(
            id="amb-1", label="AUTH SCOPE",
            source_node_title="Auth", questions=["OAuth?"],
            recommendation="Add auth section",
        )
        tree = [
            DecompositionNode(
                id="1", title="Auth", description="Authentication",
                classification=Classification.AMBIGUOUS, children=[], lineage=[],
                depth=0, complexity_hint="Medium",
            ),
        ]
        spec = render_tech_spec(tree, [amb])
        assert "NEEDS CLARIFICATION" in spec


class TestRenderAmbiguityReport:
    def test_renders_numbered_report(self):
        from codeframe.core.prd_stress_test import Ambiguity, render_ambiguity_report

        ambiguities = [
            Ambiguity(
                id="amb-1", label="AUTH SCOPE",
                source_node_title="User Authentication",
                questions=["Email/password or OAuth?", "JWT or sessions?"],
                recommendation="Add auth section",
            ),
            Ambiguity(
                id="amb-2", label="DATA PERSISTENCE",
                source_node_title="Invoice Management",
                questions=["SQL or NoSQL?"],
                recommendation="Add data architecture section",
            ),
        ]
        report = render_ambiguity_report(ambiguities)
        assert "1." in report
        assert "2." in report
        assert "AUTH SCOPE" in report
        assert "DATA PERSISTENCE" in report
        assert "Email/password or OAuth?" in report


class TestStressTestPrd:
    def test_full_stress_test(self, sample_prd, mock_provider):
        from codeframe.core.prd_stress_test import stress_test_prd

        result = stress_test_prd(sample_prd, mock_provider, max_depth=3)

        assert len(result.tree) == 3  # 3 goals
        assert len(result.ambiguities) == 1  # Auth is ambiguous
        assert result.ambiguities[0].label == "AUTH SCOPE"
        assert "# Technical Specification" in result.tech_spec_markdown
        assert len(result.ambiguity_report) > 0

    def test_max_depth_respected(self, sample_prd, mock_provider):
        from codeframe.core.prd_stress_test import stress_test_prd

        result = stress_test_prd(sample_prd, mock_provider, max_depth=1)
        # With max_depth=1, composites should stop recursing at depth 1
        for node in result.tree:
            for child in node.children:
                assert child.children == []  # No grandchildren at depth 1


# --- CLI Tests ---


class TestStressTestCLI:
    def test_stress_test_command_exists(self):
        """The stress-test command should be registered on prd_app."""
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["prd", "stress-test", "--help"])
        assert result.exit_code == 0
        assert "stress-test" in result.output.lower() or "stress_test" in result.output.lower()

    def test_stress_test_no_prd_error(self, workspace, tmp_path):
        """Should error when no PRD exists."""
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["prd", "stress-test", "-w", str(tmp_path)])
        assert result.exit_code == 1

    @patch("codeframe.adapters.llm.anthropic.AnthropicProvider")
    def test_stress_test_with_prd(self, mock_provider_cls, workspace, sample_prd, mock_provider, tmp_path):
        """Should run stress test on existing PRD."""
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        # Store a PRD first
        prd_module.store(workspace, "Test PRD", sample_prd, {})

        mock_provider_cls.return_value = mock_provider

        runner = CliRunner()
        result = runner.invoke(app, ["prd", "stress-test", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "ambiguit" in result.output.lower() or "AUTH SCOPE" in result.output

    @patch("codeframe.adapters.llm.anthropic.AnthropicProvider")
    def test_stress_test_output_flag(self, mock_provider_cls, workspace, sample_prd, mock_provider, tmp_path):
        """--output should write tech spec to file."""
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        prd_module.store(workspace, "Test PRD", sample_prd, {})
        mock_provider_cls.return_value = mock_provider

        output_path = tmp_path / "spec.md"
        runner = CliRunner()
        result = runner.invoke(app, [
            "prd", "stress-test", "-w", str(tmp_path), "--output", str(output_path),
        ])
        assert result.exit_code == 0
        assert output_path.exists()
        content = output_path.read_text()
        assert "Technical Specification" in content
