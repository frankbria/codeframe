"""Which environment variables came from the *repository* (issue #903).

``cf`` loads ``<cwd>/.env`` with ``override=True``, so a file committed inside a
cloned repo wins over what the operator exported. Anything downstream that
treats ``os.environ`` as "the operator's own configuration" is therefore wrong
for those keys — a repo can set them.

This module records which keys the workspace ``.env`` supplied, so a security
decision can tell the two apart. It deliberately holds *names only*: values stay
in ``os.environ`` and are never copied here.

Headless — no CLI or HTTP imports (architecture rule #1).

Note this is the narrow, base_url-shaped half of the problem. Stopping a repo
``.env`` from overriding the operator's environment in general is #904.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

#: Env var names supplied by the workspace's own ``.env``.
_repo_supplied: set[str] = set()


def record_repo_env_keys(keys: Iterable[str]) -> None:
    """Mark ``keys`` as having come from the repository."""
    _repo_supplied.update(keys)


def is_repo_supplied(name: str) -> bool:
    """Whether ``name``'s value in ``os.environ`` came from the repo's ``.env``."""
    return name in _repo_supplied


def reset() -> None:
    """Clear recorded provenance (tests)."""
    _repo_supplied.clear()


def keys_defined_in(env_file: Path) -> set[str]:
    """Names assigned in a ``.env`` file, without evaluating its values.

    A deliberately minimal parser: it only needs the left-hand sides, and
    reading values here would mean holding secrets in a second place.
    """
    names: set[str] = set()
    try:
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name = line.split("=", 1)[0].strip()
            if name.startswith("export "):
                name = name[len("export "):].strip()
            if name:
                names.add(name)
    except OSError:
        return set()
    return names


# ---------------------------------------------------------------------------
# Endpoint trust (issue #903)
#
# Lives here rather than in ``llm_resolution`` so the *adapters* can apply it
# too: ``llm_resolution`` imports the adapters, so the reverse would be a cycle,
# and this module deliberately depends on nothing.
# ---------------------------------------------------------------------------

#: Opt-in for a repo-supplied ``base_url`` that points off this machine. Mirrors
#: the other deliberate escape hatches (``CODEFRAME_ALLOW_PRIVATE_WEBHOOKS``,
#: ``CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES``).
ALLOW_CONFIG_BASE_URL_ENV = "CODEFRAME_ALLOW_CONFIG_BASE_URL"

_TRUTHY = {"1", "true", "yes", "on"}


class UntrustedBaseURLError(RuntimeError):
    """A repo-supplied ``base_url`` would send API traffic off this machine.

    ``.codeframe/config.yaml`` and ``.env`` both live *inside the repository*,
    so cloning an untrusted repo and running any LLM command would otherwise
    ship the operator's long-lived API key to whatever host they name — with no
    validation, no warning, and no visible difference in output (issue #903).
    """


def is_loopback_url(url) -> bool:
    """Whether ``url``'s host is this machine.

    A loopback endpoint cannot exfiltrate anything to a remote attacker, and it
    is the documented local-model setup (ollama/vLLM/LM Studio), so it stays
    friction-free. Anything else is a redirect that must be chosen deliberately.
    """
    try:
        host = (urlparse(url).hostname or "").strip()
    except Exception:
        # Deliberately broad: this predicate is fail-closed, and a malformed
        # config can set base_url to any YAML type — urlparse raises a different
        # exception per type. "Not parseable" is simply "not this machine".
        return False
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a name we cannot resolve statically is not "this machine"


def base_url_opt_in_granted() -> bool:
    """Whether the operator explicitly allowed off-machine repo endpoints."""
    return os.getenv(ALLOW_CONFIG_BASE_URL_ENV, "").strip().lower() in _TRUTHY


def vet_base_url(value, *, source: str) -> Optional[str]:
    """Return ``value`` if this caller may use it, else raise.

    Args:
        value: candidate endpoint (any type; non-strings fail closed).
        source: human description of where it came from, for the message.

    Raises:
        UntrustedBaseURLError: when it is off-machine and not opted in.
    """
    if not value or is_loopback_url(value) or base_url_opt_in_granted():
        if value and not is_loopback_url(value):
            logger.warning(
                "Using non-default LLM endpoint %s from %s (allowed via %s)",
                value, source, ALLOW_CONFIG_BASE_URL_ENV,
            )
        return value
    raise UntrustedBaseURLError(
        f"The LLM endpoint {value!r} comes from {source}, which is not this "
        "machine, so running would send your API key to that host.\n"
        f"If you trust it, re-run with {ALLOW_CONFIG_BASE_URL_ENV}=1. "
        "Otherwise remove the base_url, or pass a provider explicitly."
    )


def vet_env_base_url(env_var: str) -> Optional[str]:
    """Resolve ``env_var`` as an endpoint, refusing a repo-supplied redirect.

    Called by the provider adapters when no ``base_url`` was passed. Both SDKs
    fall back to reading these variables *themselves* when ``base_url is None``,
    so leaving the value unset does not mean "no endpoint" — it means "an
    endpoint chosen by whatever set the variable", which a repo ``.env`` can be.
    Resolving it here is what puts every construction behind the check.
    """
    value = os.getenv(env_var)
    if not value:
        return None
    if not is_repo_supplied(env_var):
        return value  # the operator's own environment
    return vet_base_url(value, source=f"the repository's .env ({env_var})")
