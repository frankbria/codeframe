"""CLI defaults and output hardening (#935).

Four separate problems:

1. `cf serve` and the server defaulted `--host` to 0.0.0.0 while the printed
   hints said localhost — so a beta server exposing SQLite state, workspace file
   access and agent-execution endpoints sat on the LAN by default. Combined with
   the documented `CODEFRAME_AUTH_REQUIRED=false` dev mode that is an
   unauthenticated remote shell.
2. `auth setup` accepted the credential via `--value/-v` and the docstring
   taught it, exposing keys through /proc/<pid>/cmdline and shell history.
3. Task titles and blocker text were interpolated into Rich-rendered output with
   markup enabled, so a title containing '[/b]' raised MarkupError and crashed
   `cf tasks list` and the TUI.
4. README.md and CLAUDE.md advertised `cf tasks show <id>`, which did not exist.
"""

import inspect
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Titles that are valid user input and also valid-looking Rich markup.
HOSTILE_TITLES = [
    "Fix the [/b] parser",
    "Support [bold] tags",
    "Handle [/] gracefully",
    "Array indexing a[0] and b[1]",
    "[red]not actually markup[/red]",
]


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


class TestServeBindsLoopback:
    def test_serve_host_default_is_loopback(self):
        from codeframe.cli.app import serve

        default = inspect.signature(serve).parameters["host"].default
        assert default.default == "127.0.0.1", (
            f"cf serve binds {default.default} by default"
        )

    def test_run_server_default_is_loopback(self):
        from codeframe.ui.server import run_server

        assert inspect.signature(run_server).parameters["host"].default == "127.0.0.1"

    def test_env_example_does_not_suggest_a_public_bind(self):
        content = (REPO_ROOT / ".env.example").read_text()

        assert "# API_HOST=0.0.0.0" not in content

    def test_exposing_the_bind_warns(self, capsys):
        from codeframe.cli.app import _warn_if_exposed

        _warn_if_exposed("0.0.0.0")

        assert "WARNING" in capsys.readouterr().out

    def test_loopback_does_not_warn(self, capsys):
        from codeframe.cli.app import _warn_if_exposed

        _warn_if_exposed("127.0.0.1")

        assert capsys.readouterr().out == ""

    def test_exposed_bind_with_auth_disabled_warns_harder(self, capsys, monkeypatch):
        """The dangerous combination the issue calls out."""
        from codeframe.cli.app import _warn_if_exposed

        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        _warn_if_exposed("0.0.0.0")

        out = capsys.readouterr().out
        assert "CODEFRAME_AUTH_REQUIRED" in out
        assert "no credentials" in out

    @pytest.mark.parametrize("bind", ["0.0.0.0", "::", "*"])
    def test_every_wildcard_bind_warns(self, capsys, bind):
        from codeframe.cli.app import _warn_if_exposed

        _warn_if_exposed(bind)

        assert "WARNING" in capsys.readouterr().out


class TestCredentialsStayOffArgv:
    def test_stdin_and_file_options_exist(self):
        from codeframe.cli.auth_commands import setup_credential

        params = inspect.signature(setup_credential).parameters
        assert "value_stdin" in params
        assert "value_file" in params

    def test_value_option_is_hidden_from_help(self):
        from codeframe.cli.auth_commands import setup_credential

        value_param = inspect.signature(setup_credential).parameters["value"].default
        assert value_param.hidden is True, "--value must not be advertised"
        assert "DEPRECATED" in value_param.help

    def test_docstring_no_longer_teaches_passing_the_secret_inline(self):
        from codeframe.cli.auth_commands import setup_credential

        doc = setup_credential.__doc__ or ""
        assert "--value sk-ant-" not in doc
        assert "-v ghp_" not in doc
        assert "--value-stdin" in doc, "the safe alternative must be shown"


