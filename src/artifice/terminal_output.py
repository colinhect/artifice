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
        margin: 0 0 1 0;
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
        self._contents = None

    def compose(self) -> ComposeResult:
        with Horizontal() as contents:
            self._contents = contents
            yield self._status_indicator
            if self._render_markdown:
                yield self._markdown
            else:
                yield self._output

    def append_output(self, output) -> None:
        self._full += output
        if self._render_markdown:
            self._markdown.append(output)
        else:
            self._output.update(self._full.rstrip('\n'))

    def append_error(self, output) -> None:
        self.append_output(output)
        self.mark_failed()

    def mark_failed(self) -> None:
        if not self._has_error:
            self._has_error = True
            self._output.remove_class("code-output")
            self._output.add_class("error-output")

    def toggle_markdown(self) -> None:
        self._render_markdown = not self._render_markdown
        if self._render_markdown:
            self._output.remove()
            self._output = None
            self._markdown = Markdown(self._full, classes="markdown-output")
            self._contents.mount(self._markdown)
        else:
            self._markdown.remove()
            self._markdown = None
            self._output = Static(self._full, classes="code-output")
            self._contents.mount(self._output)

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
            yield self._output

    def append(self, response) -> None:
        self._output.append(response)

    def mark_success(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.update("✨")

    def mark_failed(self) -> None:
        self._loading_indicator.styles.display = "none"
        self._status_indicator.update("[red]✗[/]")

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
        self._blocks = []
        self._highlighted_index: int | None = None

    def append_block(self, block: BaseOutputBlock):
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
            block.toggle_markdown()

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

