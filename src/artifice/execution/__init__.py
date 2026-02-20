"""Backward compatibility re-export for execution module."""

from __future__ import annotations

from artifice.execution.base import (
    ExecutionResult as ExecutionResult,
    ExecutionStatus as ExecutionStatus,
)
from artifice.execution.python import CodeExecutor as CodeExecutor
from artifice.execution.shell import ShellExecutor as ShellExecutor
from artifice.execution.shell import TmuxShellExecutor as TmuxShellExecutor

__all__ = [
    "ExecutionResult",
    "ExecutionStatus",
    "CodeExecutor",
    "ShellExecutor",
    "TmuxShellExecutor",
]
