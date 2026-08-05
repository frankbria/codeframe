"""Shared helpers for v2 routers."""

# The atomic-write implementation moved into core (#954) so the config,
# credential, installer and workspace-init writes all share one durable-replace
# path — and so the core-side callers do not have to import from ui/. Re-exported
# here because the v2 routers already import it from this module.
from codeframe.core.atomic_io import atomic_write_json

__all__ = ["atomic_write_json"]
