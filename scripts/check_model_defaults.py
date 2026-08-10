#!/usr/bin/env python3
"""Release guard: no dated Anthropic model ID may ship in a published artifact (#1112).

`codeframe-ai==0.9.1` pinned `claude-3-5-haiku-20241022` and four siblings. They
were valid the day they were written and 404 today, so every LLM-backed command
in the published wheel failed for every new user with a perfectly good API key.

Dated IDs get retired. The undated aliases (`claude-haiku-4-5`) do not — Anthropic
repoints them. So the rule is: **defaults and live call sites use aliases.**

Two checks:

  offline (always) — every `DEFAULT_*_MODEL` is a date-less alias, and no live
                     call site hardcodes a dated ID
  live (only when ANTHROPIC_API_KEY is set) — `models.retrieve()` each default,
                     so a retired *alias* would also be caught

The live half is opt-in on purpose: the release build must not depend on a
secret or on the network being up. The offline rule is the one that always runs,
and it is the one that would have caught 0.9.1.

Run: `python -m scripts.check_model_defaults`  (exit 1 on any violation)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# `-YYYYMMDD` at the end of a claude-* model id.
DATED_MODEL_RE = re.compile(r"claude-[a-z0-9.-]*?-(20\d{6})\b")

# Modules that issue real API calls with a hardcoded model. A dated ID here rots
# exactly the way the defaults did. Pricing tables and tests are excluded: they
# *look up* dated names the API returns, which is the opposite problem.
LIVE_CALL_SITES = (
    "codeframe/adapters/llm",
    "codeframe/cli",
    "codeframe/core",
    "codeframe/ui",
)
EXCLUDED_FILES = (
    # Pricing lookups keyed by the dated names the API reports back.
    "codeframe/lib/metrics_tracker.py",
    "codeframe/core/adapters/streaming_chat.py",
)


def _defaults() -> dict[str, str]:
    from codeframe.adapters.llm import base

    return {
        name: getattr(base, name)
        for name in dir(base)
        if name.startswith("DEFAULT_") and name.endswith("_MODEL")
    }


def check_defaults_are_aliases() -> list[str]:
    """Return a violation message per `DEFAULT_*_MODEL` carrying a date suffix."""
    return [
        f"{name} = {value!r} is a dated model ID; use the undated alias so it cannot be retired"
        for name, value in _defaults().items()
        if DATED_MODEL_RE.search(value)
    ]


def check_call_sites(repo_root: Path) -> list[str]:
    """Return a violation message per source line hardcoding a dated model ID."""
    violations = []
    for area in LIVE_CALL_SITES:
        for path in sorted((repo_root / area).rglob("*.py")):
            rel = path.relative_to(repo_root).as_posix()
            if rel in EXCLUDED_FILES:
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                match = DATED_MODEL_RE.search(line)
                if match:
                    violations.append(
                        f"{rel}:{lineno} hardcodes dated model ID {match.group(0)!r}; "
                        f"use a DEFAULT_*_MODEL alias from codeframe.adapters.llm.base"
                    )
    return violations


def check_defaults_resolve() -> list[str]:
    """Ask the API whether each default actually exists.

    No-op without a key, so local and CI-gate runs stay offline. The release job
    sets ``MODEL_GUARD_REQUIRE_LIVE=1``: there, a missing key is itself a failure,
    otherwise an unconfigured secret would silently disable the strongest check
    and we would be back to shipping unverified model IDs.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        if os.getenv("MODEL_GUARD_REQUIRE_LIVE"):
            return [
                "MODEL_GUARD_REQUIRE_LIVE is set but ANTHROPIC_API_KEY is not — "
                "the live model-resolution check cannot run. Configure the "
                "ANTHROPIC_API_KEY secret for this job."
            ]
        return []
    import anthropic

    client = anthropic.Anthropic()
    violations = []
    for name, value in sorted(_defaults().items()):
        try:
            client.models.retrieve(value)
        except anthropic.NotFoundError:
            violations.append(f"{name} = {value!r} does not resolve — the API does not know this model")
        except Exception as exc:  # network, auth, rate limit — not the model's fault
            detail = f"{name} = {value!r}: {type(exc).__name__}: {exc}"
            if os.getenv("MODEL_GUARD_REQUIRE_LIVE"):
                return [f"live model check could not complete — {detail}"]
            print(f"  ! skipped live check for {detail}", file=sys.stderr)
            return []
    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    violations = (
        check_defaults_are_aliases() + check_call_sites(repo_root) + check_defaults_resolve()
    )
    if violations:
        print("Model-default release guard FAILED (#1112):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("Model-default release guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
