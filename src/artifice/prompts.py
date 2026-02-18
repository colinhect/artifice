"""Prompt template loading from .artifice/prompts/ directories."""

from __future__ import annotations

from pathlib import Path


def get_prompt_dirs() -> list[Path]:
    """Return prompt directories in priority order (local first, then home)."""
    dirs = []
    # Local project directory
    local = Path.cwd() / ".artifice" / "prompts"
    if local.is_dir():
        dirs.append(local)
    # Home directory
    home = Path.home() / ".artifice" / "prompts"
    if home.is_dir():
        dirs.append(home)
    return dirs


def list_prompts() -> dict[str, Path]:
    """Return a mapping of prompt names to file paths.

    Local prompts take priority over home prompts with the same name.
    Names are derived from filenames without the .md extension.
    """
    prompts: dict[str, Path] = {}
    # Process in reverse priority so local overrides home
    for prompt_dir in reversed(get_prompt_dirs()):
        for md_file in prompt_dir.rglob("*.md"):
            # Name is relative path without .md, e.g. "system/cli-python-agent"
            name = str(md_file.relative_to(prompt_dir).with_suffix(""))
            prompts[name] = md_file
    return prompts


def load_prompt(name: str) -> str | None:
    """Load prompt content by name. Returns None if not found."""
    prompts = list_prompts()
    path = prompts.get(name)
    if path and path.is_file():
        return path.read_text()
    return None


def fuzzy_match(query: str, name: str) -> bool:
    """Simple fuzzy match: all query chars appear in order in name."""
    query = query.lower()
    name = name.lower()
    qi = 0
    for ch in name:
        if qi < len(query) and ch == query[qi]:
            qi += 1
    return qi == len(query)
