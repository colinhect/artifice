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
        margin: 0 0 1 0;
        padding: 0;
        padding-left: 1;
    }

    BaseBlock.in-context {
        padding-left: 0;
        border-left: solid $primary;
        margin-bottom: 0;
        padding-bottom: 1;
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

    BaseBlock .loading-indicator {
        width: 1;
        height: 1;
        content-align: center top;
        padding: 0;
    }

    BaseBlock > Horizontal > .status-indicator {
        height: 100%;
    }

    BaseBlock .status-indicator LoadingIndicator {
        height: 1;
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
    CodeInputBlock .code {
        padding: 0;
        border: none;
    }

    CodeInputBlock .prompt-indicator {
        width: 1;
        height: 1;
    }

    CodeInputBlock .code-unused {
        padding: 0;
        border: none;
    }
    """

    def __init__(self, code: str, language: str, show_loading: bool = True, in_context=False, command_number: int | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loading_indicator = LoadingIndicator(classes="status-indicator")
        if show_loading:
            self._loading_indicator.styles.display = "block"
        self._streaming = show_loading
        self._language = language
        self._command_number = command_number
        self._prompt_indicator = Static(self._get_prompt(), classes="prompt-indicator")
        # Status icon appears before the prompt (✔, ✖, or loading indicator)
        self._status_icon = Static(self._status_text(), classes="status-indicator")
        self._status_icon.add_class("status-unexecuted")
        self._original_code = code  # Store original code for re-execution
        # Always use syntax highlighting, even during streaming
        self._code = Static(highlight.highlight(code, language=language), classes="code")
        self._status_container = Horizontal(classes="status-indicator")
        if in_context:
            self.add_class("in-context")

    def _status_text(self) -> str:
        """Return the status icon text: the command number if set, else empty."""
        if self._command_number is not None:
            return str(self._command_number)
        return ""

    def _get_prompt(self) -> str:
        return "]" if self._language == "python" else "$"

    def compose(self) -> ComposeResult:
        with Horizontal():
            with self._status_container:
                yield self._loading_indicator
                yield self._status_icon
                #yield self._prompt_indicator
            yield self._code

    def update_status(self, result: ExecutionResult) -> None:
        self._loading_indicator.styles.display = "none"
        if result.status == ExecutionStatus.SUCCESS:
            self._status_icon.update("✔")
            self._status_icon.remove_class("status-error")
            self._status_icon.add_class("status-success")
        elif result.status == ExecutionStatus.ERROR:
            self._status_icon.update("✖")
            self._status_icon.remove_class("status-success")
            self._status_icon.add_class("status-error")

    async def show_loading(self) -> None:
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

        self._prompt_indicator.update(self._get_prompt())

        # Update syntax highlighting and markdown
        self._code.update(highlight.highlight(self._original_code, language=self._language))

class CodeOutputBlock(BaseBlock):
    DEFAULT_CSS = """
    CodeOutputBlock .code-output {
        background: $surface-darken-1;
        color: $foreground 66%;
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
        margin: 0;
    }

    CodeOutputBlock .markdown-output MarkdownTable {
        width: auto;
    }
    """

    def __init__(self, output="", render_markdown=False, in_context=False) -> None:
        super().__init__()
        self._status_indicator = Static(classes="status-indicator")
        self._output = Static(output, classes="code-output") if not render_markdown else None
        self._markdown = Markdown(output, classes="markdown-output") if render_markdown else None
        self._full = output
        self._render_markdown = render_markdown
        self._has_error = False
        self._dirty = False  # True when _full has changed but widget not yet updated
        self._contents = Horizontal()
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
        self._full += output
        self._dirty = True

    def flush(self) -> None:
        """Push accumulated text to the widget. Call after batching appends."""
        if not self._dirty:
            return
        self._dirty = False
        if self._markdown:
            self._markdown.update(self._full)
        elif self._output:
            self._output.update(self._full.rstrip('\n'))

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
    AgentInputBlock .prompt {
        /*background: $primary-background-darken-2;*/
        padding: 0;
        border: none;
    }
    """

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

class AgentOutputBlock(BaseBlock):
    DEFAULT_CSS = """
    AgentOutputBlock .agent-output {
        padding-left: 0;
        padding-right: 0;
        layout: stream;
    }

    AgentOutputBlock .loading-indicator {
        width: 2;
        height: 1;
    }

    AgentOutputBlock .agent-output MarkdownBlock:last-child {
        margin-bottom: 0;
    }

    AgentOutputBlock .agent-output MarkdownFence {
        margin: 0;
    }

    AgentOutputBlock .agent-output MarkdownTable {
        width: auto;
    }

    AgentOutputBlock .text-output {
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, output="", activity=True, render_markdown=True) -> None:
        super().__init__()
        self._loading_indicator = LoadingIndicator(classes="loading-indicator")
        self._status_indicator = Static("", classes="status-indicator")
        self._status_indicator.styles.display = "none"
        self._full = output
        self._render_markdown = render_markdown
        self._streaming = activity
        self._contents = Horizontal()
        self.add_class("in-context")

        # Always use Markdown if render_markdown is True (even during streaming)
        if render_markdown:
            self._output = None
            self._markdown = Markdown(output, classes="agent-output")
        else:
            self._output = Static(output, classes="text-output")
            self._markdown = None

        if not activity:
            self.mark_success()

    def compose(self) -> ComposeResult:
        with self._contents:
            yield self._loading_indicator
            yield self._status_indicator
            if self._markdown:
                yield self._markdown
            elif self._output is not None:
                yield self._output

    def append(self, response) -> None:
        self._full += response
        # Update the appropriate widget (Markdown or Static)
        if self._markdown:
            self._markdown.update(self._full)
        elif self._output:
            self._output.update(self._full)

    def finalize_streaming(self) -> None:
        """End streaming mode (widget already properly configured)."""
        self._streaming = False

    def mark_success(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.styles.display = "block"

    def mark_failed(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.styles.display = "block"

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
        Binding("up", "highlight_previous_code", "Previous Code", show=True),
        Binding("down", "highlight_next_code", "Next Code", show=True),
        Binding("ctrl+c", "activate_block", "Copy as Input", show=True),
        Binding("enter", "execute_block", "Execute", show=True),
        Binding("ctrl+o", "toggle_block_markdown", "Toggle Markdown", show=True),
        #Binding("ctrl+u", "pin_block", "Pin Block", show=True),
        Binding("insert", "cycle_language", "Mode", show=True),
        *[Binding(str(n), f"run_numbered('{n}')", f"Run #{n}", show=False) for n in range(1, 10)],
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
        self._next_command_number: int = 1

    def append_block(self, block: BaseBlock):
        self._blocks.append(block)
        self.mount(block)
        self.scroll_end(animate=False)
        return block

    def next_command_number(self) -> int:
        """Return the next command number and increment the counter."""
        n = self._next_command_number
        self._next_command_number += 1
        return n

    def auto_scroll(self) -> None:
        """Scroll to the bottom without animation."""
        self.scroll_end(animate=False)

    def clear_command_numbers(self) -> None:
        """Remove command numbers from all CodeInputBlocks and reset the counter."""
        for block in self._blocks:
            if isinstance(block, CodeInputBlock) and block._command_number is not None:
                if block._status_icon.content == str(block._command_number):
                    block._status_icon.update("")
                block._command_number = None
        self._next_command_number = 1

    def clear(self) -> None:
        """Clear all output."""
        for block in self._blocks:
            block.remove()
        self._blocks.clear()
        self._highlighted_index = None
        self._next_command_number = 1

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

    def action_highlight_previous_code(self) -> None:
        """Move highlight to the previous CodeInputBlock, skipping other block types."""
        if not self._blocks:
            return
        start = (self._highlighted_index - 1) if self._highlighted_index is not None else len(self._blocks) - 1
        for i in range(start, -1, -1):
            if isinstance(self._blocks[i], CodeInputBlock):
                self._highlighted_index = i
                self._update_highlight()
                return

    def action_highlight_next_code(self) -> None:
        """Move highlight to the next CodeInputBlock, skipping other block types."""
        if not self._blocks:
            return
        start = (self._highlighted_index + 1) if self._highlighted_index is not None else 0
        for i in range(start, len(self._blocks)):
            if isinstance(self._blocks[i], CodeInputBlock):
                self._highlighted_index = i
                self._update_highlight()
                return
        # No more code blocks forward — move focus to input
        self.app.query_one("#code-input", InputTextArea).focus()

    def action_run_numbered(self, n: str) -> None:
        """Execute the CodeInputBlock with the given command number."""
        block = self._find_numbered_block(int(n))
        if block is not None:
            self.post_message(self.BlockExecuteRequested(block))

    def _find_numbered_block(self, number: int) -> CodeInputBlock | None:
        """Find a CodeInputBlock with the given command number."""
        for block in self._blocks:
            if isinstance(block, CodeInputBlock) and block._command_number == number:
                return block
        return None

    def on_focus(self) -> None:
        """When focusing on TerminalOutput, highlight the last CodeInputBlock."""
        if self._blocks and self._highlighted_index is None:
            # Find the last CodeInputBlock
            for i in range(len(self._blocks) - 1, -1, -1):
                if isinstance(self._blocks[i], CodeInputBlock):
                    self._highlighted_index = i
                    self._update_highlight()
                    return
            # Fallback: highlight the last block if no CodeInputBlock found
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
                # Auto-scroll to make the highlighted block visible
                self.scroll_to_widget(block, animate=True)
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
                # Auto-scroll to make the highlighted block visible
                self.scroll_to_widget(block, animate=True)
            else:
                block.remove_class("highlighted")

    def _get_highlighted_block(self) -> WidgetOutputBlock | None:
        if self._highlighted_index is None or not self._pinned_blocks:
            return None
        if 0 <= self._highlighted_index < len(self._pinned_blocks):
            return self._pinned_blocks[self._highlighted_index]
        return None
