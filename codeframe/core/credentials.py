"""Secure credential management for CodeFRAME.

This module provides:
- Platform-native keyring integration (primary storage)
- Encrypted file fallback when keyring unavailable — where "unavailable" includes
  *unresponsive*, not just missing or raising: a backend can be installed and
  selected yet never answer (SecretService with no session D-Bus), so every
  keyring call is time-boxed and a timeout falls through to the file (#1181).
  ``CODEFRAME_DISABLE_KEYRING=1`` skips the keyring outright;
  ``CODEFRAME_KEYRING_TIMEOUT`` tunes the bound.
- Environment variable override support
- Credential validation and rotation

Security features:
- Fernet encryption for file-based storage
- File permissions enforced at 600 (owner-only)
- Machine-specific encryption keys
- Audit logging for credential operations

Threat model — file-fallback confidentiality (#772):
    The encrypted-file fallback derives its key from a machine-specific
    identifier (e.g. /etc/machine-id). That identifier is NOT a secret: a local
    attacker who can read the ciphertext file can typically also read the
    machine-id and re-derive the key. So this layer is obfuscation-at-rest that
    stops casual disk/backup snooping — it is NOT confidentiality against a
    local attacker with your file access. For real confidentiality either (a)
    rely on the OS keyring (the primary, preferred backend), or (b) set the
    CODEFRAME_CREDENTIAL_SECRET environment variable, which mixes a real secret
    into the KDF. Changing/adding that secret rekeys the store, so previously
    stored credentials become undecryptable and must be re-entered.

Usage:
    from codeframe.core.credentials import CredentialManager, CredentialProvider

    manager = CredentialManager()
    api_key = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
    manager.set_credential(CredentialProvider.GIT_GITHUB, "ghp_token")
"""

import base64
import hashlib
import json
import logging
import os
import time
import platform
import threading
from functools import lru_cache
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

try:
    import keyring
    from keyring.errors import KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    keyring = None
    KeyringError = Exception

try:
    from keyring.errors import PasswordDeleteError
except ImportError:  # pragma: no cover (older keyring without this subclass)
    PasswordDeleteError = KeyringError

try:
    from filelock import FileLock
except ImportError:  # pragma: no cover (filelock is a declared dependency)
    FileLock = None  # type: ignore[misc,assignment]

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from codeframe.core.atomic_io import atomic_write_bytes


logger = logging.getLogger(__name__)

# Constants
KEYRING_SERVICE_NAME = "codeframe-credentials"
ENCRYPTED_FILE_NAME = "credentials.encrypted"
SALT_FILE_NAME = "salt"
DEFAULT_STORAGE_DIR = Path.home() / ".codeframe"

# Per-process memo of completed machine-wide → per-user migrations (#790).
# CredentialManager is constructed per request, but migration is idempotent
# (copy-only), so one run per user storage_dir per process is enough — the
# next process retries anything that failed. Tests that build managers via
# ``CredentialManager.__new__`` bypass __init__ and thus this memo entirely.
# Tests reset it with ``_MIGRATION_COMPLETE.clear()``.
_MIGRATION_COMPLETE: set[Path] = set()

# Thread locks serialize concurrent migrations for the same storage root within
# a process. The optional file lock (requires ``filelock``) extends that
# serialization across processes.
_MIGRATION_THREAD_LOCKS: dict[Path, threading.Lock] = {}

# Default bound on any single keyring call. Long enough for a healthy
# SecretService round-trip (including an unlock prompt round-trip), short enough
# that a dead backend does not read as a hang.
DEFAULT_KEYRING_TIMEOUT = 2.0

# Sticky, per-process: once a keyring call has timed out, the backend is dead for
# the life of this process. CredentialStore is constructed per request on the
# server, so without this every request would pay the timeout again (#1181).
_KEYRING_TIMED_OUT = False

# One keyring call at a time per process. Without it, a burst of concurrent
# first callers each read _KEYRING_TIMED_OUT as False and each start its own
# unkillable worker, so the sticky verdict would bound nothing. Serialized, the
# losers wait on the lock and then see the verdict the winner set. Cheap: a
# healthy keyring call is milliseconds, credential reads are rare, and the
# backend serializes on its own socket anyway.
_KEYRING_CALL_LOCK = threading.Lock()


class KeyringTimeoutError(KeyringError):  # type: ignore[misc,valid-type]
    """A keyring call did not return within the timeout.

    Subclasses ``KeyringError`` on purpose: every existing call site already
    treats a ``KeyringError`` as "keyring failed, use the encrypted file", which
    is exactly the right response to a backend that never answers.
    """


