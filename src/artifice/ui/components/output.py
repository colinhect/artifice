"""Container widgets for terminal output display."""

from __future__ import annotations

import pyperclip

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message

from artifice.ui.components.input import InputTextArea
from artifice.ui.components.blocks.blocks import (
    AgentInputBlock,
    BaseBlock,
    CodeInputBlock,
    CodeOutputBlock,
    ToolCallBlock,
)


class HighlightableContainerMixin:
    """Mixin for containers that support block highlighting and navigation."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._blocks: list = []
        self._highlighted_index: int | None = None

    def highlight_next(self) -> bool:
        """Move highlight to next block. Returns True if the index changed."""
        if not self._blocks:
            return False
        previous_index = self._highlighted_index
        if self._highlighted_index is None:
            self._highlighted_index = 0
        else:
            self._highlighted_index = min(
                self._highlighted_index + 1, len(self._blocks) - 1
            )
        self._update_highlight(previous_index)
        return previous_index != self._highlighted_index

    def highlight_previous(self) -> None:
        """Move highlight to previous block."""
        if not self._blocks:
            return
        previous_index = self._highlighted_index
        if self._highlighted_index is None:
            self._highlighted_index = len(self._blocks) - 1
        else:
            self._highlighted_index = max(self._highlighted_index - 1, 0)
        self._update_highlight(previous_index)

    def _update_highlight(self, previous_index: int | None = None) -> None:
        """Update visual highlight on blocks. Only touches the old and new block (O(1))."""
        # Remove highlight from previous block
        if previous_index is not None and 0 <= previous_index < len(self._blocks):
            self._blocks[previous_index].remove_class("highlighted")
        # Add highlight to new block
        if self._highlighted_index is not None and 0 <= self._highlighted_index < len(
            self._blocks
        ):
            block = self._blocks[self._highlighted_index]
            block.add_class("highlighted")
            self.scroll_to_widget(block, animate=True)  # type: ignore

    def get_highlighted_block(self):
        """Get the currently highlighted block, if any."""
        if self._highlighted_index is None or not self._blocks:
            return None
        if 0 <= self._highlighted_index < len(self._blocks):
            return self._blocks[self._highlighted_index]
        return None

    def on_blur(self) -> None:
        """When unfocusing, unhighlight the highlighted block."""
        previous_index = self._highlighted_index
        self._highlighted_index = None
        self._update_highlight(previous_index)


class TerminalOutput(HighlightableContainerMixin, VerticalScroll):
    """Container for REPL output blocks."""

    class BlockActivated(Message):
        """Posted when the user wants to copy a block to the input."""

        def __init__(self, code: str, mode: str) -> None:
            super().__init__()
            self.code = code
            self.mode = mode

    class BlockExecuteRequested(Message):
        """Posted when the user wants to execute a code block."""

        def __init__(self, block: CodeInputBlock | ToolCallBlock) -> None:
            super().__init__()
            self.block = block

    BINDINGS = [
        Binding("end", "", "Input Prompt", show=True),
        Binding("up", "highlight_previous_code", "Previous Code", show=True),
        Binding("down", "highlight_next_code", "Next Code", show=True),
        Binding("ctrl+c", "activate_block", "Copy as Input", show=True),
        Binding("enter", "execute_block", "Execute", show=True),
        Binding("ctrl+o", "toggle_block_markdown", "Toggle Markdown", show=True),
    ]

    def append_block(self, block: BaseBlock, scroll: bool = True):
        self._blocks.append(block)
        self.mount(block)
        if scroll:
            self.scroll_end(animate=False)
        return block

    def remove_block(self, block: BaseBlock) -> None:
        """Remove a block from the blocks list and the DOM."""
        if block in self._blocks:
            self._blocks.remove(block)
        block.remove()

    def index_of(self, block: BaseBlock) -> int | None:
        """Return the index of a block, or None if not found."""
        try:
            return self._blocks.index(block)
        except ValueError:
            return None

    def clear(self) -> None:
        """Clear all output."""
        for block in self._blocks:
            block.remove()
        self._blocks.clear()
        self._highlighted_index = None

    def action_activate_block(self) -> None:
        """Copy the highlighted block's code to the input with the correct mode."""
        block = self.get_highlighted_block()
        if block is None:
            return

        # Extract code and mode from the block
        if isinstance(block, CodeInputBlock):
            code = block.get_code()
            pyperclip.copy(code)
            mode = block.get_mode()
            self.post_message(self.BlockActivated(code, mode))
        elif isinstance(block, AgentInputBlock):
            code = block.get_prompt()
            pyperclip.copy(code)
            mode = block.get_mode()
            self.post_message(self.BlockActivated(code, mode))

    def action_execute_block(self) -> None:
        """Execute the highlighted code block."""
        block = self.get_highlighted_block()
        if block is None:
            return

        if isinstance(block, (CodeInputBlock, ToolCallBlock)):
            self.post_message(self.BlockExecuteRequested(block))

    async def action_toggle_block_markdown(self) -> None:
        """Toggle markdown rendering for the currently highlighted block."""
        block = self.get_highlighted_block()
        if block and isinstance(block, CodeOutputBlock):
            block.toggle_markdown()

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
        previous_index = self._highlighted_index
        start = (
            (self._highlighted_index - 1)
            if self._highlighted_index is not None
            else len(self._blocks) - 1
        )
        for i in range(start, -1, -1):
            if isinstance(self._blocks[i], CodeInputBlock):
                self._highlighted_index = i
                self._update_highlight(previous_index)
                return

    def action_highlight_next_code(self) -> None:
        """Move highlight to the next CodeInputBlock, skipping other block types."""
        if not self._blocks:
            return
        previous_index = self._highlighted_index
        start = (
            (self._highlighted_index + 1) if self._highlighted_index is not None else 0
        )
        for i in range(start, len(self._blocks)):
            if isinstance(self._blocks[i], CodeInputBlock):
                self._highlighted_index = i
                self._update_highlight(previous_index)
                return
        # No more code blocks forward -- move focus to input
        self.app.query_one("#code-input", InputTextArea).focus()

    def on_focus(self) -> None:
        """When focusing on TerminalOutput, highlight the last CodeInputBlock."""
        if self._blocks and self._highlighted_index is None:
            self._highlighted_index = len(self._blocks) - 1
            self._update_highlight()
