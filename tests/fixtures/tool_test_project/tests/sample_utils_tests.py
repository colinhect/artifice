"""Tests for utility functions."""

import pytest

from src.utils import format_output, validate_input, merge_configs


def test_format_output():
    data = {"name": "test", "value": 42}
    output = format_output(data)
    assert "name: test" in output
    assert "value: 42" in output


def test_format_output_custom_indent():
    data = {"key": "value"}
    output = format_output(data, indent=4)
    assert output.startswith("    ")


def test_validate_input():
    data = {"a": 1, "b": 2, "c": 3}
    assert validate_input(data, ["a", "b"]) is True
    assert validate_input(data, ["d"]) is False


def test_merge_configs():
    config1 = {"a": 1, "b": 2}
    config2 = {"b": 3, "c": 4}
    result = merge_configs(config1, config2)
    assert result == {"a": 1, "b": 3, "c": 4}
