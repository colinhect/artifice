"""Output callback handler for code execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .terminal_output import TerminalOutput, CodeOutputBlock, BaseBlock


class OutputCallbackHandler:
    """Manages output callbacks for code execution with lazy block creation."""

    def __init__(
        self,
        output: TerminalOutput,
        markdown_enabled: bool,
        in_context: bool,
        save_callback: Callable[[BaseBlock], None] | None,
        schedule_fn: Callable[[Callable], None],
    ):
        self._output = output
        self._markdown_enabled = markdown_enabled
        self._in_context = in_context
        self._save_callback = save_callback
        self._schedule_fn = schedule_fn
        self._block: CodeOutputBlock | None = None
        self._flush_scheduled = False
        self._saved = False

    def _ensure_block(self) -> CodeOutputBlock:
        """Lazily create output block on first output."""
        if self._block is None:
            from .terminal_output import CodeOutputBlock

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
            # Save to session on final flush if not already saved
            if not self._saved and self._save_callback:
                self._save_callback(self._block)
                self._saved = True

    def on_output(self, text: str) -> None:
        """Handle stdout text from execution."""
        self._ensure_block().append_output(text)
        self._schedule_flush()

    def on_error(self, text: str) -> None:
        """Handle stderr text from execution."""
        self._ensure_block().append_error(text)
        self._schedule_flush()

    def flush(self) -> None:
        """Force flush any remaining buffered output."""
        self._flush()