class TestRichMarkupIsEscaped:
    """AC3 — a title containing '[/b]' must render, not raise."""

    @pytest.mark.parametrize("title", HOSTILE_TITLES)
    def test_tasks_list_renders_a_hostile_title(self, workspace, title, tmp_path):
        tasks.create(workspace, title=title, description="d", status=TaskStatus.READY)

        result = CliRunner().invoke(app, ["tasks", "list", "--workspace", str(tmp_path)])

        assert result.exception is None, f"{title!r} crashed: {result.exception!r}"
        assert result.exit_code == 0

    @pytest.mark.parametrize("title", HOSTILE_TITLES)
    def test_tasks_show_renders_a_hostile_title(self, workspace, title, tmp_path):
        task = tasks.create(
            workspace, title=title, description=f"see {title}", status=TaskStatus.READY
        )

        result = CliRunner().invoke(
            app, ["tasks", "show", task.id[:8], "--workspace", str(tmp_path)]
        )

        assert result.exception is None, f"{title!r} crashed: {result.exception!r}"
        assert result.exit_code == 0

    @pytest.mark.parametrize(
        "module",
        [
            "codeframe/cli/app.py",
            # The TUI renders the same user text through RichLog/DataTable and
            # was invisible to the first version of this scanner, which read only
            # cli/app.py — the PR bot found req.title unescaped there.
            "codeframe/tui/app.py",
        ],
    )
    def test_no_unescaped_user_text_reaches_rich_output(self, module):
        """Scanner, not a point check: a new render of user data should fail the
        build rather than wait to be found in review.

        Operates on whole *statements*, not lines. The line-based version missed
        `log.write(\n    f"... {req.title} ...")` in the TUI because the call and
        the f-string sit on different lines — which is how the reviewer found two
        sites the scanner had just declared clean.
        """
        source = (REPO_ROOT / module).read_text()

        # Join physical lines into logical ones by tracking paren depth. The
        # line-based version missed `log.write(\n    f"... {req.title} ...")` in
        # the TUI because the call and the f-string sit on different lines —
        # which is how the reviewer found two sites the scanner had just
        # declared clean. (Simple depth counting, not tokenize: 3.12 splits
        # f-strings into separate tokens and the brace never survives.)
        statements, buf, depth = [], "", 0
        for line in source.splitlines():
            stripped = line.strip()
            buf = f"{buf} {stripped}" if buf else stripped
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                statements.append(buf)
                buf, depth = "", 0

        # A denylist of free-text FIELD names — deliberately, after trying the
        # alternatives. Enumerating variable names failed (missed 17 sites);
        # deny-by-default on every attribute over-fires on 89 statements that
        # interpolate timestamps, counts and enum accessors, which would be
        # churn rather than safety. This list covers the free-prose fields that
        # actually exist in this codebase; a real lint rule is the durable
        # answer and is filed as a follow-up.
        FREE_TEXT = (
            "title|description|question|answer|label|recommendation|message|"
            "output|error|name|summary|content|text|reason|stderr|stdout|"
            "source_node_title|feedback|detail|hint|notes"
        )
        # The field may appear ANYWHERE inside the interpolation, not only as a
        # bare `{obj.field}` — `{', '.join(amb.questions)}` was the fifth gap
        # found in this review cycle. Match `{...}` spans, then look inside.
        interpolation = re.compile(r"\{[^{}]*\}")
        # `s?`: the attribute is often plural (`amb.questions`), and \b after a
        # singular name refuses to match it — which is why the reviewer found
        # `', '.join(amb.questions)` still unescaped.
        free_field = re.compile(r"\.(?:" + FREE_TEXT + r")s?\b")

        def _has_unescaped_field(statement: str) -> bool:
            return any(
                free_field.search(span) and "escape(" not in span
                for span in interpolation.findall(statement)
            )
        renders = ("console.print", "log.write", "add_row")

        # A bare loop variable (`for q in amb.questions: ... {q}`) carries no
        # field name, so the field regex above cannot see it. Collect the names
        # bound by a `for` over a free-text collection and treat a bare
        # interpolation of one as unescaped too. (The PR bot found exactly this
        # shape after five earlier rounds.)
        loop_bound = set()
        for st in statements:
            m = re.match(
                # (?:...) — ungrouped, the `\.` prefix would bind only to the
                # first alternative and the pattern would never match.
                r"for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+[A-Za-z_][A-Za-z0-9_]*\.(?:"
                + FREE_TEXT.replace("|", "s?|") + r"s?)\b",
                st,
            )
            if m:
                loop_bound.add(m.group(1))

        def _bare_loop_var(statement: str) -> bool:
            return any(
                span.strip("{}").strip() in loop_bound and "escape(" not in span
                for span in interpolation.findall(statement)
            )

        offenders = [
            st for st in statements
            if any(r in st for r in renders)
            and (_has_unescaped_field(st) or _bare_loop_var(st))
        ]

        assert not offenders, (
            f"unescaped user text rendered through Rich in {module}:\n"
            + "\n".join(o[:160] for o in offenders)
        )

    def test_markup_is_shown_literally_not_interpreted(self, workspace, tmp_path):
        tasks.create(
            workspace, title="Fix [/b] now", description="d", status=TaskStatus.READY
        )

        result = CliRunner().invoke(app, ["tasks", "list", "--workspace", str(tmp_path)])

        assert "[/b]" in result.output, "the literal text should survive escaping"

    def test_rich_would_have_raised_without_escaping(self):
        """Guard the guard: prove the hostile titles really are hostile."""
        from rich.console import Console

        console = Console(file=open("/dev/null", "w"))
        with pytest.raises(Exception):
            console.print(f"[cyan]Title:[/cyan] {HOSTILE_TITLES[0]}")