def _keyring_timeout() -> float:
    """Read the timeout per call, not at import (the #963 lesson)."""
    try:
        return float(os.environ.get("CODEFRAME_KEYRING_TIMEOUT", DEFAULT_KEYRING_TIMEOUT))
    except ValueError:
        return DEFAULT_KEYRING_TIMEOUT


def _keyring_call(fn, *args):
    """Run one keyring call under a timeout.

    A backend that is installed and selected but unresponsive — SecretService on
    a headless box with no session D-Bus — raises nothing, it blocks forever.
    Detecting "unavailable" by exception alone therefore never fires (#1181), so
    every call is time-boxed here instead.

    The blocked call cannot be cancelled (it is waiting inside libdbus), so the
    worker thread is abandoned as a daemon. That is bounded to one per process
    by the sticky ``_KEYRING_TIMED_OUT`` flag plus the lock that makes the flag
    mean something under concurrency.
    """
    with _KEYRING_CALL_LOCK:
        return _keyring_call_locked(fn, *args)


def _keyring_call_locked(fn, *args):
    """The body of :func:`_keyring_call`, run one caller at a time."""
    global _KEYRING_TIMED_OUT

    if _KEYRING_TIMED_OUT:
        # Already proved unresponsive. Short-circuit *here*, not just in
        # _check_keyring: a store built before the timeout still has
        # _keyring_available=True, and store() chases a timed-out set_password
        # with a delete_password. Without this each of those starts another
        # unkillable worker and waits the timeout again.
        raise KeyringTimeoutError("keyring backend already timed out in this process")

    outcome: list = []

    def run() -> None:
        try:
            outcome.append(("ok", fn(*args)))
        except BaseException as exc:  # re-raised on the calling thread below
            outcome.append(("error", exc))

    worker = threading.Thread(target=run, daemon=True, name="codeframe-keyring")
    worker.start()
    worker.join(_keyring_timeout())

    if worker.is_alive():
        _KEYRING_TIMED_OUT = True
        logger.warning(
            "Keyring backend did not respond within %.1fs; falling back to the "
            "encrypted credential file for the rest of this process. Set "
            "CODEFRAME_DISABLE_KEYRING=1 to skip the keyring entirely.",
            _keyring_timeout(),
        )
        raise KeyringTimeoutError("keyring call timed out")

    kind, value = outcome[0]
    if kind == "error":
        raise value
    return value


def _get_migration_locks(storage_dir: Path) -> tuple[threading.Lock, Any | None]:
    """Return the migration locks for ``storage_dir``.

    The returned tuple is ``(thread_lock, file_lock_or_none)``. ``file_lock``
    is ``None`` when ``filelock`` is not installed; callers fall back to the
    thread lock only and log a warning that cross-process serialization is
    disabled.
    """
    lock_path = storage_dir / ".migration.lock"
    thread_lock = _MIGRATION_THREAD_LOCKS.setdefault(lock_path, threading.Lock())
    file_lock: Any | None = None
    if FileLock is not None:
        file_lock = FileLock(str(lock_path))
    return thread_lock, file_lock


class CredentialStoreUnreadableError(RuntimeError):
    """The encrypted credential file exists but cannot be read or decrypted.

    Raised instead of quietly returning an empty store, because the write paths
    do read-modify-write: treating "unreadable" as "empty" made the next save
    overwrite every stored key with a single new entry (#954). The ciphertext is
    still on disk when this is raised — recoverable if the original key material
    (machine ID / ``CODEFRAME_CREDENTIAL_SECRET``) comes back.
    """


class CredentialSource(str, Enum):
    """Source of a credential."""

    ENVIRONMENT = "environment"
    STORED = "stored"
    NOT_FOUND = "not_found"


class CredentialProvider(Enum):
    """Supported credential provider types.

    Each provider type has associated metadata for env var mapping
    and display purposes.
    """

    LLM_ANTHROPIC = ("ANTHROPIC_API_KEY", "Anthropic (Claude)")
    LLM_OPENAI = ("OPENAI_API_KEY", "OpenAI (GPT)")
    GIT_GITHUB = ("GITHUB_TOKEN", "GitHub")
    GIT_GITLAB = ("GITLAB_TOKEN", "GitLab")
    CICD_GENERIC = ("CICD_TOKEN", "CI/CD")
    DATABASE = ("DATABASE_URL", "Database")

    def __init__(self, env_var: str, display_name: str):
        self._env_var = env_var
        self._display_name = display_name

    @property
    def env_var(self) -> str:
        """Environment variable name for this provider."""
        return self._env_var

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return self._display_name


