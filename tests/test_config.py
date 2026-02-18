"""Tests for configuration loading."""

import yaml

from artifice.config import ArtificeConfig, load_config


def test_default_config():
    """Test that default config has expected values."""
    config = ArtificeConfig()
    assert config.assistant is None
    assert config.assistants is None
    assert config.banner is False
    assert config.auto_send_to_assistant is True
    assert config.assistant_markdown is True


def test_load_empty_yaml(tmp_path, monkeypatch):
    """Test loading an empty YAML file returns default config."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"
    init_file.write_text("")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.assistant is None
    assert config.banner is False


def test_load_basic_yaml(tmp_path, monkeypatch):
    """Test loading a basic YAML configuration."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"

    yaml_content = {
        "assistant": "llama",
        "banner": True,
        "system_prompt": "Test prompt",
        "auto_send_to_assistant": False,
    }
    init_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.assistant == "llama"
    assert config.banner is True
    assert config.system_prompt == "Test prompt"
    assert config.auto_send_to_assistant is False


def test_load_models_dict(tmp_path, monkeypatch):
    """Test loading assistants dictionary configuration."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"

    yaml_content = {
        "assistant": "llama",
        "assistants": {
            "llama": {"provider": "ollama", "model": "llama3.2:1b"},
            "what": {"provider": "ollama", "model": "what-model"},
        },
    }
    init_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.assistants is not None
    assert "llama" in config.assistants
    assert config.assistants["llama"]["provider"] == "ollama"
    assert config.assistants["what"]["model"] == "what-model"


def test_load_all_display_settings(tmp_path, monkeypatch):
    """Test loading all display settings."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"

    yaml_content = {
        "banner": True,
        "python_markdown": True,
        "assistant_markdown": False,
        "shell_markdown": True,
    }
    init_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.banner is True
    assert config.python_markdown is True
    assert config.assistant_markdown is False
    assert config.shell_markdown is True


def test_load_shell_init_script(tmp_path, monkeypatch):
    """Test loading shell init script."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"

    yaml_content = {
        "shell_init_script": "alias ll='ls -la'\nexport MY_VAR=value",
    }
    init_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.shell_init_script == "alias ll='ls -la'\nexport MY_VAR=value"


def test_load_custom_settings(tmp_path, monkeypatch):
    """Test that custom settings are stored in _custom dict."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"

    yaml_content = {
        "assistant": "llama",
        "custom_key": "custom_value",
        "another_custom": 42,
    }
    init_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.get("custom_key") == "custom_value"
    assert config.get("another_custom") == 42


def test_load_invalid_yaml(tmp_path, monkeypatch):
    """Test that invalid YAML returns an error."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"
    init_file.write_text("invalid: yaml: content: [")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is not None
    assert "Error parsing YAML" in error
    # Should still return a config object with defaults
    assert config.banner is False


def test_load_nonexistent_file(tmp_path, monkeypatch):
    """Test that missing config file returns default config."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    # Don't create init.yaml

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.assistant is None
    assert config.banner is False


def test_multiline_yaml_strings(tmp_path, monkeypatch):
    """Test that multiline YAML strings work correctly."""
    config_dir = tmp_path / "artifice"
    config_dir.mkdir()
    init_file = config_dir / "init.yaml"

    yaml_content = """
system_prompt: |
  Line 1
  Line 2
  Line 3
"""
    init_file.write_text(yaml_content)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config, error = load_config()

    assert error is None
    assert config.system_prompt == "Line 1\nLine 2\nLine 3\n"
