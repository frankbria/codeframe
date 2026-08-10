"""#1115 — `cf tasks generate` emitted PRD prose verbatim instead of tasks.

The cold-start transcript names the mechanism exactly:

    LLM generation failed (Expecting ',' delimiter: line 179 column 6 (char 6820)),
    using simple extraction

`max_tokens=2000` truncated the JSON array mid-array, the parse blew up, and the
LLM path fell back to a markdown bullet splitter — silently, still exiting 0 with
a green "Generated 20 tasks". So the user got persona traits and `**Requirement:**`
fragments as "tasks", and every downstream stage operated on non-tasks.

Three things are pinned here: the fallback is no longer silent, titles are never
raw markdown, and the budget is big enough for a real task list.
"""

import json
from unittest.mock import MagicMock

import pytest

from codeframe.core import prd, tasks, workspace
from codeframe.core.tasks import (
    TaskGenerationError,
    _clean_task_title,
    _extract_tasks_simple,
    _generate_tasks_with_llm,
)

pytestmark = pytest.mark.v2


# The PRD from the cold-start report, trimmed to the sections that produced the
# bogus tasks: problem statement, persona traits, user goals, requirement bullets.
FIXTURE_PRD = """# Self-Hosted Todo Management REST API

## Executive Summary

A lightweight, self-hosted REST API for managing personal todos.

## Problem Statement

**Key Pain Points:**
- Todos scattered across different notes and systems make it difficult to maintain a complete view
- Existing SaaS tools add unwanted subscriptions and external dependencies
- No simple, self-hostable solution that developers can deploy and control themselves
- Lack of focus when completed items clutter active task lists

## Target Users

**Primary Persona: The Self-Hosting Developer**
- Comfortable with REST APIs and command-line tools
- Prefers self-hosted solutions over SaaS subscriptions
- Works on multiple projects simultaneously
- Values simplicity and performance over feature bloat

**User Goals:**
- Centralize task management in a single, reliable system
- Maintain control over data and hosting infrastructure

**Assumptions:**
- Has access to a laptop or small VPS for hosting
- Comfortable deploying Python applications

## Requirements

### Create Todo
- **Requirement:** Fast, lightweight endpoint to create new todos
- **Fields:** Description (required), priority (optional), created timestamp
- **Performance:** Sub-50ms response time for single todo creation
- **Validation:** Description must be non-empty, max 500 characters
"""


def _workspace_with_prd(tmp_path):
    """A real workspace holding FIXTURE_PRD — no mocking below the LLM boundary."""
    ws = workspace.create_or_load_workspace(tmp_path)
    return ws, prd.store(ws, FIXTURE_PRD, title="Self-Hosted Todo Management REST API")


def _provider_returning(payload: str) -> MagicMock:
    provider = MagicMock()
    provider.complete.return_value = MagicMock(content=payload)
    return provider


