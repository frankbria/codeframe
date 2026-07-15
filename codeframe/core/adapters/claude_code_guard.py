"""PreToolUse hook: block dangerous Bash commands from a delegated claude CLI.

``ClaudeCodeAdapter`` runs ``claude`` with ``--permission-mode bypassPermissions``
so ``--print`` mode does not silently deny Edit/Write/Bash (#739). That hands the
delegated agent unrestricted Bash with none of the ``DANGEROUS_PATTERNS``
filtering the built-in ReAct engine applies to every command it runs
(``core/tools.py`` -> ``is_dangerous_command``). With GitHub Issues import (#565)
turning externally-authored issue bodies into task prompts, that gap widens the
prompt-injection blast radius.

``claude`` runs this module as a PreToolUse hook, which fires *even under*
``bypassPermissions`` — the permission mode skips approval prompts, not hooks.
Re-using ``is_dangerous_command`` keeps one source of truth for the patterns, so
both engines block the same set. (#819)

This is the same grade of protection ReAct has, no more: a regex matcher over the
command string, evadable by an agent that means to evade it (``bash -c``, string
splicing). It raises the floor for accidental and injected destructive commands;
it is not a sandbox.

Contract (https://code.claude.com/docs/en/hooks): the hook JSON arrives on stdin;
exit 0 with no output allows the call; exit 0 with a ``permissionDecision: deny``
payload blocks it and feeds the reason back to the agent.
"""

from __future__ import annotations

import json
import sys

from codeframe.core.executor import is_dangerous_command


def main() -> int:
    """Vet one PreToolUse payload. Returns the process exit code."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        # Not a payload we understand. Allow: a guard that wedges every run on a
        # parse hiccup is worse than one that misses a hook it can't read.
        return 0

    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return 0

    dangerous, reason = is_dangerous_command(command)
    if not dangerous:
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"CodeFrame blocked this command: {reason}. "
                    "Destructive commands are refused for delegated runs; "
                    "achieve the task another way."
                ),
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
