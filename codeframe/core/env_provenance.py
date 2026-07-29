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


# ---------------------------------------------------------------------------
# The shared .env loader (issue #904)
# ---------------------------------------------------------------------------

#: Keys a repository's ``.env`` may never set. These steer *where the process
#: sends things* or *which credential it uses* — a repo that could set them
#: would redirect logins, API traffic and telemetry, or point the tool at
#: another database. Prefixes match any key ending in them.
_REPO_FORBIDDEN_EXACT = frozenset(
    {
        # Where credentials and data are sent
        "CODEFRAME_API_URL",      # `cf auth login` POSTs email+password here
        "CODEFRAME_TOKEN",        # the session token itself
        "CODEFRAME_TELEMETRY_ENDPOINT",
        "CORS_ALLOWED_ORIGINS",   # a repo could allow its own origin
        # Secrets that make sessions/keys forgeable
        "AUTH_SECRET",
        "CODEFRAME_API_KEY_SECRET",
        "CODEFRAME_CREDENTIAL_SECRET",
        "CODEFRAME_BOOTSTRAP_TOKEN",
        "JWT_LIFETIME_SECONDS",   # e.g. a decade-long session
        # Whether the guards run at all
        "CODEFRAME_AUTH_REQUIRED",        # `false` disables authentication
        "CODEFRAME_DEPLOYMENT_MODE",      # flips hosted-mode gating
        "CODEFRAME_ENABLE_TEST_ENDPOINTS",  # arms /test/broadcast (#753)
        "WORKSPACE_ROOT",         # the workspace allowlist (#655/#896)
        # Where code is found and run
        "PATH",
        "HOME",                   # relocates ~/.env and the credential store
        # How outbound HTTPS is routed and verified. `requests` honors these
        # from the environment by default (trust_env=True), and `cf auth login`
        # POSTs email+password with no proxies=/verify=/trust_env=False. So a
        # repo .env pairing HTTPS_PROXY with its own CA bundle MITMs exactly the
        # request this issue exists to protect — routing around the
        # CODEFRAME_API_URL block rather than through it. Lower-case forms are
        # covered too: the check upper-cases the name first.
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "FTP_PROXY",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)

#: Suffixes a repository's ``.env`` may never set, for the same reason.
#: ``_PATH`` covers DATABASE_PATH and KILOCODE_PATH — a filesystem location the
#: tool reads, writes, or *executes*.
#: ``_FLAGS`` covers KILOCODE_FLAGS and friends: shell-quoted arguments spliced
#: into a delegated engine's command line, i.e. argument injection.
_REPO_FORBIDDEN_SUFFIXES = ("_BASE_URL", "_API_URL", "_PATH", "_FLAGS")

#: Prefixes a repository's ``.env`` may never set. Every deliberate escape hatch
#: is named ``CODEFRAME_ALLOW_*``, and a repo granting itself one is the whole
#: problem: ``CODEFRAME_ALLOW_CONFIG_BASE_URL=1`` alone would reopen #903, and
#: ``CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES`` / ``_PRIVATE_WEBHOOKS`` disarm
#: the workspace allowlist and the SSRF guard. A prefix rule rather than a list
#: so a hatch added later is covered by default.
_REPO_FORBIDDEN_PREFIXES = ("CODEFRAME_ALLOW_",)


def is_forbidden_from_repo(name: str) -> bool:
    """Whether a repository ``.env`` is allowed to define ``name``."""
    upper = name.upper()
    return (
        upper in _REPO_FORBIDDEN_EXACT
        or upper.endswith(_REPO_FORBIDDEN_SUFFIXES)
        or upper.startswith(_REPO_FORBIDDEN_PREFIXES)
    )


def load_env_files(
    cwd: Optional[Path] = None,
    home: Optional[Path] = None,
    explicit_file: Optional[Path] = None,
) -> None:
    """Load ``~/.env`` then ``<cwd>/.env`` — the one place that does this (#904).

    Two rules the previous four copies of this logic did not follow:

    1. **The repository never overrides the operator.** ``<cwd>/.env`` used to be
       loaded with ``override=True``, so a committed file won over what the
       operator exported. A repo could therefore point ``CODEFRAME_API_URL`` at
       its own host and ``cf auth login`` would POST the user's email and
       password there — the insecure-transport warning only fires for ``http://``,
       so an ``https://`` attacker host is silent.
    2. **Security-steering keys are never taken from a repo at all**, even when
       the operator has not set them, because "unset" is the common case and
       silence is what makes this dangerous. See ``is_forbidden_from_repo``.

    The home ``.env`` is the operator's own file and is not restricted.
    Provenance is still recorded for what the repo did supply (#903).
    """
    from dotenv import load_dotenv

    if explicit_file is not None:
        # A caller naming a specific file chose it deliberately — that is the
        # operator's decision, not repo content, so it is loaded as-is.
        if explicit_file.exists():
            load_dotenv(explicit_file)
        return

    home_env = (home or Path.home()) / ".env"
    cwd_env = (cwd or Path.cwd()) / ".env"

    # When cwd *is* home the two are one file. Treat it as the repository copy —
    # fail closed — because we cannot tell an operator's ~/.env from a checkout
    # that happens to live at $HOME, and the ignored keys are logged either way.
    same_file = (
        home_env.exists()
        and cwd_env.exists()
        and home_env.resolve() == cwd_env.resolve()
    )

    if home_env.exists() and not same_file:
        load_dotenv(home_env)

    if not cwd_env.exists():
        return

    repo_keys = keys_defined_in(cwd_env)
    blocked = {k for k in repo_keys if is_forbidden_from_repo(k)}

    # Record provenance only for keys the repo actually gets to supply. A
    # blocked key's value is discarded below, so marking it repo-supplied would
    # make the #903 endpoint gate refuse the *operator's own* value merely
    # because a repo .env mentioned the same name — the opposite of this
    # module's guarantee.
    record_repo_env_keys(repo_keys - blocked)
    if blocked:
        logger.warning(
            "Ignoring %d security-sensitive key(s) from the repository's .env: %s",
            len(blocked),
            ", ".join(sorted(blocked)),
        )

    # override=False: whatever the operator exported stands. Then remove any
    # forbidden key this file introduced — dotenv has no per-key filter, so the
    # cheap correct approach is to snapshot those names first and restore them.
    preserved = {k: os.environ.get(k) for k in blocked}
    load_dotenv(cwd_env)
    for key, original in preserved.items():
        if original is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original
