from __future__ import annotations

import asyncio
import traceback
from typing import Callable, Optional

from .common import ExecutionStatus, ExecutionResult

class ShellExecutor:
    """Executes shell commands asynchronously."""

    async def execute(
        self,
        command: str,
        on_output: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """Execute a shell command asynchronously with streaming output.

        Args:
            command: The shell command to execute.
            on_output: Optional callback for stdout output.
            on_error: Optional callback for stderr output.

        Returns:
            ExecutionResult with status, output, and any errors.
        """
        result = ExecutionResult(code=command, status=ExecutionStatus.RUNNING)

        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Stream output from both stdout and stderr
            async def stream_output(stream, callback, buffer_list):
                """Stream output from a subprocess stream."""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode('utf-8')
                    buffer_list.append(text)
                    if callback:
                        callback(text)

            stdout_buffer = []
            stderr_buffer = []

            # Run both streams concurrently
            await asyncio.gather(
                stream_output(process.stdout, on_output, stdout_buffer),
                stream_output(process.stderr, on_error, stderr_buffer),
            )

            # Wait for process to complete
            await process.wait()

            # Collect results
            result.output = "".join(stdout_buffer)
            result.error = "".join(stderr_buffer)
            result.status = ExecutionStatus.SUCCESS if process.returncode == 0 else ExecutionStatus.ERROR

        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.exception = e
            error_text = f"Failed to execute command: {str(e)}\n{traceback.format_exc()}"
            result.error = error_text
            if on_error:
                on_error(error_text)

        return result
