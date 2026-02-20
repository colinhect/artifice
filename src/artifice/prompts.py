"""Backward compatibility re-export for prompts module."""

from __future__ import annotations

from artifice.core.prompts import (
    fuzzy_match,
    get_prompt_dirs,
    list_prompts,
    load_prompt,
)

__all__ = ["fuzzy_match", "get_prompt_dirs", "list_prompts", "load_prompt"]
