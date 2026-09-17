"""Command arguments are user text; rendering one through Rich needs escape() (#1206).

#1054 guards the CLI by *running* commands against hostile stored data, but it
cannot run the commands it classifies EXEMPT — network, LLM, server,
machine-mutating — and an error message in one of those that echoes an
argument back (``Invalid hook name '{hook_name}'``) crashes on ``[/b]``.

This rule reaches them statically without a name denylist, because a Typer
command's parameters are user input *by definition* and carry their own
annotations: for every ``@*.command()`` function, the ``str``-annotated
parameters are untrusted, and any ``console.print`` / ``.write`` /
``.add_row`` inside that function that interpolates one of them into an
f-string without ``escape()`` is a violation. Nothing here is inferred from
what a variable is called, so it cannot drift the way #935's field-name list
did.

Known blind spots, shared with every static rule here: a parameter copied into
another local first (``name = hook_name.strip()``) and rendered from that, and
``%``/``.format`` formatting. #1054's runtime guard covers those where the
command is runnable.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_DIR = REPO_ROOT / "codeframe" / "cli"

#: Rich renderers that treat their string as markup.
RENDERERS = {"print", "write", "add_row"}

#: ``module:function:parameter`` → reason. A site may be listed only when
#: escaping it is wrong, not merely inconvenient.
ALLOWED: dict[str, str] = {}


def _is_str_annotation(node: ast.expr | None) -> bool:
    """``str``, ``Optional[str]``, ``str | None``, ``Annotated[str, ...]``."""
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id == "str"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _is_str_annotation(ast.parse(node.value, mode="eval").body)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _is_str_annotation(node.left) or _is_str_annotation(node.right)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        if node.value.id == "Optional":
            return _is_str_annotation(node.slice)
        if node.value.id == "Annotated":
            first = node.slice.elts[0] if isinstance(node.slice, ast.Tuple) else node.slice
            return _is_str_annotation(first)
    return False


def _is_typer_command(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute) and target.attr == "command":
            return True
    return False


def _untrusted_params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func.args
    every = args.posonlyargs + args.args + args.kwonlyargs
    return {a.arg for a in every if _is_str_annotation(a.annotation)}


def _is_escape_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    return (isinstance(f, ast.Name) and f.id == "escape") or (
        isinstance(f, ast.Attribute) and f.attr == "escape"
    )


def _unescaped_names(node: ast.expr, untrusted: set[str]) -> set[str]:
    """Untrusted names referenced by ``node`` outside any ``escape(...)``.

    ``len(name)`` is not the text: an ``'...' if len(desc) > 100 else ''``
    renders a literal, so names inside ``len()`` are not counted.
    """
    if _is_escape_call(node):
        return set()
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len":
        return set()
    found: set[str] = set()
    if isinstance(node, ast.Name) and node.id in untrusted:
        found.add(node.id)
    for child in ast.iter_child_nodes(node):
        found |= _unescaped_names(child, untrusted)
    return found


def _rendered_expressions(call: ast.Call):
    """Every expression a renderer call would format as markup."""
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        if isinstance(arg, ast.JoinedStr):
            for part in arg.values:
                if isinstance(part, ast.FormattedValue):
                    yield part.value
        elif isinstance(arg, (ast.Name, ast.Subscript, ast.Call, ast.Attribute)):
            yield arg


def find_violations(path: Path) -> list[tuple[str, int, str, str]]:
    """``(function, lineno, parameter, source)`` for every unescaped render."""
    tree = ast.parse(path.read_text(), filename=str(path))
    out = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _is_typer_command(func):
            continue
        untrusted = _untrusted_params(func)
        if not untrusted:
            continue
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Attribute) and node.func.attr in RENDERERS):
                continue
            for expr in _rendered_expressions(node):
                for name in sorted(_unescaped_names(expr, untrusted)):
                    out.append((func.name, node.lineno, name, ast.unparse(expr)))
    return out


def _cli_modules() -> list[Path]:
    modules = sorted(p for p in CLI_DIR.glob("*.py") if p.name != "__init__.py")
    assert modules, "no CLI modules found — did codeframe/cli move?"
    return modules


@pytest.mark.parametrize("module", _cli_modules(), ids=lambda p: p.stem)
def test_command_arguments_are_escaped_before_rich_renders_them(module: Path):
    offenders = []
    for func, lineno, param, source in find_violations(module):
        key = f"{module.stem}:{func}:{param}"
        if key in ALLOWED:
            continue
        offenders.append(f"{module.name}:{lineno} {func}({param}): {{{source}}}")

    assert not offenders, (
        "command arguments rendered through Rich without escape():\n  "
        + "\n  ".join(offenders)
    )


def test_every_allowlist_entry_still_matches_a_site():
    live = {
        f"{m.stem}:{func}:{param}"
        for m in _cli_modules()
        for func, _, param, _ in find_violations(m)
    }
    stale = sorted(set(ALLOWED) - live)
    assert not stale, f"allowlist entries no longer match anything: {stale}"


class TestTheRuleActuallyFires:
    """Mutation checks in miniature: the rule must catch each shape it claims to."""

    def _violations(self, source: str, tmp_path: Path) -> list[str]:
        path = tmp_path / "probe.py"
        path.write_text(source)
        return [f"{f}({p})" for f, _, p, _ in find_violations(path)]

    def test_plain_interpolation_is_flagged(self, tmp_path):
        src = (
            "@app.command()\n"
            "def run(hook_name: str):\n"
            "    console.print(f\"[red]Error:[/red] Invalid hook name '{hook_name}'\")\n"
        )
        assert self._violations(src, tmp_path) == ["run(hook_name)"]

    def test_optional_and_union_annotations_count(self, tmp_path):
        src = (
            "@app.command('x')\n"
            "def run(a: Optional[str] = None, b: 'str | None' = None, c: str | None = None):\n"
            "    console.print(f'{a} {b} {c}')\n"
        )
        assert self._violations(src, tmp_path) == ["run(a)", "run(b)", "run(c)"]

    def test_escaped_interpolation_passes(self, tmp_path):
        src = (
            "@app.command()\n"
            "def run(hook_name: str):\n"
            "    console.print(f\"Invalid hook name '{escape(hook_name)}'\")\n"
            "    table.add_row(escape(hook_name[:8]))\n"
        )
        assert self._violations(src, tmp_path) == []

    def test_non_str_parameters_and_non_commands_are_ignored(self, tmp_path):
        src = (
            "@app.command()\n"
            "def run(pr_number: int, output: Path):\n"
            "    console.print(f'{pr_number} {output}')\n"
            "def helper(name: str):\n"
            "    console.print(f'{name}')\n"
        )
        assert self._violations(src, tmp_path) == []

    def test_bare_argument_and_sliced_argument_are_flagged(self, tmp_path):
        src = (
            "@app.command()\n"
            "def run(name: str):\n"
            "    console.print(name)\n"
            "    table.add_row(name[:8], 'x')\n"
            "    log.write(f'{name.upper()}')\n"
        )
        assert self._violations(src, tmp_path) == ["run(name)", "run(name)", "run(name)"]
