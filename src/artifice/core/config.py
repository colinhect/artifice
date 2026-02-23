"""Configuration management for Artifice.

This module handles loading user configuration from ~/.artifice/config.yaml
and provides YAML-based configuration.
"""

from __future__ import annotations

import logging
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
    "prompts": None,
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
    "send_user_commands_to_agent": True,
    # Tool output visibility
    "show_tool_output": True,
    # Tool settings (applied when tools are enabled)
    "tools": None,
    "tool_approval": "ask",  # "ask", "auto", "deny"
    "tool_allowlist": None,  # list of tool names/patterns to always allow
    # Shell init script
    "shell_init_script": None,
    # Tmux settings
    "tmux_target": None,
    "tmux_prompt_pattern": None,
    "tmux_echo_exit_code": False,
    # Performance settings
    "streaming_fps": 60,
    "shell_poll_interval": 0.02,
    "python_executor_sleep": 0.005,
    # Session saving
    "save_session": True,
}


class ArtificeConfig:
    """Configuration container for Artifice settings.

    This class stores configuration values that can be set by the user's config.yaml file.
    All settings have sensible defaults.
    """

    # Agent settings
    agent: str | None
    agents: dict | None
    prompts: dict | None
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
    send_user_commands_to_agent: bool

    # Tool output visibility
    show_tool_output: bool

    # Tool settings
    tools: list[str] | None
    tool_approval: str
    tool_allowlist: list[str] | None

    # Shell init script
    shell_init_script: str | None

    # Tmux settings
    tmux_target: str | None
    tmux_prompt_pattern: str | None
    tmux_echo_exit_code: bool

    # Performance settings
    streaming_fps: int
    shell_poll_interval: float
    python_executor_sleep: float

    # Session saving
    save_session: bool

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
    return Path.home() / ".artifice"


def get_config_file_path() -> Path:
    """Get the path to the user's config.yaml file."""
    return get_config_path() / "config.yaml"


def get_local_config_path() -> Path:
    """Get the path to the local project's config directory."""
    return Path.cwd() / ".artifice"


def get_local_config_file_path() -> Path:
    """Get the path to the local project's config.yaml file."""
    return get_local_config_path() / "config.yaml"


def _load_config_file(config_path: Path) -> dict[str, Any] | None:
    """Load a single config file and return its data dict.

    Returns None if file doesn't exist or is empty.
    Raises exceptions on parse errors.
    """
    if not config_path.exists():
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data if data else None


def load_config() -> tuple[ArtificeConfig, str | None]:
    """Load configuration from ~/.artifice/config.yaml and .artifice/config.yaml.

    Configuration is loaded from home directory first, then local directory
    (current working directory) overrides any settings from home.

    Returns:
        A tuple of (config, error_message). If loading fails, error_message
        will contain details about the failure.
    """
    config = ArtificeConfig()
    home_config_path = get_config_file_path()
    local_config_path = get_local_config_file_path()

    configs_to_load = []

    # Load home config first
    if home_config_path.exists():
        configs_to_load.append(("home", home_config_path))

    # Load local config second (will override home)
    if local_config_path.exists():
        configs_to_load.append(("local", local_config_path))

    # If no config files exist, return default config
    if not configs_to_load:
        logger.debug("No config files found, using defaults")
        return config, None

    try:
        for location, config_path in configs_to_load:
            data = _load_config_file(config_path)
            if data is None:
                continue

            # Load known fields from YAML data
            for key in _FIELDS:
                if key in data:
                    setattr(config, key, data[key])

            # Store any additional custom settings
            for key, value in data.items():
                if key not in _FIELDS:
                    config.set(key, value)

            logger.info("Loaded config from %s (%s)", config_path, location)

        return config, None

    except yaml.YAMLError as e:
        error_msg = f"Error parsing YAML:\n{e}"
        return config, error_msg
    except Exception:
        error_msg = f"Error loading config:\n{traceback.format_exc()}"
        return config, error_msg
