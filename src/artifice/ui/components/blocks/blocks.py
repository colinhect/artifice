"""Output block widgets for the terminal display."""

from __future__ import annotations

import asyncio

from textual import highlight
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static, LoadingIndicator, Markdown

from artifice.execution.base import ExecutionResult, ExecutionStatus


class BaseBlock(Static):
    """Base class for all output block widgets."""


class CodeInputBlock(BaseBlock):
    """Block for displaying code input with syntax highlighting and status indicator."""

    def __init__(
        self,
        code: str,
        language: str,
        show_loading: bool = True,
        in_context=False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._loading_indicator = LoadingIndicator(classes="status-indicator")
        if show_loading:
            self._loading_indicator.styles.display = "block"
        else:
            self._loading_indicator.styles.display = "none"
        self._streaming = show_loading
        self._language = language
        # Status icon appears before the prompt
        self._status_icon = Static(self._status_text(), classes="status-indicator")
        self._status_icon.add_class("status-unexecuted")
        self._original_code = code  # Store original code for re-execution
        # Always use syntax highlighting, even during streaming
        self._code = Static(
            highlight.highlight(code, language=language), classes="code"
        )
        self._status_container = Horizontal(classes="status-indicator")
        if in_context:
            self.add_class("in-context")

    def _status_text(self) -> str:
        return ""

    def compose(self) -> ComposeResult:
        with Horizontal():
            with self._status_container:
                yield self._loading_indicator
                yield self._status_icon
            yield self._code

    def update_status(self, result: ExecutionResult) -> None:
        """Update the status indicator based on execution result."""
        self._loading_indicator.styles.display = "none"
        if result.status == ExecutionStatus.SUCCESS:
            self._status_icon.update("\u2714")
            self._status_icon.remove_class("status-error")
            self._status_icon.add_class("status-success")
        elif result.status == ExecutionStatus.ERROR:
            self._status_icon.update("\u2716")
            self._status_icon.remove_class("status-success")
            self._status_icon.add_class("status-error")

    def show_loading(self) -> None:
        """Show the loading indicator (for re-execution)."""
        self._loading_indicator.styles.display = "block"
        # Clear any previous status styling
        self._status_icon.remove_class("status-success")
        self._status_icon.remove_class("status-error")
        self._status_icon.update(self._status_text())

    def finish_streaming(self) -> None:
        """End streaming: show status indicator (code already highlighted)."""
        self._loading_indicator.styles.display = "none"
        self._streaming = False

    def update_code(self, code: str) -> None:
        """Update the displayed code with syntax highlighting (used during streaming)."""
        self._original_code = code
        # Always apply syntax highlighting
        self._code.update(highlight.highlight(code.strip(), language=self._language))

    def get_code(self) -> str:
        """Get the original code."""
        return self._original_code

    def get_mode(self) -> str:
        """Get the mode for this code block (python or shell)."""
        return "shell" if self._language == "bash" else "python"


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
            # Create markdown widget with initial content if any
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
            # Flush any accumulated text that arrived before mount
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
        # render_markdown parameter kept for API compatibility but always True
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
                # Apply error styling to markdown output as well
                self._markdown.remove_class("markdown-output")
                self._markdown.add_class("error-output")


class WidgetOutputBlock(BaseBlock):
    """Block that displays an arbitrary Textual widget."""

    def __init__(self, widget: Widget, **kwargs):
        super().__init__(**kwargs)
        self._widget = widget

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("", classes="status-indicator")
            with Vertical(classes="widget-container"):
                yield self._widget


class AgentInputBlock(BaseBlock):
    """Block for displaying user input prompts."""

    def __init__(self, prompt: str, in_context: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status_indicator = Static(">", classes="status-indicator status-success")
        self._prompt = Static(prompt, classes="prompt")
        self._original_prompt = prompt  # Store original prompt for re-use
        if in_context:
            self.add_class("in-context")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self._status_indicator
            with Vertical():
                yield self._prompt

    def get_prompt(self) -> str:
        """Get the original prompt."""
        return self._original_prompt

    def get_mode(self) -> str:
        """Get the mode for this block (ai)."""
        return "ai"


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


class ToolCallBlock(CodeInputBlock):
    """Block for an AI-requested tool call.

    Created directly from AgentResponse.tool_calls — bypasses the fence
    detector XML hack used previously. Displays a tool-name label above
    the syntax-highlighted code so the user can inspect and execute it.

    For tools with a direct executor (read_file, web_fetch, etc.) the
    ``tool_args`` dict carries the full arguments so the executor can be
    invoked without reparsing the display text.
    """

    def __init__(
        self,
        tool_call_id: str,
        name: str,
        code: str,
        language: str,
        tool_args: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            code=code,
            language=language,
            show_loading=False,
            in_context=True,
            **kwargs,
        )
        self.tool_call_id = tool_call_id
        self._tool_name = name
        self.tool_args: dict = tool_args or {}
        self._label = Static(name, classes="tool-name")

    @property
    def tool_name(self) -> str:
        """Get the tool name."""
        return self._tool_name

    def compose(self) -> ComposeResult:
        yield self._label
        with Horizontal():
            with self._status_container:
                yield self._loading_indicator
                yield self._status_icon
            yield self._code
