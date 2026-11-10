"""Where a requirement's named tests live, and whether they changed (#1551).

A requirement's ``scope`` is the code it protects (``--where``), not the test
that proves it. A scoped ``cf proof run`` — the check a pre-commit hook makes —
therefore never re-checked a requirement when a commit touched only its test,
so deleting, skipping or weakening that test committed cleanly.

This module closes both halves of that gap without running anything:

* **Scope.** :class:`EvidenceScope` says whether a change touched a
  requirement's *evidence*: its ``tests/proof/<id>/`` directory, any file that
  defines or imports one of its named tests (read in both the working tree and
  ``HEAD``, so a deleted test still counts), the module such an import points
  at, and any ``conftest.py`` above one of those files. The runner and the merge
  gate add it to :func:`~codeframe.core.proof.scope.intersects`.
* **Weakening.** A test that still exists and still passes can have had its
  assertion replaced by ``assert True``. :func:`fingerprint` hashes the body of
  each named test (following an ``import … as`` pin to the function it
  imports), the runner records it when a requirement is first satisfied, and a
  later run fails the requirement when the body no longer matches.
  ``cf proof rebaseline`` is the recorded way to accept an intended change.

Everything here is static: ``ast`` over the files, ``git show`` for ``HEAD``.
Anything it cannot read or resolve makes a requirement *more* in scope, never
less.
"""

from __future__ import annotations

import ast
import configparser
import fnmatch
import glob
import hashlib
import logging
import os
import posixpath
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

logger = logging.getLogger(__name__)

#: Bumped if the canonical form below ever changes, so an old fingerprint
#: reads as "different scheme", not as a changed test.
FINGERPRINT_SCHEME = "v1"

#: Directories a test-file walk never descends into.
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", ".env", "node_modules",
    "__pycache__", "site-packages", ".tox", ".nox", "build", "dist",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".codeframe", ".eggs",
})

#: Directories skipped even when the project sets ``norecursedirs``: version
#: control and tool caches, which never hold the project's tests.
_NEVER_COLLECTED = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".codeframe",
})

#: ``from a import b as c`` chains followed before giving up (fails closed).
_MAX_IMPORT_HOPS = 5


def proof_dir(req_id: str) -> str:
    """The repo-relative directory capture writes a requirement's tests to."""
    return f"tests/proof/{req_id}"


_DEFAULT_PYTHON_FILES = ("test_*.py", "*_test.py")
_DEFAULT_PYTHON_CLASSES = ("Test",)


def _matches_prefix_or_glob(name: str, patterns: Iterable[str]) -> bool:
    """pytest's rule for ``python_classes``: a prefix, or a glob if it has one."""
    return any(
        name.startswith(p) or (any(c in p for c in "*?[") and fnmatch.fnmatch(name, p))
        for p in patterns
    )


def is_test_file(rel: str, python_files: Iterable[str] = _DEFAULT_PYTHON_FILES) -> bool:
    """A file pytest's ``python_files`` names, plus anything in ``tests/proof``."""
    name = posixpath.basename(rel)
    if not name.endswith(".py"):
        return False
    return rel.startswith("tests/proof/") or any(
        fnmatch.fnmatch(name, pattern) for pattern in python_files
    )


@dataclass(frozen=True)
class Collection:
    """The part of the project's pytest configuration that decides which files
    a bare ``pytest`` (how the runner invokes it, from the repo root) collects.

    ``testpaths`` is empty when unset: the whole tree. ``norecursedirs`` is
    ``None`` when unset, meaning only :data:`_SKIP_DIRS` applies; pytest's own
    default list is narrower than that set plus dot-directories, so leaving it
    out walks *more*, never less.

    Not exact, and only ever wider than pytest: ``addopts`` (``--ignore``,
    ``--ignore-glob``, ``--deselect``) and a conftest's ``collect_ignore`` are
    not read, so a same-named function in a file they exclude is still hashed.
    """

    testpaths: tuple[str, ...] = ()
    norecursedirs: Optional[tuple[str, ...]] = None
    python_files: tuple[str, ...] = _DEFAULT_PYTHON_FILES
    python_classes: tuple[str, ...] = _DEFAULT_PYTHON_CLASSES


