"""Tests for the ralph-claude-code project importer (issue #615).

Covers parsing of ralph project files (.ralphrc, fix_plan.md, PROMPT.md,
AGENT.md, specs/), mapping rules (optional sections, idempotency keys),
and the end-to-end import into a real CodeFRAME workspace.
"""

import shutil
from pathlib import Path

import pytest

from codeframe.core import prd, tasks
from codeframe.core.agents_config import load_preferences
from codeframe.core.importers import ralph
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import workspace_exists

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "ralph_project"


@pytest.fixture
def ralph_project(tmp_path: Path) -> Path:
    """Copy of the ralph project fixture, safe to mutate."""
    dest = tmp_path / "ralph-project"
    shutil.copytree(FIXTURE, dest)
    return dest


# =============================================================================
# parse_ralphrc
# =============================================================================


class TestParseRalphrc:
    def test_parses_unquoted_value(self):
        config = ralph.parse_ralphrc(FIXTURE / ".ralphrc")
        assert config["MAX_CALLS_PER_HOUR"] == "100"
        assert config["SESSION_CONTINUITY"] == "true"

    def test_strips_quotes(self):
        config = ralph.parse_ralphrc(FIXTURE / ".ralphrc")
        assert config["CLAUDE_OUTPUT_FORMAT"] == "json"
        assert config["ALLOWED_TOOLS"].startswith("Write,Read,Edit,")
        assert '"' not in config["ALLOWED_TOOLS"]

    def test_resolves_shell_default_expansion(self):
        # PROJECT_NAME="${PROJECT_NAME:-todo-api}" resolves to the default
        # literal; the importer never reads the caller's environment.
        config = ralph.parse_ralphrc(FIXTURE / ".ralphrc")
        assert config["PROJECT_NAME"] == "todo-api"
        assert config["PROJECT_TYPE"] == "python"

    def test_skips_comments_and_blanks(self):
        config = ralph.parse_ralphrc(FIXTURE / ".ralphrc")
        assert all(not key.startswith("#") for key in config)

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert ralph.parse_ralphrc(tmp_path / "nope") == {}

    def test_unquoted_trailing_comment_stripped(self, tmp_path: Path):
        rc = tmp_path / ".ralphrc"
        rc.write_text("FOO=bar # a comment\n")
        assert ralph.parse_ralphrc(rc)["FOO"] == "bar"

    def test_plain_expansion_without_default_is_empty(self, tmp_path: Path):
        rc = tmp_path / ".ralphrc"
        rc.write_text('X="${UNDEFINED_VAR}"\n')
        assert ralph.parse_ralphrc(rc)["X"] == ""

    def test_non_assignment_lines_ignored(self, tmp_path: Path):
        rc = tmp_path / ".ralphrc"
        rc.write_text('if [ -f .env ]; then\n  source .env\nfi\nFOO="bar"\n')
        assert ralph.parse_ralphrc(rc) == {"FOO": "bar"}

    def test_value_with_equals_sign_preserved(self, tmp_path: Path):
        rc = tmp_path / ".ralphrc"
        rc.write_text('FILTER="status:open=true"\n')
        assert ralph.parse_ralphrc(rc)["FILTER"] == "status:open=true"


# =============================================================================
# parse_fix_plan
# =============================================================================


class TestParseFixPlan:
    def test_extracts_items_with_sections(self):
        items = ralph.parse_fix_plan(FIXTURE / ".ralph" / "fix_plan.md")
        unchecked = [i for i in items if not i.checked]
        assert len(unchecked) == 7
        first = unchecked[0]
        assert first.title == "Set up basic project structure and build system"
        assert first.section == "High Priority"

    def test_checked_items_flagged_not_dropped(self):
        items = ralph.parse_fix_plan(FIXTURE / ".ralph" / "fix_plan.md")
        checked = [i for i in items if i.checked]
        assert {i.title for i in checked} == {
            "Create test framework and initial tests",
            "Project initialization",
        }

    def test_non_checkbox_bullets_ignored(self):
        items = ralph.parse_fix_plan(FIXTURE / ".ralph" / "fix_plan.md")
        titles = {i.title for i in items}
        assert "Focus on MVP functionality first" not in titles

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert ralph.parse_fix_plan(tmp_path / "nope.md") == []

    def test_asterisk_checkboxes_and_uppercase_x(self, tmp_path: Path):
        plan = tmp_path / "fix_plan.md"
        plan.write_text("## Stuff\n* [ ] star task\n- [X] done task\n")
        items = ralph.parse_fix_plan(plan)
        assert [(i.title, i.checked) for i in items] == [
            ("star task", False),
            ("done task", True),
        ]


# =============================================================================
# PROMPT.md / specs / AGENT.md
# =============================================================================


