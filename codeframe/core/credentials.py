"""Secure credential management for CodeFRAME.

This module provides:
- Platform-native keyring integration (primary storage)
- Encrypted file fallback when keyring unavailable
- Environment variable override support
- Credential validation and rotation

Security features:
- Fernet encryption for file-based storage
- File permissions enforced at 600 (owner-only)
- Machine-specific encryption keys
- Audit logging for credential operations

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
import platform
import uuid
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

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


logger = logging.getLogger(__name__)

# Constants
KEYRING_SERVICE_NAME = "codeframe-credentials"
ENCRYPTED_FILE_NAME = "credentials.encrypted"
SALT_FILE_NAME = "salt"
DEFAULT_STORAGE_DIR = Path.home() / ".codeframe"


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
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

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
    """Derive encryption key from machine-specific data.

    Uses PBKDF2 with machine ID and a persistent salt to create
    a Fernet-compatible encryption key.

    Args:
        salt_file: Path to store/retrieve the salt

    Returns:
        Fernet-compatible key (base64 encoded)
    """
    # Get or create salt
    if salt_file.exists():
        with open(salt_file, "rb") as f:
            salt = f.read()
    else:
        salt = os.urandom(16)
        salt_file.parent.mkdir(parents=True, exist_ok=True)
        with open(salt_file, "wb") as f:
            f.write(salt)
        # Secure permissions
        salt_file.chmod(0o600)

    # Get machine-specific identifier
    machine_id = _get_machine_id()

    # Derive key using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))

    return key


def _get_machine_id() -> str:
    """Get a machine-specific identifier."""
    # Try to get a stable machine ID
    components = [
        platform.node(),
        platform.machine(),
        str(uuid.getnode()),  # MAC address
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
        # Anthropic keys start with "sk-ant-"
        return len(value) >= 10

    elif provider == CredentialProvider.LLM_OPENAI:
        # OpenAI keys start with "sk-"
        return len(value) >= 10

    elif provider == CredentialProvider.GIT_GITHUB:
        # GitHub PATs: ghp_ (classic) or github_pat_ (fine-grained)
        return len(value) >= 10 and (
            value.startswith("ghp_") or
            value.startswith("github_pat_") or
            value.startswith("gho_") or  # OAuth
            value.startswith("ghs_")  # Server-to-server
        )

    elif provider == CredentialProvider.GIT_GITLAB:
        # GitLab tokens: glpat- prefix
        return len(value) >= 10

    # Default: just check minimum length
    return len(value) >= 5


class CredentialStore:
    """Low-level credential storage.

    Uses platform keyring as primary storage with encrypted file fallback.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize credential store.

        Args:
            storage_dir: Directory for encrypted file storage
        """
        self.storage_dir = storage_dir or DEFAULT_STORAGE_DIR
        self._keyring_available = self._check_keyring()
        self._fernet: Optional[Fernet] = None

    def _check_keyring(self) -> bool:
        """Check if keyring is available and working."""
        if not KEYRING_AVAILABLE:
            return False

        try:
            # Try to get the keyring backend
            kr = keyring.get_keyring()
            # Check if it's a real backend (not fail keyring)
            if "fail" in kr.__class__.__name__.lower():
                return False
            return True
        except Exception:
            return False

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
        """Load all credentials from encrypted file."""
        file_path = self._get_encrypted_file_path()
        if not file_path.exists():
            return {}

        try:
            with open(file_path, "rb") as f:
                encrypted_data = f.read()

            fernet = self._get_fernet()
            decrypted = fernet.decrypt(encrypted_data)
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Failed to load encrypted credentials: {e}")
            return {}

    def _save_encrypted_store(self, store: dict[str, dict]) -> None:
        """Save all credentials to encrypted file."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._get_encrypted_file_path()
        fernet = self._get_fernet()

        data = json.dumps(store).encode()
        encrypted = fernet.encrypt(data)

        # Write atomically
        temp_path = file_path.with_suffix(".tmp")
        with open(temp_path, "wb") as f:
            f.write(encrypted)
        temp_path.chmod(0o600)
        temp_path.replace(file_path)

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
                keyring.set_password(KEYRING_SERVICE_NAME, key, data)
                logger.debug(f"Stored {key} in keyring")
                return
            except Exception as e:
                logger.warning(f"Keyring storage failed, using encrypted file: {e}")
                self._keyring_available = False

        # Fall back to encrypted file
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
                data = keyring.get_password(KEYRING_SERVICE_NAME, key)
                if data:
                    return Credential.from_dict(json.loads(data))
            except Exception as e:
                logger.debug(f"Keyring retrieval failed: {e}")

        # Fall back to encrypted file
        store = self._load_encrypted_store()
        if key in store:
            return Credential.from_dict(store[key])

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
                keyring.delete_password(KEYRING_SERVICE_NAME, key)
                logger.debug(f"Deleted {key} from keyring")
            except Exception as e:
                logger.debug(f"Keyring deletion failed: {e}")

        # Also remove from encrypted file (if exists)
        store = self._load_encrypted_store()
        if key in store:
            del store[key]
            self._save_encrypted_store(store)
            logger.debug(f"Deleted {key} from encrypted file")

    def list_providers(self) -> list[CredentialProvider]:
        """List all stored provider types.

        Returns:
            List of providers that have stored credentials
        """
        providers = []

        # Check encrypted file
        store = self._load_encrypted_store()
        for key in store:
            try:
                providers.append(CredentialProvider[key])
            except KeyError:
                logger.warning(f"Unknown provider in store: {key}")

        # Note: We can't easily enumerate keyring entries
        # Encrypted file is the source of truth for listing

        return providers


class CredentialManager:
    """High-level credential management API.

    Provides environment variable override, storage abstraction,
    and credential lifecycle management.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize credential manager.

        Args:
            storage_dir: Directory for credential storage
        """
        self._store = CredentialStore(storage_dir)

    def get_credential(
        self,
        provider: CredentialProvider,
        name: Optional[str] = None,
    ) -> Optional[str]:
        """Get credential value, checking env var first.

        Args:
            provider: The provider type
            name: Optional credential name (unused for env var lookup)

        Returns:
            Credential value if found, None otherwise
        """
        # Check environment variable first
        env_value = os.environ.get(provider.env_var)
        if env_value:
            logger.debug(f"Using {provider.env_var} from environment")
            return env_value

        # Fall back to store
        credential = self._store.retrieve(provider)
        if credential:
            if credential.is_expired:
                logger.warning(f"Credential for {provider.name} has expired")
                return None
            return credential.value

        return None

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
