"""Rich markup safety, guarded by running the commands (#1054).

User text is interpolated into markup-enabled Rich output all over the CLI, so
a task titled ``Array indexing a[0]`` raises ``MarkupError`` and crashes the
command. #935 guarded that with a source scanner keyed on free-text *field
names*; it was too narrow four times in one review cycle, because the question
"is this expression prose or a count?" is not one a name can answer.

Measured on the real modules before replacing it:

- deny-by-default over interpolations flags 511 of 663 → 411 statement edits;
- a shape allowlist still cannot classify the 322 bare-``Name`` interpolations,
  because ``{host}`` and ``{title}`` are the same shape;
- f-string contents are invisible to mypy/pyright, so no type checker helps.

And the shape that actually broke — found by this file on its first run, in
code the field-name scanner declared clean — is a local bound one statement
*earlier*::

    question_str = b.question[:50] ...      # cf blocker list
    table.add_row(b.id[:8], status_str, task_str, question_str)

    title = task.title if task else ...     # cf schedule show
    console.print(f"  [...] {title} {agent_str}")

The render statement contains no field name at all, so no name- or shape-based
scanner can ever see it. This file drives the real call sites with real values
instead: seed hostile text into every user-supplied field, run the commands,
and let Rich raise.
"""

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import blockers, checkpoints, prd, tasks
from codeframe.core.proof import capture as proof_capture
from codeframe.core.proof.models import Severity, Source
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


#: Valid user input that is also valid-looking Rich markup. ``[/b]`` is an
#: unmatched closing tag and ``a[0]`` an unknown style; both raise.
HOSTILE = "Fix the [/b] parser, a[0] and [bold]b"


#: Commands run against the hostile workspace, with the argv they need.
#: ``{task}``/``{blocker}``/``{req}``/``{checkpoint}`` are substituted from the
#: seeded fixture. The process chdirs into the workspace, so no --workspace
#: flag is needed and the differing flag names across commands do not matter.
RUN: dict[str, list[str]] = {
    "status": [],
    "summary": [],
    "review": [],
    "version": [],
    "tasks list": [],
    "tasks tree": [],
    "tasks show": ["{task}"],
    "tasks set": ["status", "{task}", "BLOCKED"],
    "prd show": [],
    "prd list": [],
    "prd versions": ["{prd}"],
    "prd templates list": [],
    "blocker list": ["--all"],
    "blocker show": ["{blocker}"],
    "blocker answer": ["{blocker}", HOSTILE],
    "checkpoint list": [],
    "checkpoint show": ["{checkpoint}"],
    "proof list": [],
    "proof show": ["{req}"],
    "proof status": [],
    "schedule show": [],
    "schedule predict": [],
    "schedule bottlenecks": [],
    "work status": [],
    "work show": ["{task}"],
    "work diagnose": ["{task}"],
    "work update-description": ["{task}", HOSTILE],
    "work batch status": [],
    "patch list": [],
    "patch status": [],
    "stats tokens": [],
    "stats costs": [],
    "templates list": [],
    "templates show": ["bug-fix"],  # built-in template, still a render path
    "engines list": [],
    "engines stats": [],
    "hooks show": [],
    "config telemetry": ["status"],
}