class TestContentParsers:
    def test_parse_prompt_md(self):
        content = ralph.parse_prompt_md(FIXTURE / ".ralph" / "PROMPT.md")
        assert "todo-api" in content

    def test_parse_prompt_md_missing(self, tmp_path: Path):
        assert ralph.parse_prompt_md(tmp_path / "nope.md") is None

    def test_collect_specs_sorted_md_only(self):
        specs = ralph.collect_specs(FIXTURE / ".ralph" / "specs")
        assert [name for name, _ in specs] == ["api_spec.md", "data_model.md"]
        assert "GET /todos" in specs[0][1]

    def test_collect_specs_missing_dir(self, tmp_path: Path):
        assert ralph.collect_specs(tmp_path / "specs") == []

    def test_parse_agent_md(self):
        content = ralph.parse_agent_md(FIXTURE / ".ralph" / "AGENT.md")
        assert "pytest" in content


# =============================================================================
# load_ralph_project
# =============================================================================


class TestLoadRalphProject:
    def test_loads_fixture(self):
        project = ralph.load_ralph_project(FIXTURE)
        assert project.ralphrc["PROJECT_NAME"] == "todo-api"
        assert len(project.fix_plan_items) == 9
        assert project.prompt is not None
        assert project.agent_md is not None
        assert len(project.specs) == 2

    def test_state_files_reported_ignored_never_read(self):
        project = ralph.load_ralph_project(FIXTURE)
        assert "status.json" in project.state_files_ignored
        assert ".call_count" in project.state_files_ignored

    def test_missing_ralph_dir_raises(self, tmp_path: Path):
        with pytest.raises(ralph.RalphProjectNotFoundError):
            ralph.load_ralph_project(tmp_path)

    def test_requires_fix_plan_or_prompt(self, tmp_path: Path):
        (tmp_path / ".ralph").mkdir()
        (tmp_path / ".ralph" / "AGENT.md").write_text("# Agent")
        with pytest.raises(ralph.RalphProjectNotFoundError):
            ralph.load_ralph_project(tmp_path)

    def test_prompt_only_project_loads(self, tmp_path: Path):
        (tmp_path / ".ralph").mkdir()
        (tmp_path / ".ralph" / "PROMPT.md").write_text("# My project")
        project = ralph.load_ralph_project(tmp_path)
        assert project.prompt == "# My project"
        assert project.fix_plan_items == []


# =============================================================================
# map_tasks
# =============================================================================


def _make_project(tmp_path: Path, fix_plan: str, ralphrc: str = "") -> "ralph.RalphProject":
    (tmp_path / ".ralph").mkdir(exist_ok=True)
    (tmp_path / ".ralph" / "fix_plan.md").write_text(fix_plan)
    if ralphrc:
        (tmp_path / ".ralphrc").write_text(ralphrc)
    return ralph.load_ralph_project(tmp_path)


class TestMapTasks:
    def test_fixture_mapping_counts_and_statuses(self):
        project = ralph.load_ralph_project(FIXTURE)
        mapped, skipped = ralph.map_tasks(project)
        assert len(mapped) == 7
        statuses = [t["status"] for t in mapped]
        assert statuses.count(TaskStatus.READY) == 5
        assert statuses.count(TaskStatus.BACKLOG) == 2
        # Optional-section items land in BACKLOG
        backlog_titles = {t["title"] for t in mapped if t["status"] == TaskStatus.BACKLOG}
        assert backlog_titles == {
            "Nice-to-have enhancements (non-blocking)",
            "Integration with external services",
        }

    def test_checked_items_skipped_with_reason(self):
        project = ralph.load_ralph_project(FIXTURE)
        _, skipped = ralph.map_tasks(project)
        assert len(skipped) == 2
        assert all("completed" in s["reason"].lower() for s in skipped)

    def test_priority_preserves_file_order(self):
        project = ralph.load_ralph_project(FIXTURE)
        mapped, _ = ralph.map_tasks(project)
        assert [t["priority"] for t in mapped] == list(range(7))

    def test_custom_optional_sections_override_defaults(self, tmp_path: Path):
        project = _make_project(
            tmp_path,
            "## Someday\n- [ ] someday task\n\n## Optional\n- [ ] optional task\n",
            'OPTIONAL_SECTIONS="Someday"\n',
        )
        mapped, _ = ralph.map_tasks(project)
        by_title = {t["title"]: t["status"] for t in mapped}
        assert by_title["someday task"] == TaskStatus.BACKLOG
        # Custom config replaces the defaults entirely
        assert by_title["optional task"] == TaskStatus.READY

    def test_default_optional_sections(self, tmp_path: Path):
        project = _make_project(
            tmp_path,
            "## Core\n- [ ] core task\n\n## Nice to Have\n- [ ] nice task\n"
            "\n## Future Enhancements\n- [ ] future task\n",
        )
        mapped, _ = ralph.map_tasks(project)
        by_title = {t["title"]: t["status"] for t in mapped}
        assert by_title["core task"] == TaskStatus.READY
        assert by_title["nice task"] == TaskStatus.BACKLOG
        # "Future Enhancements" matches the "Future" default keyword
        assert by_title["future task"] == TaskStatus.BACKLOG

    def test_external_url_stable_when_other_tasks_inserted(self, tmp_path: Path):
        project_a = _make_project(
            tmp_path, "## Core\n- [ ] task alpha\n- [ ] task beta\n"
        )
        url_beta = {
            t["title"]: t["external_url"] for t in ralph.map_tasks(project_a)[0]
        }["task beta"]

        project_b = _make_project(
            tmp_path, "## Core\n- [ ] task alpha\n- [ ] brand new task\n- [ ] task beta\n"
        )
        url_beta_after = {
            t["title"]: t["external_url"] for t in ralph.map_tasks(project_b)[0]
        }["task beta"]
        assert url_beta == url_beta_after

    def test_duplicate_titles_get_distinct_urls(self, tmp_path: Path):
        project = _make_project(
            tmp_path, "## Core\n- [ ] repeated task\n- [ ] repeated task\n"
        )
        mapped, _ = ralph.map_tasks(project)
        urls = [t["external_url"] for t in mapped]
        assert len(urls) == len(set(urls)) == 2

    def test_external_url_uses_ralph_scheme(self):
        project = ralph.load_ralph_project(FIXTURE)
        mapped, _ = ralph.map_tasks(project)
        assert all(
            t["external_url"].startswith("ralph://fix_plan.md#") for t in mapped
        )


