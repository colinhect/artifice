"""REPL output component for displaying execution results."""

from __future__ import annotations

import logging

from textual import highlight
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static, LoadingIndicator, Markdown, Label

from .execution import ExecutionResult, ExecutionStatus
from .agent import ToolCall
from .terminal_input import InputTextArea

logger = logging.getLogger(__name__)

class BaseBlock(Static):
    DEFAULT_CSS = """
    BaseBlock {
        margin: 0 0 1 0;
        padding: 0;
    }

    BaseBlock Horizontal {
        height: auto;
        align: left top;
    }

    BaseBlock Vertical {
        height: auto;
        width: 1fr;
    }

    BaseBlock .status-indicator {
        width: 2;
        height: 1;
        content-align: center top;
        padding: 0;
    }
    """

class CodeInputBlock(BaseBlock):
    DEFAULT_CSS = """
    CodeInputBlock .code {
        background: $surface-darken-1;
        padding: 0;
        border: none;
    }
    """

    def __init__(self, code: str, language: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loading_indicator = LoadingIndicator()
        self._status_indicator = Static(classes="status-indicator")
        self._code = Static(highlight.highlight(code, language=language), classes="code")

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="status-indicator"):
                yield self._loading_indicator
                yield self._status_indicator
            with Vertical():
                yield self._code

    def update_status(self, result: ExecutionResult) -> None:
        self._loading_indicator.styles.display = "none"
        if result.status == ExecutionStatus.SUCCESS:
            self._status_indicator.update("[green]✓[/]")
        elif result.status == ExecutionStatus.ERROR:
            self._status_indicator.update("[red]✗[/]")

class CodeOutputBlock(BaseBlock):
    DEFAULT_CSS = """
    CodeOutputBlock .code-output {
        background: $surface-darken-1;
        color: $text-muted;
        padding-left: 0;
        padding-right: 0;
    }
    """

    def __init__(self, output="") -> None:
        super().__init__()
        self._status_indicator = Static(classes="status-indicator")
        self._output = Static(output, classes="code-output")
        self._full = output

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self._status_indicator
            with Vertical():
                yield self._output

    def append_output(self, output) -> None:
        self._full += output
        self._output.update(self._full)

