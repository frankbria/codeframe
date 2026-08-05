"""Issue #954 — atomic, crash-safe writes for config, credentials, installer, workspace init.

Each test drives a failure *through* the real code path rather than asserting a
helper is called, so a refactor that keeps the call but loses the guarantee
still fails.
"""

import json
import os
import sqlite3
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


# --- AC1: one shared, headless atomic helper --------------------------------


def test_atomic_io_is_headless():
    """core must not grow a FastAPI dependency by hosting the helper."""
    source = (
        Path(__file__).resolve().parents[2] / "codeframe" / "core" / "atomic_io.py"
    ).read_text(encoding="utf-8")
    for banned in ("fastapi", "starlette", "codeframe.ui"):
        assert banned not in source, f"core/atomic_io.py imports {banned}"


def test_a_failed_write_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    from codeframe.core import atomic_io

    target = tmp_path / "config.json"
    atomic_io.atomic_write_json(target, {"version": 1})
    original = target.read_bytes()

    # Blow up after the temp file is written but before it is renamed.
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_io.os, "replace", boom)
    with pytest.raises(OSError):
        atomic_io.atomic_write_json(target, {"version": 2})

    assert target.read_bytes() == original, "in-place truncation destroyed the old file"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "config.json"]
    assert leftovers == [], f"temp files leaked: {leftovers}"


def test_concurrent_writers_do_not_collide(tmp_path):
    from codeframe.core import atomic_io

    target = tmp_path / "shared.json"
    errors: list[BaseException] = []

    def write(n):
        try:
            for _ in range(25):
                atomic_io.atomic_write_json(target, {"writer": n})
        except BaseException as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # Whoever won, the file is complete and parseable — never a partial write.
    assert json.loads(target.read_text())["writer"] in range(4)
    assert [p.name for p in tmp_path.iterdir()] == ["shared.json"]


def test_helpers_reexport_keeps_existing_router_callers_working():
    from codeframe.core.atomic_io import atomic_write_json as core_impl
    from codeframe.ui.routers._helpers import atomic_write_json as router_impl

    assert router_impl is core_impl


# --- AC2: a failed decrypt must never overwrite the store -------------------


@pytest.fixture
def corrupt_store(tmp_path):
    """A credential store whose ciphertext cannot be decrypted."""
    from codeframe.core.credentials import CredentialStore

    store = CredentialStore(storage_dir=tmp_path)
    path = store._get_encrypted_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"gAAAAABnot-a-valid-fernet-token")
    return store, path


def test_storing_over_an_undecryptable_file_raises_and_preserves_ciphertext(corrupt_store):
    from codeframe.core.credentials import (
        Credential,
        CredentialProvider,
        CredentialStoreUnreadableError,
    )

    store, path = corrupt_store
    store._keyring_available = False
    before = path.read_bytes()

    with pytest.raises(CredentialStoreUnreadableError):
        store.store(
            Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-ant-new-key")
        )

    assert path.read_bytes() == before, (
        "a failed decrypt overwrote the store — every other provider key is gone"
    )


def test_deleting_from_an_undecryptable_file_raises_and_preserves_ciphertext(corrupt_store):
    from codeframe.core.credentials import CredentialProvider, CredentialStoreUnreadableError

    store, path = corrupt_store
    store._keyring_available = False
    before = path.read_bytes()

    with pytest.raises(CredentialStoreUnreadableError):
        store.delete(CredentialProvider.LLM_ANTHROPIC)

    assert path.read_bytes() == before


def test_reads_still_degrade_gracefully_on_an_undecryptable_file(corrupt_store, caplog):
    """A read is allowed to report 'nothing usable'; it just must not write."""
    from codeframe.core.credentials import CredentialProvider

    store, path = corrupt_store
    store._keyring_available = False
    before = path.read_bytes()

    assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is None
    assert store.list_providers() == []
    assert path.read_bytes() == before


def test_a_readable_store_still_round_trips(tmp_path):
    """The raise-on-corruption change must not break the normal path."""
    from codeframe.core.credentials import Credential, CredentialProvider, CredentialStore

    store = CredentialStore(storage_dir=tmp_path)
    store._keyring_available = False

    store.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-ant-1"))
    store.store(Credential(provider=CredentialProvider.LLM_OPENAI, value="sk-oai-2"))

    assert store.retrieve(CredentialProvider.LLM_ANTHROPIC).value == "sk-ant-1"
    assert store.retrieve(CredentialProvider.LLM_OPENAI).value == "sk-oai-2"
    assert set(store.list_providers()) == {
        CredentialProvider.LLM_ANTHROPIC,
        CredentialProvider.LLM_OPENAI,
    }

    store.delete(CredentialProvider.LLM_ANTHROPIC)
    assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is None
    assert store.retrieve(CredentialProvider.LLM_OPENAI).value == "sk-oai-2"


