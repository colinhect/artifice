"""Tests for BaseExecutor class."""

from __future__ import annotations

from artifice.execution import BaseExecutor


class MockExecutor(BaseExecutor):
    """Mock executor for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.executed = False

    async def execute(self, code: str, **kwargs):
        self.executed = True
        return f"Executed: {code}"


def test_base_executor_initialization():
    """Test BaseExecutor initialization with callbacks."""

    def on_output(x):
        return x

    def on_error(x):
        return x

    timeout = 30.0

    executor = BaseExecutor(on_output=on_output, on_error=on_error, timeout=timeout)

    assert executor.on_output == on_output
    assert executor.on_error == on_error
    assert executor.timeout == timeout


def test_base_executor_default_values():
    """Test BaseExecutor with default values."""
    executor = BaseExecutor()

    assert executor.on_output is None
    assert executor.on_error is None
    assert executor.timeout is None


def test_inherited_executor_uses_base_params():
    """Test that inherited executors properly use BaseExecutor params."""

    def on_output(x):
        return x

    def on_error(x):
        return x

    timeout = 60.0

    executor = MockExecutor(on_output=on_output, on_error=on_error, timeout=timeout)

    assert executor.on_output == on_output
    assert executor.on_error == on_error
    assert executor.timeout == timeout
