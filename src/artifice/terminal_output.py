"""REPL output component for displaying execution results."""

from __future__ import annotations


from textual import highlight
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, LoadingIndicator, Markdown

from .execution import ExecutionResult, ExecutionStatus
from .terminal_input import InputTextArea
from .ansi_handler import ansi_to_textual

class BaseBlock(Static):
    DEFAULT_CSS = """
    BaseBlock {
        margin: 0 0 0 0;
        padding: 0;
        padding-left: 1;
    }

    BaseBlock.in-context {
        padding-left: 0;
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

    BaseBlock .status-success {
        color: $primary;
    }

    BaseBlock .status-error {
        color: $error;
    }

    BaseBlock .status-unexecuted {
    }

    BaseBlock .status-pending {
        color: $secondary;
    }
    """

class CodeInputBlock(BaseBlock):
    DEFAULT_CSS = """
    CodeInputBlock {
        margin: 0;
    }

    CodeInputBlock .code {
        background: $background-darken-3;
        padding: 0;
        border: none;
    }

    CodeInputBlock .code-unused {
        background: $surface-darken-1;
        padding: 0;
        border: none;
    }

    CodeInputBlock .markdown-code {
        background: $background-darken-3;
        padding: 0;
        border: none;
        layout: stream;
    }

    CodeInputBlock .markdown-code MarkdownFence {
        margin: 0;
    }
    """

    def __init__(self, code: str, language: str, show_loading: bool = True, use_markdown=False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loading_indicator = LoadingIndicator()
        self._show_loading = show_loading
        self._language = language
        # Always show the prompt based on language
        prompt = ">" if language == "python" else "$"
        self._status_indicator = Static(prompt, classes="status-indicator")
        self._status_indicator.add_class("status-unexecuted")
        self._original_code = code  # Store original code for re-execution
        use_markdown = False
        self._code = Static(highlight.highlight(code if not use_markdown else "", language=language), classes="code")
        if use_markdown:
            # Format code as markdown code fence

            markdown_code = f"```{language}\n{code}\n```"
            self._markdown_code = Markdown(markdown_code, classes="markdown-code")
            self.styles.margin = (0, 0, 0, 0)
            self._code.classes = "code-unused"
        else:
            self._markdown_code = None
            self.styles.margin = (1, 0, 0, 0)

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="status-indicator"):
                if self._show_loading:
                    yield self._loading_indicator
                yield self._status_indicator
            with Vertical():
                yield self._code
                if self._markdown_code:
                    yield self._markdown_code

    def update_status(self, result: ExecutionResult) -> None:
        self._loading_indicator.styles.display = "none"
        prompt = ">" if self._language == "python" else "$"
        if result.status == ExecutionStatus.SUCCESS:
            self._status_indicator.update(prompt)
            self._status_indicator.add_class("status-success")
        elif result.status == ExecutionStatus.ERROR:
            self._status_indicator.update(prompt)
            self._status_indicator.add_class("status-error")

    def show_loading(self) -> None:
        """Show the loading indicator (for re-execution)."""
        self._loading_indicator.styles.display = "block"
        # Clear any previous status styling
        self._status_indicator.remove_class("status-success")
        self._status_indicator.remove_class("status-error")
        self._status_indicator.update("")

    def update_code(self, code: str) -> None:
        """Update the displayed code (used during streaming)."""
        self._original_code = code
        if self._markdown_code:
            # Format code as markdown code fence and update
            markdown_code = f"```{self._language}\n{code}\n```"
            self._markdown_code.update(markdown_code)
        else:
            self._code.update(highlight.highlight(code, language=self._language))

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

        # Update the prompt
        prompt = ">" if self._language == "python" else "$"
        self._status_indicator.update(prompt)

        # Update syntax highlighting and markdown
        if self._markdown_code:
            markdown_code = f"```{self._language}\n{self._original_code}\n```"
            self._markdown_code.update(markdown_code)
        else:
            self._code.update(highlight.highlight(self._original_code, language=self._language))