class AgentInputBlock(BaseBlock):
    DEFAULT_CSS = """
    AgentInputBlock .prompt {
        background: $surface-darken-1;
        padding: 0;
        border: none;
    }
    """

    def __init__(self, prompt: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status_indicator = Static("[cyan]?[/]", classes="status-indicator")
        self._prompt = Static(prompt, classes="prompt")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self._status_indicator
            with Vertical():
                yield self._prompt

class AgentOutputBlock(BaseBlock):
    DEFAULT_CSS = """
    AgentOutputBlock .code {
        background: $surface-darken-1;
        padding: 0;
        border: none;
    }

    AgentOutputBlock .agent-output {
        background: $surface-darken-1;
        padding-left: 0;
        padding-right: 0;
        layout: stream;
    }

    AgentOutputBlock .agent-output MarkdownBlock:last-child {
        margin-bottom: 0;
    }

    AgentOutputBlock .agent-output MarkdownFence {
        margin: 0 0 1 0;
    }
    """

    def __init__(self, output="") -> None:
        super().__init__()
        self._loading_indicator = LoadingIndicator()
        self._status_indicator = Static(classes="status-indicator")
        self._output = Markdown(output, classes="agent-output")

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="status-indicator"):
                yield self._loading_indicator
                yield self._status_indicator
            with Vertical():
                yield self._output

    def append(self, response) -> None:
        self._output.append(response)

    def mark_success(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.update("[green]✓[/]")

    def mark_failed(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.update("[red]✗[/]")


class OutputBlock(Static):
    """A single output block showing code and its result.

    Supports streaming updates for output and error lines.
    """

    class StreamOutput(Message):
        """Message for streaming output updates."""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class StreamError(Message):
        """Message for streaming error updates."""
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    DEFAULT_CSS = """
    OutputBlock {
        height: auto;
        margin: 0 0 1 0;
        padding: 0;
    }

    OutputBlock .code-container {
        background: $surface-darken-1;
        padding: 0;
        border: none;
    }

    OutputBlock .output-line {
        background: $surface-darken-1;
        color: $text-muted;
        padding-left: 0;
    }

    OutputBlock .error-line {
        background: $surface-darken-1;
        color: $error;
        padding-left: 0;
    }

    OutputBlock .agent-output {
        background: $surface-darken-1;
        padding-left: 0;
        padding-right: 0;
        layout: stream;
    }

    OutputBlock .agent-output MarkdownBlock:last-child {
        margin-bottom: 0;
    }

    OutputBlock .agent-output MarkdownFence {
        margin: 0 0 1 0;
    }

    OutputBlock .status-indicator {
        width: 2;
        height: auto;
        content-align: center top;
        padding: 0;
    }

    OutputBlock .status-success {
        color: $success;
    }

    OutputBlock .status-error {
        color: $error;
    }

    OutputBlock .status-running {
        width: 2;
        height: 1;
        content-align: center top;
    }

    OutputBlock .status-magic {
        color: $accent;
    }

    OutputBlock .status-question {
        color: $primary;
    }

    OutputBlock .status-empty {
        color: transparent;
    }

    OutputBlock Horizontal {
        height: auto;
        align: left top;
    }

    OutputBlock Vertical {
        height: auto;
        width: 1fr;
    }
    """

    ICON_SUCCESS = "✓"
    ICON_ERROR = "✗"
    ICON_PENDING = "○"
    ICON_MAGIC = " "
    ICON_QUESTION = "?"

    def __init__(self, result: ExecutionResult, is_agent: bool = False, show_code: bool = True, show_output: bool = True, block_type: str = "auto", render_markdown: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self._result = result
        self._is_agent = is_agent  # Track if this is an agent response
        self._show_code = show_code  # Whether to show the code section
        self._show_output = show_output  # Whether to show the output section
        self._block_type = block_type  # Type of block: "auto", "code_input", "code_output", "agent_prompt", "agent_response"
        self._output_container: Vertical | None = None
        self._error_lines: list[str] = []
        self._markdown_widget: Markdown | None = None  # For agent responses
        self._tool_calls: list[ToolCall] = []  # Track tool calls
        self._current_text_segment: list[str] = []  # Current text segment before next tool
        self._render_as_markdown: bool = render_markdown  # Whether to render output as markdown

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Status indicator based on block type
            icon, css_class = self._get_status_display()
            
            if icon is None:
                # No icon for this block type
                yield Static("", classes="status-indicator status-empty status-widget")
            elif self._result.status == ExecutionStatus.RUNNING and self._block_type != "agent_prompt":
                yield LoadingIndicator(classes="status-running status-widget")
            else:
                yield Static(icon, classes=f"status-indicator {css_class} status-widget")

            # Content container
            with Vertical(id="output-content") as container:
                self._output_container = container
                
                # Show code container if enabled and there's code to display
                if self._show_code and self._result.code:
                    if self._is_agent:
                        # No syntax highlighting for agent messages
                        yield Static(self._result.code, classes="code-container")
                    elif self._block_type in ("shell_input", "shell_output"):
                        # Shell syntax highlighting for shell commands
                        highlighted_code = highlight.highlight(
                            self._result.code,
                            language="bash"
                        )
                        yield Static(highlighted_code, classes="code-container")
                    else:
                        # Python syntax highlighting for code
                        highlighted_code = highlight.highlight(
                            self._result.code,
                            language="python"
                        )
                        yield Static(highlighted_code, classes="code-container")

                # Show output section if enabled
                if self._show_output:
                    # Respect the render_markdown setting
                    if self._render_as_markdown:
                        # Use Markdown for output
                        if self._result.output:
                            self._markdown_widget = Markdown(self._result.output, classes="agent-output")
                            yield self._markdown_widget
                    else:
                        # Use plain text for output
                        if self._result.output:
                            yield Static(self._result.output, classes="output-line")

                    # Show result value if present (for Python execution)
                    if not self._is_agent and self._result.result_value is not None:
                        yield Static(repr(self._result.result_value), classes="output-line")

                    # Show error if present (for both agent and Python)
                    if self._result.error:
                        yield Static(self._result.error.rstrip(), classes="error-line")

    def _get_status_display(self) -> tuple[str | None, str]:
        """Get the status icon and CSS class based on block type.

        Returns:
            Tuple of (icon, css_class). Icon can be None for no icon.
        """
        if self._block_type == "code_input":
            # Python code input: success/failure icon
            if self._result.status == ExecutionStatus.SUCCESS:
                return (self.ICON_SUCCESS, "status-success")
            elif self._result.status == ExecutionStatus.ERROR:
                return (self.ICON_ERROR, "status-error")
            return (self.ICON_PENDING, "status-pending")

        elif self._block_type == "code_output":
            # Python code output: no icon
            return (None, "status-empty")

        elif self._block_type == "shell_input":
            # Shell command input: success/failure icon
            if self._result.status == ExecutionStatus.SUCCESS:
                return (self.ICON_SUCCESS, "status-success")
            elif self._result.status == ExecutionStatus.ERROR:
                return (self.ICON_ERROR, "status-error")
            return (self.ICON_PENDING, "status-pending")

        elif self._block_type == "shell_output":
            # Shell command output: no icon
            return (None, "status-empty")

        elif self._block_type == "agent_prompt":
            # Agent prompt: blue question mark
            return (self.ICON_QUESTION, "status-question")

        elif self._block_type == "agent_response":
            # Agent response: magic icon
            if self._result.status == ExecutionStatus.RUNNING:
                return (self.ICON_MAGIC, "status-magic")
            return (self.ICON_MAGIC, "status-magic")

        # Default/auto behavior (backwards compatibility)
        if self._result.status == ExecutionStatus.SUCCESS:
            return (self.ICON_SUCCESS, "status-success")
        elif self._result.status == ExecutionStatus.ERROR:
            return (self.ICON_ERROR, "status-error")
        return (self.ICON_PENDING, "status-pending")
    
    def _get_status_icon(self) -> str:
        """Get the status icon based on execution status (legacy method)."""
        icon, _ = self._get_status_display()
        return icon if icon else ""

    def append_output(self, text: str) -> None:
        """Append output text to the block (for streaming).

        This can be called from any thread - it posts a message that will be
        handled on the main event loop with proper context.
        """
        if not text:
            return
        self.post_message(self.StreamOutput(text))

    async def on_output_block_stream_output(self, message: StreamOutput) -> None:
        """Handle streamed output update."""
        if not self._output_container:
            return

        self._current_text_segment.append(message.text)
        segment_text = "".join(self._current_text_segment)

        # Respect the render_markdown setting
        if self._render_as_markdown:
            # Use Markdown for output
            if self._markdown_widget:
                # Update existing markdown widget
                self._markdown_widget.update(segment_text)
            else:
                # Create new markdown widget for this text segment
                self._markdown_widget = Markdown(segment_text, classes="agent-output")
                await self._output_container.mount(self._markdown_widget)
        else:
            # Use plain text output
            try:
                output_widget = self._output_container.query_one(".output-line")
                output_widget.update(segment_text)
            except Exception as e:
                # No output widget yet, create one
                try:
                    await self._output_container.mount(Static(segment_text, classes="output-line"))
                except Exception as mount_error:
                    logger.warning(f"Failed to mount output widget: {mount_error}")

        # Scroll parent to bottom
        parent = self.parent
        if parent and hasattr(parent, 'scroll_end'):
            parent.scroll_end(animate=False)

    def append_error(self, text: str) -> None:
        """Append error text to the block (for streaming).

        This can be called from any thread - it posts a message that will be
        handled on the main event loop with proper context.
        """
        if not text:
            return
        self.post_message(self.StreamError(text))
    
    async def on_output_block_stream_error(self, message: StreamError) -> None:
        """Handle streamed error update."""
        if not self._output_container:
            return

        self._error_lines.append(message.text)
        full_error = "".join(self._error_lines)

        # Update or create the error widget
        try:
            error_widget = self._output_container.query_one(".error-line")
            error_widget.update(full_error)
        except Exception as e:
            # No error widget yet, create one
            try:
                self._output_container.mount(Static(full_error, classes="error-line"))
            except Exception as mount_error:
                logger.warning(f"Failed to mount error widget: {mount_error}")

        # Scroll parent to bottom
        parent = self.parent
        if parent and hasattr(parent, 'scroll_end'):
            parent.scroll_end(animate=False)

    def update_status(self, result: ExecutionResult) -> None:
        """Update the status indicator when execution completes."""
        self._result = result
        
        # Update status indicator - query by class instead of ID
        try:
            status_widget = self.query_one(".status-widget")
            status_widget.remove()
        except Exception as e:
            # Widget might already be removed during shutdown
            logger.debug(f"Failed to remove status widget (possibly during shutdown): {e}")
        
        # Get icon and CSS class based on block type
        icon, css_class = self._get_status_display()
        
        # Create new indicator (skip if no icon for this block type)
        if icon is not None:
            new_indicator = Static(icon, classes=f"status-indicator {css_class} status-widget")
        else:
            new_indicator = Static("", classes="status-indicator status-empty status-widget")
        
        # Mount before the content container
        try:
            content = self.query_one("#output-content")
            self.mount(new_indicator, before=content)
        except Exception as e:
            # Widget might be unmounted during shutdown
            logger.debug(f"Failed to mount status indicator (possibly during shutdown): {e}")
        
        # Add result value if present
        if result.result_value is not None and self._output_container:
            try:
                self._output_container.mount(Static(repr(result.result_value), classes="output-line"))
            except Exception as e:
                # Container might be unmounted during shutdown
                logger.debug(f"Failed to mount result value (possibly during shutdown): {e}")
        
        # Add error if present (for errors that weren't streamed)
        if result.error and self._output_container:
            # Check if we already have error displayed
            if not self._error_lines:
                try:
                    self._output_container.mount(Static(result.error.rstrip(), classes="error-line"))
                except Exception as e:
                    # Container might be unmounted during shutdown
                    logger.debug(f"Failed to mount error message (possibly during shutdown): {e}")
        
        # Scroll parent to bottom
        parent = self.parent
        if parent and hasattr(parent, 'scroll_end'):
            parent.scroll_end(animate=False)

    async def toggle_markdown(self) -> None:
        """Toggle between markdown and plain text rendering for this block's output."""
        if not self._output_container:
            return
        
        # Toggle the state
        self._render_as_markdown = not self._render_as_markdown
        
        # Get the current content to re-render
        content = "".join(self._current_text_segment)
        
        # If we don't have content in current segment but have output in result, use that
        if not content and self._result.output:
            content = self._result.output
        
        if not content:
            return  # Nothing to toggle
        
        # Remove existing markdown/output widgets
        try:
            if self._render_as_markdown:
                # Switch to markdown rendering
                # Remove any plain text output widgets
                for widget in self._output_container.query(".output-line"):
                    widget.remove()
                
                # Create or update markdown widget
                if self._markdown_widget and self._markdown_widget.parent:
                    await self._markdown_widget.remove()
                
                self._markdown_widget = Markdown(content, classes="agent-output")
                await self._output_container.mount(self._markdown_widget)
            else:
                # Switch to plain text rendering
                # Remove markdown widget
                if self._markdown_widget and self._markdown_widget.parent:
                    await self._markdown_widget.remove()
                    self._markdown_widget = None
                
                # Add plain text widget
                await self._output_container.mount(Static(content, classes="output-line"))
        except Exception as e:
            # Widget might be unmounted during operation
            logger.debug(f"Failed to toggle markdown rendering: {e}")


class TerminalOutput(VerticalScroll):
    """Scrollable container for REPL output blocks."""

    DEFAULT_CSS = """
    TerminalOutput {
        height: 1fr;
        border: none;
        padding: 0;
        margin: 0;
        align: center bottom;
    }
    """

    BINDINGS = [
        Binding("tab", "", "Move to Input", show=True),
        Binding("up", "highlight_previous", "Previous Block", show=True),
        Binding("down", "highlight_next", "Next Block", show=True),
        Binding("ctrl+o", "toggle_block_markdown", "Toggle Markdown On Block", show=True),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        #self._blocks: list[BaseOutputBlock] = []
        self._blocks = []
        self._highlighted_index: int | None = None

    def append_block(self, block: BaseOutputBlock):
        self._blocks.append(block)
        self.mount(block)
        self.scroll_end(animate=False)
        return block

    def add_result(self, result: ExecutionResult, is_agent: bool = False, show_code: bool = True, show_output: bool = True, block_type: str = "auto", render_markdown: bool = True) -> OutputBlock:
        """Add an execution result to the output."""
        block = OutputBlock(result, is_agent=is_agent, show_code=show_code, show_output=show_output, block_type=block_type, render_markdown=render_markdown)
        self._blocks.append(block)
        self.mount(block)
        self.scroll_end(animate=False)
        return block

    def clear(self) -> None:
        """Clear all output."""
        for block in self._blocks:
            block.remove()
        self._blocks.clear()
        self._highlighted_index = None

    def highlight_next(self) -> bool:
        """Move highlight to next block."""
        if not self._blocks:
            return
        original_index = self._highlighted_index
        if self._highlighted_index is None:
            self._highlighted_index = 0
        else:
            self._highlighted_index = min(self._highlighted_index + 1, len(self._blocks) - 1)
        self._update_highlight()
        return original_index != self._highlighted_index

    def highlight_previous(self) -> None:
        """Move highlight to previous block."""
        if not self._blocks:
            return
        if self._highlighted_index is None:
            self._highlighted_index = len(self._blocks) - 1
        else:
            self._highlighted_index = max(self._highlighted_index - 1, 0)
        self._update_highlight()

    async def action_toggle_block_markdown(self) -> None:
        """Toggle markdown rendering for the currently highlighted block."""
        block = self.get_highlighted_block()
        if block:
            await block.toggle_markdown()

    def action_highlight_previous(self) -> None:
        """Move highlight to previous output block."""
        self.highlight_previous()

    def action_highlight_next(self) -> None:
        """Move highlight to next output block."""
        if not self.highlight_next():
            self.app.query_one("#code-input", InputTextArea).focus()

    def on_focus(self) -> None:
        """When focusing on TerminalOutput, highlight the newest block."""
        if self._blocks:
            self._highlighted_index = len(self._blocks) - 1
            self._update_highlight()

    def on_blur(self) -> None:
        """When unfocusing, unhighlight the highlighted block."""
        self._highlighted_index = None
        self._update_highlight()

    def _update_highlight(self) -> None:
        """Update visual highlight on blocks."""
        for i, block in enumerate(self._blocks):
            if i == self._highlighted_index:
                block.add_class("highlighted")
            else:
                block.remove_class("highlighted")

    def get_highlighted_block(self) -> OutputBlock | None:
        """Get the currently highlighted block, if any."""
        if self._highlighted_index is None or not self._blocks:
            return None
        if 0 <= self._highlighted_index < len(self._blocks):
            return self._blocks[self._highlighted_index]
        return None

