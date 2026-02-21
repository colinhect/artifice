"""Tests for the edit tool executor."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from artifice.agent.tools.executors import execute_edit


@pytest.mark.asyncio
async def test_edit_replaces_unique_string():
    """Edit should replace a unique string in a file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def hello():\n    print('world')\n")
        f.flush()
        path = f.name

    try:
        result = await execute_edit(
            {
                "path": path,
                "old_string": "print('world')",
                "new_string": "print('hello')",
            }
        )
        data = json.loads(result)

        assert data["success"] is True
        assert data["old_lines"] == ["print('world')"]
        assert data["new_lines"] == ["print('hello')"]

        content = Path(path).read_text()
        assert "print('hello')" in content
        assert "print('world')" not in content
    finally:
        Path(path).unlink()


@pytest.mark.asyncio
async def test_edit_fails_on_multiple_occurrences():
    """Edit should fail if old_string appears multiple times."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1\nx = 1\n")
        f.flush()
        path = f.name

    try:
        result = await execute_edit(
            {
                "path": path,
                "old_string": "x = 1",
                "new_string": "x = 2",
            }
        )
        data = json.loads(result)

        assert data["success"] is False
        assert "2 times" in data["error"]
    finally:
        Path(path).unlink()


@pytest.mark.asyncio
async def test_edit_fails_on_not_found():
    """Edit should fail if old_string is not found."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def hello():\n    pass\n")
        f.flush()
        path = f.name

    try:
        result = await execute_edit(
            {
                "path": path,
                "old_string": "nonexistent",
                "new_string": "replacement",
            }
        )
        data = json.loads(result)

        assert data["success"] is False
        assert "not found" in data["error"]
    finally:
        Path(path).unlink()


@pytest.mark.asyncio
async def test_edit_fails_on_missing_file():
    """Edit should fail if file does not exist."""
    result = await execute_edit(
        {
            "path": "/nonexistent/path/file.py",
            "old_string": "old",
            "new_string": "new",
        }
    )
    data = json.loads(result)

    assert data["success"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_edit_includes_context():
    """Edit should include context lines in result."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("line1\nline2\nline3\ntarget\nline5\nline6\nline7\n")
        f.flush()
        path = f.name

    try:
        result = await execute_edit(
            {
                "path": path,
                "old_string": "target",
                "new_string": "replaced",
            }
        )
        data = json.loads(result)

        assert data["success"] is True
        assert "line1" in data["context_before"] or "line2" in data["context_before"]
        assert "line5" in data["context_after"] or "line6" in data["context_after"]
        assert data["start_line"] == 4
    finally:
        Path(path).unlink()


@pytest.mark.asyncio
async def test_edit_multiline_string():
    """Edit should handle multiline old_string and new_string."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def foo():\n    pass\n\ndef bar():\n    pass\n")
        f.flush()
        path = f.name

    try:
        result = await execute_edit(
            {
                "path": path,
                "old_string": "def foo():\n    pass",
                "new_string": "def foo():\n    return 42",
            }
        )
        data = json.loads(result)

        assert data["success"] is True
        assert data["old_lines"] == ["def foo():", "    pass"]
        assert data["new_lines"] == ["def foo():", "    return 42"]
    finally:
        Path(path).unlink()
