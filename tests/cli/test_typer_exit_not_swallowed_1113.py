"""#1113 — a deliberate `typer.Exit` was being re-printed as "Error: 1".

`typer.Exit` subclasses `RuntimeError`, so a command's own catch-all caught its
own intentional exit and stringified the exit *code* as a message:

    Error: No PRD found.
    Add one first: codeframe prd add <file.md>
    Error: 1

To a new user that reads as a second, unexplained failure right after a message
that was otherwise clear.

The per-command fix is one `except typer.Exit: raise`. The scanner below is the
part that matters long-term: it fails for any *new* command that reintroduces
the pattern, which is what the issue asked for in preference to spot fixes.
"""

import ast
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()
APP_SOURCE = Path(__file__).resolve().parents[2] / "codeframe" / "cli" / "app.py"

_BROAD = {"Exception", "BaseException"}


def _raises_typer_exit(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Raise) and n.exc is not None:
            call = n.exc
            if isinstance(call, ast.Call):
                call = call.func
            if isinstance(call, ast.Attribute) and call.attr == "Exit":
                return True
    return False


def _handler_names(handler: ast.ExceptHandler) -> list[ast.expr]:
    if handler.type is None:
        return []
    if isinstance(handler.type, ast.Tuple):
        return list(handler.type.elts)
    return [handler.type]


def find_unguarded_exits() -> list[tuple[str, int]]:
    """Every `try` that raises typer.Exit and then catches it with a broad handler."""
    tree = ast.parse(APP_SOURCE.read_text())
    offenders: list[tuple[str, int]] = []

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try):
                continue
            # Only the try *body* matters: a raise inside a handler propagates
            # out of the statement rather than into a sibling handler.
            if not any(_raises_typer_exit(stmt) for stmt in node.body):
                continue

            guarded = any(
                isinstance(name, ast.Attribute) and name.attr == "Exit"
                for handler in node.handlers
                for name in _handler_names(handler)
            )
            if guarded:
                continue

            broad = [
                h
                for h in node.handlers
                if h.type is None
                or (isinstance(h.type, ast.Name) and h.type.id in _BROAD)
            ]
            if broad:
                offenders.append((fn.name, broad[0].lineno))

    return offenders


class TestTheScannerIsTheRule:
    def test_no_command_swallows_its_own_exit(self):
        offenders = find_unguarded_exits()
        assert offenders == [], (
            "these raise typer.Exit inside a try whose broad handler will catch "
            "it and print the exit code as 'Error: <n>'. Add "
            "`except typer.Exit: raise` above the catch-all:\n"
            + "\n".join(f"  {name} (app.py:{line})" for name, line in offenders)
        )

    def test_the_scanner_actually_detects_the_pattern(self):
        """A scanner that cannot fail is worse than no scanner."""
        source = (
            "import typer\n"
            "def cmd():\n"
            "    try:\n"
            "        raise typer.Exit(1)\n"
            "    except Exception as e:\n"
            "        print(e)\n"
        )
        tree = ast.parse(source)
        fn = tree.body[1]
        try_node = fn.body[0]
        assert _raises_typer_exit(try_node.body[0])
        assert not any(
            isinstance(name, ast.Attribute) and name.attr == "Exit"
            for handler in try_node.handlers
            for name in _handler_names(handler)
        )


class TestTheUserVisibleOutput:
    """AC: `cf tasks generate` with no PRD prints its message and nothing else."""

    def _init(self, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_tasks_generate_with_no_prd(self, tmp_path):
        self._init(tmp_path)
        result = runner.invoke(app, ["tasks", "generate", "-w", str(tmp_path)])

        assert result.exit_code == 1, "the exit code must still signal failure"
        assert "Error: 1" not in result.output
        assert "No PRD found" in result.output

    def test_templates_apply_with_no_prd(self, tmp_path):
        self._init(tmp_path)
        result = runner.invoke(app, ["templates", "apply", "standard", "-w", str(tmp_path)])

        assert result.exit_code == 1
        assert "Error: 1" not in result.output

    def test_no_command_prints_a_bare_numeric_error(self, tmp_path):
        """A stringified exit code has no business in any message."""
        self._init(tmp_path)
        for argv in (
            ["tasks", "generate", "-w", str(tmp_path)],
            ["templates", "apply", "standard", "-w", str(tmp_path)],
            ["prd", "show", "-w", str(tmp_path)],
            ["tasks", "show", "deadbeef", "-w", str(tmp_path)],
        ):
            result = runner.invoke(app, argv)
            for code in range(1, 5):
                assert f"Error: {code}" not in result.output, (
                    f"`cf {' '.join(argv)}` printed its exit code as a message"
                )