@dataclass
class Credential:
    """A stored credential with metadata.

    Attributes:
        provider: The provider type (LLM, Git, etc.)
        value: The actual credential value (API key, token, etc.)
        name: Optional friendly name for the credential
        metadata: Additional metadata (scopes, permissions, etc.)
        created_at: When the credential was stored
        expires_at: Optional expiration timestamp
    """

    provider: CredentialProvider
    value: str
    name: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    @property
    def is_expired(self) -> bool:
        """Check if credential has expired."""
        exp = self.expires_at
        if exp is None:
            return False
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > exp

    @property
    def masked_value(self) -> str:
        """Get masked version of value for display."""
        if len(self.value) <= 8:
            return "***"
        return f"{self.value[:4]}...{self.value[-4:]}"

    def to_safe_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding actual value."""
        return {
            "provider": self.provider.name,
            "name": self.name,
            "masked_value": self.masked_value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage (includes value)."""
        return {
            "provider": self.provider.name,
            "value": self.value,
            "name": self.name,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Credential":
        """Create Credential from dictionary."""
        provider = CredentialProvider[data["provider"]]

        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        expires_at = None
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])

        return cls(
            provider=provider,
            value=data["value"],
            name=data.get("name"),
            metadata=data.get("metadata", {}),
            created_at=created_at or datetime.now(timezone.utc),
            expires_at=expires_at,
        )


@dataclass
class CredentialInfo:
    """Summary information about a credential (no actual value)."""

    provider: CredentialProvider
    source: CredentialSource
    name: Optional[str] = None
    masked_value: Optional[str] = None
    is_expired: bool = False
    last_validated: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)


def derive_encryption_key(salt_file: Path) -> bytes:
    """Derive the store's Fernet key, memoized per (salt file, secret).

    PBKDF2 at 480,000 iterations costs hundreds of milliseconds, and the Fernet
    was cached only per ``CredentialStore`` instance — while ``CredentialManager``
    is built per request via ``Depends``. So a headless server with no keyring
    paid a full derivation *per provider per request* on the event loop (#920).

    Keyed on the secret as well as the salt file: a changed
    ``CODEFRAME_CREDENTIAL_SECRET`` must produce a different key, not a stale
    cached one.
    """
    return _derive_key_cached(
        str(salt_file), os.environ.get("CODEFRAME_CREDENTIAL_SECRET")
    )


@lru_cache(maxsize=32)
def _derive_key_cached(salt_file_str: str, _secret: str | None) -> bytes:
    """Memoization boundary. ``_secret`` is part of the cache key only."""
    return _derive_key_uncached(Path(salt_file_str))


#: So callers (and tests) can drop the memo, e.g. after rotating the secret.
derive_encryption_key.cache_clear = _derive_key_cached.cache_clear  # type: ignore[attr-defined]


