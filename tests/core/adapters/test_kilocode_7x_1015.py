"""The kilocode adapter must match the CLI that is actually installed (#1015 / P0.30).

`@kilocode/cli` was rewritten between 0.22.0 (2026-01-15) and 7.x (2026-07-29) —
213 releases apart — and the two invocations share nothing:

|            | 0.22.0                          | 7.4.17                     |
|------------|---------------------------------|----------------------------|
| usage      | `kilocode [options] [prompt]`   | `kilo run [message..]`     |
| workspace  | `--workspace <path>`            | `--dir <path>`             |
| `--auto`   | "run in autonomous mode"        | **"auto-approve ALL perms"**|

That last row is why this could not be a rename. On 7.x `--auto` *is* the old
`--yolo` — the permission bypass #916 established must stay off — so carrying
the flag across would have silently upgraded the adapter into a bypass while
looking like a cosmetic fix.

Detection reads the CLI's own `--help`, never a version string (the issue's AC3),
and is matched against **verbatim captured help from both real CLIs** in
`fixtures/kilocode_help/` rather than text invented here.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from codeframe.core.adapters import kilocode as kilo_mod
from codeframe.core.adapters.kilocode import KilocodeAdapter

pytestmark = pytest.mark.v2

_FIXTURES = Path(__file__).parent / "fixtures" / "kilocode_help"
_LEGACY_HELP = (_FIXTURES / "help-0.22.0.txt").read_text()
_MODERN_HELP = (_FIXTURES / "help-7.4.17.txt").read_text()


@pytest.fixture(autouse=True)
def _clear_surface_cache():
    kilo_mod._SURFACE_CACHE.clear()
    yield
    kilo_mod._SURFACE_CACHE.clear()


@pytest.fixture
def adapter():
    a = KilocodeAdapter.__new__(KilocodeAdapter)
    a._binary_path = "/usr/local/bin/kilo"
    a._cli_args = []
    return a


def _with_help(monkeypatch, help_text: str) -> None:
    class _Proc:
        stdout = help_text
        stderr = ""

    monkeypatch.setattr(kilo_mod.subprocess, "run", lambda *a, **k: _Proc())


# ---------------------------------------------------------------------------
# Detection, against the real help text of both CLIs
# ---------------------------------------------------------------------------


def test_the_modern_cli_is_detected(monkeypatch):
    _with_help(monkeypatch, _MODERN_HELP)
    assert kilo_mod._detect_surface("/usr/local/bin/kilo") == kilo_mod._MODERN


def test_the_legacy_cli_is_detected(monkeypatch):
    _with_help(monkeypatch, _LEGACY_HELP)
    assert kilo_mod._detect_surface("/usr/local/bin/kilo") == kilo_mod._LEGACY


def test_detection_does_not_read_a_version_string(monkeypatch):
    """AC3: never guessed from a version. A legacy CLI reporting a high version
    number must still be driven the legacy way."""
    _with_help(monkeypatch, "kilocode 7.9.9\n" + _LEGACY_HELP)
    assert kilo_mod._detect_surface("/usr/local/bin/kilo") == kilo_mod._LEGACY


def test_an_unreadable_help_falls_back_to_modern(monkeypatch):
    """Modern is what a new install gets, and its `run` fails loudly rather than
    opening the TUI that hung until timeout in #1012."""
    def _boom(*a, **k):
        raise OSError("cannot exec")

    monkeypatch.setattr(kilo_mod.subprocess, "run", _boom)
    assert kilo_mod._detect_surface("/usr/local/bin/kilo") == kilo_mod._MODERN


def test_detection_is_cached(monkeypatch):
    """build_command runs per task; re-execing `--help` each time would add a
    subprocess to every run."""
    calls: list[int] = []

    class _Proc:
        stdout = _MODERN_HELP
        stderr = ""

    def _counted(*a, **k):
        calls.append(1)
        return _Proc()

    monkeypatch.setattr(kilo_mod.subprocess, "run", _counted)
    for _ in range(5):
        kilo_mod._detect_surface("/usr/local/bin/kilo")

    assert len(calls) == 1


# ---------------------------------------------------------------------------
# The command each surface gets
# ---------------------------------------------------------------------------


def test_modern_uses_run_and_dir(adapter, monkeypatch, tmp_path):
    _with_help(monkeypatch, _MODERN_HELP)

    cmd = adapter.build_command("do a thing", tmp_path)

    assert cmd == ["/usr/local/bin/kilo", "run", "--dir", str(tmp_path), "do a thing"]


