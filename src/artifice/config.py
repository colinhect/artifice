"""Configuration loading for Artifice."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


class ArtificeConfig:
    """Configuration for Artifice environment.
    
    Loads settings from ~/.artificerc to initialize the shell environment.
    """
    
    def __init__(self) -> None:
        """Initialize empty configuration."""
        self.shell_init_script: Optional[str] = None
        self.use_simple_subprocess: bool = True
        
    @classmethod
    def load(cls) -> ArtificeConfig:
        """Load configuration from ~/.artificerc file.
        
        The .artificerc file should contain shell commands that will be
        sourced before each shell command execution. This allows setting
        aliases, environment variables, and other shell configurations.
        
        Returns:
            ArtificeConfig instance with loaded settings.
        """
        config = cls()
        
        # Look for .artificerc in home directory
        rc_file = Path.home() / ".artificerc"
        
        if rc_file.exists():
            try:
                with open(rc_file, 'r', encoding='utf-8') as f:
                    config.shell_init_script = f.read()
            except Exception as e:
                # If we can't read the config file, just warn but don't fail
                import warnings
                warnings.warn(f"Failed to load .artificerc: {e}")
        
        return config
