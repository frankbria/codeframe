"""UnicodeDecodeError escaped OSError-shaped handlers across 57 sites (#1029).

`subprocess.run(..., text=True)` decodes with the **locale** encoding and no
error handler, and `Path.read_text()` does the same. Both raise
`UnicodeDecodeError`, which is a `ValueError` and **not** an `OSError` — so it
slips straight past the handler people reach for:

    except (OSError, subprocess.SubprocessError):   # does not catch it
    except (OSError, json.JSONDecodeError):         # does not catch it

Modern Python coerces a C locale to C.UTF-8 (PEP 538), which hides this on a
normal developer machine. It does not hide it in a container or a systemd unit
running `LANG=C` on an image without C.UTF-8 — where kilo 7.x's box-drawing help
banner crashed `build_command` outright (#1015), and codex's auth.json did the
same (#1010). Both were found by review, not by search.

The fix is uniform: pin `encoding="utf-8"` at every site, and add
`errors="replace"` wherever the content is arbitrary third-party output. The
tests below prove the mechanism, enforce the invariant across the tree so a new
call site cannot reintroduce it, and — for AC4 — force a non-UTF-8
`locale.getpreferredencoding()` so the guard cannot regress silently.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE = REPO_ROOT / "codeframe"

#: Byte 0x80 is invalid in UTF-8 and undecodable in ASCII — the shape of the
#: box-drawing characters that broke the kilo adapter.
UNDECODABLE = b"ok \x80\xff bad\n"


class TestTheMechanism:
    """Why an `except OSError` was never going to be enough."""

    def test_a_decode_error_is_a_value_error_not_an_os_error(self):
        with pytest.raises(ValueError):
            UNDECODABLE.decode("utf-8")

        assert not issubclass(UnicodeDecodeError, OSError)
        assert issubclass(UnicodeDecodeError, ValueError)

    def test_the_handler_people_reach_for_does_not_catch_it(self):
        """Written out because this is the whole defect."""
        with pytest.raises(UnicodeDecodeError):
            try:
                UNDECODABLE.decode("utf-8")
            except (OSError, subprocess.SubprocessError):
                pytest.fail("this handler is not supposed to be reachable")

    def test_replace_never_raises(self):
        assert UNDECODABLE.decode("utf-8", errors="replace")


class TestDecodeHostileOutputUnderANonUtf8Locale:
    """AC4. `PYTHONCOERCECLOCALE=0` + `PYTHONUTF8=0` defeats PEP 538/540, so the
    child really does get an ASCII preferred encoding — the condition that makes
    this bug live rather than latent.
    """

    HOSTILE_ENV = {
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONCOERCECLOCALE": "0",
        "PYTHONUTF8": "0",
        "PATH": "/usr/bin:/bin",
    }

    def _child(self, body: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", body],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.HOSTILE_ENV,
            timeout=60,
        )

    @pytest.fixture(autouse=True)
    def _require_a_non_utf8_locale(self):
        """If the interpreter still reports UTF-8 under this environment the
        tests below would pass vacuously. Skip loudly instead of pretending."""
        probe = self._child(
            "import locale; print(locale.getpreferredencoding(False))"
        )
        if "utf" in probe.stdout.strip().lower():
            pytest.skip(
                f"could not force a non-UTF-8 locale (got {probe.stdout.strip()!r})"
            )

    def test_the_environment_really_is_hostile(self):
        """The premise, asserted rather than assumed."""
        probe = self._child("import locale; print(locale.getpreferredencoding(False))")

        assert "utf" not in probe.stdout.strip().lower()

    def test_text_true_alone_raises_there(self):
        """Reproducing the reported failure, so the fix below is not solving a
        problem that no longer exists."""
        out = self._child(
            "import subprocess, sys\n"
            "try:\n"
            "    subprocess.run([sys.executable, '-c',"
            " \"import sys; sys.stdout.buffer.write(b'\\\\x80\\\\xff')\"],"
            " capture_output=True, text=True)\n"
            "    print('NO-RAISE')\n"
            "except UnicodeDecodeError:\n"
            "    print('RAISED')\n"
        )

        assert out.stdout.strip() == "RAISED", out.stderr[-800:]

    def test_our_kwargs_survive_it(self):
        """The same call with the kwargs this issue adds everywhere."""
        out = self._child(
            "import subprocess, sys\n"
            "r = subprocess.run([sys.executable, '-c',"
            " \"import sys; sys.stdout.buffer.write(b'ok\\\\x80\\\\xff')\"],"
            " capture_output=True, text=True, encoding='utf-8', errors='replace')\n"
            "print('OK' if r.stdout.startswith('ok') else 'BAD')\n"
        )

        assert out.stdout.strip() == "OK", out.stderr[-800:]

    def test_read_text_with_a_pinned_encoding_survives_it(self, tmp_path):
        target = tmp_path / "hostile.txt"
        target.write_bytes(UNDECODABLE)

        out = self._child(
            "from pathlib import Path\n"
            f"p = Path({str(target)!r})\n"
            "try:\n"
            "    p.read_text()\n"
            "    print('NO-RAISE')\n"
            "except UnicodeDecodeError:\n"
            "    print('RAISED')\n"
            "print(p.read_text(encoding='utf-8', errors='replace').startswith('ok'))\n"
        )

        assert out.stdout.split() == ["RAISED", "True"], out.stderr[-800:]

    def test_the_agents_run_command_tool_survives_undecodable_output(self, tmp_path):
        """End to end through the product's own code, not a synthetic call.

        `_execute_run_command` backs the ReAct agent's shell tool, so it handles
        the least predictable output in the system — and it is the path that
        crashed for real in #1015.
        """
        script = tmp_path / "noisy.py"
        script.write_text(
            "import sys; sys.stdout.buffer.write(b'start \\x80\\xff end')\n"
        )

        out = self._child(
            "import sys\n"
            f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
            "from pathlib import Path\n"
            "from codeframe.core.tools import _execute_run_command\n"
            "r = _execute_run_command(\n"
            f"    {{'command': 'python {script.name}'}}, Path({str(tmp_path)!r}), 'tc-1'\n"
            ")\n"
            "print('SURVIVED')\n"
        )

        assert "SURVIVED" in out.stdout, out.stderr[-1500:]


def _text_true_calls():
    """(path, lineno, kwargs) for every call passing text=True under codeframe/."""
    for path in sorted(PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "text=True" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            kwargs = {k.arg for k in node.keywords}
            if any(
                k.arg == "text" and getattr(k.value, "value", None) is True
                for k in node.keywords
            ):
                yield path.relative_to(REPO_ROOT), node.lineno, kwargs


def _read_text_calls():
    for path in sorted(PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if ".read_text(" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "read_text"
            ):
                yield path.relative_to(REPO_ROOT), node.lineno, {
                    k.arg for k in node.keywords
                }


class TestNoCallSiteCanReintroduceIt:
    """AC5 as a lint rule rather than a `run_text()` helper.

    A helper only protects the sites that adopt it; this fails on any new one.
    It is also the cheaper change — 57 call sites keep their own signatures
    instead of being funnelled through a wrapper that would have to forward
    cwd, env, timeout, check, input and stdin.
    """

    def test_there_are_call_sites_to_check(self):
        """An empty sweep satisfies "all of them are safe"."""
        assert len(list(_text_true_calls())) > 50
        assert len(list(_read_text_calls())) > 25

    def test_every_text_true_call_pins_utf8_and_replaces(self):
        bad = [
            f"{path}:{line}"
            for path, line, kwargs in _text_true_calls()
            if not {"encoding", "errors"} <= kwargs
        ]

        assert not bad, (
            "these decode with the locale encoding and will raise "
            "UnicodeDecodeError under LANG=C:\n  " + "\n  ".join(bad)
        )

    def test_every_read_text_call_pins_an_encoding(self):
        """`errors` is deliberately NOT required here. Files we wrote ourselves
        stay strict, so genuine corruption still surfaces — as a ValueError,
        which the handlers around them catch."""
        bad = [
            f"{path}:{line}"
            for path, line, kwargs in _read_text_calls()
            if "encoding" not in kwargs
        ]

        assert not bad, (
            "these decode with the locale encoding:\n  " + "\n  ".join(bad)
        )

    def test_the_rule_matches_a_deliberately_bad_call(self, tmp_path):
        """A lint rule that cannot fail is worth nothing. Parse a file with an
        unprotected call and confirm the same predicate flags it."""
        source = "import subprocess\nsubprocess.run(['x'], text=True)\n"
        found = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and any(
                k.arg == "text" and getattr(k.value, "value", None) is True
                for k in node.keywords
            ):
                kwargs = {k.arg for k in node.keywords}
                if not {"encoding", "errors"} <= kwargs:
                    found.append(node.lineno)

        assert found == [2]


class TestHandlersAroundAStrictReadCatchValueError:
    """AC3. `errors="replace"` means a subprocess can no longer raise, but a
    strict `read_text` still can — so anything defensive around one must catch
    `ValueError`, not just `OSError`."""

    def _narrow_handlers(self):
        import re

        for path in sorted(PACKAGE.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source)):
                if not isinstance(node, ast.Try):
                    continue
                body = "\n".join(ast.unparse(s) for s in node.body)
                if not re.search(r"read_text\(encoding='utf-8'\)", body):
                    continue
                # A try whose LAST handler is broad is already covered.
                caught: set[str] = set()
                for handler in node.handlers:
                    if handler.type is None:
                        caught.add("Exception")
                        continue
                    parts = (
                        handler.type.elts
                        if isinstance(handler.type, ast.Tuple)
                        else [handler.type]
                    )
                    caught |= {ast.unparse(p) for p in parts}
                # `json.JSONDecodeError` is deliberately NOT in this set. It
                # is a SIBLING of UnicodeDecodeError under ValueError, not a
                # parent, so catching it does nothing for a decode error.
                # Treating it as sufficient is what let proof/runner.py through
                # the first audit — found in review, not by this test.
                if not caught & {
                    "Exception",
                    "BaseException",
                    "ValueError",
                    "UnicodeDecodeError",
                }:
                    yield f"{path.relative_to(REPO_ROOT)}:{node.lineno}"

    def test_no_strict_read_is_wrapped_in_an_os_error_only_handler(self):
        narrow = list(self._narrow_handlers())

        assert not narrow, (
            "a UnicodeDecodeError would escape these:\n  " + "\n  ".join(narrow)
        )

    def test_json_decode_error_does_not_cover_a_decode_error(self):
        """The relationship that made the first audit miss a site.

        `json.JSONDecodeError` and `UnicodeDecodeError` are SIBLINGS under
        `ValueError`, not parent and child. An `except (OSError,
        json.JSONDecodeError)` around a strict read therefore catches nothing
        that matters, while reading as though it were defensive.
        """
        import json

        assert issubclass(json.JSONDecodeError, ValueError)
        assert not issubclass(UnicodeDecodeError, json.JSONDecodeError)

    def test_a_corrupt_proof_config_falls_back_to_defaults(self, tmp_path):
        """The site both reviewers found and the first audit let through: one
        non-UTF-8 byte in proof_config.json crashed `cf proof run` outright
        instead of using defaults."""
        from codeframe.core.proof.models import PROOF_CONFIG_FILENAME
        from codeframe.core.proof.runner import _load_proof_config
        from codeframe.core.workspace import create_or_load_workspace

        workspace = create_or_load_workspace(tmp_path)
        config = tmp_path / ".codeframe" / PROOF_CONFIG_FILENAME
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_bytes(b'{"enabled_gates": ["\x80\xff"]}')

        enabled, strictness = _load_proof_config(workspace)

        assert enabled is None
        assert strictness == "strict"

    def test_the_machine_id_read_falls_through_instead_of_crashing(self, monkeypatch):
        """The one this audit actually found. A non-UTF-8 /etc/machine-id used
        to crash credential-key derivation outright; it must fall through to the
        portable identifiers."""
        from codeframe.core import credentials

        real_read_text = Path.read_text

        def hostile(self, *args, **kwargs):
            if str(self) == "/etc/machine-id":
                raise UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", hostile)
        monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/etc/machine-id")

        key = credentials._get_machine_id()

        assert key, "machine-id derivation crashed on an undecodable file"


class TestAnExportedPatchIsByteFaithful:
    """Raised in review, and the one place where "a mangled character beats a
    crash" is the WRONG trade.

    `export_patch` captured `git diff` with `errors="replace"` and persisted the
    result with `write_text` — no encoding, so it re-encoded with the locale.
    A single undecodable byte in a tracked file therefore produced either a
    patch that silently does not round-trip (U+FFFD written into the file, while
    PATCH_EXPORTED reports success) or, under LANG=C, a UnicodeEncodeError on
    the very character the lossy read had just introduced — moving the crash
    from the read to the write.

    A patch is byte-faithful by definition: it is written back out and fed to
    `git apply`. So this path captures bytes and writes bytes.
    """

    @pytest.fixture
    def repo_with_a_latin1_byte(self, tmp_path):
        """A committed file, then an edit introducing a byte that is not valid
        UTF-8 — a Latin-1 comment, or a stray byte from a bad merge."""
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path)
        target = tmp_path / "notes.txt"
        target.write_bytes(b"original\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
        target.write_bytes(b"caf\xe9 latin-1\n")
        return tmp_path

    def test_the_exported_patch_still_applies(self, repo_with_a_latin1_byte):
        """The claim that matters. A patch with U+FFFD substituted for the
        original byte does not restore the file."""
        from codeframe.core import artifacts
        from codeframe.core.workspace import create_or_load_workspace

        workspace = create_or_load_workspace(repo_with_a_latin1_byte)
        info = artifacts.export_patch(workspace)

        # Reset the tree, then apply the exported patch back onto it.
        subprocess.run(
            ["git", "checkout", "--", "notes.txt"],
            cwd=repo_with_a_latin1_byte,
            check=True,
        )
        applied = subprocess.run(
            ["git", "apply", str(info.path)],
            cwd=repo_with_a_latin1_byte,
            capture_output=True,
        )

        assert applied.returncode == 0, applied.stderr[-500:]
        assert (repo_with_a_latin1_byte / "notes.txt").read_bytes() == (
            b"caf\xe9 latin-1\n"
        ), "the patch round-tripped to different bytes"

    def test_the_undecodable_byte_survives_into_the_patch_file(
        self, repo_with_a_latin1_byte
    ):
        """Directly: the raw byte is present and no replacement character is."""
        from codeframe.core import artifacts
        from codeframe.core.workspace import create_or_load_workspace

        workspace = create_or_load_workspace(repo_with_a_latin1_byte)
        info = artifacts.export_patch(workspace)

        written = Path(info.path).read_bytes()
        assert b"\xe9" in written, "the original byte was lost"
        assert "�".encode() not in written, "a replacement character was written"

    def test_a_plain_ascii_diff_is_unaffected(self, tmp_path):
        """The control — the ordinary path must still work."""
        from codeframe.core import artifacts
        from codeframe.core.workspace import create_or_load_workspace

        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path)
        (tmp_path / "a.txt").write_text("one\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
        (tmp_path / "a.txt").write_text("two\n")

        info = artifacts.export_patch(create_or_load_workspace(tmp_path))

        assert "two" in Path(info.path).read_text(encoding="utf-8")

    def test_nothing_decodes_what_it_is_about_to_persist(self):
        """The rule, not just this instance. `errors="replace"` is right for
        display and parsing and wrong for anything written back out."""
        import inspect

        from codeframe.core import artifacts

        source = inspect.getsource(artifacts.export_patch)
        code = "\n".join(line.split("#")[0] for line in source.splitlines())

        assert "write_bytes(" in code
        assert "write_text(" not in code, "the patch is persisted through a decode"
