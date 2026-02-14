"""Tests for the shell command executor."""

import pytest
from artifice.execution.shell import ShellExecutor
from artifice.execution.common import ExecutionStatus


@pytest.fixture
def executor():
    return ShellExecutor()


class TestBasicExecution:
    @pytest.mark.asyncio
    async def test_echo(self, executor):
        result = await executor.execute("echo hello")
        assert result.status == ExecutionStatus.SUCCESS
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_multiline_output(self, executor):
        result = await executor.execute("echo 'line1'; echo 'line2'")
        assert result.status == ExecutionStatus.SUCCESS
        assert "line1" in result.output
        assert "line2" in result.output

    @pytest.mark.asyncio
    async def test_exit_code_success(self, executor):
        result = await executor.execute("true")
        assert result.status == ExecutionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_exit_code_failure(self, executor):
        result = await executor.execute("false")
        assert result.status == ExecutionStatus.ERROR


class TestOutputStreaming:
    @pytest.mark.asyncio
    async def test_stdout_callback(self, executor):
        lines = []
        await executor.execute(
            "echo one; echo two", on_output=lambda t: lines.append(t)
        )
        assert any("one" in line for line in lines)
        assert any("two" in line for line in lines)

    @pytest.mark.asyncio
    async def test_stderr_callback(self, executor):
        errors = []
        await executor.execute("echo err >&2", on_error=lambda t: errors.append(t))
        assert any("err" in e for e in errors)


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_nonexistent_command(self, executor):
        result = await executor.execute("nonexistent_command_xyz_12345")
        assert result.status == ExecutionStatus.ERROR

    @pytest.mark.asyncio
    async def test_stderr_captured(self, executor):
        result = await executor.execute("echo error_msg >&2; exit 1")
        assert result.status == ExecutionStatus.ERROR
        assert "error_msg" in result.error


class TestPipeAndRedirect:
    @pytest.mark.asyncio
    async def test_pipe(self, executor):
        result = await executor.execute("echo 'hello world' | tr 'h' 'H'")
        assert result.status == ExecutionStatus.SUCCESS
        assert "Hello" in result.output

    @pytest.mark.asyncio
    async def test_command_substitution(self, executor):
        result = await executor.execute("echo $(echo nested)")
        assert "nested" in result.output
