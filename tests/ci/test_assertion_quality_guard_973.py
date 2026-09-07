"""Issue #973 — the weak assertions and dead skips stay gone.

#973 removed three classes of test that could not fail: suites skipped at module
level for reasons that had stopped being true, ``exit_code in (0, 1)`` (which
accepts both success and failure of the command under test), and a bare
``assert result is not None`` standing alone as a test's only claim.

These are all easy to reintroduce under deadline pressure — each one turns a red
test green in one line — so they are pinned structurally rather than left to
review. Everything here parses the AST rather than matching source text: a guard
that only recognises one spelling of the defect is the same kind of check this
issue exists to delete.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Weak-assertion checks are scoped to the CliRunner/TestClient suites #973
#: named. The e2e suites run outside the CI gate and are not in scope.
WEAK_ASSERT_DIRS = ("tests/cli", "tests/ui")

#: The retired-skip check covers the whole tree. Two of the suites #973 retired
#: lived in tests/blockers and tests/integration, so scoping this to cli+ui
#: would leave the exact directories the issue emptied unguarded.
SKIP_SCAN_DIRS = ("tests",)


def _files(dirs: tuple[str, ...]) -> list[Path]:
    files = sorted({f for d in dirs for f in (REPO_ROOT / d).rglob("test_*.py")})
    assert files, f"guard found no test files under {dirs} — did they move?"
    return files


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _tests_in(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            yield node


def _accepts_success_and_failure(container: ast.expr) -> bool:
    """True for a literal container holding 0 *and* at least one non-zero code.

    That pair is the defect: the assertion passes whether the command succeeded
    or failed. ``in (1, 2)`` is two distinct failure modes and a legitimate
    thing to assert, so it is left alone.
    """
    if not isinstance(container, (ast.Tuple, ast.List, ast.Set)):
        return False
    codes = [e.value for e in container.elts if isinstance(e, ast.Constant)]
    if len(codes) != len(container.elts):
        return False  # not all literal — not something we can judge
    return 0 in codes and any(c != 0 for c in codes)


def test_no_exit_code_accepts_both_success_and_failure():
    """``assert result.exit_code in (0, 1)`` asserts nothing about the command.

    Matched on the AST, so ``in [0, 1]``, ``in {0, 1}`` and a tuple wrapped
    across lines are all caught — the substring form of this check would let
    every one of them back in.

    Scoped to ``assert`` statements whose accepted set contains both 0 and a
    non-zero code. ``assert result.exit_code in (1, 2)`` distinguishes two
    failure modes and is fine; ``if result.exit_code in (...)`` is control flow,
    not a claim. A named container (``in EXPECTED_CODES``) is not resolved here
    — indirection through a constant is a deliberate, reviewable act, unlike an
    inline ``(0, 1)``.
    """
    offenders = []
    for path in _files(WEAK_ASSERT_DIRS):
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Assert):
                continue
            for cmp_node in ast.walk(node.test):
                if not isinstance(cmp_node, ast.Compare):
                    continue
                if len(cmp_node.ops) != 1 or not isinstance(cmp_node.ops[0], ast.In):
                    continue
                left = cmp_node.left
                if not (isinstance(left, ast.Attribute) and left.attr == "exit_code"):
                    continue
                if _accepts_success_and_failure(cmp_node.comparators[0]):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {ast.unparse(cmp_node)}"
                    )

    assert not offenders, (
        "exit_code membership assertions accept both success and failure.\n"
        "Assert the exit code the command actually returns:\n  " + "\n  ".join(offenders)
    )


#: Objects a test runner or HTTP client always returns. Asserting one of these
#: "is not None" restates the runner's contract, never the code under test.
NEVER_NONE = ("result", "response", "resp")


def test_no_test_asserts_only_that_the_runner_returned_something():
    """``assert result is not None`` is true of every CliRunner invocation.

    Narrow on purpose. ``assert conductor.get_batch(...) is not None`` is a real
    claim about persistence, and ``assert console is not None`` after an import
    is carried by the import itself — neither is flagged. What is rejected is a
    test whose sole assertion is that a runner or client handed back an object,
    which it always does, pass or fail.
    """
    offenders = []
    for path in _files(WEAK_ASSERT_DIRS):
        for node in _tests_in(_parse(path)):
            asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            if len(asserts) != 1:
                continue
            test = asserts[0].test
            if not (
                isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.IsNot)
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value is None
            ):
                continue
            # `result`, or any attribute of it (`result.exit_code`).
            root = test.left
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name) and root.id in NEVER_NONE:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {node.name}")

    assert (
        not offenders
    ), "these tests assert only that the runner returned an object:\n  " + "\n  ".join(offenders)


def _is_unconditional_skip(node: ast.expr) -> bool:
    """True for ``pytest.mark.skip``/``skip(...)``, but not ``skipif``.

    ``skipif`` states a condition that is re-evaluated every run, so it cannot
    silently outlive its reason the way a bare ``skip`` did in all three suites
    #973 retired.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "skip":
            return True
    return False


def test_no_module_level_skip_anywhere_in_the_suite():
    """A whole suite skipped at module level is coverage the badge still counts.

    All three suites #973 retired were hidden this way, and each stayed hidden
    long after its stated reason stopped being true.
    """
    offenders = []
    for path in _files(SKIP_SCAN_DIRS):
        for node in _parse(path).body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
                continue
            if _is_unconditional_skip(node.value):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert not offenders, "these modules skip their entire suite:\n  " + "\n  ".join(offenders)