def test_credential_saves_go_through_the_shared_atomic_writer(tmp_path, monkeypatch):
    """AC1 names credentials.py explicitly.

    Raised by ``codex review``: the store kept its own private temp/replace copy,
    which fsynced neither the file nor the directory — so a crash right after
    `cf auth setup` could still lose the new key.
    """
    from codeframe.core import atomic_io, credentials
    from codeframe.core.credentials import Credential, CredentialProvider, CredentialStore

    calls: list[tuple] = []
    real = atomic_io.atomic_write_bytes
    monkeypatch.setattr(
        credentials,
        "atomic_write_bytes",
        lambda p, d, mode=None: (calls.append((Path(p).name, mode)), real(p, d, mode=mode))[1],
    )

    store = CredentialStore(storage_dir=tmp_path)
    store._keyring_available = False
    store.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-ant-1"))

    assert calls, "credential save bypassed the shared atomic writer"
    name, mode = calls[-1]
    assert name == "credentials.encrypted"
    assert mode == 0o600, "ciphertext must be 0600 before it takes its final name"


def test_credential_file_stays_owner_only(tmp_path):
    from codeframe.core.credentials import Credential, CredentialProvider, CredentialStore

    store = CredentialStore(storage_dir=tmp_path)
    store._keyring_available = False
    store.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-ant-1"))

    path = store._get_encrypted_file_path()
    assert path.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


# --- AC3: record_installation tolerates any environment.json shape ----------


@pytest.fixture
def installer(tmp_path, monkeypatch):
    from codeframe.core.installer import ToolInstaller

    monkeypatch.setenv("HOME", str(tmp_path))
    inst = ToolInstaller()
    inst.history_dir = tmp_path / "hist"
    inst.history_file = inst.history_dir / "environment.json"
    inst.history_dir.mkdir(parents=True, exist_ok=True)
    return inst


def _result():
    from codeframe.core.installer import InstallResult, InstallStatus

    return InstallResult(
        tool_name="ruff",
        status=InstallStatus.SUCCESS,
        message="installed",
        command_used="uv tool install ruff",
    )


@pytest.mark.parametrize(
    "junk",
    ['["a", "b"]', '"just a string"', "42", "null", '{"installations": "not-a-dict"}'],
)
def test_record_installation_survives_an_unexpected_history_shape(installer, junk):
    """A malformed history file must not fail an install that already succeeded."""
    installer.history_file.write_text(junk)

    installer.record_installation(_result())

    history = json.loads(installer.history_file.read_text())
    assert history["installations"]["ruff"]["status"] == "success"


def test_record_installation_preserves_existing_entries(installer):
    installer.history_file.write_text(
        json.dumps({"installations": {"black": {"status": "success"}}})
    )

    installer.record_installation(_result())

    entries = json.loads(installer.history_file.read_text())["installations"]
    assert set(entries) == {"black", "ruff"}


def test_record_installation_does_not_truncate_on_a_failed_write(installer, monkeypatch):
    from codeframe.core import atomic_io

    installer.record_installation(_result())
    before = installer.history_file.read_bytes()

    monkeypatch.setattr(
        atomic_io.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("full"))
    )
    with pytest.raises(OSError):
        installer.record_installation(_result())

    assert installer.history_file.read_bytes() == before


# --- AC4: workspace init is all-or-nothing ----------------------------------


def test_a_failed_init_leaves_no_half_built_workspace(tmp_path, monkeypatch):
    """The bug: state.db existed but held no workspace row, forever."""
    from codeframe.core import workspace as ws

    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setattr(
        ws, "_init_database", lambda p: (_ for _ in ()).throw(RuntimeError("crash"))
    )
    with pytest.raises(RuntimeError):
        ws.create_or_load_workspace(repo)

    assert not (repo / ".codeframe" / ws.STATE_DB_NAME).exists(), (
        "a rowless state.db survives and permanently breaks `cf init`"
    )


def test_init_is_retryable_after_a_failure(tmp_path, monkeypatch):
    from codeframe.core import workspace as ws

    repo = tmp_path / "repo"
    repo.mkdir()

    real_init = ws._init_database
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 1:
            real_init(path)  # leave a fully built DB behind, then die
            raise RuntimeError("crash after schema creation")
        return real_init(path)

    monkeypatch.setattr(ws, "_init_database", flaky)
    with pytest.raises(RuntimeError):
        ws.create_or_load_workspace(repo)

    monkeypatch.setattr(ws, "_init_database", real_init)
    workspace = ws.create_or_load_workspace(repo, tech_stack="python")

    assert workspace.tech_stack == "python"
    assert ws.get_workspace(repo).id == workspace.id