#: Commands deliberately not exercised, each with the reason. This is a
#: classification, not a denylist of field names: the completeness test below
#: fails when a new command belongs to neither set, so the coverage gap has to
#: be stated rather than drifting in silently.
#:
#: The gap this leaves: a str-typed Typer parameter echoed back by an error
#: message ("no such req: {req_id}") is user text too, and in an EXEMPT command
#: nothing here runs it. 93 such renders remain across the CLI — see the #1054
#: follow-up. They are latent, not open crashes: reaching one needs hostile
#: text in the argument itself.
EXEMPT: dict[str, str] = {
    "init": "creates a workspace; renders the path, not stored user text",
    "serve": "starts a long-running server",
    "prd add": "reads a file argument; the stored text is covered by `prd show`",
    "prd update": "same store as `prd add`",
    "prd delete": "destroys the fixture the other prd commands render",
    "prd export": "writes a file; renders no user text",
    "prd diff": "needs two stored versions; covered by `prd versions`",
    "prd generate": "LLM call",
    "prd stress-test": "LLM call",
    "prd templates show": "ships built-in templates, not user text",
    "prd templates export": "writes a file; renders no user text",
    "prd templates import": "reads a file argument",
    "tasks generate": "LLM call",
    "tasks delete": "destroys the fixture the other task commands render",
    "work start": "runs an agent",
    "work resume": "runs an agent",
    "work rerun": "runs an agent",
    "work retry": "runs an agent",
    "work stop": "signals a running agent",
    "work follow": "blocks tailing a live run",
    "work replay": "needs a recorded trace",
    "work diff": "needs a recorded trace",
    "work export-trace": "needs a recorded trace",
    "work batch run": "runs agents",
    "work batch resume": "runs agents",
    "work batch stop": "signals a running batch",
    "work batch follow": "blocks tailing a live batch",
    "events tail": "blocks following the event log",
    "blocker create": "covered by the seeded blocker",
    "blocker resolve": "covered by `blocker answer`",
    "patch export": "writes a patch file; renders no user text",
    "commit create": "writes a git commit",
    "checkpoint create": "covered by the seeded checkpoint",
    "checkpoint restore": "rewrites the workspace under the other commands",
    "checkpoint delete": "destroys the fixture `checkpoint show` renders",
    "gates run": "runs the project's test suite",
    "templates apply": "writes template files into the workspace",
    "proof capture": "covered by the seeded requirement",
    "proof run": "runs the 9 gates, i.e. the project's test suite",
    "proof waive": "mutates the seeded requirement `proof show` renders",
    "import ralph": "reads an external Ralph export",
    "hooks run": "executes repo-configured shell hooks",
    "hooks set": "edits .codeframe/config.yaml",
    "hooks clear": "edits .codeframe/config.yaml",
    "hooks trust": "writes the machine-wide trust store",
    "stats export": "writes a file; renders no user text",
    "engines check": "probes the machine for installed agent CLIs",
    "engines compare": "probes the machine for installed agent CLIs",
    "env check": "probes the machine's environment",
    "env doctor": "probes the machine's environment",
    "env install-missing": "installs packages",
    "env auto-install": "installs packages",
    "pr create": "GitHub network call",
    "pr list": "GitHub network call",
    "pr get": "GitHub network call",
    "pr merge": "GitHub network call",
    "pr close": "GitHub network call",
    "pr status": "GitHub network call",
    "auth login": "server network call",
    "auth logout": "server network call",
    "auth register": "server network call",
    "auth whoami": "server network call",
    "auth setup": "writes the machine-wide credential store",
    "auth list": "reads the machine-wide credential store, not workspace text",
    "auth validate": "provider network call",
    "auth rotate": "writes the machine-wide credential store",
    "auth remove": "writes the machine-wide credential store",
    "auth api-key-create": "writes the machine-wide platform store",
    "auth api-key-list": "reads the machine-wide platform store",
    "auth api-key-revoke": "writes the machine-wide platform store",
    "auth api-key-rotate": "writes the machine-wide platform store",
    "auth set-password":
        "writes the machine-wide platform store",
    "auth deactivate": "writes the machine-wide platform store",
    "auth activate": "writes the machine-wide platform store",
    "auth user-list": "reads the machine-wide platform store",
}


def _registered_commands(typer_app, prefix: str = "") -> list[str]:
    """Every command path in the live Typer tree, e.g. ``work batch status``."""
    found = []
    for command in typer_app.registered_commands:
        name = command.name or (
            command.callback.__name__.replace("_", "-") if command.callback else "?"
        )
        found.append(prefix + name)
    for group in typer_app.registered_groups:
        sub = group.typer_instance
        found += _registered_commands(sub, prefix + (group.name or sub.info.name) + " ")
    return found


@pytest.fixture
def hostile_workspace(tmp_path, monkeypatch):
    """A workspace whose every user-supplied text field is hostile markup."""
    workspace = create_or_load_workspace(tmp_path)

    dependency = tasks.create(
        workspace, title=HOSTILE, description=HOSTILE, status=TaskStatus.DONE
    )
    task = tasks.create(
        workspace,
        title=HOSTILE,
        description=HOSTILE,
        status=TaskStatus.READY,
        depends_on=[dependency.id],
    )
    blocker = blockers.create(workspace, question=HOSTILE, task_id=task.id)
    prd_record = prd.store(
        workspace, content=f"# {HOSTILE}\n\n{HOSTILE}\n", title=HOSTILE
    )
    checkpoint = checkpoints.create(workspace, name=HOSTILE, include_git_ref=False)
    requirement, _ = proof_capture.capture_requirement(
        workspace,
        title=HOSTILE,
        description=HOSTILE,
        where="codeframe/cli/app.py",
        severity=Severity.MEDIUM,
        source=Source.USER_REPORT,
    )

    monkeypatch.chdir(tmp_path)
    return {
        "workspace": workspace,
        "task": task.id,
        "blocker": blocker.id,
        "prd": prd_record.id,
        "checkpoint": checkpoint.id,
        "req": requirement.id,
    }


def _is_placeholder(arg: str) -> bool:
    return arg.startswith("{") and arg.endswith("}")


def _invoke(command: str, argv: list[str], ids: dict):
    resolved = [ids[a[1:-1]] if _is_placeholder(a) else a for a in argv]
    return CliRunner().invoke(app, command.split() + resolved)