# =============================================================================
# map_prd_content / map_agent_preferences
# =============================================================================


class TestMapPrdContent:
    def test_combines_prompt_and_specs_with_attribution(self):
        project = ralph.load_ralph_project(FIXTURE)
        mapping = ralph.map_prd_content(project)
        assert mapping is not None
        assert "todo-api" in mapping["title"]
        assert ".ralph/PROMPT.md" in mapping["content"]
        assert ".ralph/specs/api_spec.md" in mapping["content"]
        assert "GET /todos" in mapping["content"]
        assert mapping["metadata"]["ralph_import"] is True
        assert "PROMPT.md" in mapping["metadata"]["sources"][0]

    def test_returns_none_without_prompt_or_specs(self, tmp_path: Path):
        project = _make_project(tmp_path, "## Core\n- [ ] only tasks here\n")
        assert ralph.map_prd_content(project) is None

    def test_specs_only_project_still_maps(self, tmp_path: Path):
        project = _make_project(tmp_path, "## Core\n- [ ] a task\n")
        specs_dir = tmp_path / ".ralph" / "specs"
        specs_dir.mkdir()
        (specs_dir / "spec.md").write_text("# Spec\nDetails here.")
        project = ralph.load_ralph_project(tmp_path)

        mapping = ralph.map_prd_content(project)
        assert mapping is not None
        assert ".ralph/specs/spec.md" in mapping["content"]
        assert mapping["metadata"]["sources"] == [".ralph/specs/spec.md"]


class TestMapAgentPreferences:
    def test_extracts_commands_and_allowed_tools(self):
        project = ralph.load_ralph_project(FIXTURE)
        mapping = ralph.map_agent_preferences(project)
        assert mapping is not None
        content = mapping["content"]
        assert "pip install -r requirements.txt" in content
        assert "pytest" in content
        assert "Bash(git add *)" in content

    def test_round_trips_through_load_preferences(self, tmp_path: Path):
        project = ralph.load_ralph_project(FIXTURE)
        mapping = ralph.map_agent_preferences(project)
        (tmp_path / "AGENTS.md").write_text(mapping["content"])
        prefs = load_preferences(tmp_path)
        assert prefs.commands["test"] == "pytest"
        assert prefs.commands["install"] == "pip install -r requirements.txt"
        assert prefs.commands["build"] == "python -m build"
        assert prefs.commands["dev"] == "uvicorn app.main:app --reload"
        assert any("Bash(git add *)" in item for item in prefs.always_do)

    def test_returns_none_without_agent_md_or_allowed_tools(self, tmp_path: Path):
        project = _make_project(tmp_path, "## Core\n- [ ] a task\n")
        assert ralph.map_agent_preferences(project) is None


# =============================================================================
# import_ralph_project (integration — real workspace, no mocks)
# =============================================================================


