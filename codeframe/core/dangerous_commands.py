"""Dangerous shell-command patterns — the shared filter for every engine.

Deliberately a **leaf module**: it imports nothing but the stdlib. Both consumers
need it cheaply.

- The built-in ReAct engine imports it once per process (``core/tools.py``).
- The claude-code guard (``core/claude_code_guard.py``) is spawned as a fresh
  subprocess for *every* Bash call the delegated CLI makes, so it pays this
  module's import cost per command. Living under ``core/executor.py`` — which
  pulls in ``codeframe.adapters.llm`` and the openai SDK, ~930 modules — cost
  ~420ms per Bash call for what is a regex match. (#819 review)

``core/executor.py`` re-exports both names, so the historical import path keeps
working and the patterns stay a single source of truth.
"""

from __future__ import annotations

import re
import shlex

#: How the home directory can be spelled. ``~`` is the obvious one, but nothing
#: here expands variables — ``shlex.split`` leaves ``$HOME`` as the literal token
#: ``$HOME``, and the *shell* expands it later — so a denylist that only knows
#: ``~`` never sees ``rm -rf $HOME`` coming (#955). ``\b`` after ``HOME`` is what
#: keeps ``$HOMEDIR`` and ``$HOMEBREW_PREFIX`` out.
_HOME = r"(?:~|\$\{?HOME\b\}?)"

#: Interpreters that will happily execute whatever a download hands them. The
#: pattern used to be ``(ba)?sh``, which reads as "shells" but matches exactly
#: two of them — ``curl … | zsh`` and ``curl … | python`` walked straight past
#: it (#955). ``\b`` at the end is load-bearing: without it ``| shasum`` matches
#: as ``sh``.
_INTERPRETERS = r"(?:(?:ba|z|k|da|a)?sh|fish|python[0-9.]*|perl|ruby|node|php)"

# Module-level dangerous command patterns (importable by other modules like tools.py)
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Recursive delete of root or home
    (rf"\brm\s+(-[rf]+\s+)*(?:/|{_HOME})", "recursive deletion of root or home"),
    (r"\brm\s+--no-preserve-root", "rm with --no-preserve-root"),
    # Writing to /dev/ devices
    (r">\s*/dev/", "redirect to /dev device"),
    (r"\bdd\s+.*of=/dev/", "dd writing to device"),
    # Filesystem destruction
    (r"\bmkfs\b", "filesystem format command"),
    (r"\bfdisk\b", "disk partition command"),
    # Fork bombs
    (r":\s*\(\s*\)\s*\{", "potential fork bomb"),
    (r"\bfork\s*while\s*true", "potential fork bomb"),
    # Dangerous dd operations
    (r"\bdd\s+if=/dev/", "dd reading from device"),
    # Dangerous chmod
    (r"\bchmod\s+(-[Rr]\s+)?777\s+/", "chmod 777 on root"),
    # Wget/curl piped to an interpreter (potential malware download)
    (
        rf"\b(wget|curl)\s+.*\|\s*(?:sudo\s+)?{_INTERPRETERS}\b",
        "download piped to interpreter",
    ),
    # Overwriting important system files
    (r">\s*/(etc|bin|usr|lib|sbin)/", "overwriting system directory"),
    # Reaching the operator's credential store (#905). run_command already gets a
    # sandboxed HOME, so `~/.codeframe` and `$HOME/.codeframe` resolve into the
    # workspace — this catches the absolute path an agent can still discover via
    # `ls /home`. Defense in depth against prompt injection, not a containment
    # boundary: an obfuscated path defeats it, and only OS-level isolation
    # (worktree/E2B/container) actually contains a hostile command.
    (r"\.codeframe/credentials", "reading the credential store"),
]


def is_dangerous_command(command: str) -> tuple[bool, str]:
    """Check if a command matches dangerous patterns.

    Uses regex-based patterns that are harder to bypass than substring matching.
    Normalizes whitespace and handles common shell escapes.

    Args:
        command: The shell command to check

    Returns:
        Tuple of (is_dangerous, description) where description explains the match
    """
    # Normalize the command for comparison
    try:
        # Use shlex to handle escapes, then rejoin
        tokens = shlex.split(command)
        normalized = " ".join(tokens)
    except ValueError:
        # If shlex fails, use the original with normalized whitespace
        normalized = " ".join(command.split())

    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return (True, description)
        # Also check original command in case normalization removed something
        if re.search(pattern, command, re.IGNORECASE):
            return (True, description)

    return (False, "")
