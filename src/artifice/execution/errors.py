from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from typing import TYPE_CHECKING

from artifice.execution.base import ExecutionResult, ExecutionStatus

if TYPE_CHECKING:
    from typing import Any


@contextmanager
def execution_error_handler(
    result: ExecutionResult,
    on_error: Callable[[str], None] | None = None,
) -> Any:
    """Context manager for consistent execution error handling.

    Args:
        result: The ExecutionResult to modify on errors
        on_error: Optional callback to invoke with error messages

    Yields:
        The result object for use within the context

    Example:
        def execute(self, code: str) -> ExecutionResult:
            result = ExecutionResult()
            with execution_error_handler(result, self.on_error):
                # execution logic here
                result.output = output
                result.status = ExecutionStatus.SUCCESS
            return result
    """
    try:
        yield result
    except asyncio.CancelledError:
        result.status = ExecutionStatus.ERROR
        result.error = "\n[Execution cancelled]\n"
        if on_error:
            on_error(result.error)
        raise
    except Exception as e:
        result.status = ExecutionStatus.ERROR
        result.exception = e
        result.error = traceback.format_exc()
        if on_error:
            on_error(result.error)