def test_modern_does_not_pass_auto(adapter, monkeypatch, tmp_path):
    """The security half of this issue: on 7.x `--auto` auto-approves ALL
    permissions — the 0.22 `--yolo` the adapter has always withheld (#916)."""
    _with_help(monkeypatch, _MODERN_HELP)

    cmd = adapter.build_command("do a thing", tmp_path)

    assert "--auto" not in cmd
    assert "--yolo" not in cmd
    assert "--dangerously-skip-permissions" not in cmd


def test_legacy_keeps_the_invocation_1012_verified(adapter, monkeypatch, tmp_path):
    _with_help(monkeypatch, _LEGACY_HELP)

    cmd = adapter.build_command("do a thing", tmp_path)

    assert cmd == [
        "/usr/local/bin/kilo", "do a thing", "--auto", "--workspace", str(tmp_path),
    ]
    assert "run" not in cmd, "0.22.0 has no `run`; it gets swallowed as the prompt"
    assert "--yolo" not in cmd


def test_legacy_auto_is_not_the_bypass(adapter, monkeypatch, tmp_path):
    """Both eras must end up without a permission bypass, by different means."""
    _with_help(monkeypatch, _LEGACY_HELP)

    assert "--yolo" not in adapter.build_command("x", tmp_path)
    # …and the fixture proves the two flags really are distinct on 0.22.0.
    assert "--yolo" in _LEGACY_HELP
    assert "Run in autonomous mode" in _LEGACY_HELP


def test_env_overrides_still_apply_on_both(adapter, monkeypatch, tmp_path):
    monkeypatch.setenv("KILOCODE_MODEL", "some-model")
    monkeypatch.setenv("KILOCODE_FLAGS", '--flag "val"')

    for help_text in (_MODERN_HELP, _LEGACY_HELP):
        kilo_mod._SURFACE_CACHE.clear()
        _with_help(monkeypatch, help_text)
        cmd = adapter.build_command("x", tmp_path)
        assert "--model" in cmd and "some-model" in cmd
        assert "--flag" in cmd and "val" in cmd


# ---------------------------------------------------------------------------
# Oversized prompts
# ---------------------------------------------------------------------------


def test_modern_moves_an_oversized_prompt_to_stdin(adapter, monkeypatch, tmp_path):
    """Linux caps one argv entry at 128 KiB, under CodeFrame's ~100K-token
    budget. `kilo run` with no positional reads stdin — verified against 7.4.17,
    where `echo "say ok" | kilo run --dir /tmp` reaches the model call."""
    _with_help(monkeypatch, _MODERN_HELP)
    big = "x" * 200_000

    cmd = adapter.build_command(big, tmp_path)

    assert cmd == ["/usr/local/bin/kilo", "run", "--dir", str(tmp_path)]
    assert adapter.get_stdin(big) == big


def test_a_normal_prompt_stays_positional(adapter, monkeypatch, tmp_path):
    _with_help(monkeypatch, _MODERN_HELP)

    assert adapter.get_stdin("small") is None


def test_legacy_never_uses_stdin(adapter, monkeypatch, tmp_path):
    """0.22.0 has no stdin path; sending it there would silently do nothing."""
    _with_help(monkeypatch, _LEGACY_HELP)

    assert adapter.get_stdin("x" * 200_000) is None


# ---------------------------------------------------------------------------
# Against the installed binary
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("kilo") is None, reason="kilo not installed")
def test_the_installed_cli_matches_one_of_the_two_known_surfaces():
    """Pins the next rewrite: a third surface must fail here, not in production."""
    proc = subprocess.run(
        ["kilo", "--help"], capture_output=True, text=True, timeout=90
    )
    help_text = proc.stdout + proc.stderr

    modern = kilo_mod._RUN_SUBCOMMAND_MARKER in help_text
    legacy = "--workspace" in help_text and "--yolo" in help_text

    assert modern or legacy, (
        "installed kilo matches neither known surface — the CLI was rewritten "
        f"again. Help begins:\n{help_text[:600]}"
    )


@pytest.mark.skipif(shutil.which("kilo") is None, reason="kilo not installed")
def test_the_detected_surface_documents_the_flags_the_adapter_uses(tmp_path):
    """Whatever is installed, every flag the adapter emits must exist on it."""
    adapter = KilocodeAdapter()
    cmd = adapter.build_command("x", tmp_path)

    if adapter._surface() == kilo_mod._MODERN:
        proc = subprocess.run(
            ["kilo", "run", "--help"], capture_output=True, text=True, timeout=90
        )
        help_text = proc.stdout + proc.stderr
    else:
        proc = subprocess.run(
            ["kilo", "--help"], capture_output=True, text=True, timeout=90
        )
        help_text = proc.stdout + proc.stderr

    for flag in (f for f in cmd if f.startswith("--")):
        assert flag in help_text, f"adapter emits {flag}, absent from the CLI's help"
