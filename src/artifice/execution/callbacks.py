"""Output callback handler for code execution."""

from __future__ import annotations

from typing import Callable

from artifice.ui.components.output import TerminalOutput
from artifice.ui.components.blocks.blocks import CodeOutputBlock


class OutputCallbackHandler:
    """Manages output callbacks for code execution with lazy block creation."""

    def __init__(
        self,
        output: TerminalOutput,
        markdown_enabled: bool,
        in_context: bool,
        schedule_fn: Callable[[Callable], None],
        use_code_block: bool = True,
    ):
        self._output = output
        self._markdown_enabled = markdown_enabled
        self._in_context = in_context
        self._schedule_fn = schedule_fn
        self._use_code_block = use_code_block
        self._block: CodeOutputBlock | None = None
        self._flush_scheduled = False

    def _ensure_block(self) -> CodeOutputBlock | None:
        """Lazily create output block on first output."""
        if not self._use_code_block:
            return None
        if self._block is None:
            self._block = CodeOutputBlock(
                render_markdown=self._markdown_enabled, in_context=self._in_context
            )
            self._output.append_block(self._block)
        return self._block

    def _schedule_flush(self) -> None:
        """Schedule a flush for the next event loop tick."""
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self._schedule_fn(self._flush)

    def _flush(self) -> None:
        """Flush buffered output to the widget."""
        self._flush_scheduled = False
        if self._block:
            self._block.flush()
            self._output.scroll_end(animate=False)

    def on_output(self, text: str) -> None:
        """Handle stdout text from execution."""
        block = self._ensure_block()
        if block:
            block.append_output(text)
            self._schedule_flush()

    def on_error(self, text: str) -> None:
        """Handle stderr text from execution."""
        block = self._ensure_block()
        if block:
            block.append_error(text)
            self._schedule_flush()

    def flush(self) -> None:
        """Force flush any remaining buffered output."""
        self._flush()
