"""System and widget block widgets."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static

from artifice.ui.components.blocks.output import BufferedOutputBlock


class WidgetOutputBlock(BufferedOutputBlock):
    """Block that displays an arbitrary Textual widget."""

    def __init__(self, widget: Widget, **kwargs):
        super().__init__(**kwargs)
        self._widget = widget

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("", classes="status-indicator")
            with Vertical(classes="widget-container"):
                yield self._widget


class SystemBlock(BufferedOutputBlock):
    """Block for displaying system messages."""

    _STATIC_CSS_CLASS = "system-output"
    _MARKDOWN_CSS_CLASS = "system-markdown-output"

    def __init__(self, output: str = "", render_markdown: bool = True) -> None:
        super().__init__(output=output, render_markdown=render_markdown)
        self._status_indicator = Static(">", classes="status-indicator status-success")

    def compose(self) -> ComposeResult:
        with self._contents:
            yield self._status_indicator
            yield self._output
            yield self._markdown

    def on_mount(self) -> None:
        """Switch to Markdown immediately since system blocks are always complete."""
        self._markdown.styles.display = "none"
        if self._render_markdown:
            self._switch_to_markdown()
