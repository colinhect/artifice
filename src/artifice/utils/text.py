"""Utility functions and helpers for Artifice."""

from __future__ import annotations


def format_tokens(n: int) -> str:
    """Format token count as a compact string (e.g. 1.2k, 128k)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)
