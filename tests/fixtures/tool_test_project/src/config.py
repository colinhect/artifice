"""Configuration module for the sample project."""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

# Default settings
DEFAULT_CONFIG = {
    "debug": False,
    "log_level": "INFO",
    "max_workers": 4,
    "timeout": 30,
}


def get_config(overrides: dict | None = None) -> dict:
    """Get configuration with optional overrides."""
    config = DEFAULT_CONFIG.copy()
    if overrides:
        config.update(overrides)
    return config
