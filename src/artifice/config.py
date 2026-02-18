"""Configuration management for Artifice.

This module handles loading user configuration from ~/.config/artifice/init.yaml
and provides YAML-based configuration.
"""

from __future__ import annotations

import logging
import os
import traceback
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Declarative mapping of YAML keys to their default values.
# Used by ArtificeConfig.__init__ and load_config to avoid repetition.
_FIELDS: dict[str, Any] = {
    # Agent settings
    "agent": None,
    "agents": None,
    "system_prompt": None,
    "prompt_prefix": None,
    "thinking_budget": None,
    # Display settings
    "banner": False,
    "python_markdown": False,
    "agent_markdown": True,
    "shell_markdown": False,
    # Output code block settings
    "shell_output_code_block": True,
    "tmux_output_code_block": False,
    "python_output_code_block": True,
    # Auto-send settings
    "auto_send_to_agent": True,
    # Shell init script
    "shell_init_script": None,
    # Tmux settings
    "tmux_target": None,
    "tmux_prompt_pattern": None,
    "tmux_echo_exit_code": False,
}


class ArtificeConfig:
    """Configuration container for Artifice settings.

    This class stores configuration values that can be set by the user's init.yaml file.
    All settings have sensible defaults.
    """

    # Agent settings
    agent: str | None
    agents: dict | None
    system_prompt: str | None
    prompt_prefix: str | None
    thinking_budget: int | None

    # Display settings
    banner: bool
    python_markdown: bool
    agent_markdown: bool
    shell_markdown: bool

    # Output code block settings
    shell_output_code_block: bool
    tmux_output_code_block: bool
    python_output_code_block: bool

    # Auto-send settings
    auto_send_to_agent: bool

    # Shell init script
    shell_init_script: str | None

    # Tmux settings
    tmux_target: str | None
    tmux_prompt_pattern: str | None
    tmux_echo_exit_code: bool

    def __init__(self):
        for key, default in _FIELDS.items():
            setattr(self, key, default)
        # Custom settings (user can add any additional settings)
        self._custom: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        """Set a custom configuration value."""
        self._custom[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a custom configuration value."""
        return self._custom.get(key, default)


def get_config_path() -> Path:
    """Get the path to the user's config directory."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "artifice"
    return Path.home() / ".config" / "artifice"


def get_init_script_path() -> Path:
    """Get the path to the user's init.yaml script."""
    return get_config_path() / "init.yaml"


def load_config() -> tuple[ArtificeConfig, str | None]:
    """Load configuration from ~/.config/artifice/init.yaml.

    The init.yaml file is parsed as YAML and configuration values are loaded
    from the resulting dictionary.

    Returns:
        A tuple of (config, error_message). If loading fails, error_message
        will contain details about the failure.
    """
    config = ArtificeConfig()
    init_path = get_init_script_path()

    # If no init.yaml exists, return default config
    if not init_path.exists():
        logger.debug("No config file at %s, using defaults", init_path)
        return config, None

    try:
        # Read and parse the YAML file
        with open(init_path, "r") as f:
            data = yaml.safe_load(f)

        # If the file is empty or invalid YAML, return default config
        if data is None:
            return config, None

        # Load known fields from YAML data
        for key in _FIELDS:
            if key in data:
                setattr(config, key, data[key])

        # Store any additional custom settings
        for key, value in data.items():
            if key not in _FIELDS:
                config.set(key, value)

        logger.info("Loaded config from %s", init_path)
        return config, None

    except yaml.YAMLError as e:
        error_msg = f"Error parsing YAML from {init_path}:\n{e}"
        return config, error_msg
    except Exception:
        error_msg = f"Error loading config from {init_path}:\n{traceback.format_exc()}"
        return config, error_msg
