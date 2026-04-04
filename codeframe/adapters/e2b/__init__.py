"""E2B cloud execution adapter package."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "E2BAgentAdapter":
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter
        return E2BAgentAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["E2BAgentAdapter"]