def _derive_key_uncached(salt_file: Path) -> bytes:
    """Derive encryption key from machine-specific data.

    Uses PBKDF2 with machine ID and a persistent salt to create
    a Fernet-compatible encryption key.

    The machine ID is not secret, so on its own this only obfuscates the file
    at rest (see the module docstring "Threat model"). When the
    CODEFRAME_CREDENTIAL_SECRET environment variable is set, its value is mixed
    into the KDF input to provide real confidentiality. Note: adding or changing
    that secret changes the derived key, rendering any previously stored
    credentials undecryptable (they must be re-entered).

    Args:
        salt_file: Path to store/retrieve the salt

    Returns:
        Fernet-compatible key (base64 encoded)
    """
    # Get or create salt
    if salt_file.exists():
        # Waits out a concurrent creator that has made the file but not yet
        # written to it, and raises the same explicit error as before for a
        # salt that is genuinely the wrong size (#920 review).
        salt = _read_salt_when_written(salt_file)
    else:
        # Create exclusively, and on a lost race read back the winner's salt.
        #
        # `open(..., "wb")` truncates, so two first-time derivations each wrote
        # their own random salt and the second clobbered the first. Every caller
        # used to re-read the disk salt, so the mismatch self-healed on the next
        # call; with the derivation memoized (#920) the losing key is pinned for
        # the whole process lifetime — the process encrypts under a key the
        # on-disk salt can never reproduce, and after a restart every credential
        # written in that window fails to decrypt and reads as an empty store.
        # (#920 review)
        salt_file.parent.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(16)
        try:
            fd = os.open(salt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            salt = _read_salt_when_written(salt_file)
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(salt)
            salt_file.chmod(0o600)

    # Get machine-specific identifier; optionally mix in a real user secret so
    # the key isn't recoverable from the (non-secret) machine ID alone (#772).
    machine_id = _get_machine_id()
    user_secret = os.environ.get("CODEFRAME_CREDENTIAL_SECRET")
    # When no secret is set, key material stays exactly machine_id (unchanged
    # from prior versions) so existing stored credentials remain decryptable.
    if user_secret:
        key_material = f"{machine_id}\0{user_secret}".encode()
    else:
        key_material = machine_id.encode()

    # Derive key using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(key_material))

    return key


def _read_salt_when_written(salt_file: Path) -> bytes:
    """Read a salt another process/thread is in the middle of creating (#920).

    Losing the ``O_EXCL`` race means the file exists but the winner may not have
    written to it yet, so a plain read can return zero bytes — which derives a
    different key just as surely as a clobbered salt would. The write is a
    single 16-byte call immediately after the create, so this settles within
    microseconds; the bound is here so a genuinely truncated salt raises the
    same explicit error as the validation path above rather than spinning.
    """
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        data = salt_file.read_bytes()
        if len(data) == 16:
            return data
        time.sleep(0.005)

    raise ValueError(
        f"Invalid salt file at {salt_file}: expected 16 bytes, got "
        f"{len(salt_file.read_bytes())}. Delete the salt file to regenerate "
        "(note: this will make existing credentials inaccessible)."
    )


def _get_machine_id() -> str:
    """Get a machine-specific identifier.

    Uses platform-specific stable identifiers when available:
    - Linux: /etc/machine-id
    - Windows: MachineGuid from registry
    - Fallback: hostname + machine type + MAC address

    Note: MAC address (uuid.getnode) can be randomized on WiFi adapters
    on privacy-focused systems, so we prefer OS-level machine IDs.
    """
    components = []

    # Try Linux machine-id first (most stable)
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        try:
            machine_id = machine_id_path.read_text(encoding="utf-8").strip()
            if machine_id:
                components.append(machine_id)
        # ValueError covers UnicodeDecodeError (#1029), which is NOT an OSError.
        # A /etc/machine-id that is not valid UTF-8 would otherwise crash key
        # derivation outright rather than falling through to the portable
        # identifiers below.
        except (OSError, ValueError):
            pass

    # Try Windows MachineGuid
    if platform.system() == "Windows" and not components:
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography"
            ) as key:
                machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                if machine_guid:
                    components.append(machine_guid)
        except (ImportError, OSError, FileNotFoundError):
            pass

    # Fallback: use portable identifiers
    if not components:
        components = [
            platform.node(),
            platform.machine(),
            str(uuid.getnode()),  # MAC address (less stable on some systems)
        ]

    combined = "-".join(components)
    return hashlib.sha256(combined.encode()).hexdigest()


def validate_credential_format(
    provider: CredentialProvider,
    value: str,
) -> bool:
    """Validate credential format for a provider.

    Args:
        provider: The credential provider type
        value: The credential value to validate

    Returns:
        True if format appears valid, False otherwise
    """
    if not value or len(value) < 5:
        return False

    if provider == CredentialProvider.LLM_ANTHROPIC:
        # Anthropic keys start with "sk-ant-" (e.g., sk-ant-api03-...)
        return len(value) >= 20 and value.startswith("sk-ant-")

    elif provider == CredentialProvider.LLM_OPENAI:
        # OpenAI keys start with "sk-" (legacy) or "sk-proj-" (project-scoped)
        return len(value) >= 20 and value.startswith("sk-")

    elif provider == CredentialProvider.GIT_GITHUB:
        # GitHub PATs: ghp_ (classic) or github_pat_ (fine-grained)
        return len(value) >= 10 and (
            value.startswith("ghp_") or
            value.startswith("github_pat_") or
            value.startswith("gho_") or  # OAuth
            value.startswith("ghs_")  # Server-to-server
        )

    elif provider == CredentialProvider.GIT_GITLAB:
        # GitLab tokens start with "glpat-"
        return len(value) >= 20 and value.startswith("glpat-")

    # Default: just check minimum length
    return len(value) >= 5


