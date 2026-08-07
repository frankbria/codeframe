"""Delete the unused PRD Jinja renderer; de-duplicate templates apply (#962).

``PrdTemplateManager`` built a full ``jinja2.Environment`` (not
``SandboxedEnvironment``) and ``render_template`` executed ``format_template``
bodies loaded from repo-controlled ``.codeframe/templates/prd/*.yaml`` — a
latent SSTI/RCE path from a cloned untrusted repo. The only mitigation was that
``render_template`` had zero production callers: the real PRD path reads
``section.title`` / ``.required`` / ``.source``.

The renderer is deleted rather than sandboxed. Sandboxing hardens a feature
nobody uses; deleting removes the execution surface outright.

Separately, ``cli templates apply`` reimplemented ``core.templates.apply_template``
and had drifted — it gated on a PRD existing but never passed ``prd_id`` to
``tasks.create``, so the tasks it created were unlinked.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


# ─────────────────────────────────────────────────────────────────────────────
# The template-execution surface is gone
# ─────────────────────────────────────────────────────────────────────────────


class TestJinjaRendererRemoved:
    def test_render_template_is_deleted(self):
        from codeframe.planning.prd_templates import PrdTemplateManager

        assert not hasattr(PrdTemplateManager, "render_template")

    def test_no_jinja_environment_on_the_manager(self):
        from codeframe.planning.prd_templates import PrdTemplateManager

        manager = PrdTemplateManager()
        env_attrs = [a for a in vars(manager) if "env" in a.lower()]
        assert env_attrs == [], f"template environment still present: {env_attrs}"

    def test_the_module_does_not_import_jinja(self):
        import codeframe.planning.prd_templates as mod

        source = Path(mod.__file__).read_text()
        tree = compile(source, mod.__file__, "exec", flags=0, dont_inherit=True)
        assert "jinja2" not in {
            n for n in tree.co_names
        }, "jinja2 still referenced"
        # Belt and braces: no import statement survives either.
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                assert "jinja" not in stripped.lower(), stripped

    def test_no_template_function_registry_remains(self):
        import codeframe.planning.prd_templates as mod

        assert not hasattr(mod, "TEMPLATE_FUNCTIONS")

    def test_an_ssti_payload_in_a_repo_template_is_never_evaluated(self, tmp_path):
        """A cloned repo can supply .codeframe/templates/prd/*.yaml.

        The payload must survive as inert text — proof that nothing renders it.
        """
        import yaml

        from codeframe.planning.prd_templates import load_template_from_file

        payload = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
        template_file = tmp_path / "evil.yaml"
        template_file.write_text(
            yaml.safe_dump(
                {
                    "id": "evil",
                    "name": "Evil",
                    "description": "d",
                    "sections": [
                        {
                            "id": "s1",
                            "title": "S",
                            "required": True,
                            "source": "problem",
                            "format_template": payload,
                        }
                    ],
                }
            )
        )

        template = load_template_from_file(template_file)

        # Loaded verbatim, never rendered — no class hierarchy leaked.
        assert template.sections[0].format_template == payload
        assert "__subclasses__" not in str(template.sections[0].title)

    def test_prd_generation_still_reads_the_fields_it_actually_uses(self):
        """title/required/source are the real contract — keep them working."""
        from codeframe.planning.prd_templates import PrdTemplateManager

        manager = PrdTemplateManager()
        template = manager.get_template("standard")
        assert template is not None
        assert template.sections
        for section in template.sections:
            assert section.title
            assert isinstance(section.required, bool)
            assert section.source is not None


# ─────────────────────────────────────────────────────────────────────────────
# CLI help no longer advertises formatting it cannot do
# ─────────────────────────────────────────────────────────────────────────────


class TestCliHelpDoesNotOverpromise:
    def test_prd_templates_help_does_not_claim_output_formats(self):
        from codeframe.cli import app as cli_app

        source = Path(inspect.getfile(cli_app)).read_text()
        assert "customizable output formats" not in source


# ─────────────────────────────────────────────────────────────────────────────
# templates apply delegates, and links the PRD
# ─────────────────────────────────────────────────────────────────────────────


class TestTemplatesApplyDelegates:
    def test_core_apply_template_accepts_and_stores_prd_id(self, tmp_path):
        from codeframe.core import prd, tasks, templates
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        record = prd.store(ws, content="# PRD", title="P")

        result = templates.apply_template(ws, "bug-fix", prd_id=record.id)

        assert result.tasks_created > 0
        for task_id in result.task_ids:
            assert tasks.get(ws, task_id).prd_id == record.id

    def test_core_apply_template_still_works_without_a_prd(self, tmp_path):
        from codeframe.core import tasks, templates
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        result = templates.apply_template(ws, "bug-fix")

        assert result.tasks_created > 0
        assert tasks.get(ws, result.task_ids[0]).prd_id is None

    def test_cli_delegates_instead_of_reimplementing(self):
        from codeframe.cli import app as cli_app

        source = inspect.getsource(cli_app.templates_apply)
        assert "apply_template(" in source
        # The duplicated body is gone: no direct task creation or manual
        # dependency wiring left in the command.
        assert "tasks.create(" not in source
        assert "update_depends_on" not in source

    def test_cli_apply_links_created_tasks_to_the_prd(self, tmp_path):
        from typer.testing import CliRunner

        from codeframe.cli import app as cli_app
        from codeframe.core import prd, tasks
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        record = prd.store(ws, content="# PRD", title="P")

        result = CliRunner().invoke(
            cli_app.app,
            ["templates", "apply", "bug-fix", "--workspace", str(tmp_path)],
        )

        assert result.exit_code == 0, result.output
        created = tasks.list_tasks(ws)
        assert created, "no tasks created"
        for task in created:
            assert task.prd_id == record.id, (
                "the command requires a PRD but did not link it"
            )

    def test_cli_apply_still_requires_a_prd(self, tmp_path):
        from typer.testing import CliRunner

        from codeframe.cli import app as cli_app
        from codeframe.core import tasks
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)

        result = CliRunner().invoke(
            cli_app.app,
            ["templates", "apply", "bug-fix", "--workspace", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert tasks.list_tasks(ws) == []

    def test_cli_apply_reports_an_unknown_template(self, tmp_path):
        from typer.testing import CliRunner

        from codeframe.cli import app as cli_app
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        prd.store(ws, content="# PRD", title="P")

        result = CliRunner().invoke(
            cli_app.app,
            ["templates", "apply", "no-such-template", "--workspace", str(tmp_path)],
        )

        assert result.exit_code == 1
        assert "no-such-template" in " ".join(result.output.split())
