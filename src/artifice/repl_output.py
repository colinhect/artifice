"""REPL output component for displaying execution results."""

from __future__ import annotations

from textual import highlight
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static, LoadingIndicator, Markdown

from .executor import ExecutionResult, ExecutionStatus
from .agent import ToolCall


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
        color: $text-muted;
        padding-left: 0;
    }

    OutputBlock .error-line {
        color: $error;
        padding-left: 0;
    }

    OutputBlock .agent-output {
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

    OutputBlock .tool-call {
        background: $surface;
        padding: 1;
        margin: 1 0 1 0;
        border-left: thick $accent;
    }

    OutputBlock .tool-call-name {
        color: $accent;
        text-style: bold;
    }

    OutputBlock .tool-call-input {
        color: $text-muted;
        padding-left: 2;
    }

    OutputBlock .tool-call-output {
        color: $text;
        padding-left: 1;
        padding-top: 1;
    }

    OutputBlock .tool-call-error {
        color: $error;
        padding-left: 1;
        padding-top: 1;
    }
    
    OutputBlock .tool-call .code-container {
        background: $surface-darken-1;
        padding: 0;
        border: none;
        margin: 0;
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
        self._output_lines: list[str] = []
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
            except Exception:
                # No output widget yet, create one
                await self._output_container.mount(Static(segment_text, classes="output-line"))

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
    
    def add_tool_call(self, tool_call: ToolCall) -> None:
        """Add a tool call to the output display.
        
        Args:
            tool_call: The tool call to display.
        """
        if not self._output_container:
            return
        
        self._tool_calls.append(tool_call)
        
        # Finalize current text segment - subsequent text will go to a new widget
        self._markdown_widget = None
        self._current_text_segment = []
        
        # Create tool call display - build widgets list first, then mount together
        try:
            widgets_to_add = []
            
            # For execute_python tool, show the code with syntax highlighting
            if tool_call.name == "execute_python" and "code" in tool_call.input:
                code = tool_call.input["code"]
                highlighted_code = highlight.highlight(code, language="python")
                widgets_to_add.append(Static(highlighted_code, classes="code-container"))
            else:
                # For other tools, show name and input
                widgets_to_add.append(Static(f"🔧 {tool_call.name}", classes="tool-call-name"))
                
                # Tool input (pretty printed)
                import json
                try:
                    input_str = json.dumps(tool_call.input, indent=2)
                except Exception:
                    input_str = str(tool_call.input)
                widgets_to_add.append(Static(f"Input:\n{input_str}", classes="tool-call-input"))
            
            # Tool output/error (if available)
            if tool_call.output:
                widgets_to_add.append(Static(f"{tool_call.output}", classes="tool-call-output"))
            elif tool_call.error:
                widgets_to_add.append(Static(f"Error:\n{tool_call.error}", classes="tool-call-error"))
            
            # Create container and mount all widgets
            tool_widget = Vertical(*widgets_to_add, classes="tool-call")
            self._output_container.mount(tool_widget)
            
            # Scroll parent to bottom
            parent = self.parent
            if parent and hasattr(parent, 'scroll_end'):
                parent.scroll_end(animate=False)
        except Exception as e:
            # Debug: log the error
            import sys
            print(f"Error adding tool call: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            pass  # Container might be unmounted during shutdown

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
        except Exception:
            # No error widget yet, create one
            self._output_container.mount(Static(full_error, classes="error-line"))

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
        except Exception:
            # Widget might already be removed during shutdown
            pass
        
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
        except Exception:
            # Widget might be unmounted during shutdown
            pass
        
        # Add result value if present
        if result.result_value is not None and self._output_container:
            try:
                self._output_container.mount(Static(repr(result.result_value), classes="output-line"))
            except Exception:
                # Container might be unmounted during shutdown
                pass
        
        # Add error if present (for errors that weren't streamed)
        if result.error and self._output_container:
            # Check if we already have error displayed
            if not self._error_lines:
                try:
                    self._output_container.mount(Static(result.error.rstrip(), classes="error-line"))
                except Exception:
                    # Container might be unmounted during shutdown
                    pass
        
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
        except Exception:
            # Widget might be unmounted during operation
            pass


class ReplOutput(VerticalScroll):
    """Scrollable container for REPL output blocks."""

    DEFAULT_CSS = """
    ReplOutput {
        height: 1fr;
        border: none;
        padding: 0;
        margin: 0;
        align: center bottom;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._blocks: list[OutputBlock] = []
        self._highlighted_index: int | None = None

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

    def highlight_next(self) -> None:
        """Move highlight to next block."""
        if not self._blocks:
            return
        if self._highlighted_index is None:
            self._highlighted_index = 0
        else:
            self._highlighted_index = min(self._highlighted_index + 1, len(self._blocks) - 1)
        self._update_highlight()

    def highlight_previous(self) -> None:
        """Move highlight to previous block."""
        if not self._blocks:
            return
        if self._highlighted_index is None:
            self._highlighted_index = len(self._blocks) - 1
        else:
            self._highlighted_index = max(self._highlighted_index - 1, 0)
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
