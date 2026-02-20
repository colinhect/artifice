"""State machine states for code fence detection."""

from __future__ import annotations

import enum


class FenceState(enum.Enum):
    """State machine states for fence detection."""

    PROSE = "prose"
    CODE = "code"
