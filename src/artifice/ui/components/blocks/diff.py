"""Diff output block for displaying file edits."""

from __future__ import annotations

import json
from pathlib import Path

from textual import highlight
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from artifice.ui.components.blocks.base import BaseBlock


def _detect_language(path: str) -> str:
    """Detect syntax highlighting language from file extension."""
    ext = Path(path).suffix.lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "bash",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".html": "html",
        ".css": "css",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".rb": "ruby",
        ".php": "php",
        ".sql": "sql",
        ".xml": "xml",
    }
    return lang_map.get(ext, "text")


class DiffLine(Static):
    """A single line in the diff display."""

    def __init__(
        self,
        content: str,
        line_number: int | None,
        status: str,
        language: str,
        **kwargs,
    ) -> None:
        self._content = content
        self._line_number = line_number
        self._status = status
        self._language = language
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self.add_class(f"diff-line-{self._status}")

        if self._line_number is not None:
            gutter = f"{self._line_number:4d} "
        else:
            gutter = "     "

        if self._status == "removed":
            marker = "-"
        elif self._status == "added":
            marker = "+"
        else:
            marker = " "

        highlighted = highlight.highlight(self._content, language=self._language)
        self.update(f"{gutter}{marker} {highlighted}")


class DiffSide(Vertical):
    """One side of a split diff (before or after)."""

    def __init__(
        self,
        title: str,
        lines: list[tuple[str, int | None, str]],
        language: str,
        **kwargs,
    ) -> None:
        self._title = title
        self._lines = lines
        self._language = language
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="diff-header")
        for content, line_number, status in self._lines:
            yield DiffLine(
                content=content,
                line_number=line_number,
                status=status,
                language=self._language,
                classes="diff-line",
            )


class DiffOutputBlock(BaseBlock):
    """Side-by-side diff display with syntax highlighting.

    Shows before/after view of file changes with:
    - Line numbers
    - Syntax highlighting
    - Color-coded additions (green) and removals (red)
    - Context lines around changes
    """

    def __init__(
        self,
        path: str,
        old_lines: list[str],
        new_lines: list[str],
        start_line: int,
        context_before: list[str],
        context_after: list[str],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._path = path
        self._old_lines = old_lines
        self._new_lines = new_lines
        self._start_line = start_line
        self._context_before = context_before
        self._context_after = context_after
        self._language = _detect_language(path)
        self._status_indicator = Static("", classes="status-indicator status-success")
        self.add_class("in-context")

    def compose(self) -> ComposeResult:
        yield self._status_indicator

        before_lines = []
        after_lines = []

        context_start = self._start_line - len(self._context_before)
        for i, line in enumerate(self._context_before):
            before_lines.append((line, context_start + i, "context"))
            after_lines.append((line, context_start + i, "context"))

        for i, line in enumerate(self._old_lines):
            before_lines.append((line, self._start_line + i, "removed"))

        for i, line in enumerate(self._new_lines):
            after_lines.append((line, self._start_line + i, "added"))

        after_change_start = self._start_line + len(self._new_lines)
        for i, line in enumerate(self._context_after):
            before_lines.append((line, after_change_start + i, "context"))
            after_lines.append((line, after_change_start + i, "context"))

        with Horizontal(classes="diff-container"):
            yield DiffSide(
                title=f"Before: {self._path}",
                lines=before_lines,
                language=self._language,
                classes="diff-side diff-side-before",
            )
            yield DiffSide(
                title=f"After: {self._path}",
                lines=after_lines,
                language=self._language,
                classes="diff-side diff-side-after",
            )

    @classmethod
    def from_json(cls, json_str: str) -> "DiffOutputBlock | None":
        """Create a DiffOutputBlock from executor result JSON.

        Returns None if parsing fails or success is False.
        """
        try:
            data = json.loads(json_str)
            if not data.get("success"):
                return None
            return cls(
                path=data["path"],
                old_lines=data["old_lines"],
                new_lines=data["new_lines"],
                start_line=data["start_line"],
                context_before=data["context_before"],
                context_after=data["context_after"],
            )
        except (json.JSONDecodeError, KeyError):
            return None
