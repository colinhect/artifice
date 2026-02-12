"""Tests for configuration management."""

import tempfile
from pathlib import Path
import pytest

from artifice.config import (
    ArtificeConfig,
    load_config,
    get_config_path,
    get_init_script_path,
    get_sessions_dir,
    ensure_sessions_dir,
)


def test_artifice_config_defaults():
    """Test that ArtificeConfig has sensible defaults."""
    config = ArtificeConfig()
    
    assert config.agent_type is None
    assert config.model is None
    assert config.ollama_host is None
    assert config.show_banner is False
    assert config.python_markdown is False
    assert config.agent_markdown is True
    assert config.shell_markdown is False
    assert config.auto_send_to_agent is True
    assert config.shell_init_script is None
    assert config.save_sessions is True
    assert config.sessions_dir is None


def test_artifice_config_custom_values():
    """Test setting custom configuration values."""
    config = ArtificeConfig()
    
    config.set("custom_key", "custom_value")
    assert config.get("custom_key") == "custom_value"
    assert config.get("nonexistent_key") is None
    assert config.get("nonexistent_key", "default") == "default"


def test_get_config_path():
    """Test getting the config directory path."""
    path = get_config_path()
    assert isinstance(path, Path)
    assert path.name == "artifice"


def test_get_init_script_path():
    """Test getting the init script path."""
    path = get_init_script_path()
    assert isinstance(path, Path)
    assert path.name == "init.py"


def test_load_config_no_file():
    """Test loading config when no init.py exists."""
    config, error = load_config()
    
    assert isinstance(config, ArtificeConfig)
    assert error is None  # No error when file doesn't exist


def test_load_config_with_file(tmp_path, monkeypatch):
    """Test loading config from a valid init.py file."""
    # Create a temporary init.py
    init_file = tmp_path / "init.py"
    init_file.write_text("""
config.agent_type = "ollama"
config.model = "llama3.2:1b"
config.show_banner = True
config.python_markdown = True
config.ollama_host = "http://localhost:8080"
config.set("custom", "value")
""")
    
    # Mock get_init_script_path to return our temp file
    monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
    
    config, error = load_config()
    
    assert error is None
    assert config.agent_type == "ollama"
    assert config.model == "llama3.2:1b"
    assert config.show_banner is True
    assert config.python_markdown is True
    assert config.ollama_host == "http://localhost:8080"
    assert config.get("custom") == "value"


def test_load_config_with_syntax_error(tmp_path, monkeypatch):
    """Test loading config with a syntax error."""
    init_file = tmp_path / "init.py"
    init_file.write_text("this is not valid python @@#$")
    
    monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
    
    config, error = load_config()
    
    assert isinstance(config, ArtificeConfig)
    assert error is not None
    assert "Error loading config" in error


def test_load_config_sandboxing(tmp_path, monkeypatch):
    """Test that dangerous operations are blocked in init.py."""
    # Try to use __import__ (should be disabled)
    init_file = tmp_path / "init.py"
    init_file.write_text("__import__('os').system('echo pwned')")
    
    monkeypatch.setattr("artifice.config.get_init_script_path", lambda: init_file)
    
    config, error = load_config()
    
    # Should get an error because __import__ is None
    assert error is not None


def test_get_sessions_dir_default():
    """Test getting default sessions directory."""
    config = ArtificeConfig()
    sessions_dir = get_sessions_dir(config)
    
    assert isinstance(sessions_dir, Path)
    assert sessions_dir.name == "sessions"
    assert ".artifice" in str(sessions_dir)


def test_get_sessions_dir_custom():
    """Test getting custom sessions directory."""
    config = ArtificeConfig()
    config.sessions_dir = "/tmp/my_sessions"
    
    sessions_dir = get_sessions_dir(config)
    
    assert sessions_dir == Path("/tmp/my_sessions")


def test_ensure_sessions_dir(tmp_path):
    """Test creating sessions directory."""
    config = ArtificeConfig()
    config.sessions_dir = str(tmp_path / "test_sessions")
    
    # Directory shouldn't exist yet
    sessions_dir = get_sessions_dir(config)
    assert not sessions_dir.exists()
    
    # Create it
    ensure_sessions_dir(config)
    
    # Now it should exist
    assert sessions_dir.exists()
    assert sessions_dir.is_dir()