class CodeOutputBlock(BaseBlock):
    DEFAULT_CSS = """
    CodeOutputBlock {
        margin: 0 0 0 0;
    }

    CodeOutputBlock .code-output {
        background: $surface-darken-1;
        /*background: $surface-darken-1;*/
        /*color: $text-muted;*/
        padding-left: 0;
        padding-right: 0;
    }

    CodeOutputBlock .error-output {
        background: $surface-darken-1;
        color: $error;
        padding-left: 0;
        padding-right: 0;
    }

    CodeOutputBlock .markdown-output {
        background: $surface-darken-1;
        padding-left: 0;
        padding-right: 0;
        layout: stream;
    }

    CodeOutputBlock .markdown-output MarkdownBlock:last-child {
        margin-bottom: 0;
    }

    CodeOutputBlock .markdown-output MarkdownFence {
        margin: 0 0 0 0;
    }

    CodeOutputBlock .markdown-output MarkdownTable {
        width: auto;
    }
    """

    def __init__(self, output="", render_markdown=False) -> None:
        super().__init__()
        self._status_indicator = Static(classes="status-indicator")
        self._output = Static(output, classes="code-output") if not render_markdown else None
        self._markdown = Markdown(output, classes="markdown-output") if render_markdown else None
        self._full = output
        self._render_markdown= render_markdown
        self._has_error = False
        self._contents = Horizontal()

    def compose(self) -> ComposeResult:
        with self._contents:
            yield self._status_indicator
            if self._markdown:
                yield self._markdown
            elif self._output is not None:
                yield self._output

    def append_output(self, output) -> None:
        self._full += output
        if self._markdown:
            self._markdown.append(output)
        elif self._output:
            # Convert ANSI escape codes to Textual markup
            textual_output = ansi_to_textual(self._full.rstrip('\n'))
            self._output.update(textual_output)

    def append_error(self, output) -> None:
        self.append_output(output)
        self.mark_failed()

    def mark_failed(self) -> None:
        if not self._has_error:
            self._has_error = True
            if self._output:
                self._output.remove_class("code-output")
                self._output.add_class("error-output")

    def toggle_markdown(self) -> None:
        self._render_markdown = not self._render_markdown
        if self._render_markdown:
            if self._output:
                self._output.remove()
                self._output = None
            self._markdown = Markdown(self._full, classes="markdown-output")
            self._contents.mount(self._markdown)
        else:
            if self._markdown:
                self._markdown.remove()
                self._markdown = None
            # Convert ANSI escape codes to Textual markup
            textual_output = ansi_to_textual(self._full.rstrip('\n'))
            self._output = Static(textual_output, classes="code-output")
            self._contents.mount(self._output)

class WidgetOutputBlock(BaseBlock):
    """Block that displays an arbitrary Textual widget."""

    DEFAULT_CSS = """
    WidgetOutputBlock .widget-container {
        height: auto;
        width: 1fr;
    }
    """

    def __init__(self, widget: Widget, **kwargs):
        super().__init__(**kwargs)
        self._widget = widget

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("", classes="status-indicator")
            with Vertical(classes="widget-container"):
                yield self._widget

