"""Backward compatibility re-export for execution.common module (now base)."""

from __future__ import annotations

from artifice.execution.base import (
    ExecutionResult as ExecutionResult,
    ExecutionStatus as ExecutionStatus,
)

__all__ = ["ExecutionResult", "ExecutionStatus"]
