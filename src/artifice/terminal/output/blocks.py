"""Output block widgets for the terminal display."""

from __future__ import annotations

import time

from textual import highlight
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static, LoadingIndicator, Markdown

from ...execution import ExecutionResult, ExecutionStatus


class BaseBlock(Static):
    pass


class CodeInputBlock(BaseBlock):
    def __init__(
        self,
        code: str,
        language: str,
        show_loading: bool = True,
        in_context=False,
        command_number: int | None = None,
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
        self._command_number = command_number
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
        """Return the status icon text: the command number if set, else empty."""
        if self._command_number is not None:
            return str(self._command_number)
        return ""

    def compose(self) -> ComposeResult:
        with Horizontal():
            with self._status_container:
                yield self._loading_indicator
                yield self._status_icon
            yield self._code

    def update_status(self, result: ExecutionResult) -> None:
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

    def cycle_language(self) -> None:
        """Cycle to the next language (python -> bash -> python)."""
        if self._language == "python":
            self._language = "bash"
        else:
            self._language = "python"

        # Update syntax highlighting
        self._code.update(
            highlight.highlight(self._original_code.strip(), language=self._language)
        )


class BufferedOutputBlock(BaseBlock):
    """Base class for output blocks with buffered text and markdown toggle.

    Subclasses set _STATIC_CSS_CLASS and _MARKDOWN_CSS_CLASS to control
    which CSS classes are applied to the Static/Markdown child widgets.
    """

    _STATIC_CSS_CLASS: str = ""
    _MARKDOWN_CSS_CLASS: str = ""

    def __init__(self, output="", render_markdown=False) -> None:
        super().__init__()
        self._output_str: str = output
        self._render_markdown = render_markdown
        self._dirty = False
        self._contents = Horizontal()

        if render_markdown:
            self._output = None
            self._markdown = Markdown(output, classes=self._MARKDOWN_CSS_CLASS)
        else:
            self._output = Static(output, markup=False, classes=self._STATIC_CSS_CLASS)
            self._markdown = None

    def flush(self) -> None:
        """Push accumulated text to the widget. Call after batching appends."""
        if not self._dirty:
            return
        self._dirty = False
        if self._markdown:
            self._markdown.update(self._output_str.strip())
        elif self._output:
            self._output.update(self._output_str.strip())

    def toggle_markdown(self) -> None:
        self._render_markdown = not self._render_markdown
        if self._render_markdown:
            if self._output:
                self._output.remove()
                self._output = None
            self._markdown = Markdown(
                self._output_str, classes=self._MARKDOWN_CSS_CLASS
            )
            self._contents.mount(self._markdown)
        else:
            if self._markdown:
                self._markdown.remove()
                self._markdown = None
            self._output = Static(
                self._output_str, markup=False, classes=self._STATIC_CSS_CLASS
            )
            self._contents.mount(self._output)


class CodeOutputBlock(BufferedOutputBlock):
    _STATIC_CSS_CLASS = "code-output"
    _MARKDOWN_CSS_CLASS = "markdown-output"

    def __init__(self, output="", render_markdown=False, in_context=False) -> None:
        super().__init__(output=output, render_markdown=render_markdown)
        self._status_indicator = Static(classes="status-indicator")
        self._has_error = False
        if in_context:
            self.add_class("in-context")

    def compose(self) -> ComposeResult:
        with self._contents:
            yield self._status_indicator
            if self._markdown:
                yield self._markdown
            elif self._output is not None:
                yield self._output

    def append_output(self, output) -> None:
        self._output_str += output
        self._dirty = True

    def append_error(self, output) -> None:
        self.append_output(output)
        self.mark_failed()

    def mark_failed(self) -> None:
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


class AssistantInputBlock(BaseBlock):
    def __init__(self, prompt: str, in_context=False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status_indicator = Static(">", classes="status-indicator status-pending")
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


class AssistantOutputBlock(BufferedOutputBlock):
    _STATIC_CSS_CLASS = "text-output"
    _MARKDOWN_CSS_CLASS = "assistant-output"

    _FLUSH_INTERVAL = (
        0.1  # Minimum seconds between full Markdown re-renders during streaming
    )

    def __init__(self, output="", activity=True, render_markdown=True) -> None:
        super().__init__(output=output, render_markdown=render_markdown)
        self._status_indicator = Static("", classes="status-indicator")
        self._streaming = activity
        self._last_full_update_time: float = 0.0
        self._chunk: str = ""
        self.add_class("in-context")

        if not activity:
            self.mark_success()

    def compose(self) -> ComposeResult:
        with self._contents:
            yield self._status_indicator
            if self._markdown:
                yield self._markdown
            elif self._output is not None:
                yield self._output

    def append(self, response) -> None:
        self._output_str += response
        self._chunk += response
        self._dirty = True

    def flush(self) -> None:
        """Push accumulated text to the widget.

        Uses markdown.append() for incremental updates most of the time,
        but performs a full update() every _FLUSH_INTERVAL to re-render everything.
        """
        if not self._dirty:
            return

        self._dirty = False

        # For non-markdown output, always do a simple update
        if self._output:
            self._output.update(self._output_str.strip())
            return

        # For markdown output during streaming, decide between append and full update
        if self._markdown and self._streaming:
            now = time.monotonic()
            elapsed = now - self._last_full_update_time

            # Do a full update every _FLUSH_INTERVAL
            if elapsed >= self._FLUSH_INTERVAL:
                self._markdown.update(self._output_str.lstrip())
                self._last_full_update_time = now
        elif self._markdown:
            # Not streaming, just do a full update
            self._markdown.update(self._output_str.strip())

        self._chunk = ""

    def finalize_streaming(self) -> None:
        """End streaming mode -- force final flush to ensure content is current."""
        self._streaming = False
        if self._dirty:
            self.flush()
        # Ensure final content is fully rendered
        if self._markdown:
            self._markdown.update(self._output_str.strip())

    def mark_success(self) -> None:
        self._status_indicator.styles.display = "block"

    def mark_failed(self) -> None:
        self._status_indicator.styles.display = "block"


class ThinkingOutputBlock(AssistantOutputBlock):
    """Block for AI thinking content. Styled distinctly via CSS."""

    def __init__(self, output="", activity=True) -> None:
        super().__init__(output=output, activity=activity, render_markdown=False)