class TestStdinValueNeverLeaks:
    """Raised by the PR bot: `--value-stdin` without `--provider` let the
    interactive provider prompt consume the piped SECRET as the provider choice,
    and the error path then echoed it back — leaking the exact thing the flag
    exists to protect."""

    def test_stdin_without_provider_is_rejected_before_any_prompt(self):
        result = CliRunner().invoke(
            app, ["auth", "setup", "--value-stdin"], input="sk-ant-SUPERSECRET\n"
        )

        assert result.exit_code == 1
        assert "--provider is required" in result.output
        assert "SUPERSECRET" not in result.output, "the piped secret was echoed"

    def test_value_file_without_provider_is_rejected(self, tmp_path):
        secret = tmp_path / "k"
        secret.write_text("ghp_SUPERSECRET\n")

        result = CliRunner().invoke(
            app, ["auth", "setup", "--value-file", str(secret)]
        )

        assert result.exit_code == 1
        assert "SUPERSECRET" not in result.output

    def test_an_unknown_provider_is_not_echoed_back(self):
        """The rejected value could be a mis-consumed credential."""
        result = CliRunner().invoke(
            app, ["auth", "setup", "--provider", "sk-ant-SUPERSECRET"]
        )

        assert result.exit_code == 1
        assert "SUPERSECRET" not in result.output
        assert "Unknown provider" in result.output


class TestTasksShowExists:
    """AC4 — README.md and CLAUDE.md advertise it."""

    def test_command_is_registered(self):
        result = CliRunner().invoke(app, ["tasks", "--help"])

        assert "show" in result.output

    def test_shows_details_and_dependencies(self, workspace, tmp_path):
        dep = tasks.create(workspace, title="First", description="", status=TaskStatus.READY)
        task = tasks.create(
            workspace,
            title="Second",
            description="Do the thing",
            status=TaskStatus.READY,
            depends_on=[dep.id],
        )

        result = CliRunner().invoke(
            app, ["tasks", "show", task.id, "--workspace", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        assert "Second" in result.output
        assert "Do the thing" in result.output
        assert "Dependencies" in result.output
        assert dep.id[:8] in result.output
        assert "First" in result.output, "the dependency's title should resolve"

    def test_accepts_a_unique_prefix(self, workspace, tmp_path):
        task = tasks.create(workspace, title="Prefixed", description="", status=TaskStatus.READY)

        result = CliRunner().invoke(
            app, ["tasks", "show", task.id[:8], "--workspace", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        assert "Prefixed" in result.output

    def test_unknown_id_exits_nonzero(self, workspace, tmp_path):
        result = CliRunner().invoke(
            app, ["tasks", "show", "nosuchtask", "--workspace", str(tmp_path)]
        )

        assert result.exit_code == 1
        assert "No task matching" in result.output

    def test_docs_reference_a_command_that_exists(self):
        for doc in ("README.md", "CLAUDE.md"):
            content = (REPO_ROOT / doc).read_text()
            if "tasks show" in content:
                # Imported here, not at module scope: a module-level import
                # would turn "the command is missing" into a collection error
                # that hides every other test in this file.
                from codeframe.cli.app import tasks_show

                assert tasks_show is not None
                break
        else:
            pytest.fail("neither doc mentions `tasks show` — did the reference move?")
