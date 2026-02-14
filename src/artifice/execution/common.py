from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


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

    @property
    def is_complete(self) -> bool:
        """Check if execution is complete."""
        return self.status in (ExecutionStatus.SUCCESS, ExecutionStatus.ERROR)

    @property
    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.status == ExecutionStatus.SUCCESS