class TestTitlesAreNeverRawMarkdown:
    """AC: no task title contains raw markdown markers (`**`, leading `-`, `#`)."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("**Requirement:** Fast, lightweight endpoint", "Fast, lightweight endpoint"),
            ("**Fields:** Description (required)", "Description (required)"),
            ("- Implement POST /todos", "Implement POST /todos"),
            ("## Create the Todo model", "Create the Todo model"),
            ("*Add pytest fixtures*", "Add pytest fixtures"),
            ("`cf init` wiring", "cf init wiring"),
            ("Implement POST /todos", "Implement POST /todos"),
        ],
    )
    def test_markdown_is_stripped(self, raw, expected):
        assert _clean_task_title(raw) == expected

    def test_non_work_sections_never_become_tasks(self):
        """AC: persona traits, user goals and problem statements are never tasks.

        This holds on the --no-llm path too, because the new error message
        actively points users there — it must not hand back PRD prose.
        """
        titles = [t["title"] for t in _extract_tasks_simple(FIXTURE_PRD)]
        for prose in (
            "Todos scattered across different notes",  # pain point
            "Comfortable with REST APIs and command-line tools",  # persona trait
            "Centralize task management in a single, reliable system",  # user goal
            "Has access to a laptop or small VPS for hosting",  # assumption
        ):
            assert not any(prose in t for t in titles), f"{prose!r} is not a task"

        # ...while the actual requirements survive.
        assert any("endpoint to create new todos" in t for t in titles)

    def test_the_simple_extractor_emits_no_markdown_markers(self):
        for task in _extract_tasks_simple(FIXTURE_PRD):
            assert "**" not in task["title"]
            assert not task["title"].startswith(("-", "#", "*"))

    def test_llm_titles_are_cleaned_too(self):
        payload = json.dumps([{"title": "**Requirement:** Build the API", "description": "x"}])
        result = _generate_tasks_with_llm(FIXTURE_PRD, provider=_provider_returning(payload))
        assert result[0]["title"] == "Build the API"


class TestTheFallbackIsLoud:
    """AC: if the LLM path silently falls back to a text splitter, that must be loud.

    It is now not a fallback at all. Silently emitting 20 unimplementable items
    that exit 0 is worse than an error — one of them consumed a whole agent run.
    `--no-llm` remains the explicit way to ask for bullet extraction.
    """

    def test_truncated_json_raises_instead_of_degrading(self):
        # Exactly the 0.9.x failure: a JSON array cut off mid-object.
        truncated = '[{"title": "Define the Todo model", "description": "x"}, {"title": "Imple'
        with pytest.raises(TaskGenerationError) as exc:
            _generate_tasks_with_llm(FIXTURE_PRD, provider=_provider_returning(truncated))
        assert "truncated" in str(exc.value).lower()

    def test_the_error_tells_the_user_what_to_do(self):
        with pytest.raises(TaskGenerationError) as exc:
            _generate_tasks_with_llm(FIXTURE_PRD, provider=_provider_returning("not json"))
        assert "--no-llm" in str(exc.value)

    def test_generate_from_prd_does_not_swallow_it(self, tmp_path):
        ws, record = _workspace_with_prd(tmp_path)
        with pytest.raises(TaskGenerationError):
            tasks.generate_from_prd(
                ws, record, use_llm=True, provider=_provider_returning("garbage")
            )

    def test_no_llm_still_uses_the_extractor_without_raising(self, tmp_path):
        ws, record = _workspace_with_prd(tmp_path)
        created = tasks.generate_from_prd(ws, record, use_llm=False)
        assert created, "--no-llm is an explicit opt-in and must keep working"


class TestTheBudgetFitsARealTaskList:
    """The truncation was a budget bug, not a model bug."""

    def test_max_tokens_is_large_enough_for_a_full_array(self):
        provider = _provider_returning(json.dumps([{"title": "Define the Todo model"}]))
        _generate_tasks_with_llm(FIXTURE_PRD, provider=provider)
        max_tokens = provider.complete.call_args.kwargs["max_tokens"]
        # The real run truncated at ~6820 chars (~1900 tokens) partway through
        # a 20-task array. Anything at or below that repeats the bug.
        assert max_tokens >= 8000


class TestThePromptAsksForTasks:
    """AC: persona traits, user goals and problem statements must never become tasks."""

    def _prompt(self) -> str:
        provider = _provider_returning(json.dumps([{"title": "Define the Todo model"}]))
        _generate_tasks_with_llm(FIXTURE_PRD, provider=provider)
        return provider.complete.call_args.kwargs["messages"][0]["content"].lower()

    def test_it_excludes_the_prd_sections_that_are_not_work(self):
        prompt = self._prompt()
        for term in ("persona", "user goal", "problem statement"):
            assert term in prompt, f"prompt must tell the model to skip {term}s"

    def test_it_demands_verb_first_concrete_titles(self):
        prompt = self._prompt()
        assert "verb" in prompt
        assert "depends_on_titles" in prompt


class TestDependenciesArePopulated:
    """AC: dependencies are populated for a PRD with obvious ordering."""

    def test_title_dependencies_resolve_to_ids(self, tmp_path):
        payload = json.dumps([
            {"title": "Define the Todo SQLAlchemy model", "depends_on_titles": []},
            {
                "title": "Implement the todo CRUD layer",
                "depends_on_titles": ["Define the Todo SQLAlchemy model"],
            },
            {
                "title": "Implement POST /todos",
                "depends_on_titles": ["Implement the todo CRUD layer"],
            },
        ])
        ws, record = _workspace_with_prd(tmp_path)
        created = tasks.generate_from_prd(
            ws, record, use_llm=True, provider=_provider_returning(payload)
        )

        by_title = {t.title: t for t in created}
        model = by_title["Define the Todo SQLAlchemy model"]
        crud = by_title["Implement the todo CRUD layer"]
        endpoint = by_title["Implement POST /todos"]

        assert model.depends_on == []
        assert crud.depends_on == [model.id]
        assert endpoint.depends_on == [crud.id]

    def test_dependency_titles_are_matched_after_cleaning(self, tmp_path):
        """A model that echoes a markdown-y title in depends_on_titles must still link."""
        payload = json.dumps([
            {"title": "**Define the Todo model**", "depends_on_titles": []},
            {"title": "Implement POST /todos", "depends_on_titles": ["**Define the Todo model**"]},
        ])
        ws, record = _workspace_with_prd(tmp_path)
        created = tasks.generate_from_prd(
            ws, record, use_llm=True, provider=_provider_returning(payload)
        )
        model, endpoint = created
        assert model.title == "Define the Todo model"
        assert endpoint.depends_on == [model.id]


class TestTaskShapeOnTheFixturePrd:
    """AC: a test asserts task-shape — no `**` in titles, every title starts with a verb."""

    # A plausible decomposition of FIXTURE_PRD, as the fixed prompt should yield.
    REALISTIC = [
        {"title": "Define the Todo SQLAlchemy model", "depends_on_titles": []},
        {"title": "Create the SQLite database session module", "depends_on_titles": []},
        {
            "title": "Implement the todo CRUD layer",
            "depends_on_titles": ["Define the Todo SQLAlchemy model"],
        },
        {
            "title": "Implement POST /todos with validation",
            "depends_on_titles": ["Implement the todo CRUD layer"],
        },
        {
            "title": "Add pytest fixtures for the test database",
            "depends_on_titles": ["Create the SQLite database session module"],
        },
    ]

    def test_generated_tasks_have_task_shape(self, tmp_path):
        ws, record = _workspace_with_prd(tmp_path)
        created = tasks.generate_from_prd(
            ws, record, use_llm=True, provider=_provider_returning(json.dumps(self.REALISTIC))
        )

        assert len(created) == len(self.REALISTIC)
        for task in created:
            assert "**" not in task.title
            assert not task.title.startswith(("-", "#", "*"))
            first_word = task.title.split()[0].lower()
            assert first_word in {
                "define", "create", "implement", "add", "build", "write",
                "configure", "set", "wire", "expose", "validate",
            }, f"{task.title!r} does not start with a verb"

        assert any(t.depends_on for t in created), "ordering must produce dependencies"
