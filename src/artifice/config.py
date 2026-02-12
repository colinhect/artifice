"""Configuration management for Artifice.

This module handles loading user configuration from ~/.config/artifice/init.py
and provides a sandboxed execution environment for user settings.
"""

from __future__ import annotations

import os
import traceback
from pathlib import Path
from typing import Any, Optional


class ArtificeConfig:
    """Configuration container for Artifice settings.
    
    This class stores configuration values that can be set by the user's init.py file.
    All settings have sensible defaults.
    """
    
    def __init__(self):
        # Agent settings
        self.provider: Optional[str] = None  # claude, copilot, ollama, simulated
        self.model: Optional[str] = None  # claude-sonnet-4-5, gpt-4, llama3.2:1b, etc
        
        # Provider-specific settings
        self.ollama_host: Optional[str] = None  # e.g., http://localhost:11434
        
        # Display settings
        self.banner: bool = False
        self.python_markdown: bool = False
        self.agent_markdown: bool = True
        self.shell_markdown: bool = False
        
        # Auto-send settings
        self.auto_send_to_agent: bool = True
        
        # Shell init script (for bash)
        self.shell_init_script: Optional[str] = None
        
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
    config_home = os.environ.get('XDG_CONFIG_HOME')
    if config_home:
        return Path(config_home) / 'artifice'
    return Path.home() / '.config' / 'artifice'


def get_init_script_path() -> Path:
    """Get the path to the user's init.py script."""
    return get_config_path() / 'init.py'


def load_config() -> tuple[ArtificeConfig, Optional[str]]:
    """Load configuration from ~/.config/artifice/init.py.
    
    The init.py file is executed in a sandboxed environment where it can set
    configuration values on a 'config' object.
    
    Returns:
        A tuple of (config, error_message). If loading fails, error_message
        will contain details about the failure.
    """
    config = ArtificeConfig()
    init_path = get_init_script_path()
    
    # If no init.py exists, return default config
    if not init_path.exists():
        return config, None
    
    # Create a sandboxed namespace for executing the init script
    sandbox = {
        '__builtins__': {
            # Allow basic builtins
            'True': True,
            'False': False,
            'None': None,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'len': len,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'print': print,  # Allow print for debugging config
            # Explicitly deny dangerous operations
            '__import__': None,
            'open': None,
            'exec': None,
            'eval': None,
            'compile': None,
        },
        'config': config,
    }
    
    try:
        # Read and execute the init script
        with open(init_path, 'r') as f:
            code = f.read()
        
        exec(code, sandbox)
        return config, None
        
    except Exception as e:
        error_msg = f"Error loading config from {init_path}:\n{traceback.format_exc()}"
        return config, error_msg


def get_sessions_dir(config: ArtificeConfig) -> Path:
    """Get the directory for storing session transcripts.
    
    Returns the configured sessions directory, or the default ~/.artifice/sessions/
    """
    if config.sessions_dir:
        return Path(config.sessions_dir).expanduser()
    
    return Path.home() / '.artifice' / 'sessions'


def ensure_sessions_dir(config: ArtificeConfig) -> None:
    """Ensure the sessions directory exists."""
    sessions_dir = get_sessions_dir(config)
    sessions_dir.mkdir(parents=True, exist_ok=True)
