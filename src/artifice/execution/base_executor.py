from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class BaseExecutor:
    """Base class for code executors with common functionality."""

    def __init__(
        self,
        on_output: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize base executor.

        Args:
            on_output: Callback invoked for output messages
            on_error: Callback invoked for error messages
            timeout: Default timeout in seconds
        """
        self.on_output = on_output
        self.on_error = on_error
        self.timeout = timeout
