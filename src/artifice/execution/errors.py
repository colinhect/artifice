"""Execution error handling utilities."""

from __future__ import annotations

import asyncio
import traceback
from contextlib import contextmanager
from typing import Callable

from artifice.execution.base import ExecutionResult, ExecutionStatus


@contextmanager
def execution_error_context(
    result: ExecutionResult, on_error: Callable[[str], None] | None = None
):
    """Context manager for standardized execution error handling.

    Handles asyncio.CancelledError and general exceptions consistently,
    updating the ExecutionResult and calling the optional error callback.

    Args:
        result: The ExecutionResult to update on error.
        on_error: Optional callback for error messages.

    Yields:
        None

    Raises:
        asyncio.CancelledError: Re-raised after handling.
    """
    try:
        yield
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
