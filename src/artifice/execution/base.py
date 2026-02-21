"""Base types for code execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable


class ExecutionStatus(Enum):
    """Status of code execution."""

    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    ERROR = auto()


@dataclass
class ExecutionResult:
    """Result of executing Python code."""

    code: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    output: str = ""
    error: str = ""
    result_value: Any = None
    exception: Exception | None = None


@dataclass
class ExecutionCallbacks:
    """Callbacks for execution output streaming."""

    on_output: Callable[[str], None] | None = None
    on_error: Callable[[str], None] | None = None
