"""Container widgets for terminal output display."""

from __future__ import annotations

import pyperclip

from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message

from ..input import InputTextArea
from .blocks import (
    AssistantInputBlock,
    AssistantOutputBlock,
    BaseBlock,
    CodeInputBlock,
    CodeOutputBlock,
    ToolCallBlock,
    WidgetOutputBlock,
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
        original_index = self._highlighted_index
        if self._highlighted_index is None:
            self._highlighted_index = 0
        else:
            self._highlighted_index = min(
                self._highlighted_index + 1, len(self._blocks) - 1
            )
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

    def _update_highlight(self) -> None:
        """Update visual highlight on blocks."""
        for i, block in enumerate(self._blocks):
            if i == self._highlighted_index:
                block.add_class("highlighted")
                # Auto-scroll to make the highlighted block visible
                self.scroll_to_widget(block, animate=True)  # type: ignore
            else:
                block.remove_class("highlighted")

    def get_highlighted_block(self):
        """Get the currently highlighted block, if any."""
        if self._highlighted_index is None or not self._blocks:
            return None
        if 0 <= self._highlighted_index < len(self._blocks):
            return self._blocks[self._highlighted_index]
        return None

    def on_blur(self) -> None:
        """When unfocusing, unhighlight the highlighted block."""
        self._highlighted_index = None
        self._update_highlight()


class TerminalOutput(HighlightableContainerMixin, VerticalScroll):
    """Container for REPL output blocks."""

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
        # Binding("ctrl+u", "pin_block", "Pin Block", show=True),
        # Binding("insert", "cycle_language", "Mode", show=True),
        # *[
        #    Binding(str(n), f"run_numbered('{n}')", f"Run #{n}", show=False)
        #    for n in range(1, 10)
        # ],
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

    def append_block(self, block: BaseBlock):
        self._blocks.append(block)
        self.mount(block)
        self.scroll_end(animate=False)
        return block

    def auto_scroll(self) -> None:
        """Scroll to the bottom without animation."""
        self.scroll_end(animate=False)

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
        elif isinstance(block, AssistantInputBlock):
            code = block.get_prompt()
            pyperclip.copy(code)
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
        if block and isinstance(block, (CodeOutputBlock, AssistantOutputBlock)):
            block.toggle_markdown()

    def action_cycle_language(self) -> None:
        """Cycle the language of the highlighted CodeInputBlock (not ToolCallBlocks)."""
        block = self.get_highlighted_block()
        if (
            block
            and isinstance(block, CodeInputBlock)
            and not isinstance(block, ToolCallBlock)
        ):
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
        elif self._highlighted_index is not None and self._highlighted_index >= len(
            self._blocks
        ):
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
        start = (
            (self._highlighted_index - 1)
            if self._highlighted_index is not None
            else len(self._blocks) - 1
        )
        for i in range(start, -1, -1):
            if isinstance(self._blocks[i], CodeInputBlock):
                self._highlighted_index = i
                self._update_highlight()
                return

    def action_highlight_next_code(self) -> None:
        """Move highlight to the next CodeInputBlock, skipping other block types."""
        if not self._blocks:
            return
        start = (
            (self._highlighted_index + 1) if self._highlighted_index is not None else 0
        )
        for i in range(start, len(self._blocks)):
            if isinstance(self._blocks[i], CodeInputBlock):
                self._highlighted_index = i
                self._update_highlight()
                return
        # No more code blocks forward -- move focus to input
        self.app.query_one("#code-input", InputTextArea).focus()

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


class PinnedOutput(HighlightableContainerMixin, Vertical):
    """Container for pinned output blocks, displayed below the input."""

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

    can_focus = True

    async def add_pinned_block(self, block: WidgetOutputBlock) -> None:
        self._blocks.append(block)
        await self.mount(block)
        await block.recompose()
        self.add_class("has-pins")

    async def remove_pinned_block(self, block: WidgetOutputBlock) -> None:
        if block in self._blocks:
            idx = self._blocks.index(block)
            self._blocks.remove(block)
            await block.remove()
            # Adjust highlighted index
            if not self._blocks:
                self._highlighted_index = None
                self.remove_class("has-pins")
            elif self._highlighted_index is not None:
                if idx <= self._highlighted_index:
                    self._highlighted_index = max(0, self._highlighted_index - 1)
                if self._highlighted_index >= len(self._blocks):
                    self._highlighted_index = len(self._blocks) - 1
            self._update_highlight()

    def action_highlight_previous(self) -> None:
        self.highlight_previous()

    def action_highlight_next(self) -> None:
        if not self.highlight_next():
            pass  # Already at end

    def action_unpin_block(self) -> None:
        block = self.get_highlighted_block()
        if block:
            self.post_message(self.UnpinRequested(block))

    def on_focus(self) -> None:
        if self._blocks:
            self._highlighted_index = 0
            self._update_highlight()
