"""Tests for the Python code executor."""

import pytest
from artifice.execution.python import CodeExecutor
from artifice.execution.base import ExecutionStatus


@pytest.fixture
def executor():
    return CodeExecutor()


class TestExpressionEvaluation:
    @pytest.mark.asyncio
    async def test_simple_expression(self, executor):
        result = await executor.execute("2 + 2")
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result_value == 4

    @pytest.mark.asyncio
    async def test_string_expression(self, executor):
        result = await executor.execute("'hello' + ' world'")
        assert result.result_value == "hello world"

    @pytest.mark.asyncio
    async def test_list_expression(self, executor):
        result = await executor.execute("[1, 2, 3]")
        assert result.result_value == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_none_expression(self, executor):
        result = await executor.execute("None")
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result_value is None


class TestStatementExecution:
    @pytest.mark.asyncio
    async def test_assignment(self, executor):
        result = await executor.execute("x = 42")
        assert result.status == ExecutionStatus.SUCCESS
        # Assignments don't produce a return value
        assert result.result_value is None

    @pytest.mark.asyncio
    async def test_print_output(self, executor):
        captured = []
        result = await executor.execute(
            "print('hello')", on_output=lambda t: captured.append(t)
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert "hello" in result.output or "hello" in "".join(captured)

    @pytest.mark.asyncio
    async def test_multiline(self, executor):
        code = "for i in range(3):\n    print(i)"
        result = await executor.execute(code)
        assert result.status == ExecutionStatus.SUCCESS
        assert "0" in result.output
        assert "1" in result.output
        assert "2" in result.output


class TestStatePersistence:
    @pytest.mark.asyncio
    async def test_variable_persists(self, executor):
        """Variables defined in one execution should be available in the next."""
        await executor.execute("my_persist_var_99 = 99")
        result = await executor.execute("my_persist_var_99")
        assert result.result_value == 99

    @pytest.mark.asyncio
    async def test_function_persists(self, executor):
        await executor.execute("def _test_double(x): return x * 2")
        result = await executor.execute("_test_double(5)")
        assert result.result_value == 10

    @pytest.mark.asyncio
    async def test_import_persists(self, executor):
        await executor.execute("import math")
        result = await executor.execute("math.pi")
        assert abs(result.result_value - 3.14159) < 0.001


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_syntax_error(self, executor):
        result = await executor.execute("def f(:")
        assert result.status == ExecutionStatus.ERROR
        assert result.error  # Should have error text

    @pytest.mark.asyncio
    async def test_runtime_error(self, executor):
        result = await executor.execute("1 / 0")
        assert result.status == ExecutionStatus.ERROR
        assert "ZeroDivisionError" in result.error or "division by zero" in result.error

    @pytest.mark.asyncio
    async def test_name_error(self, executor):
        result = await executor.execute("undefined_variable")
        assert result.status == ExecutionStatus.ERROR

    @pytest.mark.asyncio
    async def test_error_callbacks(self, executor):
        errors = []
        result = await executor.execute("1/0", on_error=lambda t: errors.append(t))
        assert result.status == ExecutionStatus.ERROR
        # Error should have been reported via callback or captured
        assert result.error or errors


class TestStreamingOutput:
    @pytest.mark.asyncio
    async def test_output_callback(self, executor):
        chunks = []
        await executor.execute(
            "print('line1')\nprint('line2')", on_output=lambda t: chunks.append(t)
        )
        combined = "".join(chunks)
        assert "line1" in combined
        assert "line2" in combined

    @pytest.mark.asyncio
    async def test_stderr_callback(self, executor):
        errors = []
        code = "import sys; sys.stderr.write('warning\\n')"
        await executor.execute(code, on_error=lambda t: errors.append(t))
        combined = "".join(errors)
        assert "warning" in combined
