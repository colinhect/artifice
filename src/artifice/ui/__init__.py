"""User interface layer."""

from __future__ import annotations

__all__ = [
    "ArtificeTerminal",
]


def __getattr__(name: str):
    """Lazy import to avoid circular imports."""
    if name == "ArtificeTerminal":
        from artifice.ui.widget import ArtificeTerminal

        return ArtificeTerminal
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
