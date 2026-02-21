"""Tests for the tmux shell executor."""

import asyncio
import shutil
import uuid

import pytest
import pytest_asyncio

from artifice.execution.shell import TmuxShellExecutor
from artifice.execution.base import ExecutionStatus

TMUX_AVAILABLE = shutil.which("tmux") is not None
pytestmark = pytest.mark.skipif(not TMUX_AVAILABLE, reason="tmux not installed")

TEST_PROMPT_PS1 = "TESTPROMPT$ "
# Make pattern more specific: match lines that start with TESTPROMPT$ followed by space
# This avoids matching command echo lines like "TESTPROMPT$ echo hello"
TEST_PROMPT_PATTERN = r"^TESTPROMPT\$ (?!\S)"


@pytest_asyncio.fixture
async def tmux_session():
    """Create a temporary tmux session with a known prompt."""
    session_name = f"artifice_test_{uuid.uuid4().hex[:8]}"
    proc = await asyncio.create_subprocess_exec(
        "tmux",
        "new-session",
        "-d",
        "-s",
        session_name,
        "-x",
        "200",
        "-y",
        "50",
    )
    await proc.wait()
    # Set a known prompt for reliable detection
    proc = await asyncio.create_subprocess_exec(
        "tmux",
        "send-keys",
        "-t",
        session_name,
        f"export PS1='{TEST_PROMPT_PS1}'",
        "Enter",
    )
    await proc.wait()
    # Send a simple command to ensure prompt is ready and visible
    proc = await asyncio.create_subprocess_exec(
        "tmux",
        "send-keys",
        "-t",
        session_name,
        ":",
        "Enter",
    )
    await proc.wait()
    await asyncio.sleep(0.5)
    yield session_name
    proc = await asyncio.create_subprocess_exec(
        "tmux",
        "kill-session",
        "-t",
        session_name,
    )
    await proc.wait()


@pytest.fixture
def executor(tmux_session):
    return TmuxShellExecutor(
        target=tmux_session, prompt_pattern=TEST_PROMPT_PATTERN, check_exit_code=True
    )


@pytest.fixture
def executor_no_exit_check(tmux_session):
    """Executor that doesn't check exit codes (assumes success on prompt)."""
    return TmuxShellExecutor(
        target=tmux_session, prompt_pattern=TEST_PROMPT_PATTERN, check_exit_code=False
    )


class TestTmuxBasicExecution:
    @pytest.mark.asyncio
    async def test_echo(self, executor):
        result = await executor.execute("echo hello", timeout=5.0)
        assert result.status == ExecutionStatus.SUCCESS
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_multiline_output(self, executor):
        result = await executor.execute("echo line1; echo line2", timeout=5.0)
        assert result.status == ExecutionStatus.SUCCESS
        assert "line1" in result.output
        assert "line2" in result.output

    @pytest.mark.asyncio
    async def test_exit_code_success(self, executor):
        result = await executor.execute("true", timeout=5.0)
        assert result.status == ExecutionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_exit_code_failure(self, executor):
        result = await executor.execute("false", timeout=5.0)
        assert result.status == ExecutionStatus.ERROR


class TestTmuxOutputStreaming:
    @pytest.mark.asyncio
    async def test_stdout_callback(self, executor):
        chunks = []
        await executor.execute(
            "echo one; echo two", on_output=lambda t: chunks.append(t), timeout=5.0
        )
        combined = "".join(chunks)
        assert "one" in combined
        assert "two" in combined


class TestTmuxErrorHandling:
    @pytest.mark.asyncio
    async def test_invalid_session(self):
        executor = TmuxShellExecutor(
            target="nonexistent_session_xyz_12345",
            prompt_pattern=TEST_PROMPT_PATTERN,
        )
        result = await executor.execute("echo hello", timeout=5.0)
        assert result.status == ExecutionStatus.ERROR
        assert "not found" in result.error.lower() or "session" in result.error.lower()

    @pytest.mark.asyncio
    async def test_failed_command(self, executor):
        result = await executor.execute("bash -c 'exit 42'", timeout=5.0)
        assert result.status == ExecutionStatus.ERROR


class TestTmuxTargetWithWindow:
    @pytest.mark.asyncio
    async def test_session_colon_window(self, tmux_session):
        """Test targeting session:0 (first window)."""
        executor = TmuxShellExecutor(
            target=f"{tmux_session}:0",
            prompt_pattern=TEST_PROMPT_PATTERN,
            check_exit_code=True,
        )
        result = await executor.execute("echo window_test", timeout=5.0)
        assert result.status == ExecutionStatus.SUCCESS
        assert "window_test" in result.output


class TestTmuxExitCodeCheck:
    """Tests for the check_exit_code option."""

    @pytest.mark.asyncio
    async def test_with_exit_code_check_success(self, executor):
        """With check_exit_code=True, successful commands return SUCCESS."""
        result = await executor.execute("true", timeout=5.0)
        assert result.status == ExecutionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_with_exit_code_check_failure(self, executor):
        """With check_exit_code=True, failed commands return ERROR."""
        result = await executor.execute("false", timeout=5.0)
        assert result.status == ExecutionStatus.ERROR

    @pytest.mark.asyncio
    async def test_without_exit_code_check_success(self, executor_no_exit_check):
        """With check_exit_code=False, successful commands return SUCCESS."""
        result = await executor_no_exit_check.execute("true", timeout=5.0)
        assert result.status == ExecutionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_without_exit_code_check_failure(self, executor_no_exit_check):
        """With check_exit_code=False, failed commands still return SUCCESS (no check)."""
        result = await executor_no_exit_check.execute("false", timeout=5.0)
        # When check_exit_code is False, we assume success when prompt appears
        assert result.status == ExecutionStatus.SUCCESS
        # Output should still be captured
        assert result.output is not None
