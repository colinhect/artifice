from __future__ import annotations

import asyncio
import shlex
import traceback
from typing import Callable, Optional

from .common import ExecutionStatus, ExecutionResult

class ShellExecutor:
    """Executes shell commands asynchronously with streaming output.

    Commands are parsed using shlex.split() and executed via subprocess
    without shell interpretation, reducing shell injection risks.

    Stdout and stderr are streamed concurrently with real-time callbacks.

    Security Note: Commands run with full user permissions without sandboxing.
    Only execute commands from trusted sources.
    """

    async def execute(
        self,
        command: str,
        on_output: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> ExecutionResult:
        """Execute a shell command asynchronously with streaming output.

        The command string is parsed into arguments using shlex.split() to
        avoid shell injection vulnerabilities. Commands with shell-specific
        features (pipes, redirects, etc.) may not work as expected.

        Args:
            command: The shell command string to execute (will be parsed into args).
            on_output: Optional callback invoked for each stdout line.
            on_error: Optional callback invoked for each stderr line.

        Returns:
            ExecutionResult with status (SUCCESS/ERROR), output, and any errors.
        """
        result = ExecutionResult(code=command, status=ExecutionStatus.RUNNING)

        try:
            # Detect if command contains shell metacharacters
            shell_metachars = {'|', '&', ';', '>', '<', '*', '?', '[', ']', '$', '(', ')', '{', '}', '`', '\n'}
            use_shell = any(char in command for char in shell_metachars)

            if use_shell:
                # Use shell for commands with shell metacharacters
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # Parse command into arguments to avoid shell injection
                try:
                    args = shlex.split(command)
                except ValueError as e:
                    # If command parsing fails, return error immediately
                    result.status = ExecutionStatus.ERROR
                    result.error = f"Invalid command syntax: {e}"
                    if on_error:
                        on_error(result.error)
                    return result

                # Create subprocess with argument list (more secure than shell=True)
                process = await asyncio.create_subprocess_exec(
                    *args,
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
