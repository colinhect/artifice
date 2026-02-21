"""Python code executor with async streaming support."""

from __future__ import annotations

import asyncio
import sys
import threading
from io import StringIO
from queue import Queue
from typing import TYPE_CHECKING, Any

from artifice.execution.base import ExecutionResult, ExecutionStatus
from artifice.execution.base_executor import BaseExecutor
from artifice.execution.errors import execution_error_handler

if TYPE_CHECKING:
    from collections.abc import Callable


class StreamCapture(StringIO):
    """StringIO that puts output into a queue."""

    def __init__(self, queue: Queue, stream_type: str) -> None:
        super().__init__()
        self._queue = queue
        self._stream_type = stream_type

    def write(self, s: str) -> int:
        result = super().write(s)
        if s:
            self._queue.put((self._stream_type, s))
        return result


class CodeExecutor(BaseExecutor):
    """Executes Python code asynchronously with persistent session context.

    The executor maintains a persistent globals/locals dictionary across executions,
    allowing variables, functions, and imports to persist between code executions
    (similar to a Python REPL).

    Execution happens in a thread pool to avoid blocking the async event loop,
    with output streamed via callbacks as it's generated.

    Security Note: Code is executed with eval()/exec() without sandboxing.
    Only execute trusted code from trusted sources.
    """

    def __init__(
        self,
        sleep_interval: float = 0.005,
        on_output: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(on_output=on_output, on_error=on_error, timeout=timeout)
        self._globals: dict[str, Any] = {
            "__name__": "__main__",
            "__builtins__": __builtins__,
        }
        self._locals: dict[str, Any] = {}
        self._exec_lock = threading.Lock()
        self.sleep_interval = sleep_interval

    def reset(self) -> None:
        """Reset the execution context."""
        self._globals = {"__name__": "__main__", "__builtins__": __builtins__}
        self._locals = {}

    async def execute(
        self,
        code: str,
        on_output: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> ExecutionResult:
        """Execute Python code asynchronously with streaming output.

        Args:
            code: The Python code to execute.
            on_output: Optional callback for stdout output.
            on_error: Optional callback for stderr output.

        Returns:
            ExecutionResult with status, output, and any errors.
        """
        on_output = on_output or self.on_output
        on_error = on_error or self.on_error

        result = ExecutionResult(code=code, status=ExecutionStatus.RUNNING)

        with execution_error_handler(result, on_error):
            output_queue: Queue = Queue()
            result_value, captured_stdout, captured_stderr = await self._execute_cell(
                code, output_queue, on_output, on_error
            )

            result.result_value = result_value
            result.output = captured_stdout
            result.error = captured_stderr
            result.status = (
                ExecutionStatus.SUCCESS
                if not captured_stderr
                else ExecutionStatus.ERROR
            )

        return result

    async def _execute_cell(
        self,
        code: str,
        output_queue: Queue,
        on_output: Callable[[str], None] | None,
        on_error: Callable[[str], None] | None,
    ) -> tuple[Any, str, str]:
        """Execute a cell of code and capture output.

        Args:
            code: The code to execute
            output_queue: Queue for thread-safe output capture
            on_output: Callback for stdout
            on_error: Callback for stderr

        Returns:
            Tuple of (result_value, stdout, stderr)
        """
        loop = asyncio.get_running_loop()
        exec_task = loop.run_in_executor(None, self._execute_sync, code, output_queue)

        try:
            await self._capture_output_queue(
                output_queue, on_output, on_error, exec_task
            )
            return await exec_task
        except asyncio.CancelledError:
            exec_task.cancel()
            raise

    async def _capture_output_queue(
        self,
        queue: Queue,
        on_output: Callable[[str], None] | None,
        on_error: Callable[[str], None] | None,
        exec_task: asyncio.Future,
    ) -> None:
        """Capture output from queue while task is running.

        Args:
            queue: Queue to read from
            on_output: Callback for stdout messages
            on_error: Callback for stderr messages
            exec_task: Task to monitor
        """
        while not exec_task.done():
            output_lines = self._drain_queue(queue)
            self._dispatch_output(output_lines, on_output, on_error)
            await asyncio.sleep(self.sleep_interval)

        # Process remaining output
        output_lines = self._drain_queue(queue)
        self._dispatch_output(output_lines, on_output, on_error)

    def _drain_queue(self, queue: Queue) -> list[tuple[str, str]]:
        """Drain all items from queue.

        Args:
            queue: Queue to drain

        Returns:
            List of (stream_type, text) tuples
        """
        items = []
        while not queue.empty():
            items.append(queue.get_nowait())
        return items

    def _dispatch_output(
        self,
        output_lines: list[tuple[str, str]],
        on_output: Callable[[str], None] | None,
        on_error: Callable[[str], None] | None,
    ) -> None:
        """Dispatch output to appropriate callbacks.

        Args:
            output_lines: List of (stream_type, text) tuples
            on_output: Callback for stdout
            on_error: Callback for stderr
        """
        for stream_type, text in output_lines:
            if stream_type == "stdout" and on_output:
                on_output(text)
            elif stream_type == "stderr" and on_error:
                on_error(text)

    def _execute_sync(self, code: str, output_queue: Queue) -> tuple[Any, str, str]:
        """Execute code synchronously (called in thread pool)."""
        with self._exec_lock:
            old_stdout, old_stderr = sys.stdout, sys.stderr

            captured_stdout = StreamCapture(output_queue, "stdout")
            captured_stderr = StreamCapture(output_queue, "stderr")

            sys.stdout = captured_stdout
            sys.stderr = captured_stderr

            result_value = None
            try:
                # Try to compile as expression first (for return value)
                try:
                    compiled = compile(code, "<repl>", "eval")
                    result_value = eval(compiled, self._globals, self._locals)
                except SyntaxError:
                    # Not an expression, try as statements
                    try:
                        compiled = compile(code, "<repl>", "exec")
                        exec(compiled, self._globals, self._locals)
                    except Exception as exec_error:
                        # Error during exec - re-raise without showing the eval attempt
                        raise exec_error from None

                return (
                    result_value,
                    captured_stdout.getvalue(),
                    captured_stderr.getvalue(),
                )
            except Exception as e:
                # Any error - capture traceback in stderr
                captured_stderr.write(str(e))
                return None, captured_stdout.getvalue(), captured_stderr.getvalue()
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr
