"""Backward compatibility re-export for input_mode module (now events)."""

from __future__ import annotations

from artifice.core.events import InputMode, InputModeConfig

__all__ = ["InputMode", "InputModeConfig"]
