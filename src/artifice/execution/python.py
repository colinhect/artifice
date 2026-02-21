"""Python code executor with async streaming support."""

from __future__ import annotations

import asyncio
import sys
import threading
import traceback
from io import StringIO
from queue import Queue
from typing import TYPE_CHECKING, Any

from artifice.execution.base import ExecutionResult, ExecutionStatus

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


class CodeExecutor:
    """Executes Python code asynchronously with persistent session context.

    The executor maintains a persistent globals/locals dictionary across executions,
    allowing variables, functions, and imports to persist between code executions
    (similar to a Python REPL).

    Execution happens in a thread pool to avoid blocking the async event loop,
    with output streamed via callbacks as it's generated.

    Security Note: Code is executed with eval()/exec() without sandboxing.
    Only execute trusted code from trusted sources.
    """

    def __init__(self, sleep_interval: float = 0.005) -> None:
        """Initialize executor with fresh globals/locals context."""
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
        result = ExecutionResult(code=code, status=ExecutionStatus.RUNNING)

        # Create queue for thread-safe communication
        output_queue: Queue = Queue()

        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_running_loop()

            # Start execution task
            exec_task = loop.run_in_executor(
                None, self._execute_sync, code, output_queue
            )
            try:
                while not exec_task.done():
                    # Process any queued output
                    while not output_queue.empty():
                        stream_type, text = output_queue.get_nowait()
                        if stream_type == "stdout" and on_output:
                            on_output(text)
                        elif stream_type == "stderr" and on_error:
                            on_error(text)

                    # Small sleep to avoid busy-waiting
                    await asyncio.sleep(self.sleep_interval)
            except asyncio.CancelledError:
                # Cancel the execution task
                exec_task.cancel()
                result.status = ExecutionStatus.ERROR
                result.error = "\n[Execution cancelled]\n"
                if on_error:
                    on_error(result.error)
                raise

            # Process any remaining output
            while not output_queue.empty():
                stream_type, text = output_queue.get_nowait()
                if stream_type == "stdout" and on_output:
                    on_output(text)
                elif stream_type == "stderr" and on_error:
                    on_error(text)

            # Get result
            result_value, captured_stdout, captured_stderr = await exec_task
            result.result_value = result_value
            result.output = captured_stdout
            result.error = captured_stderr
            result.status = (
                ExecutionStatus.SUCCESS
                if not captured_stderr
                else ExecutionStatus.ERROR
            )
        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.exception = e
            error_text = traceback.format_exc()
            result.error = error_text
            if on_error:
                on_error(error_text)

        return result

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
