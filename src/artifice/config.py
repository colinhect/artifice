"""Backward compatibility re-export for config module."""

from __future__ import annotations

from artifice.core.config import (
    ArtificeConfig,
    get_config_path,
    get_init_script_path,
    load_config,
)

__all__ = ["ArtificeConfig", "get_config_path", "get_init_script_path", "load_config"]