class AgentInputBlock(BaseBlock):
    DEFAULT_CSS = """
    AgentInputBlock {
        margin: 1 0 0 0;
    }

    AgentInputBlock .prompt {
        background: $primary-background-darken-2;
        padding: 0;
        border: none;
    }
    """

    def __init__(self, prompt: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status_indicator = Static("?", classes="status-indicator status-pending")
        self._prompt = Static(prompt, classes="prompt")
        self._original_prompt = prompt  # Store original prompt for re-use

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

class AgentOutputBlock(BaseBlock):
    DEFAULT_CSS = """
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
        margin: 0 0 0 0;
    }

    AgentOutputBlock .agent-output MarkdownTable {
        width: auto;
    }

    AgentOutputBlock .text-output {
        background: $surface-darken-1;
        padding-left: 0;
        padding-right: 0;
    }
    """

    def __init__(self, output="", activity=True, render_markdown=True) -> None:
        super().__init__()
        self._loading_indicator = LoadingIndicator()
        self._status_indicator = Static(classes="status-indicator")
        self._output = Static(output, classes="text-output") if not render_markdown else None
        self._markdown = Markdown(output, classes="agent-output") if render_markdown else None
        self._full = output
        self._render_markdown = render_markdown
        self._contents = Horizontal()
        self.add_class("in-context")
        if not activity:
            self.mark_success()

    def compose(self) -> ComposeResult:
        with self._contents:
            with Vertical(classes="status-indicator"):
                yield self._loading_indicator
                yield self._status_indicator
            if self._markdown:
                yield self._markdown
            elif self._output is not None:
                yield self._output

    def append(self, response) -> None:
        self._full += response
        if self._markdown:
            self._markdown.append(response)
        elif self._output:
            self._output.update(self._full)

    def mark_success(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.update("✨")

    def mark_failed(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.update("✗")
        self._status_indicator.add_class("status-error")

    def toggle_markdown(self) -> None:
        self._render_markdown = not self._render_markdown
        if self._render_markdown:
            if self._output:
                self._output.remove()
                self._output = None
            self._markdown = Markdown(self._full, classes="agent-output")
            self._contents.mount(self._markdown)
        else:
            if self._markdown:
                self._markdown.remove()
                self._markdown = None
            self._output = Static(self._full, classes="text-output")
            self._contents.mount(self._output)

class TerminalOutput(VerticalScroll):
    """Container for REPL output blocks."""

    DEFAULT_CSS = """
    TerminalOutput {
        border: none;
        padding: 0;
        margin: 0;
    }
    """

    class PinRequested(Message):
        """Posted when the user wants to pin the highlighted widget block."""
        def __init__(self, block: WidgetOutputBlock) -> None:
            super().__init__()
            self.block = block

    class BlockActivated(Message):
        """Posted when the user wants to copy a block to the input."""
        def __init__(self, code: str, mode: str) -> None:
            super().__init__()
            self.code = code
            self.mode = mode

    class BlockExecuteRequested(Message):
        """Posted when the user wants to execute a code block."""
        def __init__(self, block: CodeInputBlock) -> None:
            super().__init__()
            self.block = block

    BINDINGS = [
        Binding("end", "", "Input Prompt", show=True),
        #Binding("up", "highlight_previous", "Previous Block", show=True),
        #Binding("down", "highlight_next", "Next Block", show=True),
        Binding("ctrl+s", "activate_block", "Copy to Input", show=True),
        Binding("enter", "execute_block", "Execute Block", show=True),
        Binding("ctrl+o", "toggle_block_markdown", "Toggle Markdown On Block", show=True),
        Binding("ctrl+u", "pin_block", "Pin Block", show=True),
        Binding("insert", "cycle_language", "Cycle Language", show=True),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._blocks = []
        self._highlighted_index: int | None = None

    def append_block(self, block: BaseBlock):
        self._blocks.append(block)
        self.mount(block)
        self.scroll_end(animate=False)
        return block

    def auto_scroll(self) -> None:
        """Scroll to end if already at or near the bottom."""
        # Check if we're already near the bottom (within a few lines)
        # If so, scroll to the new end. Otherwise, let the user read where they are.
        max_scroll_y = self.max_scroll_y
        current_y = self.scroll_y

        # If we're within 3 lines of the bottom, auto-scroll
        if max_scroll_y - current_y <= 3:
            self.scroll_end(animate=False)

    def clear(self) -> None:
        """Clear all output."""
        for block in self._blocks:
            block.remove()
        self._blocks.clear()
        self._highlighted_index = None

    def highlight_next(self) -> bool:
        """Move highlight to next block."""
        if not self._blocks:
            return False
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

    def action_activate_block(self) -> None:
        """Copy the highlighted block's code to the input with the correct mode."""
        block = self.get_highlighted_block()
        if block is None:
            return

        # Extract code and mode from the block
        if isinstance(block, CodeInputBlock):
            code = block.get_code()
            mode = block.get_mode()
            self.post_message(self.BlockActivated(code, mode))
        elif isinstance(block, AgentInputBlock):
            code = block.get_prompt()
            mode = block.get_mode()
            self.post_message(self.BlockActivated(code, mode))

    def action_execute_block(self) -> None:
        """Execute the highlighted code block."""
        block = self.get_highlighted_block()
        if block is None:
            return

        # Only execute CodeInputBlock
        if isinstance(block, CodeInputBlock):
            self.post_message(self.BlockExecuteRequested(block))

    async def action_toggle_block_markdown(self) -> None:
        """Toggle markdown rendering for the currently highlighted block."""
        block = self.get_highlighted_block()
        if block and isinstance(block, (CodeOutputBlock, AgentOutputBlock)):
            block.toggle_markdown()

    def action_cycle_language(self) -> None:
        """Cycle the language of the highlighted CodeInputBlock."""
        block = self.get_highlighted_block()
        if block and isinstance(block, CodeInputBlock):
            block.cycle_language()

    def action_pin_block(self) -> None:
        """Pin the currently highlighted widget block."""
        block = self.get_highlighted_block()
        if not isinstance(block, WidgetOutputBlock):
            return
        self._blocks.remove(block)
        # Adjust highlighted index after removal
        if not self._blocks:
            self._highlighted_index = None
        elif self._highlighted_index is not None and self._highlighted_index >= len(self._blocks):
            self._highlighted_index = len(self._blocks) - 1
        self._update_highlight()
        self.post_message(self.PinRequested(block))

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

    def get_highlighted_block(self) -> BaseBlock | None:
        """Get the currently highlighted block, if any."""
        if self._highlighted_index is None or not self._blocks:
            return None
        if 0 <= self._highlighted_index < len(self._blocks):
            return self._blocks[self._highlighted_index]
        return None


class PinnedOutput(Vertical):
    """Container for pinned output blocks, displayed below the input."""

    DEFAULT_CSS = """
    PinnedOutput {
        height: auto;
        max-height: 30vh;
        overflow-y: auto;
        display: none;
    }

    PinnedOutput.has-pins {
        display: block;
        border-top: solid $accent;
        padding-top: 1;
    }
    """

    class UnpinRequested(Message):
        """Posted when the user wants to unpin a block."""
        def __init__(self, block: WidgetOutputBlock) -> None:
            super().__init__()
            self.block = block

    BINDINGS = [
        Binding("tab", "", "Move to Next", show=False),
        Binding("up", "highlight_previous", "Previous Pin", show=True),
        Binding("down", "highlight_next", "Next Pin", show=True),
        Binding("ctrl+u", "unpin_block", "Unpin Block", show=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pinned_blocks: list[WidgetOutputBlock] = []
        self._highlighted_index: int | None = None

    can_focus = True

    async def add_pinned_block(self, block: WidgetOutputBlock) -> None:
        self._pinned_blocks.append(block)
        await self.mount(block)
        await block.recompose()
        self.add_class("has-pins")

    async def remove_pinned_block(self, block: WidgetOutputBlock) -> None:
        if block in self._pinned_blocks:
            idx = self._pinned_blocks.index(block)
            self._pinned_blocks.remove(block)
            await block.remove()
            # Adjust highlighted index
            if not self._pinned_blocks:
                self._highlighted_index = None
                self.remove_class("has-pins")
            elif self._highlighted_index is not None:
                if idx <= self._highlighted_index:
                    self._highlighted_index = max(0, self._highlighted_index - 1)
                if self._highlighted_index >= len(self._pinned_blocks):
                    self._highlighted_index = len(self._pinned_blocks) - 1
            self._update_highlight()

    def action_highlight_previous(self) -> None:
        if not self._pinned_blocks:
            return
        if self._highlighted_index is None:
            self._highlighted_index = len(self._pinned_blocks) - 1
        else:
            self._highlighted_index = max(self._highlighted_index - 1, 0)
        self._update_highlight()

    def action_highlight_next(self) -> None:
        if not self._pinned_blocks:
            return
        if self._highlighted_index is None:
            self._highlighted_index = 0
        else:
            self._highlighted_index = min(self._highlighted_index + 1, len(self._pinned_blocks) - 1)
        self._update_highlight()

    def action_unpin_block(self) -> None:
        block = self._get_highlighted_block()
        if block:
            self.post_message(self.UnpinRequested(block))

    def on_focus(self) -> None:
        if self._pinned_blocks:
            self._highlighted_index = 0
            self._update_highlight()

    def on_blur(self) -> None:
        self._highlighted_index = None
        self._update_highlight()

    def _update_highlight(self) -> None:
        for i, block in enumerate(self._pinned_blocks):
            if i == self._highlighted_index:
                block.add_class("highlighted")
            else:
                block.remove_class("highlighted")

    def _get_highlighted_block(self) -> WidgetOutputBlock | None:
        if self._highlighted_index is None or not self._pinned_blocks:
            return None
        if 0 <= self._highlighted_index < len(self._pinned_blocks):
            return self._pinned_blocks[self._highlighted_index]
        return None
