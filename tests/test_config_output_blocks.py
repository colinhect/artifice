"""Tests for output code block configuration options."""

from pathlib import Path

from artifice.core.config import ArtificeConfig


def test_default_config_values():
    """Test that config has correct default values for output blocks."""
    config = ArtificeConfig()

    # Code block settings
    assert config.shell_output_code_block is True
    assert config.tmux_output_code_block is False
    assert config.python_output_code_block is True

    # Tmux exit code setting
    assert config.tmux_echo_exit_code is False


def test_config_loading_output_block_settings(tmp_path, monkeypatch):
    """Test that output block settings can be loaded from YAML."""
    import yaml
    from artifice.core.config import load_config

    config_dir = tmp_path / ".artifice"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_data = {
        "shell_output_code_block": False,
        "tmux_output_code_block": True,
        "python_output_code_block": False,
        "tmux_echo_exit_code": True,
    }
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config, error = load_config()
    assert error is None
    assert config.shell_output_code_block is False
    assert config.tmux_output_code_block is True
    assert config.python_output_code_block is False
    assert config.tmux_echo_exit_code is True
