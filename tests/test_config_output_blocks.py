"""Tests for output code block configuration options."""

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


def test_config_loading_output_block_settings(tmp_path):
    """Test that output block settings can be loaded from YAML."""
    import yaml
    from artifice.core.config import load_config

    # Create a temp config file
    config_file = tmp_path / "init.yaml"
    config_data = {
        "shell_output_code_block": False,
        "tmux_output_code_block": True,
        "python_output_code_block": False,
        "tmux_echo_exit_code": True,
    }
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    # Monkey patch the config path
    import artifice.core.config as config_module

    original_get_init_script_path = config_module.get_init_script_path

    def mock_get_init_script_path():
        return config_file

    config_module.get_init_script_path = mock_get_init_script_path

    try:
        config, error = load_config()
        assert error is None
        assert config.shell_output_code_block is False
        assert config.tmux_output_code_block is True
        assert config.python_output_code_block is False
        assert config.tmux_echo_exit_code is True
    finally:
        config_module.get_init_script_path = original_get_init_script_path