class TestImportRalphProject:
    def test_import_creates_working_cf_project(self, ralph_project: Path):
        report = ralph.import_ralph_project(ralph_project)

        assert workspace_exists(ralph_project)
        assert len(report.tasks_created) == 7
        assert report.prd_action == "created"
        assert report.agents_md_action == "written"
        assert "status.json" in report.state_files_ignored

        from codeframe.core.workspace import get_workspace

        ws = get_workspace(ralph_project)
        all_tasks = tasks.list_tasks(ws)
        assert len(all_tasks) == 7
        by_status = {}
        for t in all_tasks:
            by_status.setdefault(t.status, []).append(t)
        assert len(by_status[TaskStatus.READY]) == 5
        assert len(by_status[TaskStatus.BACKLOG]) == 2

        record = prd.get_latest(ws)
        assert record is not None
        assert record.metadata["ralph_import"] is True
        assert (ralph_project / "AGENTS.md").exists()

    def test_tasks_linked_to_imported_prd(self, ralph_project: Path):
        ralph.import_ralph_project(ralph_project)
        from codeframe.core.workspace import get_workspace

        ws = get_workspace(ralph_project)
        record = prd.get_latest(ws)
        assert all(t.prd_id == record.id for t in tasks.list_tasks(ws))

    def test_rerun_is_idempotent(self, ralph_project: Path):
        ralph.import_ralph_project(ralph_project)
        report = ralph.import_ralph_project(ralph_project)

        assert report.tasks_created == []
        assert len(report.tasks_skipped) == 9  # 7 already imported + 2 completed
        assert report.prd_action == "skipped_identical"
        assert report.agents_md_action == "skipped_exists"

        from codeframe.core.workspace import get_workspace

        ws = get_workspace(ralph_project)
        assert len(tasks.list_tasks(ws)) == 7
        assert prd.get_latest(ws).version == 1

    def test_duplicate_titles_idempotent_on_rerun(self, ralph_project: Path):
        fix_plan = ralph_project / ".ralph" / "fix_plan.md"
        fix_plan.write_text(
            "## Core\n- [ ] repeated task\n- [ ] repeated task\n"
        )
        first = ralph.import_ralph_project(ralph_project)
        assert len(first.tasks_created) == 2
        second = ralph.import_ralph_project(ralph_project)
        assert second.tasks_created == []

        from codeframe.core.workspace import get_workspace

        assert len(tasks.list_tasks(get_workspace(ralph_project))) == 2

    def test_rerun_after_fix_plan_edit_imports_only_new(self, ralph_project: Path):
        ralph.import_ralph_project(ralph_project)
        fix_plan = ralph_project / ".ralph" / "fix_plan.md"
        fix_plan.write_text(
            fix_plan.read_text() + "\n## High Priority Extras\n- [ ] fresh task\n"
        )
        report = ralph.import_ralph_project(ralph_project)
        assert [t["title"] for t in report.tasks_created] == ["fresh task"]

    def test_prd_new_version_when_sources_change(self, ralph_project: Path):
        ralph.import_ralph_project(ralph_project)
        prompt = ralph_project / ".ralph" / "PROMPT.md"
        prompt.write_text(prompt.read_text() + "\n## New Section\nMore detail.\n")
        report = ralph.import_ralph_project(ralph_project)

        assert report.prd_action == "new_version"
        from codeframe.core.workspace import get_workspace

        ws = get_workspace(ralph_project)
        assert prd.get_latest(ws).version == 2

    def test_dry_run_makes_no_changes(self, ralph_project: Path):
        report = ralph.import_ralph_project(ralph_project, dry_run=True)

        assert report.dry_run is True
        assert len(report.tasks_created) == 7
        assert report.prd_action == "created"
        assert report.agents_md_action == "written"
        assert not (ralph_project / ".codeframe").exists()
        assert not (ralph_project / "AGENTS.md").exists()

    def test_dry_run_against_existing_workspace_reports_skips(
        self, ralph_project: Path
    ):
        ralph.import_ralph_project(ralph_project)
        report = ralph.import_ralph_project(ralph_project, dry_run=True)
        assert report.tasks_created == []
        assert report.prd_action == "skipped_identical"
        assert report.agents_md_action == "skipped_exists"

    def test_existing_agents_md_never_overwritten(self, ralph_project: Path):
        (ralph_project / "AGENTS.md").write_text("# Custom prefs\n")
        report = ralph.import_ralph_project(ralph_project)
        assert report.agents_md_action == "skipped_exists"
        assert (ralph_project / "AGENTS.md").read_text() == "# Custom prefs\n"

    def test_separate_workspace_target(self, ralph_project: Path, tmp_path: Path):
        target = tmp_path / "cf-workspace"
        target.mkdir()
        report = ralph.import_ralph_project(ralph_project, workspace_path=target)

        assert workspace_exists(target)
        assert not workspace_exists(ralph_project)
        assert (target / "AGENTS.md").exists()
        assert len(report.tasks_created) == 7

    def test_invalid_project_raises(self, tmp_path: Path):
        with pytest.raises(ralph.RalphProjectNotFoundError):
            ralph.import_ralph_project(tmp_path)
