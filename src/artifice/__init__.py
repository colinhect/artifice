"""Artifice - AI-powered terminal interface."""

from __future__ import annotations

__all__ = ["ArtificeTerminal"]
__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy import to avoid loading UI for CLI commands."""
    if name == "ArtificeTerminal":
        from artifice.ui.widget import ArtificeTerminal

        return ArtificeTerminal
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
