"""Shared fixtures for Artifice tests."""

import pytest


@pytest.fixture
def tmp_history_file(tmp_path):
    """Provide a temporary history file path."""
    return tmp_path / "test_history.json"


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Provide a temporary config directory."""
    config_dir = tmp_path / "config" / "artifice"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def tmp_sessions_dir(tmp_path):
    """Provide a temporary sessions directory."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)
    return sessions_dir