def test_a_crash_between_schema_and_the_workspace_row_leaves_nothing(tmp_path, monkeypatch):
    """Reproduces the exact reported window: schema built, row never inserted."""
    from codeframe.core import workspace as ws

    repo = tmp_path / "repo"
    repo.mkdir()

    real_uuid4 = ws.uuid.uuid4

    def explode():
        ws.uuid.uuid4 = real_uuid4  # only fail the first time
        raise RuntimeError("died before INSERT")

    monkeypatch.setattr(ws.uuid, "uuid4", explode)
    with pytest.raises(RuntimeError):
        ws.create_or_load_workspace(repo)
    monkeypatch.undo()

    assert not (repo / ".codeframe" / ws.STATE_DB_NAME).exists()
    workspace = ws.create_or_load_workspace(repo)
    assert workspace.id  # no "contains no workspace record"


def test_workspace_init_fsyncs_the_state_dir_after_the_rename(tmp_path, monkeypatch):
    """os.replace is atomic but not durable — the directory entry needs syncing.

    Raised by ``codex review``: without this, a power loss right after the
    rename loses it, so `cf init` reports success and comes back to an
    uninitialized workspace.
    """
    from codeframe.core import atomic_io, workspace as ws

    synced: list[str] = []
    real = atomic_io.fsync_directory
    monkeypatch.setattr(
        ws, "fsync_directory", lambda p: (synced.append(str(p)), real(p))[1]
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    ws.create_or_load_workspace(repo)

    assert str(repo / ".codeframe") in synced


def test_an_existing_workspace_is_still_loaded_not_rebuilt(tmp_path):
    from codeframe.core import workspace as ws

    repo = tmp_path / "repo"
    repo.mkdir()
    first = ws.create_or_load_workspace(repo, tech_stack="python")
    second = ws.create_or_load_workspace(repo, tech_stack="ignored")

    assert second.id == first.id
    assert second.tech_stack == "python"


def test_workspace_db_keeps_its_schema_version(tmp_path):
    """os.replace of the temp DB must carry PRAGMA user_version with it."""
    from codeframe.core import workspace as ws

    repo = tmp_path / "repo"
    repo.mkdir()
    ws.create_or_load_workspace(repo)

    conn = sqlite3.connect(repo / ".codeframe" / ws.STATE_DB_NAME)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == ws.SCHEMA_VERSION
    finally:
        conn.close()


# --- AC1 (cont.): config save is atomic -------------------------------------


def test_config_save_does_not_truncate_on_a_failed_write(tmp_path, monkeypatch):
    from codeframe.core import atomic_io
    from codeframe.core.config import (
        EnvironmentConfig,
        load_environment_config,
        save_environment_config,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    save_environment_config(repo, EnvironmentConfig(engine="react"))
    before = (repo / ".codeframe" / "config.yaml").read_bytes()

    monkeypatch.setattr(
        atomic_io.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("full"))
    )
    with pytest.raises(OSError):
        save_environment_config(repo, EnvironmentConfig(engine="plan"))

    assert (repo / ".codeframe" / "config.yaml").read_bytes() == before
    assert load_environment_config(repo).engine == "react"


def test_config_round_trips_non_ascii(tmp_path):
    """The #931 UTF-8 guarantee must survive the move to the atomic writer."""
    from codeframe.core.config import (
        EnvironmentConfig,
        load_environment_config,
        save_environment_config,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    save_environment_config(repo, EnvironmentConfig(test_command="pytest -k café ☕"))

    assert load_environment_config(repo).test_command == "pytest -k café ☕"
    raw = (repo / ".codeframe" / "config.yaml").read_text(encoding="utf-8")
    assert "café ☕" in raw


def test_atomic_write_fsyncs_before_replace(tmp_path, monkeypatch):
    """Crash-safety, not just atomicity: the bytes must be durable pre-rename."""
    from codeframe.core import atomic_io

    order: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(
        atomic_io.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1]
    )
    monkeypatch.setattr(
        atomic_io.os,
        "replace",
        lambda a, b: (order.append("replace"), real_replace(a, b))[1],
    )

    atomic_io.atomic_write_json(tmp_path / "d.json", {"a": 1})

    assert "fsync" in order, "no fsync — a crash after rename can still lose the data"
    assert order.index("fsync") < order.index("replace")
