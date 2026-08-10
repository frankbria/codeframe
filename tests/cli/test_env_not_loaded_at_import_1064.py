"""#1064 — importing the CLI wrote the repository's .env into os.environ.

`codeframe/cli/app.py` called `load_env_files()` at module import, so any test
doing `from codeframe.cli.app import app` — most of the CLI suite — loaded the
repo's `.env` into the ambient environment for the rest of the session. That
silently flipped `requires_api_key`-gated tests from skip to run, and forced any
test asserting on an *absent* key to defend itself with `monkeypatch.delenv`.

The behaviour is correct for `cf` and wrong for `import`. It now happens in the
Typer root callback, which runs before any command.

Spun off from #946, whose AC3 is "running `pytest tests/` leaves os.environ
unchanged"; #946 fixed the conftest mechanism and named this one as remaining.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]


def _child(code: str, *, drop_key: bool = True) -> subprocess.CompletedProcess:
    """Run `code` in a fresh interpreter.

    A child process on purpose (the AC asks for it): this test module has almost
    certainly already imported the CLI transitively, so asserting in-process
    would prove nothing — the environment would already be poisoned.
    """
    env = dict(os.environ)
    if drop_key:
        env.pop("ANTHROPIC_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


class TestImportingTheCliIsInert:
    def test_import_does_not_set_the_api_key(self):
        """AC: import with the key unset leaves it unset."""
        result = _child(
            "import os\n"
            "from codeframe.cli.app import app\n"
            "print(bool(os.environ.get('ANTHROPIC_API_KEY')))\n"
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().endswith("False"), result.stdout + result.stderr

    def test_import_does_not_print_the_env_loader_notice(self):
        """The loader announces refused keys; silence proves it did not run."""
        result = _child(
            "from codeframe.cli.app import app\n"
        )
        assert result.returncode == 0, result.stderr
        combined = result.stdout + result.stderr
        assert "security-sensitive" not in combined, combined

    def test_importing_validators_is_inert_too(self):
        """AC: the other load_env_files caller is checked for the same pattern.

        validators.py calls it inside functions, not at import — this pins that.
        """
        result = _child(
            "import os\n"
            "import codeframe.cli.validators  # noqa: F401\n"
            "print(bool(os.environ.get('ANTHROPIC_API_KEY')))\n"
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().endswith("False"), result.stdout + result.stderr


class TestRunningACommandStillLoadsIt:
    """AC: `cf` from a directory with a .env still picks the values up."""

    def test_a_command_loads_the_env(self):
        result = _child(
            "import os\n"
            "from typer.testing import CliRunner\n"
            "from codeframe.cli.app import app\n"
            "before = bool(os.environ.get('ANTHROPIC_API_KEY'))\n"
            "CliRunner().invoke(app, ['config', 'telemetry', 'status'])\n"
            "after = bool(os.environ.get('ANTHROPIC_API_KEY'))\n"
            "print(f'{before}->{after}')\n"
        )
        assert result.returncode == 0, result.stderr
        assert "False->True" in result.stdout, result.stdout + result.stderr

    def test_the_operator_environment_still_wins(self):
        """#904 precedence is unchanged — it just applies a moment later."""
        env = dict(os.environ)
        env["ANTHROPIC_API_KEY"] = "operator-value"
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import os\n"
                "from typer.testing import CliRunner\n"
                "from codeframe.cli.app import app\n"
                "CliRunner().invoke(app, ['config', 'telemetry', 'status'])\n"
                "print(os.environ['ANTHROPIC_API_KEY'])\n",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        assert "operator-value" in result.stdout, result.stdout + result.stderr


class TestTheModuleHasNoImportTimeCall:
    """A structural check, so the call cannot drift back to module scope."""

    def test_load_env_files_is_not_called_at_module_level(self):
        import ast

        source = (REPO_ROOT / "codeframe" / "cli" / "app.py").read_text()
        tree = ast.parse(source)

        offenders = [
            node.lineno
            for node in tree.body  # module level only
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "load_env_files"
        ]
        assert offenders == [], (
            f"load_env_files() is called at module scope (app.py:{offenders}); "
            "importing the CLI must not mutate os.environ (#1064)"
        )
