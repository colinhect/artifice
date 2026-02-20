from __future__ import annotations

import asyncio
import os
import re
import tempfile
import traceback

from typing import Callable

from artifice.execution.base import ExecutionResult, ExecutionStatus


class ShellExecutor:
    """Executes shell commands asynchronously with streaming output.

    Stdout and stderr are streamed concurrently with real-time callbacks.

    Security Note: Commands run with full user permissions without sandboxing.
    Only execute commands from trusted sources.
    """

    def __init__(self) -> None:
        self.working_directory = os.getcwd()
        self.init_script: str | None = None

    async def execute(
        self,
        command: str,
        on_output: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> ExecutionResult:
        """Execute a shell command asynchronously with streaming output.

        Args:
            command: The shell command string to execute.
            on_output: Optional callback invoked for each stdout line.
            on_error: Optional callback invoked for each stderr line.

        Returns:
            ExecutionResult with status (SUCCESS/ERROR), output, and any errors.
        """
        return await self._execute_simple(command, on_output, on_error)

    async def _execute_simple(
        self,
        command: str,
        on_output: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> ExecutionResult:
        result = ExecutionResult(code=command, status=ExecutionStatus.RUNNING)
        process = None

        try:
            # Create subprocess with pipes for stdout and stderr
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Collect output
            stdout_lines = []
            stderr_lines = []

            async def read_stream(stream, lines_list, callback):
                """Read from a stream and collect lines."""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    lines_list.append(text)
                    if text and callback:
                        callback(text)

            # Read stdout and stderr concurrently
            await asyncio.gather(
                read_stream(process.stdout, stdout_lines, on_output),
                read_stream(process.stderr, stderr_lines, on_error),
            )

            # Wait for process to complete
            returncode = await process.wait()

            # Collect results
            full_output = "".join(stdout_lines)
            full_error = "".join(stderr_lines)

            result.output = full_output
            result.error = full_error
            result.status = (
                ExecutionStatus.SUCCESS if returncode == 0 else ExecutionStatus.ERROR
            )

        except asyncio.CancelledError:
            result.status = ExecutionStatus.ERROR
            result.error = "\n[Execution cancelled]\n"
            if on_error:
                on_error(result.error)
            if process:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            raise
        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.exception = e
            error_text = (
                f"Failed to execute command: {str(e)}\n{traceback.format_exc()}"
            )
            result.error = error_text
            if on_error:
                on_error(error_text)

        return result


class TmuxShellExecutor:
    """Executes commands by sending them to an existing tmux session.

    Output is captured via `tmux pipe-pane` streaming to a temp file.
    Command completion is detected by the shell prompt reappearing. If
    check_exit_code is True, the exit code is retrieved by a follow-up
    `echo $?`. Otherwise, seeing the prompt is assumed to be success.

    Security Note: Commands run with full user permissions in the target
    tmux session without sandboxing. Only execute commands from trusted sources.
    """

    def __init__(
        self, target: str, prompt_pattern: str, check_exit_code: bool = False
    ) -> None:
        """Initialize with a tmux target string and prompt pattern.

        Args:
            target: A tmux target like 'session:window' or 'session:window.pane'.
            prompt_pattern: Regex matching the shell prompt (used with re.MULTILINE).
                Example: r"^colin@lucidity:\\S+\\$ " for a prompt like "colin@lucidity:~$ ".
            check_exit_code: Whether to check exit code with `echo $?` (default False).
        """
        self.target = target
        self.prompt_re = re.compile(prompt_pattern, re.MULTILINE)
        self.check_exit_code = check_exit_code

    @staticmethod
    def _strip_escapes(text: str) -> str:
        """Strip ANSI/OSC escape sequences and carriage returns from terminal output."""
        # OSC sequences: ESC ] ... (ST or BEL)
        text = re.sub(r"\x1b\].*?(?:\x1b\\|\x07)", "", text)
        # CSI sequences: ESC [ ... letter
        text = re.sub(r"\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]", "", text)
        # Other escape sequences (but not ESC followed by arbitrary chars)
        # Only strip: ESC followed by specific single-char sequences
        text = re.sub(r"\x1b[()#].", "", text)  # Character set selection
        text = re.sub(r"\x1b[=>]", "", text)  # Keypad modes
        # Strip carriage returns
        text = text.replace("\r", "")
        return text

    async def _run_tmux(self, *args: str) -> tuple[int, str, str]:
        """Run a tmux command and return (returncode, stdout, stderr)."""
        proc = await asyncio.create_subprocess_exec(
            "tmux",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    def _read_content(self, tmpfile: str) -> str:
        """Read and clean the pipe-pane output file."""
        with open(tmpfile, "r", errors="replace") as f:
            return self._strip_escapes(f.read())

    async def execute(
        self,
        command: str,
        on_output: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        timeout: float | None = None,
    ) -> ExecutionResult:
        """Execute a command in the tmux target with streaming output.

        Sends the command, detects completion when the prompt reappears,
        then queries the exit code with `echo $?`.

        Args:
            command: The shell command string to execute.
            on_output: Optional callback invoked for each chunk of output.
            on_error: Optional callback invoked for error messages.
            timeout: Optional timeout in seconds. None means no timeout.

        Returns:
            ExecutionResult with status (SUCCESS/ERROR), output, and any errors.
        """
        result = ExecutionResult(code=command, status=ExecutionStatus.RUNNING)
        tmpfile = None

        try:
            # Validate target exists
            rc, _, err = await self._run_tmux(
                "has-session", "-t", self.target.split(":")[0]
            )
            if rc != 0:
                result.status = ExecutionStatus.ERROR
                result.error = f"tmux session not found: {err.strip()}"
                if on_error:
                    on_error(result.error)
                return result

            # Create temp file for pipe-pane output
            tmpfd, tmpfile = tempfile.mkstemp(prefix="artifice_tmux_")
            os.close(tmpfd)

            # Start output capture and send command
            await self._run_tmux("pipe-pane", "-t", self.target, f"cat >> {tmpfile}")
            await self._run_tmux("send-keys", "-t", self.target, command, "Enter")

            # Phase 1: Capture command output until prompt reappears
            streamed_len = 0
            cmd_echo_end = -1
            poll_interval = 0.05
            elapsed = 0.0

            while True:
                if timeout is not None and elapsed >= timeout:
                    result.status = ExecutionStatus.ERROR
                    result.error = f"Command timed out after {timeout}s"
                    if on_error:
                        on_error(result.error)
                    return result
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                content = self._read_content(tmpfile)

                # Find command echo line end
                if cmd_echo_end < 0:
                    echo_pos = content.find(command)
                    if echo_pos < 0:
                        continue
                    nl = content.find("\n", echo_pos)
                    if nl < 0:
                        continue
                    cmd_echo_end = nl + 1

                body = content[cmd_echo_end:]

                # Look for prompt after command output
                prompt_match = self.prompt_re.search(body)
                if prompt_match:
                    command_output = body[: prompt_match.start()].rstrip("\n")
                    if len(command_output) > streamed_len and on_output:
                        on_output(command_output[streamed_len:])
                    result.output = command_output
                    break
                else:
                    if len(body) > streamed_len:
                        chunk = body[streamed_len:]
                        streamed_len = len(body)
                        if chunk and on_output:
                            on_output(chunk)

            # Phase 2: Query exit code (if enabled)
            if self.check_exit_code:
                content_before_len = len(self._read_content(tmpfile))
                await self._run_tmux("send-keys", "-t", self.target, "echo $?", "Enter")

                while True:
                    if timeout is not None and elapsed >= timeout:
                        result.status = ExecutionStatus.ERROR
                        result.error = f"Command timed out after {timeout}s"
                        if on_error:
                            on_error(result.error)
                        return result
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                    content = self._read_content(tmpfile)
                    new_content = content[content_before_len:]

                    prompt_match = self.prompt_re.search(new_content)
                    if not prompt_match:
                        continue

                    # Parse exit code between "echo $?" echo and prompt
                    before_prompt = new_content[: prompt_match.start()]
                    echo_pos = before_prompt.find("echo $?")
                    if echo_pos < 0:
                        continue
                    nl = before_prompt.find("\n", echo_pos)
                    if nl < 0:
                        continue
                    exit_str = before_prompt[nl + 1 :].strip()
                    try:
                        exit_code = int(exit_str)
                    except ValueError:
                        exit_code = -1

                    result.status = (
                        ExecutionStatus.SUCCESS
                        if exit_code == 0
                        else ExecutionStatus.ERROR
                    )
                    break
            else:
                # Assume success when prompt appears
                result.status = ExecutionStatus.SUCCESS

        except asyncio.CancelledError:
            result.status = ExecutionStatus.ERROR
            result.error = "\n[Execution cancelled]\n"
            if on_error:
                on_error(result.error)
            raise
        except Exception as e:
            result.status = ExecutionStatus.ERROR
            result.exception = e
            error_text = (
                f"Failed to execute command: {str(e)}\n{traceback.format_exc()}"
            )
            result.error = error_text
            if on_error:
                on_error(error_text)
        finally:
            try:
                await self._run_tmux("pipe-pane", "-t", self.target)
            except Exception:
                pass
            if tmpfile:
                try:
                    os.unlink(tmpfile)
                except OSError:
                    pass

        return result
