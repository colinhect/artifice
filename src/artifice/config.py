"""Configuration management for Artifice.

This module handles loading user configuration from ~/.config/artifice/init.yaml
and provides YAML-based configuration.
"""

from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Any, Optional

import yaml


class ArtificeConfig:
    """Configuration container for Artifice settings.

    This class stores configuration values that can be set by the user's init.yaml file.
    All settings have sensible defaults.
    """

    def __init__(self):
        # Assistant settings
        self.assistant: Optional[str] = None
        self.assistants: Optional[dict] = None
        self.system_prompt: Optional[str] = None
        self.prompt_prefix: Optional[str] = None
        self.thinking_budget: Optional[int] = None

        # Provider-specific settings
        self.ollama_host: Optional[str] = None  # e.g., http://localhost:11434

        # Display settings
        self.banner: bool = False
        self.python_markdown: bool = False
        self.assistant_markdown: bool = True
        self.shell_markdown: bool = False

        # Auto-send settings
        self.auto_send_to_assistant: bool = True

        # Shell init script (for bash)
        self.shell_init_script: Optional[str] = None

        # Tmux settings
        self.tmux_target: Optional[str] = None
        self.tmux_prompt_pattern: Optional[str] = None

        # Session settings
        self.save_sessions: bool = True
        self.sessions_dir: Optional[str] = None  # Defaults to ~/.artifice/sessions/

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


def load_config() -> tuple[ArtificeConfig, Optional[str]]:
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
        return config, None

    try:
        # Read and parse the YAML file
        with open(init_path, "r") as f:
            data = yaml.safe_load(f)

        # If the file is empty or invalid YAML, return default config
        if data is None:
            return config, None

        # Load configuration values from the YAML data
        # Assistant settings
        if "assistant" in data:
            config.assistant = data["assistant"]
        if "assistants" in data:
            config.assistants = data["assistants"]
        if "tmux_target" in data:
            config.tmux_target = data["tmux_target"]
        if "tmux_prompt_pattern" in data:
            config.tmux_prompt_pattern = data["tmux_prompt_pattern"]
        if "system_prompt" in data:
            config.system_prompt = data["system_prompt"]
        if "prompt_prefix" in data:
            config.prompt_prefix = data["prompt_prefix"]
        if "thinking_budget" in data:
            config.thinking_budget = data["thinking_budget"]

        # Provider-specific settings
        if "ollama_host" in data:
            config.ollama_host = data["ollama_host"]

        # Display settings
        if "banner" in data:
            config.banner = data["banner"]
        if "python_markdown" in data:
            config.python_markdown = data["python_markdown"]
        if "assistant_markdown" in data:
            config.assistant_markdown = data["assistant_markdown"]
        if "shell_markdown" in data:
            config.shell_markdown = data["shell_markdown"]

        # Auto-send settings
        if "auto_send_to_assistant" in data:
            config.auto_send_to_assistant = data["auto_send_to_assistant"]

        # Shell init script
        if "shell_init_script" in data:
            config.shell_init_script = data["shell_init_script"]

        # Session settings
        if "save_sessions" in data:
            config.save_sessions = data["save_sessions"]
        if "sessions_dir" in data:
            config.sessions_dir = data["sessions_dir"]

        # Store any additional custom settings
        known_keys = {
            "assistant",
            "assistants",
            "system_prompt",
            "prompt_prefix",
            "thinking_budget",
            "ollama_host",
            "banner",
            "python_markdown",
            "assistant_markdown",
            "shell_markdown",
            "auto_send_to_assistant",
            "shell_init_script",
            "save_sessions",
            "sessions_dir",
            "tmux_target",
            "tmux_prompt_pattern",
        }
        for key, value in data.items():
            if key not in known_keys:
                config.set(key, value)

        return config, None

    except yaml.YAMLError as e:
        error_msg = f"Error parsing YAML from {init_path}:\n{e}"
        return config, error_msg
    except Exception:
        error_msg = f"Error loading config from {init_path}:\n{traceback.format_exc()}"
        return config, error_msg


def get_sessions_dir(config: ArtificeConfig) -> Path:
    """Get the directory for storing session transcripts.

    Returns the configured sessions directory, or the default ~/.artifice/sessions/
    """
    if config.sessions_dir:
        return Path(config.sessions_dir).expanduser()

    return Path.home() / ".artifice" / "sessions"


def ensure_sessions_dir(config: ArtificeConfig) -> None:
    """Ensure the sessions directory exists."""
    sessions_dir = get_sessions_dir(config)
    sessions_dir.mkdir(parents=True, exist_ok=True)