def _ini_values(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return tuple(raw.split())
    if isinstance(raw, (list, tuple)):
        return tuple(str(v) for v in raw)
    return ()


#: Files whose pytest section can change what a bare ``pytest`` collects.
PYTEST_CONFIG_FILES = ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")


def _read_worktree(repo_root: Path) -> Callable[[str], Optional[str]]:
    def read(name: str) -> Optional[str]:
        path = Path(repo_root) / name
        return path.read_text(encoding="utf-8") if path.is_file() else None
    return read


def _pytest_section(read: Callable[[str], Optional[str]]) -> Optional[dict]:
    """The first pytest config section in pytest's own search order, or None.

    Order and "first file that has a section wins" follow pytest's rootdir
    lookup for the repo root itself: ``pytest.ini`` / ``.pytest.ini`` (which
    win even with no section), ``pyproject.toml``'s
    ``[tool.pytest.ini_options]``, ``tox.ini``'s ``[pytest]``, ``setup.cfg``'s
    ``[tool:pytest]``. ``read`` returns a root file's text, or None if absent,
    so the same lookup serves the working tree and ``HEAD``.
    """
    for name in ("pytest.ini", ".pytest.ini"):
        text = read(name)
        if text is not None:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(text)
            return dict(parser["pytest"]) if parser.has_section("pytest") else {}
    text = read("pyproject.toml")
    if text is not None:
        tool_pytest = tomllib.loads(text).get("tool", {}).get("pytest")
        if isinstance(tool_pytest, dict):
            legacy = tool_pytest.get("ini_options")
            if isinstance(legacy, dict):
                return legacy
            native = {k: v for k, v in tool_pytest.items() if k != "ini_options"}
            if native:  # pytest 9's native ``[tool.pytest]`` table
                return native
    for name, header in (("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")):
        text = read(name)
        if text is not None:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read_string(text)
            if parser.has_section(header):
                return dict(parser[header])
    return None


_CONFIG_ERRORS = (OSError, UnicodeDecodeError, configparser.Error, tomllib.TOMLDecodeError)


def collection(repo_root: Path) -> Collection:
    """Read :class:`Collection` from the repo root's pytest configuration.

    A file that cannot be read or parsed gives the default, which is the whole
    tree: a wider index can only make a fingerprint cover more, never let a
    collected test go unseen.
    """
    try:
        section = _pytest_section(_read_worktree(Path(repo_root)))
    except _CONFIG_ERRORS as exc:
        logger.debug("pytest config unreadable, indexing the whole tree: %s", exc)
        return Collection()
    if not section:
        return Collection()
    norecurse = section.get("norecursedirs")
    python_files = _ini_values(section.get("python_files")) or _DEFAULT_PYTHON_FILES
    python_classes = _ini_values(section.get("python_classes")) or _DEFAULT_PYTHON_CLASSES
    return Collection(
        testpaths=_ini_values(section.get("testpaths")),
        norecursedirs=_ini_values(norecurse) if norecurse is not None else None,
        python_files=python_files,
        python_classes=python_classes,
    )


def enforced_test_names(req) -> list[str]:
    """Every pytest-style ``must_pass`` rule name, across all gates."""
    seen: list[str] = []
    for rule in req.evidence_rules:
        if rule.must_pass and rule.test_id.startswith("test_") and rule.test_id not in seen:
            seen.append(rule.test_id)
    return seen


# --- Reading Python sources ------------------------------------------------


@dataclass(frozen=True)
class _Binding:
    """One way a module binds a name: a ``def``, a ``from … import``, or
    anything else (``opaque``: an assignment, a plain ``import … as``, a class)
    that static analysis cannot turn into a function body."""

    node: Optional[ast.AST] = None  # the FunctionDef, for a def
    module: Optional[str] = None  # for an import
    level: int = 0
    orig: Optional[str] = None
    opaque: bool = False
    #: Marks that decide which cases the def runs although they sit outside
    #: it: enclosing classes' decorators and ``pytestmark`` assignments in the
    #: module and those classes (a class-level parametrize, say).
    context: tuple = ()


def _pytestmarks(body: Iterable[ast.stmt]) -> list[ast.stmt]:
    """``pytestmark = …`` statements directly in ``body``, and in the
    if/try/with/for blocks there that ``_bindings`` also walks."""
    found: list[ast.stmt] = []
    for stmt in body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            if any("pytestmark" in _target_names(t) for t in targets):
                found.append(stmt)
        elif isinstance(stmt, (ast.If, ast.For, ast.AsyncFor)):
            found += _pytestmarks(stmt.body) + _pytestmarks(stmt.orelse)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            found += _pytestmarks(stmt.body)
        elif isinstance(stmt, ast.Try) or type(stmt).__name__ == "TryStar":
            found += _pytestmarks(stmt.body) + _pytestmarks(stmt.orelse)
            found += _pytestmarks(stmt.finalbody)
            for handler in stmt.handlers:
                found += _pytestmarks(handler.body)
    return found


def _target_names(target: ast.AST) -> list[str]:
    """Names an assignment target binds (``a``, ``a, b``, ``[a, *b]``)."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _target_names(elt)]
    return []


def _bindings(
    source: str, python_classes: tuple[str, ...] = _DEFAULT_PYTHON_CLASSES
) -> dict[str, list[_Binding]]:
    """Names a module binds to a function or an imported object.

    Module-level ``def``, and ``def`` in a class pytest collects (its name
    matches ``python_classes``; nested ones too) since pytest collects test
    methods by the same name; inside ``if``/``try``/``with`` blocks too; and
    module-level ``from … import``. A same-named method on a helper class is
    not the test pytest runs, so it is left out. Raises ``SyntaxError`` like
    ``ast.parse``.
    """
    out: dict[str, list[_Binding]] = {}

    def opaque(name: str) -> None:
        out.setdefault(name, []).append(_Binding(opaque=True))

    def visit(body: Iterable[ast.stmt], in_class: bool, context: tuple = ()) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(stmt.name, []).append(_Binding(node=stmt, context=context))
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
                # ``test_x = lambda: None`` after ``def test_x`` replaces the
                # test pytest runs; fingerprinting the def would bless that.
                targets = (
                    stmt.targets if isinstance(stmt, (ast.Assign, ast.Delete))
                    else [stmt.target]
                )
                for target in targets:
                    for name in _target_names(target):
                        opaque(name)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    opaque(alias.asname or alias.name.split(".")[0])
            elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                for name in _target_names(stmt.target):
                    opaque(name)
                visit(stmt.body, in_class, context)
                visit(stmt.orelse, in_class, context)
            elif isinstance(stmt, ast.ClassDef):
                opaque(stmt.name)
                # pytest also collects a unittest.TestCase subclass whatever
                # its name, and a base may be a TestCase two modules away, so
                # any class with a real base counts: wider, never narrower.
                has_base = any(
                    not (isinstance(b, ast.Name) and b.id == "object") for b in stmt.bases
                )
                if has_base or _matches_prefix_or_glob(stmt.name, python_classes):
                    visit(
                        stmt.body, True,
                        context + tuple(stmt.decorator_list) + tuple(_pytestmarks(stmt.body)),
                    )
            elif isinstance(stmt, ast.ImportFrom) and not in_class:
                for alias in stmt.names:
                    if alias.name == "*":
                        continue
                    # The importing module's marks apply to the test it
                    # collects, wherever the def itself lives.
                    out.setdefault(alias.asname or alias.name, []).append(_Binding(
                        module=stmt.module, level=stmt.level, orig=alias.name,
                        context=context,
                    ))
            elif isinstance(stmt, (ast.If, ast.With, ast.AsyncWith)):
                for item in getattr(stmt, "items", []):
                    if item.optional_vars is not None:
                        for name in _target_names(item.optional_vars):
                            opaque(name)
                visit(stmt.body, in_class, context)
                visit(getattr(stmt, "orelse", []), in_class, context)
            elif isinstance(stmt, ast.Try) or type(stmt).__name__ == "TryStar":
                visit(stmt.body, in_class, context)
                for handler in stmt.handlers:
                    visit(handler.body, in_class, context)
                visit(stmt.orelse, in_class, context)
                visit(stmt.finalbody, in_class, context)

    module = ast.parse(source).body
    visit(module, False, tuple(_pytestmarks(module)))
    return out


def _canonical(node: object) -> str:
    """A serialization of an AST that is stable across Python versions.

    ``ast.dump`` is not: 3.13 stopped printing empty lists and ``None`` fields,
    and 3.12 added ``type_params``. Omitting every empty value on both sides
    makes those differences vanish. Positions are never included, so
    reformatting a test and editing its comments do not change it.
    """
    if isinstance(node, ast.AST):
        parts = []
        for name in node._fields:
            value = getattr(node, name, None)
            if value is None or value == []:
                continue
            if name == "type_comment":
                continue
            parts.append(f"{name}={_canonical(value)}")
        return f"{type(node).__name__}({','.join(parts)})"
    if isinstance(node, list):
        return "[" + ",".join(_canonical(v) for v in node) + "]"
    return repr(node)


def _def_digest(node: ast.AST, context: tuple = ()) -> str:
    """Digest of one test function: decorators, signature and body, plus the
    marks around it (``_Binding.context``) when there are any.

    A leading docstring is dropped, so documenting a test is not a change to
    what it proves.
    """
    body = list(getattr(node, "body", []))
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    shadow = type(node)(**{f: getattr(node, f, None) for f in node._fields})
    shadow.body = body
    text = _canonical(shadow)
    if context:
        text += "|context=" + _canonical(list(context))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Sources:
    """Cached reads of repo files, from the working tree or ``HEAD``."""

    def __init__(
        self, repo_root: Path, python_classes: tuple[str, ...] = _DEFAULT_PYTHON_CLASSES
    ):
        self.root = repo_root
        self.python_classes = python_classes
        self._text: dict[tuple[str, str], Optional[str]] = {}
        self._parsed: dict[tuple[str, str], Optional[dict[str, list[_Binding]]]] = {}

    def text(self, rel: str, version: str) -> Optional[str]:
        key = (rel, version)
        if key not in self._text:
            self._text[key] = self._read(rel, version)
        return self._text[key]

    def _read(self, rel: str, version: str) -> Optional[str]:
        if version == "worktree":
            try:
                return (self.root / rel).read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                return None
        try:
            result = subprocess.run(
                ["git", "show", f"HEAD:{rel}"],
                cwd=self.root, capture_output=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("git show HEAD:%s failed: %s", rel, exc)
            return None
        if result.returncode != 0:
            # Usual for a file new since HEAD; logged for "why is this not in scope?"
            logger.debug(
                "git show HEAD:%s exited %d: %s", rel, result.returncode,
                result.stderr.decode("utf-8", errors="replace").strip(),
            )
            return None
        return result.stdout.decode("utf-8", errors="replace")

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def bindings(self, rel: str, version: str) -> Optional[dict[str, list[_Binding]]]:
        """``None`` when the file is absent; ``{}`` when it does not parse."""
        key = (rel, version)
        if key not in self._parsed:
            text = self.text(rel, version)
            if text is None:
                self._parsed[key] = None
            else:
                try:
                    self._parsed[key] = _bindings(text, self.python_classes)
                except (SyntaxError, ValueError, RecursionError):
                    self._parsed[key] = {}
        return self._parsed[key]


def _basedir(directory: str, sources: Optional["_Sources"]) -> str:
    """The directory pytest's default ``prepend`` import mode puts on
    ``sys.path`` for a module in ``directory``: the first one up that is not a
    package (has no ``__init__.py``)."""
    while directory and sources is not None and sources.exists(
        posixpath.join(directory, "__init__.py")
    ):
        directory = posixpath.dirname(directory)
    return directory


def _module_paths(
    importer: str, module: Optional[str], level: int, sources: Optional["_Sources"] = None
) -> list[str]:
    """Repo-relative files an import could name; the caller checks existence.

    Absolute imports are tried where pytest's ``prepend`` mode makes them
    importable: the importing test module's basedir, the basedir of each
    ``conftest.py`` above it, then the repo root and ``src/`` (rootdir
    insertion and an installed package). So a non-package ``tests/`` that
    does ``from test_original import …`` resolves to ``tests/test_original.py``.
    """
    parts = module.split(".") if module else []
    if level:
        base = posixpath.dirname(importer)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        roots = [base]
    else:
        roots = [_basedir(posixpath.dirname(importer), sources)]
        directory = posixpath.dirname(importer)
        while directory:
            if sources is not None and sources.exists(posixpath.join(directory, "conftest.py")):
                roots.append(_basedir(directory, sources))
            directory = posixpath.dirname(directory)
        roots += ["", "src"]
        roots = list(dict.fromkeys(roots))
    out = []
    for root in roots:
        stem = posixpath.join(root, *parts) if parts else root
        if not stem:
            continue
        if stem + ".py" in out:
            continue
        # In one directory a package wins over a module of the same name.
        out.append(posixpath.join(stem, "__init__.py"))
        out.append(stem + ".py")
    return out


# --- Locating a test, and fingerprinting it --------------------------------


@dataclass
class Located:
    """Where a named test is defined, and its fingerprint.

    ``fingerprint`` is ``None`` when the name is bound nowhere, or bound by an
    import that cannot be followed to a function. ``files`` holds every file
    the search passed through either way: the definitions, and each module an
    import named.
    """

    fingerprint: Optional[str] = None
    files: set[str] = field(default_factory=set)


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class TestIndex:
    """The working tree's test files, scanned once and only on demand."""

    __test__ = False  # not a pytest class, whatever its name says

    def __init__(self, repo_root: Path, sources: Optional[_Sources] = None):
        self.root = Path(repo_root)
        self.config = collection(self.root)
        self.sources = sources or _Sources(self.root, self.config.python_classes)
        self._files: Optional[list[str]] = None
        self._by_name: Optional[dict[str, list[str]]] = None

    def test_files(self) -> list[str]:
        """The test files a bare ``pytest`` in the repo root collects.

        A same-named function in a file pytest never collects (an
        ``examples/`` tree outside ``testpaths``, say) is not the test the
        verdict came from, so hashing it would report a change to evidence
        that did not change. ``tests/proof/`` is always included: capture
        writes pins there.
        """
        if self._files is None:
            config = self.config
            found: set[str] = set()
            for start in self._starts(config.testpaths) + [self.root / "tests" / "proof"]:
                self._walk(start, config, found)
            self._files = sorted(found)
        return self._files

    def _starts(self, testpaths: tuple[str, ...]) -> list[Path]:
        if not testpaths:
            return [self.root]
        starts: list[Path] = []
        for pattern in testpaths:
            # pytest expands globs in testpaths (7.0+); a plain path globs to itself.
            for match in sorted(glob.glob(str(self.root / pattern), recursive=True)):
                starts.append(Path(match))
        return starts

    def _walk(self, start: Path, config: Collection, found: set[str]) -> None:
        def skipped(parent: str, d: str) -> bool:
            if config.norecursedirs is None:
                return d in _SKIP_DIRS or d.endswith(".egg-info")
            # A configured norecursedirs replaces pytest's defaults, so our own
            # list must not narrow it: a test under build/ that pytest collects
            # has to be indexed. Only what pytest itself never enters stays out
            # (VCS and cache dirs, and a virtualenv, which pytest detects).
            if d in _NEVER_COLLECTED or (Path(parent, d) / "pyvenv.cfg").is_file():
                return True
            full = Path(parent, d).as_posix()
            # pytest's fnmatch_ex: a bare pattern matches the basename, one with
            # a separator matches the end of the full path.
            return any(
                fnmatch.fnmatch(full, "*/" + pattern) if "/" in pattern
                else fnmatch.fnmatch(d, pattern)
                for pattern in config.norecursedirs
            )

        if start.is_file():
            try:
                rel = start.relative_to(self.root).as_posix()
            except ValueError:
                return
            if rel.endswith(".py"):
                found.add(rel)  # pytest collects a file named in testpaths outright
            return
        if not start.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(d for d in dirnames if not skipped(dirpath, d))
            try:
                rel_dir = Path(dirpath).relative_to(self.root).as_posix()
            except ValueError:
                continue  # a testpath outside the repo is not ours to index
            for name in filenames:
                rel = name if rel_dir == "." else f"{rel_dir}/{name}"
                if is_test_file(rel, config.python_files):
                    found.add(rel)

    def files_naming(self, name: str) -> list[str]:
        """Test files in which ``name`` appears as an identifier.

        Built in one pass over every test file, so locating N names costs one
        scan plus N lookups rather than N scans (a ratchet ledger can name
        thousands of tests). A file that never spells the name cannot bind it.
        """
        if self._by_name is None:
            by_name: dict[str, list[str]] = {}
            for rel in self.test_files():
                text = self.sources.text(rel, "worktree")
                if text is None:
                    continue
                for ident in set(_IDENT.findall(text)):
                    by_name.setdefault(ident, []).append(rel)
            self._by_name = by_name
        return self._by_name.get(name, [])

    def locate(self, name: str) -> Located:
        located = Located()
        digests: list[str] = []
        resolvable = True
        for rel in self.files_naming(name):
            for binding in (self.sources.bindings(rel, "worktree") or {}).get(name, []):
                ok = _follow(self.sources, rel, binding, ("worktree",), located.files, digests, 0)
                resolvable = resolvable and ok
        if digests and resolvable:
            joined = "\n".join(sorted(digests))
            located.fingerprint = (
                f"{FINGERPRINT_SCHEME}:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()
            )
        return located


def _follow(
    sources: _Sources,
    rel: str,
    binding: _Binding,
    versions: tuple[str, ...],
    files: set[str],
    digests: Optional[list[str]],
    hops: int,
    outer: tuple = (),
) -> bool:
    """Record ``rel`` and everything ``binding`` leads to; False if it dead-ends.

    ``digests`` collects one digest per function reached, when the caller wants
    a fingerprint. Imports are followed into whichever of ``versions`` holds
    the target module, so a scope check sees a module as it was at ``HEAD``
    too.

    ``outer`` holds the marks of the module that collects the test, carried
    through its imports: pytest applies them to whatever function the import
    hands over.
    """
    files.add(rel)
    if binding.opaque:
        return False  # bound to something that is not a function body we can read
    if binding.node is not None:
        if digests is not None:
            digests.append(_def_digest(binding.node, outer + binding.context))
        return True
    if hops >= _MAX_IMPORT_HOPS or binding.orig is None:
        return False
    if hops == 0:
        outer = binding.context
    reached = False
    dead_end = False
    for target in _module_paths(rel, binding.module, binding.level, sources):
        found = False
        for version in versions:
            target_bindings = sources.bindings(target, version)
            if target_bindings is None:
                continue
            found = True
            files.add(target)
            for nxt in target_bindings.get(binding.orig, []):
                # Every binding must resolve: one def beside a rebinding of the
                # same name is not the function the import hands over.
                if _follow(
                    sources, target, nxt, versions, files, digests, hops + 1, outer
                ):
                    reached = True
                else:
                    dead_end = True
            break  # the first version that has the module answers for it
        if found and digests is not None:
            # A fingerprint follows the module Python would import: the first
            # candidate on the path. A scope check (no digests) keeps going,
            # since naming one file too many only costs a re-run.
            break
    return reached and not dead_end


def fingerprint(repo_root: Path, name: str, index: Optional[TestIndex] = None) -> Located:
    """Locate and fingerprint the test named ``name`` in the working tree."""
    return (index or TestIndex(repo_root)).locate(name)


# --- Scope -----------------------------------------------------------------


def _norm(path: str) -> str:
    return posixpath.normpath(path.strip())


def _under(path: str, directory: str) -> bool:
    return directory in ("", ".") or path == directory or path.startswith(directory + "/")


class EvidenceScope:
    """Whether a set of changed files touches a requirement's tests.

    Built once per run from the changed file list. ``stored_files`` lets the
    caller add where a requirement's tests were found when it was satisfied,
    which still names a file after the definition in it has been deleted.
    """

    def __init__(
        self,
        repo_root: Path,
        changed_files: Iterable[str],
        *,
        local_diff: bool = True,
    ):
        """``local_diff`` says the changed files are this checkout's own
        working-tree changes, so ``HEAD`` and the working tree hold both sides
        of them. The merge gate passes a PR's file list instead, whose
        revisions are not here; a pytest config file named there then counts
        as changed without a comparison.
        """
        self.root = Path(repo_root)
        self.local_diff = local_diff
        self.sources = _Sources(self.root, collection(self.root).python_classes)
        self.changed = {_norm(f) for f in changed_files if f}
        self.changed_py = sorted(f for f in self.changed if f.endswith(".py"))
        self.changed_conftests = [
            posixpath.dirname(f) for f in self.changed
            if posixpath.basename(f) == "conftest.py"
        ]
        self._config_changed: Optional[bool] = None

    def pytest_config_changed(self) -> bool:
        """Whether the effective pytest section differs between ``HEAD`` and the
        working tree. It decides what pytest collects (``python_functions``,
        ``testpaths``, ``addopts``…), so changing it can drop a test without
        touching any Python file. A dependency bump in ``pyproject.toml``
        leaves the section alone and does not count; anything unreadable on
        either side does, and so does any config file in a change whose
        revisions are not in this checkout (``local_diff=False``).
        """
        if self._config_changed is None:
            if not any(f in PYTEST_CONFIG_FILES for f in self.changed):
                self._config_changed = False
            elif not self.local_diff:
                self._config_changed = True
            else:
                try:
                    self._config_changed = _pytest_section(
                        lambda name: self.sources.text(name, "worktree")
                    ) != _pytest_section(lambda name: self.sources.text(name, "HEAD"))
                except _CONFIG_ERRORS as exc:
                    logger.debug("pytest config unreadable, treating it as changed: %s", exc)
                    self._config_changed = True
        return self._config_changed

    def evidence_files(self, req, stored_files: Iterable[str] = ()) -> set[str]:
        """Files that define, import or pin ``req``'s named tests.

        Read from the changed Python files (working tree and ``HEAD``) and the
        requirement's proof directory; the files there point onward through
        their imports. Unchanged files elsewhere are not scanned: a change can
        only touch evidence by changing one of the files named here.
        """
        names = enforced_test_names(req)
        files: set[str] = {_norm(f) for f in stored_files}
        candidates = list(self.changed_py)
        pdir = proof_dir(req.id)
        pdir_path = self.root / pdir
        if pdir_path.is_dir():
            for path in sorted(pdir_path.rglob("*.py")):
                rel = path.relative_to(self.root).as_posix()
                if rel not in candidates:
                    candidates.append(rel)
        for rel in candidates:
            for version in ("worktree", "HEAD"):
                text = self.sources.text(rel, version)
                if text is None or not any(n in text for n in names):
                    continue
                bound = self.sources.bindings(rel, version) or {}
                for name in names:
                    for binding in bound.get(name, []):
                        _follow(
                            self.sources, rel, binding, ("worktree", "HEAD"),
                            files, None, 0,
                        )
        return files

    def touches(self, req, stored_files: Iterable[str] = ()) -> bool:
        if not self.changed:
            return False
        pdir = proof_dir(req.id)
        if any(_under(f, pdir) for f in self.changed):
            return True
        if enforced_test_names(req) and self.pytest_config_changed():
            return True
        if not self.changed_py:
            # Past the pytest config, only a Python file can define, import
            # or neuter a test.
            return False
        evidence = self.evidence_files(req, stored_files)
        if evidence & self.changed:
            return True
        # A conftest above a test can neuter it (an autouse fixture, a hook
        # that skips) without touching the test file itself.
        anchors = evidence | {pdir + "/"}
        return any(
            _under(anchor, conftest_dir)
            for conftest_dir in self.changed_conftests
            for anchor in anchors
        )
