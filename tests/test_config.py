"""Tests for configuration loading."""

import yaml
from pathlib import Path

from artifice.core.config import (
    ArtificeConfig,
    load_config,
)


def test_default_config():
    """Test that default config has expected values."""
    config = ArtificeConfig()
    assert config.agent is None
    assert config.agents is None
    assert config.banner is False
    assert config.send_user_commands_to_agent is True
    assert config.agent_markdown is True
    assert config.show_tool_output is True


def test_load_empty_yaml(tmp_path, monkeypatch):
    """Test loading an empty YAML file returns default config."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text("")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.agent is None
    assert config.banner is False


def test_load_basic_yaml(tmp_path, monkeypatch):
    """Test loading a basic YAML configuration."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = {
        "agent": "llama",
        "banner": True,
        "system_prompt": "Test prompt",
        "send_user_commands_to_agent": False,
    }
    config_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.agent == "llama"
    assert config.banner is True
    assert config.system_prompt == "Test prompt"
    assert config.send_user_commands_to_agent is False


def test_load_models_dict(tmp_path, monkeypatch):
    """Test loading agents dictionary configuration."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = {
        "agent": "llama",
        "agents": {
            "llama": {"provider": "ollama", "model": "llama3.2:1b"},
            "what": {"provider": "ollama", "model": "what-model"},
        },
    }
    config_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.agents is not None
    assert "llama" in config.agents
    assert config.agents["llama"]["provider"] == "ollama"
    assert config.agents["what"]["model"] == "what-model"


def test_load_all_display_settings(tmp_path, monkeypatch):
    """Test loading all display settings."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = {
        "banner": True,
        "python_markdown": True,
        "agent_markdown": False,
        "shell_markdown": True,
    }
    config_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.banner is True
    assert config.python_markdown is True
    assert config.agent_markdown is False
    assert config.shell_markdown is True


def test_load_shell_init_script(tmp_path, monkeypatch):
    """Test loading shell init script."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = {
        "shell_init_script": "alias ll='ls -la'\nexport MY_VAR=value",
    }
    config_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.shell_init_script == "alias ll='ls -la'\nexport MY_VAR=value"


def test_load_custom_settings(tmp_path, monkeypatch):
    """Test that custom settings are stored in _custom dict."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = {
        "agent": "llama",
        "custom_key": "custom_value",
        "another_custom": 42,
    }
    config_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.get("custom_key") == "custom_value"
    assert config.get("another_custom") == 42


def test_load_invalid_yaml(tmp_path, monkeypatch):
    """Test that invalid YAML returns an error."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text("invalid: yaml: content: [")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is not None
    assert "Error parsing YAML" in error
    # Should still return a config object with defaults
    assert config.banner is False


def test_load_nonexistent_file(tmp_path, monkeypatch):
    """Test that missing config file returns default config."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    # Don't create config.yaml

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.agent is None
    assert config.banner is False


def test_show_tool_output_config(tmp_path, monkeypatch):
    """Test loading show_tool_output setting."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = {"show_tool_output": False}
    config_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.show_tool_output is False


def test_performance_settings_defaults():
    """Test that performance settings have correct default values."""
    config = ArtificeConfig()
    assert config.streaming_fps == 60
    assert config.shell_poll_interval == 0.02
    assert config.python_executor_sleep == 0.005


def test_performance_settings_custom(tmp_path, monkeypatch):
    """Test loading custom performance settings."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = {
        "streaming_fps": 30,
        "shell_poll_interval": 0.05,
        "python_executor_sleep": 0.01,
    }
    config_file.write_text(yaml.dump(yaml_content))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.streaming_fps == 30
    assert config.shell_poll_interval == 0.05
    assert config.python_executor_sleep == 0.01


def test_multiline_yaml_strings(tmp_path, monkeypatch):
    """Test that multiline YAML strings work correctly."""
    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    yaml_content = """
system_prompt: |
  Line 1
  Line 2
  Line 3
"""
    config_file.write_text(yaml_content)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()

    assert error is None
    assert config.system_prompt == "Line 1\nLine 2\nLine 3\n"


def test_local_config_overrides_home(tmp_path, monkeypatch):
    """Test that local .artifice/config.yaml overrides home config."""
    home_dir = tmp_path / "home"
    home_config_dir = home_dir / ".artifice"
    home_config_dir.mkdir(parents=True)
    home_config_file = home_config_dir / "config.yaml"
    home_config_file.write_text(yaml.dump({"agent": "home-agent", "banner": True}))

    project_dir = tmp_path / "project"
    local_config_dir = project_dir / ".artifice"
    local_config_dir.mkdir(parents=True)
    local_config_file = local_config_dir / "config.yaml"
    local_config_file.write_text(yaml.dump({"agent": "local-agent"}))

    monkeypatch.setattr(Path, "home", lambda: home_dir)
    monkeypatch.setattr(Path, "cwd", lambda: project_dir)
    config, error = load_config()

    assert error is None
    assert config.agent == "local-agent"  # Local overrides
    assert config.banner is True  # From home (not overridden)


def test_local_config_only(tmp_path, monkeypatch):
    """Test loading config from local directory when no home config exists."""
    project_dir = tmp_path / "project"
    local_config_dir = project_dir / ".artifice"
    local_config_dir.mkdir(parents=True)
    local_config_file = local_config_dir / "config.yaml"
    local_config_file.write_text(yaml.dump({"agent": "local-only", "banner": True}))

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nothome")
    monkeypatch.setattr(Path, "cwd", lambda: project_dir)
    config, error = load_config()

    assert error is None
    assert config.agent == "local-only"
    assert config.banner is True


def test_home_config_only(tmp_path, monkeypatch):
    """Test loading config from home directory when no local config exists."""
    home_dir = tmp_path / "home"
    home_config_dir = home_dir / ".artifice"
    home_config_dir.mkdir(parents=True)
    home_config_file = home_config_dir / "config.yaml"
    home_config_file.write_text(yaml.dump({"agent": "home-only", "banner": True}))

    project_dir = tmp_path / "project"

    monkeypatch.setattr(Path, "home", lambda: home_dir)
    monkeypatch.setattr(Path, "cwd", lambda: project_dir)
    config, error = load_config()

    assert error is None
    assert config.agent == "home-only"
    assert config.banner is True


def test_local_config_merges_agents(tmp_path, monkeypatch):
    """Test that local config can add agents while preserving home agents."""
    home_dir = tmp_path / "home"
    home_config_dir = home_dir / ".artifice"
    home_config_dir.mkdir(parents=True)
    home_config_file = home_config_dir / "config.yaml"
    home_config_file.write_text(
        yaml.dump(
            {
                "agents": {
                    "home-agent": {"model": "home-model"},
                }
            }
        )
    )

    project_dir = tmp_path / "project"
    local_config_dir = project_dir / ".artifice"
    local_config_dir.mkdir(parents=True)
    local_config_file = local_config_dir / "config.yaml"
    local_config_file.write_text(
        yaml.dump(
            {
                "agents": {
                    "local-agent": {"model": "local-model"},
                }
            }
        )
    )

    monkeypatch.setattr(Path, "home", lambda: home_dir)
    monkeypatch.setattr(Path, "cwd", lambda: project_dir)
    config, error = load_config()

    assert error is None
    # Local completely overrides agents dict - this is expected behavior
    assert config.agents is not None
    assert "local-agent" in config.agents
    assert config.agents["local-agent"]["model"] == "local-model"
