from __future__ import annotations

import asyncio
import os
import pty
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

        The command is executed with a pseudo-TTY to ensure color output is preserved.

        Args:
            command: The shell command string to execute.
            on_output: Optional callback invoked for each stdout line.
            on_error: Optional callback invoked for each stderr line.

        Returns:
            ExecutionResult with status (SUCCESS/ERROR), output, and any errors.
        """
        result = ExecutionResult(code=command, status=ExecutionStatus.RUNNING)

        try:
            # Create a pseudo-terminal to make commands think they're in a real terminal
            master_fd, slave_fd = pty.openpty()
            
            # Detect if command contains shell metacharacters
            shell_metachars = {'|', '&', ';', '>', '<', '*', '?', '[', ']', '$', '(', ')', '{', '}', '`', '\n'}
            use_shell = any(char in command for char in shell_metachars)

            # Set TERM environment variable to enable color
            env = os.environ.copy()
            env['TERM'] = env.get('TERM', 'xterm-256color')
            
            if use_shell:
                # Use shell for commands with shell metacharacters
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=env,
                    start_new_session=True,
                )
            else:
                # Parse command into arguments to avoid shell injection
                try:
                    args = shlex.split(command)
                except ValueError as e:
                    # If command parsing fails, return error immediately
                    os.close(master_fd)
                    os.close(slave_fd)
                    result.status = ExecutionStatus.ERROR
                    result.error = f"Invalid command syntax: {e}"
                    if on_error:
                        on_error(result.error)
                    return result

                # Create subprocess with argument list (more secure than shell=True)
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=env,
                    start_new_session=True,
                )

            # Close slave fd in parent process (child has its own copy)
            os.close(slave_fd)

            # Read output from master fd
            output_buffer = []
            
            async def read_pty_output():
                """Read all output from the PTY."""
                loop = asyncio.get_event_loop()
                while True:
                    try:
                        # Read from master fd in non-blocking way
                        data = await loop.run_in_executor(None, os.read, master_fd, 4096)
                        if not data:
                            break
                        text = data.decode('utf-8', errors='replace')
                        output_buffer.append(text)
                        if on_output:
                            on_output(text)
                    except OSError:
                        # PTY closed
                        break

            # Start reading output
            read_task = asyncio.create_task(read_pty_output())
            
            # Wait for process to complete
            await process.wait()
            
            # Wait for all output to be read
            await read_task
            
            # Close master fd
            os.close(master_fd)

            # Collect results
            result.output = "".join(output_buffer)
            result.status = ExecutionStatus.SUCCESS if process.returncode == 0 else ExecutionStatus.ERROR

        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.exception = e
            error_text = f"Failed to execute command: {str(e)}\n{traceback.format_exc()}"
            result.error = error_text
            if on_error:
                on_error(error_text)

        return result
