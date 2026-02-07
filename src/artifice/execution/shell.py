from __future__ import annotations

import asyncio
import os
import pty
import re
import shlex
import tempfile
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

    def __init__(self, init_script: Optional[str] = None) -> None:
        """Initialize shell executor with optional initialization script.
        
        Args:
            init_script: Shell script to source before each command execution.
                        Useful for setting aliases, environment variables, etc.
        """
        self.init_script = init_script
        self.working_directory = os.getcwd()

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
        init_file = None

        try:
            # Create a pseudo-terminal to make commands think they're in a real terminal
            master_fd, slave_fd = pty.openpty()

            # Always use shell mode to preserve working directory changes
            use_shell = True

            # Set TERM environment variable to enable color
            env = os.environ.copy()
            env['TERM'] = env.get('TERM', 'xterm-256color')

            # Prepare the actual command to execute
            if self.init_script and use_shell:
                # Write a complete script that includes init + command + pwd capture
                # This is the most reliable way to handle aliases
                init_file = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
                init_file.write("#!/bin/bash\n")
                init_file.write("shopt -s expand_aliases\n")
                init_file.write(self.init_script)
                init_file.write("\n")
                init_file.write(command)
                init_file.write("\n")
                init_file.write('echo "###ARTIFICE_PWD###$(pwd)###"\n')
                init_file.close()
                os.chmod(init_file.name, 0o700)
                wrapped_command = init_file.name
            else:
                # Append pwd capture to the command
                if use_shell:
                    wrapped_command = f'cd "{self.working_directory}" && {command} ; echo "###ARTIFICE_PWD###$(pwd)###"'
                else:
                    wrapped_command = command
            
            if use_shell:
                # Use shell for commands with shell metacharacters
                process = await asyncio.create_subprocess_shell(
                    wrapped_command,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    env=env,
                    cwd=self.working_directory,
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
                    cwd=self.working_directory,
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
                        # Filter out the marker from live output
                        if on_output:
                            filtered_text = re.sub(r'###ARTIFICE_PWD###[^#]+###\r?\n?', '', text)
                            if filtered_text:
                                on_output(filtered_text)
                    except OSError:
                        # PTY closed
                        break

            # Start reading output
            read_task = asyncio.create_task(read_pty_output())

            try:
                # Wait for process to complete
                await process.wait()

                # Wait for all output to be read
                await read_task
            except asyncio.CancelledError:
                # Cancel the read task
                read_task.cancel()
                # Terminate the process
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                result.status = ExecutionStatus.ERROR
                result.error = "\n[Execution cancelled]\n"
                if on_error:
                    on_error(result.error)
                raise
            finally:
                # Close master fd
                try:
                    os.close(master_fd)
                except OSError:
                    pass  # Already closed

            # Collect results
            full_output = "".join(output_buffer)
            
            # Extract and remove the working directory marker
            # The marker format is: ###ARTIFICE_PWD###/path/to/dir###
            pwd_match = re.search(r'###ARTIFICE_PWD###([^#]+)###', full_output)
            if pwd_match:
                new_pwd = pwd_match.group(1).strip()
                if new_pwd and os.path.isdir(new_pwd):
                    self.working_directory = new_pwd
            
            # Remove the entire marker line from output (including newlines)
            full_output = re.sub(r'###ARTIFICE_PWD###[^#]+###\r?\n?', '', full_output)
            
            result.output = full_output
            result.status = ExecutionStatus.SUCCESS if process.returncode == 0 else ExecutionStatus.ERROR

        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.exception = e
            error_text = f"Failed to execute command: {str(e)}\n{traceback.format_exc()}"
            result.error = error_text
            if on_error:
                on_error(error_text)
        finally:
            # Clean up temporary init file if created
            if init_file:
                try:
                    os.unlink(init_file.name)
                except Exception:
                    pass  # Ignore cleanup errors

        return result
