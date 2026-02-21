"""Tests for error handling utilities."""

from __future__ import annotations

import asyncio

import pytest

from artifice.execution.base import ExecutionResult, ExecutionStatus
from artifice.execution.errors import execution_error_handler


def test_execution_error_handler_success():
    """Test error handler with successful execution."""
    result = ExecutionResult(code="test code")
    error_calls = []

    with execution_error_handler(result, error_calls.append):
        result.status = ExecutionStatus.SUCCESS
        result.output = "Success"

    assert result.status == ExecutionStatus.SUCCESS
    assert result.output == "Success"
    assert result.error == ""
    assert len(error_calls) == 0


def test_execution_error_handler_general_exception():
    """Test error handler with general exception."""
    result = ExecutionResult(code="test code")
    error_calls = []

    try:
        with execution_error_handler(result, error_calls.append):
            raise ValueError("Test error")
    except ValueError:
        pass  # Expected

    assert result.status == ExecutionStatus.ERROR
    assert result.exception is not None
    assert isinstance(result.exception, ValueError)
    assert "Test error" in result.error
    assert len(error_calls) == 1
    assert "Test error" in error_calls[0]


def test_execution_error_handler_no_callback():
    """Test error handler without error callback."""
    result = ExecutionResult(code="test code")

    try:
        with execution_error_handler(result):
            raise RuntimeError("Test error")
    except RuntimeError:
        pass  # Expected

    assert result.status == ExecutionStatus.ERROR
    assert result.exception is not None
    assert isinstance(result.exception, RuntimeError)


@pytest.mark.asyncio
async def test_execution_error_handler_cancellation():
    """Test error handler with asyncio cancellation."""
    result = ExecutionResult(code="test code")
    error_calls = []

    try:
        with execution_error_handler(result, error_calls.append):
            raise asyncio.CancelledError()
    except asyncio.CancelledError:
        pass  # Expected

    assert result.status == ExecutionStatus.ERROR
    assert result.error == "\n[Execution cancelled]\n"
    assert len(error_calls) == 1
