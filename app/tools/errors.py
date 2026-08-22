"""Shared tool error types.

Kept in its own module so `app.tools.credentials` and `app.tools.providers`
can both use it without an import cycle.
"""

from __future__ import annotations


class ToolProviderError(Exception):
    """Raised when an external tool provider cannot be reached safely."""
