"""Output block widgets."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static, Markdown

from artifice.ui.components.blocks.base import BaseBlock


class StreamingMarkdownBlock(BaseBlock):
    """Block that streams markdown content in real-time using Textual's MarkdownStream.

    Uses the Markdown widget with streaming support for real-time rendering
    as content arrives from the LLM.
    """

    def __init__(self, initial_text: str = "", activity: bool = True) -> None:
        super().__init__()
        self._status_indicator = Static("", classes="status-indicator")
        self._streaming = activity
        self._markdown_widget: Markdown | None = None
        self._markdown_stream = None
        self._accumulated_text: str = initial_text
        self._stream_ready: bool = False
        self.add_class("in-context")

        if not activity:
            self.mark_success()

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self._status_indicator
            if self._accumulated_text:
                self._markdown_widget = Markdown(self._accumulated_text)
            else:
                self._markdown_widget = Markdown("")
            yield self._markdown_widget

    def on_mount(self) -> None:
        """Get the markdown stream once the widget is mounted."""
        if self._markdown_widget is not None:
            self._markdown_stream = self._markdown_widget.get_stream(
                self._markdown_widget
            )
            self._stream_ready = True
            if self._accumulated_text:
                asyncio.create_task(self._markdown_stream.write(self._accumulated_text))

    async def append(self, text: str) -> None:
        """Append text to the streaming markdown.

        Accumulates text and writes to the markdown stream when ready.
        """
        self._accumulated_text += text
        if self._stream_ready and self._markdown_stream is not None:
            await self._markdown_stream.write(text)

    def flush(self) -> None:
        """No-op for streaming markdown - updates happen immediately via append."""

    def finalize_streaming(self) -> None:
        """End streaming - mark as complete."""
        if not self._streaming:
            return
        self._streaming = False

    def mark_success(self) -> None:
        """Mark the block as successful."""
        self._status_indicator.styles.display = "block"

    def mark_failed(self) -> None:
        """Mark the block as failed."""
        self._status_indicator.styles.display = "block"


class AgentOutputBlock(StreamingMarkdownBlock):
    """Block for AI agent output with real-time markdown streaming."""

    def __init__(self, output: str = "", activity: bool = True) -> None:
        super().__init__(initial_text=output, activity=activity)


class ThinkingOutputBlock(StreamingMarkdownBlock):
    """Block for AI thinking content. Styled distinctly via CSS."""

    def __init__(self, activity: bool = True) -> None:
        super().__init__(activity=activity)


class BufferedOutputBlock(BaseBlock):
    """Base class for output blocks with buffered text and markdown toggle.

    Subclasses set _STATIC_CSS_CLASS and _MARKDOWN_CSS_CLASS to control
    which CSS classes are applied to the Static/Markdown child widgets.

    Both Static and Markdown are pre-mounted; toggling uses CSS display to avoid flicker.
    """

    _STATIC_CSS_CLASS: str = ""
    _MARKDOWN_CSS_CLASS: str = ""

    def __init__(self, output: str = "", render_markdown: bool = False) -> None:
        super().__init__()
        self._output_str: str = output
        self._render_markdown = render_markdown
        self._dirty = False
        self._contents = Horizontal()
        self._output = Static(output, markup=False, classes=self._STATIC_CSS_CLASS)
        self._markdown = Markdown("", classes=self._MARKDOWN_CSS_CLASS)
        self._markdown_loaded = False

    def flush(self) -> None:
        """Push accumulated text to the widget. Call after batching appends."""
        if not self._dirty:
            return
        self._dirty = False
        if self._output:
            self._output.update(self._output_str)

    def toggle_markdown(self) -> None:
        """Toggle between static and markdown rendering."""
        self._render_markdown = not self._render_markdown
        if self._render_markdown:
            if not self._markdown_loaded:
                self._markdown_loaded = True
                self._markdown.update(self._output_str.strip())
            self._output.styles.display = "none"
            self._markdown.styles.display = "block"
        else:
            self._markdown.styles.display = "none"
            self._output.styles.display = "block"

    def _switch_to_markdown(self) -> None:
        """Switch to markdown display - both widgets pre-mounted, just toggle display."""
        if not self._markdown_loaded:
            self._markdown_loaded = True
            self._markdown.update(self._output_str.strip())
        self._output.styles.display = "none"
        self._markdown.styles.display = "block"


class CodeOutputBlock(BufferedOutputBlock):
    """Block for displaying code output with optional markdown rendering."""

    _STATIC_CSS_CLASS = "code-output"
    _MARKDOWN_CSS_CLASS = "markdown-output"

    def __init__(
        self, output: str = "", render_markdown: bool = False, in_context: bool = False
    ) -> None:
        super().__init__(output=output, render_markdown=render_markdown)
        self._status_indicator = Static(classes="status-indicator")
        self._has_error = False
        if in_context:
            self.add_class("in-context")

    def compose(self) -> ComposeResult:
        with self._contents:
            yield self._status_indicator
            yield self._output
            yield self._markdown

    def on_mount(self) -> None:
        """Hide markdown widget on mount."""
        self._markdown.styles.display = "none"

    def append_output(self, output: str) -> None:
        """Append output text to the buffer."""
        self._output_str += output
        self._dirty = True

    def append_error(self, output: str) -> None:
        """Append error output and mark as failed."""
        self.append_output(output)
        self.mark_failed()

    def mark_failed(self) -> None:
        """Mark the output as having an error."""
        if not self._has_error:
            self._has_error = True
            if self._output:
                self._output.remove_class("code-output")
                self._output.add_class("error-output")
            elif self._markdown:
                self._markdown.remove_class("markdown-output")
                self._markdown.add_class("error-output")