class CredentialStore:
    """Low-level credential storage.

    Uses platform keyring as primary storage with encrypted file fallback.

    Storage is machine-wide by default (``user_id=None``). With a ``user_id``
    the store is scoped to that user (#790): keyring entries live under a
    per-user service name and the encrypted-file fallback lives under
    ``<storage_dir>/users/<id>/`` with its own salt — the per-directory salt
    yields per-user encryption keys from the unchanged key derivation.
    """

    def __init__(self, storage_dir: Optional[Path] = None, user_id: Optional[int] = None):
        """Initialize credential store.

        Args:
            storage_dir: Directory for encrypted file storage
            user_id: Scope storage to this user; None keeps machine-wide storage
        """
        self.user_id = user_id
        self.storage_dir = self._resolve_storage_dir(storage_dir, user_id)
        self._keyring_service_name = self._resolve_keyring_service_name(user_id)
        self._keyring_available = self._check_keyring()
        self._fernet: Optional[Fernet] = None

    @staticmethod
    def _resolve_storage_dir(storage_dir: Optional[Path], user_id: Optional[int]) -> Path:
        """Per-user stores live in ``<storage_dir>/users/<id>/``."""
        base = storage_dir or DEFAULT_STORAGE_DIR
        if user_id is None:
            return base
        return base / "users" / str(user_id)

    @staticmethod
    def _resolve_keyring_service_name(user_id: Optional[int]) -> str:
        """Per-user keyring entries are addressed under their own service."""
        if user_id is None:
            return KEYRING_SERVICE_NAME
        return f"{KEYRING_SERVICE_NAME}-user-{user_id}"

    def _check_keyring(self) -> bool:
        """Check if keyring is available and working."""
        if not KEYRING_AVAILABLE:
            return False
        if os.environ.get("CODEFRAME_DISABLE_KEYRING", "").lower() not in ("", "0", "false"):
            return False
        if _KEYRING_TIMED_OUT:
            # An earlier call already proved this backend unresponsive (#1181).
            return False

        try:
            # Try to get the keyring backend. Backend selection itself can block
            # on a dead D-Bus, so it is time-boxed like every other call.
            kr = _keyring_call(keyring.get_keyring)
            # Check if it's a real backend (not fail keyring)
            if "fail" in kr.__class__.__name__.lower():
                return False
            return True
        except Exception:
            return False

    @contextmanager
    def _store_lock(self):
        """Serialize a read-modify-write of the encrypted store.

        Reuses the migration locks so both paths contend on the same pair: a
        thread lock within the process, plus a cross-process file lock when
        ``filelock`` is installed.
        """
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        thread_lock, file_lock = _get_migration_locks(self.storage_dir)
        with thread_lock:
            if file_lock is None:
                # Single-process serialization only. Same degradation the
                # migration path documents.
                yield
            else:
                with file_lock:
                    yield

    def _get_fernet(self) -> Fernet:
        """Get or create Fernet instance for encryption."""
        if self._fernet is None:
            salt_file = self.storage_dir / SALT_FILE_NAME
            key = derive_encryption_key(salt_file)
            self._fernet = Fernet(key)
        return self._fernet

    def _get_encrypted_file_path(self) -> Path:
        """Get path to encrypted credentials file."""
        return self.storage_dir / ENCRYPTED_FILE_NAME

    def _load_encrypted_store(self) -> dict[str, dict]:
        """Load all credentials from the encrypted file.

        Returns:
            Dictionary of stored credentials, or empty dict if the file does not
            exist yet.

        Raises:
            CredentialStoreUnreadableError: The file exists but cannot be read
                or decrypted (machine ID changed, ``CODEFRAME_CREDENTIAL_SECRET``
                added, VM clone, corruption, bad permissions).

        This used to return ``{}`` on failure, which read as "no credentials
        stored". The write paths do load → mutate → save, so the very next
        ``store()`` re-encrypted that empty dict plus one new entry over the top
        of the real file — permanently destroying every other provider key, in
        exactly the key-rotation scenario CLAUDE.md documents (#954). Failing
        loudly is the only safe answer: the ciphertext might still be
        recoverable, and only if nothing overwrites it.
        """
        file_path = self._get_encrypted_file_path()
        if not file_path.exists():
            return {}

        try:
            with open(file_path, "rb") as f:
                encrypted_data = f.read()

            fernet = self._get_fernet()
            decrypted = fernet.decrypt(encrypted_data)
        except InvalidToken as e:
            raise CredentialStoreUnreadableError(
                "Failed to decrypt the credentials file. This happens when the "
                "machine ID changed (new machine, VM clone) or when "
                "CODEFRAME_CREDENTIAL_SECRET was added or changed. The stored "
                "credentials are unreadable but have NOT been deleted. Restore the "
                "original secret to recover them, or delete "
                f"{file_path} and re-run 'cf auth setup' to start fresh."
            ) from e
        except (PermissionError, OSError) as e:
            raise CredentialStoreUnreadableError(
                f"Failed to read the credentials file {file_path}: {e}"
            ) from e

        try:
            loaded = json.loads(decrypted.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise CredentialStoreUnreadableError(
                f"Credentials file {file_path} decrypted but is not valid JSON: {e}"
            ) from e

        if not isinstance(loaded, dict):
            raise CredentialStoreUnreadableError(
                f"Credentials file {file_path} decrypted to "
                f"{type(loaded).__name__}, expected an object."
            )
        return loaded

    def _load_encrypted_store_for_read(self) -> dict[str, dict]:
        """``_load_encrypted_store``, degraded to ``{}`` for read-only callers.

        A lookup may reasonably answer "nothing usable here" — it writes
        nothing, so it cannot destroy anything. Write paths must NOT use this.
        """
        try:
            return self._load_encrypted_store()
        except CredentialStoreUnreadableError as e:
            logger.error("%s", e)
            return {}

    def _save_encrypted_store(self, store: dict[str, dict]) -> None:
        """Save all credentials to encrypted file."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if self.user_id is not None:
            # Per-user dirs are 0700 so other local accounts cannot enumerate
            # tenant ids (#790). The machine-wide base dir keeps its default
            # perms. Best-effort — Windows does not honor POSIX modes.
            for directory in (self.storage_dir, self.storage_dir.parent):
                try:
                    directory.chmod(0o700)
                except OSError:  # pragma: no cover (chmod may fail on Windows)
                    pass

        file_path = self._get_encrypted_file_path()
        fernet = self._get_fernet()

        data = json.dumps(store).encode()
        encrypted = fernet.encrypt(data)

        # The shared helper (#954) instead of a private temp/replace copy: it
        # keeps the per-writer unique temp name that #920 added, and adds the
        # fsync of both the file and its directory that this path was missing —
        # so a crash right after `cf auth setup` cannot lose the new key.
        # ``mode`` applies 0600 *before* the rename, so the ciphertext is never
        # briefly world-readable at its final name.
        atomic_write_bytes(file_path, encrypted, mode=0o600)

    def store(self, credential: Credential) -> None:
        """Store a credential securely.

        Tries keyring first, falls back to encrypted file.

        Args:
            credential: The credential to store
        """
        key = credential.provider.name
        data = json.dumps(credential.to_dict())

        # Try keyring first
        if self._keyring_available:
            try:
                _keyring_call(keyring.set_password, self._keyring_service_name, key, data)
                logger.debug(f"Stored {key} in keyring")
                return
            except Exception as e:
                logger.warning(f"Keyring storage failed, using encrypted file: {e}")
                try:
                    _keyring_call(keyring.delete_password, self._keyring_service_name, key)
                except Exception:
                    pass
                self._keyring_available = False

        # Fall back to encrypted file. The whole read-modify-write runs under
        # the lock: unlocked, two writers each read the same base and the last
        # to save silently dropped the other's credential (#920).
        with self._store_lock():
            store = self._load_encrypted_store()
            store[key] = credential.to_dict()
            self._save_encrypted_store(store)
        logger.debug(f"Stored {key} in encrypted file")

    def retrieve(self, provider: CredentialProvider) -> Optional[Credential]:
        """Retrieve a credential.

        Tries keyring first, falls back to encrypted file.

        Args:
            provider: The provider type to retrieve

        Returns:
            Credential if found, None otherwise
        """
        key = provider.name

        # Try keyring first
        if self._keyring_available:
            try:
                data = _keyring_call(keyring.get_password, self._keyring_service_name, key)
                if data:
                    return Credential.from_dict(json.loads(data))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Malformed credential data in keyring for {key}: {e}")
            except KeyringTimeoutError:
                # Unresponsive backend: stop asking it on this instance too, so
                # the timeout is paid once rather than on every read (#1181).
                self._keyring_available = False
            except Exception as e:
                logger.debug(f"Keyring retrieval failed: {e}")

        # Fall back to encrypted file
        store = self._load_encrypted_store_for_read()
        if key in store:
            try:
                return Credential.from_dict(store[key])
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Malformed credential data in encrypted store for {key}: {e}")
                return None

        return None

    def delete(self, provider: CredentialProvider) -> None:
        """Delete a credential.

        Args:
            provider: The provider type to delete
        """
        key = provider.name

        # Try keyring
        if self._keyring_available:
            try:
                _keyring_call(keyring.delete_password, self._keyring_service_name, key)
                logger.debug(f"Deleted {key} from keyring")
            except PasswordDeleteError:
                # Not in the keyring (e.g. a file-only entry) — that is
                # "nothing to do", not a failure. Continue to file cleanup.
                logger.debug(f"{key} not present in keyring; nothing to delete there")
            except KeyringTimeoutError:
                # An unresponsive backend must degrade, not fail the delete: the
                # entry may well be file-only, and the file cleanup below is the
                # part that matters (#1181).
                self._keyring_available = False
            except Exception as e:
                logger.warning(f"Keyring deletion failed: {e}")
                raise

        # Also remove from encrypted file (if exists), under the same lock as
        # store() — a delete is a read-modify-write too, and unlocked it would
        # resurrect credentials written concurrently (#920).
        with self._store_lock():
            store = self._load_encrypted_store()
            if key in store:
                del store[key]
                self._save_encrypted_store(store)
                logger.debug(f"Deleted {key} from encrypted file")

    def list_providers(self) -> list[CredentialProvider]:
        """List all stored provider types from encrypted file storage.

        Note:
            This only returns credentials stored in the encrypted file.
            Credentials stored directly in the system keyring (when keyring
            is available and working) are not enumerable due to keyring API
            limitations. However, CredentialManager.list_credentials()
            checks all known provider types and will find keyring entries.

        Returns:
            List of providers that have stored credentials in encrypted file
        """
        providers = []

        # Check encrypted file only - keyring doesn't support enumeration
        store = self._load_encrypted_store_for_read()
        for key in store:
            try:
                providers.append(CredentialProvider[key])
            except KeyError:
                logger.warning(f"Unknown provider in store: {key}")

        return providers


class CredentialManager:
    """High-level credential management API.

    Provides environment variable override, storage abstraction,
    and credential lifecycle management.

    With ``user_id`` the underlying store is scoped to that user (#790); the
    first per-user manager also copies any legacy machine-wide entries into
    the user's store while leaving the machine-wide source intact.
    ``user_id=None`` is the machine-wide store itself and never migrates.
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        user_id: Optional[int] = None,
        migrate: bool = True,
    ):
        """Initialize credential manager.

        Args:
            storage_dir: Directory for credential storage
            user_id: Scope credentials to this user; None keeps the machine-wide store
            migrate: Whether to run the machine-wide → per-user migration on first
                construction for this user.  Pass ``False`` from read-only endpoints
                so that a plain GET cannot write credentials into a new tenant store
                (the admin-scoped PUT/POST paths keep the default ``True``).
        """
        self._user_id = user_id
        self._storage_dir = storage_dir
        self._store = CredentialStore(storage_dir, user_id=user_id)
        if migrate and user_id is not None:
            if self._store.storage_dir not in _MIGRATION_COMPLETE:
                self._migrate_machine_wide_entries()
                _MIGRATION_COMPLETE.add(self._store.storage_dir)

    def _migrate_machine_wide_entries(self) -> None:
        """Copy legacy machine-wide credentials into this user's store (#790).

        Probes every known provider (the keyring backend cannot enumerate, so
        the enum is the probe list — same trick as ``list_credentials``), copies
        entries the user's store lacks, and leaves the machine-wide entries in
        place. Idempotent; first-come-first-served for the per-user copy only.
        The machine-wide file + salt are left in place so legacy managers
        (CLI/background, ``user_id=None``) continue to work and autoclose keeps
        seeing the source credential.

        A thread lock and an optional file lock (when ``filelock`` is installed)
        serialize concurrent migrations for the same storage root, protecting
        the per-user store's read-modify-write save from concurrent first-time
        requests for the same user.
        """
        machine_store = CredentialStore(self._storage_dir)
        if FileLock is None:
            logger.warning(
                "filelock is not installed; cross-process migration serialization "
                "is disabled. Install filelock for multi-process deployments."
            )

        thread_lock, file_lock = _get_migration_locks(machine_store.storage_dir)
        with ExitStack() as stack:
            stack.enter_context(thread_lock)
            if file_lock is not None:
                stack.enter_context(file_lock)

            copied: list[str] = []
            for provider in CredentialProvider:
                if self._store.retrieve(provider) is not None:
                    continue
                credential = machine_store.retrieve(provider)
                if credential is None:
                    continue
                self._store.store(credential)
                copied.append(provider.name)
            if copied:
                logger.info(
                    f"Copied {len(copied)} legacy credential(s) into user "
                    f"{self._user_id}'s store: {', '.join(copied)}"
                )

    def get_credential(
        self,
        provider: CredentialProvider,
        name: Optional[str] = None,
        *,
        prefer_stored: bool = False,
    ) -> Optional[str]:
        """Get credential value, checking env var first.

        Args:
            provider: The provider type
            name: Optional credential name (unused for env var lookup)
            prefer_stored: Check this manager's store *before* the environment.
                The default env-first order is a self-hosted convenience, but it
                is wrong for a user-scoped manager: the environment belongs to
                the operator, not to the caller, so an ambient ``GITHUB_TOKEN``
                would silently win over the PAT a user connected in the UI and
                act on the operator's behalf (issue #900). Callers resolving a
                per-user credential must pass this.

        Returns:
            Credential value if found, None otherwise
        """
        def _from_store() -> Optional[str]:
            credential = self._store.retrieve(provider)
            if credential is None:
                return None
            if credential.is_expired:
                logger.warning(f"Credential for {provider.name} has expired")
                return None
            return credential.value

        def _from_env() -> Optional[str]:
            env_value = os.environ.get(provider.env_var)
            if env_value:
                logger.debug(f"Using {provider.env_var} from environment")
            return env_value or None

        first, second = (_from_store, _from_env) if prefer_stored else (_from_env, _from_store)
        return first() or second()

    def get_stored_credential(
        self,
        provider: CredentialProvider,
    ) -> Optional[str]:
        """Get a credential from this manager's store only, never the environment.

        For contexts where the process environment is not the caller's to use —
        hosted/multi-tenant mode, where ``GITHUB_TOKEN`` is shared by every
        tenant and falling back to it is the cross-tenant leak itself (#900).
        """
        credential = self._store.retrieve(provider)
        if credential is None:
            return None
        if credential.is_expired:
            logger.warning(f"Credential for {provider.name} has expired")
            return None
        return credential.value

    def get_credential_source(
        self,
        provider: CredentialProvider,
    ) -> CredentialSource:
        """Determine where a credential comes from.

        Args:
            provider: The provider type

        Returns:
            CredentialSource indicating the source
        """
        if os.environ.get(provider.env_var):
            return CredentialSource.ENVIRONMENT

        credential = self._store.retrieve(provider)
        if credential:
            return CredentialSource.STORED

        return CredentialSource.NOT_FOUND

    def set_credential(
        self,
        provider: CredentialProvider,
        value: str,
        name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Store a credential securely.

        Args:
            provider: The provider type
            value: The credential value
            name: Optional friendly name
            metadata: Optional metadata (scopes, etc.)
            expires_at: Optional expiration timestamp
        """
        credential = Credential(
            provider=provider,
            value=value,
            name=name,
            metadata=metadata or {},
            expires_at=expires_at,
        )
        self._store.store(credential)
        logger.info(f"Stored credential for {provider.display_name}")

    def delete_credential(self, provider: CredentialProvider) -> None:
        """Delete a credential.

        Args:
            provider: The provider type to delete
        """
        self._store.delete(provider)
        logger.info(f"Deleted credential for {provider.display_name}")

    def rotate_credential(
        self,
        provider: CredentialProvider,
        new_value: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Rotate a credential atomically.

        Stores new value, only removes old after successful store.

        Args:
            provider: The provider type
            new_value: The new credential value
            metadata: Optional updated metadata
        """
        # Get existing metadata if not provided
        existing = self._store.retrieve(provider)
        if existing and metadata is None:
            metadata = existing.metadata

        # Store new credential (overwrites old)
        self.set_credential(
            provider=provider,
            value=new_value,
            name=existing.name if existing else None,
            metadata=metadata,
        )
        logger.info(f"Rotated credential for {provider.display_name}")

    def list_credentials(self) -> list[CredentialInfo]:
        """List all available credentials with their sources.

        Returns:
            List of CredentialInfo objects
        """
        credentials = []

        # Check all providers
        for provider in CredentialProvider:
            source = self.get_credential_source(provider)

            if source == CredentialSource.NOT_FOUND:
                continue

            info = CredentialInfo(
                provider=provider,
                source=source,
            )

            if source == CredentialSource.ENVIRONMENT:
                env_value = os.environ.get(provider.env_var, "")
                if len(env_value) > 8:
                    info.masked_value = f"{env_value[:4]}...{env_value[-4:]}"
                else:
                    info.masked_value = "***"

            elif source == CredentialSource.STORED:
                cred = self._store.retrieve(provider)
                if cred:
                    info.name = cred.name
                    info.masked_value = cred.masked_value
                    info.is_expired = cred.is_expired
                    info.metadata = cred.metadata

            credentials.append(info)

        return credentials

    def validate_credential_format(
        self,
        provider: CredentialProvider,
        value: str,
    ) -> bool:
        """Validate credential format.

        Args:
            provider: The provider type
            value: The credential value

        Returns:
            True if format appears valid
        """
        return validate_credential_format(provider, value)