@pytest.mark.parametrize("command", sorted(RUN), ids=lambda c: c.replace(" ", "-"))
def test_command_survives_hostile_user_text(command, hostile_workspace):
    """The property itself: hostile text renders, it does not crash the command."""
    result = _invoke(command, RUN[command], hostile_workspace)

    assert result.exit_code != 2, (
        f"`cf {command}` rejected its argv — the RUN table is stale:\n{result.output}"
    )
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"`cf {command}` crashed on hostile user text: {result.exception!r}"
    )
    # A blanket `except Exception` turns the crash into an error message and a
    # clean exit, which would pass the assertion above while the command is
    # just as broken. `prd show` and `schedule show` did exactly that.
    assert "doesn't match any open tag" not in result.output, (
        f"`cf {command}` swallowed a MarkupError instead of rendering:\n{result.output}"
    )


#: The commands above that take an id, re-run with hostile text *as the id*.
#: "not found" messages echo the argument back through the same markup-enabled
#: console, so the argument is user text too.
TAKES_AN_ID = sorted(
    command
    for command, argv in RUN.items()
    if any(_is_placeholder(arg) for arg in argv)
)


@pytest.mark.parametrize("command", TAKES_AN_ID, ids=lambda c: c.replace(" ", "-"))
def test_command_survives_a_hostile_argument(command, hostile_workspace):
    """`cf proof show '[/b]'` must report a miss, not crash reporting it."""
    argv = [HOSTILE if _is_placeholder(arg) else arg for arg in RUN[command]]
    result = CliRunner().invoke(app, command.split() + argv)

    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"`cf {command}` crashed on a hostile argument: {result.exception!r}"
    )
    assert "doesn't match any open tag" not in result.output, (
        f"`cf {command}` swallowed a MarkupError on a hostile argument:\n{result.output}"
    )


class TestTheGuardActuallyGuards:
    """A smoke test that renders nothing would pass in silence."""

    @pytest.mark.parametrize(
        "command, argv",
        [
            ("tasks list", []),
            ("tasks show", ["{task}"]),
            ("blocker list", ["--all"]),
            ("prd show", []),
            ("checkpoint list", []),
            ("proof list", []),
            ("schedule show", []),
        ],
    )
    def test_the_hostile_text_reaches_the_output_literally(
        self, command, argv, hostile_workspace
    ):
        """Escaped, not stripped — and proof the seeding really landed."""
        result = _invoke(command, argv, hostile_workspace)

        assert "[/b]" in result.output, (
            f"`cf {command}` rendered no hostile text, so it guards nothing:\n"
            f"{result.output}"
        )

    def test_the_hostile_text_would_really_crash_rich(self):
        """Guard the guard: prove the fixture's text is hostile."""
        import io

        from rich.console import Console

        console = Console(file=io.StringIO())
        with pytest.raises(Exception):
            console.print(f"[cyan]Title:[/cyan] {HOSTILE}")


class TestEveryCommandIsClassified:
    """The anti-drift half: a new command cannot land unclassified."""

    def test_run_and_exempt_cover_the_live_command_tree(self):
        registered = set(_registered_commands(app))
        classified = set(RUN) | set(EXEMPT)

        assert registered - classified == set(), (
            "new CLI commands are neither run against hostile data nor exempted "
            "with a reason — add them to RUN or EXEMPT in this file"
        )
        assert classified - registered == set(), (
            "these entries name commands the CLI no longer registers"
        )

    def test_no_command_is_in_both_sets(self):
        assert set(RUN) & set(EXEMPT) == set()

    def test_every_exemption_states_a_reason(self):
        assert [name for name, reason in EXEMPT.items() if not reason.strip()] == []


class TestTuiSurvivesHostileUserText:
    """AC2's other half. The TUI renders the same rows through RichLog and
    DataTable, and the first version of the #935 scanner did not read this
    module at all."""

    @pytest.mark.asyncio
    async def test_dashboard_renders_a_hostile_workspace(self, hostile_workspace):
        from codeframe.tui.app import DashboardApp

        app = DashboardApp(workspace=hostile_workspace["workspace"])
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert app.query_one("#task-table") is not None

    @pytest.mark.asyncio
    async def test_the_hostile_title_reaches_the_task_table(self, hostile_workspace):
        """Proof the panels actually rendered the seeded rows."""
        from textual.widgets import DataTable

        from codeframe.tui.app import DashboardApp

        app = DashboardApp(workspace=hostile_workspace["workspace"])
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one("#task-table", DataTable)

            rendered = " ".join(
                str(cell) for row in table.rows for cell in table.get_row(row)
            )
            assert "[/b]" in rendered, f"the TUI rendered no hostile text: {rendered!r}"
