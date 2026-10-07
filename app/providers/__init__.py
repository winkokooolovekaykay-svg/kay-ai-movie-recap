"""Provider abstractions. Secrets stay server-side; the frontend only sees
capability flags and honest 'needs API key' states."""
from __future__ import annotations


class ProviderUnavailable(Exception):
    """Raised when a provider cannot run (no key, no dependency, quota...).
    Message must be a user-facing Burmese string."""

    pass
