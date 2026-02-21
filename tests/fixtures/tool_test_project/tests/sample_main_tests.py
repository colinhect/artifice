"""Tests for the main module."""

import pytest

from src.main import greet, calculate_sum, process_data, DataProcessor


def test_greet():
    assert greet("World") == "Hello, World!"
    assert greet("Alice") == "Hello, Alice!"


def test_calculate_sum():
    assert calculate_sum([1, 2, 3]) == 6
    assert calculate_sum([]) == 0
    assert calculate_sum([-1, 1]) == 0


def test_process_data():
    data = {"a": 1, "b": 2}
    result = process_data(data)
    assert result["original"] == data
    assert result["count"] == 2
    assert "a" in result["keys"]


class TestDataProcessor:
    def test_init(self):
        processor = DataProcessor("test")
        assert processor.name == "test"

    def test_process(self):
        processor = DataProcessor("test")
        item = {"id": "item1", "value": 42, "extra": None}
        result = processor.process(item)
        assert result["id"] == "item1"
        assert result["value"] == 42
        assert "extra" not in result  # None values filtered
