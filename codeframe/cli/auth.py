"""CLI authentication module - JWT token storage and retrieval.

This module handles:
- Storing JWT tokens securely in ~/.codeframe/credentials.json
- Retrieving tokens for API requests
- Supporting CODEFRAME_TOKEN environment variable override
- Clearing stored credentials on logout

Security considerations:
- Credentials file has 600 permissions (owner read/write only)
- Environment variable takes precedence over file storage
- No token validation is done here (that's the API's job)
"""

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def get_credentials_path() -> Path:
    """Get the path to the credentials file.

    Returns:
        Path to ~/.codeframe/credentials.json
    """
    return Path.home() / ".codeframe" / "credentials.json"


def store_token(token: str) -> None:
    """Store JWT token securely.

    Creates the credentials file with restricted permissions (600).
    Parent directories are created if they don't exist.

    Args:
        token: JWT access token to store
    """
    creds_path = get_credentials_path()

    # Create parent directory owner-only. mkdir's mode is masked by umask and
    # only applies on creation, so chmod unconditionally to guarantee 0o700.
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.parent.chmod(0o700)

    credentials = {"access_token": token}

    # Write to a fresh temp file (mkstemp creates it 0o600 with O_EXCL) and
    # atomically replace the target. The token is thus only ever written to a
    # born-owner-only file, closing the open()+chmod TOCTOU window even when a
    # credentials file already exists with looser permissions (#772).
    fd, tmp_path = tempfile.mkstemp(
        dir=creds_path.parent, prefix=".credentials-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(credentials, f, indent=2)
        os.replace(tmp_path, creds_path)
    except BaseException:
        # Never leave a stray temp file holding the token behind.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise

    logger.debug(f"Token stored in {creds_path}")


def get_token() -> str | None:
    """Get the stored JWT token.

    Checks in order:
    1. CODEFRAME_TOKEN environment variable
    2. ~/.codeframe/credentials.json file

    Returns:
        JWT token string, or None if not found
    """
    # Check environment variable first
    env_token = os.environ.get("CODEFRAME_TOKEN")
    if env_token:
        logger.debug("Using token from CODEFRAME_TOKEN environment variable")
        return env_token

    # Check credentials file
    creds_path = get_credentials_path()

    if not creds_path.exists():
        logger.debug(f"Credentials file not found: {creds_path}")
        return None

    try:
        with open(creds_path) as f:
            data = json.load(f)

        token = data.get("access_token")
        if token:
            logger.debug("Using token from credentials file")
            return token

        logger.debug("No access_token key in credentials file")
        return None

    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in credentials file: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error reading credentials file: {e}")
        return None


def clear_token() -> None:
    """Clear stored credentials.

    Removes the credentials file if it exists.
    """
    creds_path = get_credentials_path()

    if creds_path.exists():
        creds_path.unlink()
        logger.debug(f"Removed credentials file: {creds_path}")
    else:
        logger.debug(f"No credentials file to remove: {creds_path}")


def is_authenticated() -> bool:
    """Check if user is authenticated.

    Returns:
        True if a token is available, False otherwise
    """
    return get_token() is not None
