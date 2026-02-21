"""File utilities for project file search."""

from __future__ import annotations

import fnmatch
from pathlib import Path

LARGE_FILE_THRESHOLD = 100 * 1024  # 100KB

IGNORE_PATTERNS = [
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.egg",
    "*.egg-info",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "coverage.xml",
    "*.cover",
    ".coverage",
    "htmlcov",
    ".idea",
    ".vscode",
    "*.swp",
    "*.swo",
]


def get_ignore_patterns() -> list[str]:
    """Return standard patterns to ignore during file search."""
    return IGNORE_PATTERNS.copy()


def should_ignore(path: Path) -> bool:
    """Check if path matches any ignore pattern."""
    name = path.name
    for pattern in IGNORE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def list_project_files(root: Path | None = None) -> list[Path]:
    """Recursively list all files in project, excluding ignored patterns."""
    if root is None:
        root = Path.cwd()

    files: list[Path] = []

    def scan_dir(directory: Path) -> None:
        try:
            for item in directory.iterdir():
                if should_ignore(item):
                    continue
                if item.is_dir():
                    scan_dir(item)
                elif item.is_file():
                    files.append(item)
        except PermissionError:
            pass

    scan_dir(root)
    return files


def is_binary_file(path: Path) -> bool:
    """Check if file appears to be binary (contains null bytes in first chunk)."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True


def get_file_size(path: Path) -> int:
    """Get file size in bytes."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def read_file_content(path: Path) -> tuple[str, bool, int]:
    """Read file content.

    Returns:
        tuple of (content, is_binary, size)
        - content: file text or empty string if binary
        - is_binary: True if file appears to be binary
        - size: file size in bytes
    """
    size = get_file_size(path)

    if is_binary_file(path):
        return ("", True, size)

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        return (content, False, size)
    except OSError:
        return ("", True, size)


def fuzzy_match_files(
    query: str, files: list[Path], root: Path | None = None
) -> list[Path]:
    """Fuzzy match files by query.

    Simple fuzzy match: all query chars appear in order in the path string.
    Returns files sorted by match quality (shorter relative paths first).
    """
    if root is None:
        root = Path.cwd()

    query = query.lower()

    def match_score(path: Path) -> int | None:
        """Return match score or None if no match. Lower is better."""
        rel_path = str(path.relative_to(root))
        rel_lower = rel_path.lower()

        qi = 0
        for ch in rel_lower:
            if qi < len(query) and ch == query[qi]:
                qi += 1

        if qi == len(query):
            return len(rel_path)
        return None

    scored: list[tuple[int, Path]] = []
    for f in files:
        score = match_score(f)
        if score is not None:
            scored.append((score, f))

    scored.sort(key=lambda x: x[0])
    return [f for _, f in scored]
