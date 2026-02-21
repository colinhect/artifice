"""Manages streaming state: chunk/thinking buffers, detector."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from artifice.agent.streaming.buffer import ChunkBuffer
from artifice.agent.streaming.detector import StreamingFenceDetector
from artifice.ui.components.blocks.blocks import ThinkingOutputBlock

if TYPE_CHECKING:
    from artifice.ui.components.output import TerminalOutput

logger = logging.getLogger(__name__)


class StreamManager:
    """Encapsulates streaming state and buffer management.

    Owns the chunk/thinking buffers, current detector, and thinking block.
    Delegates UI operations (batch_update, scroll, highlight) back to the
    terminal via callbacks.
    """

    def __init__(
        self,
        output: TerminalOutput,
        call_later: Callable,
        call_after_refresh: Callable,
        batch_update: Callable,
    ) -> None:
        self._output = output
        self._call_after_refresh = call_after_refresh
        self._batch_update = batch_update

        self._current_detector: StreamingFenceDetector | None = None
        self._thinking_block: ThinkingOutputBlock | None = None
        self._chunk_buf = ChunkBuffer(call_later, self._drain_chunks)
        self._thinking_buf = ChunkBuffer(call_later, self._drain_thinking)
        self._scroll_scheduled = False

    @property
    def current_detector(self) -> StreamingFenceDetector | None:
        return self._current_detector

    @current_detector.setter
    def current_detector(self, value: StreamingFenceDetector | None) -> None:
        self._current_detector = value

    def create_detector(self) -> StreamingFenceDetector:
        """Create a new fence detector for an agent response."""
        self._current_detector = StreamingFenceDetector(self._output)
        return self._current_detector

    def on_chunk(self, text: str) -> None:
        """Handle an incoming stream chunk."""
        if self._current_detector:
            self._chunk_buf.append(text)

    def on_thinking_chunk(self, text: str) -> None:
        """Handle an incoming thinking chunk."""
        self._thinking_buf.append(text)

    def _schedule_scroll(self) -> None:
        """Schedule a single scroll_end after the next refresh, debounced."""
        if not self._scroll_scheduled:
            self._scroll_scheduled = True
            self._call_after_refresh(self._do_scroll)

    def _do_scroll(self) -> None:
        """Execute the debounced scroll."""
        self._scroll_scheduled = False
        self._output.scroll_end(animate=False)

    async def _drain_chunks(self, text: str) -> None:
        """Process all accumulated chunks in the buffer at once."""
        if not self._current_detector:
            return
        self._current_detector.start()
        try:
            with self._batch_update():
                await self._current_detector.feed(text)
            self._schedule_scroll()
        except Exception:
            logger.exception("Error processing chunk buffer")

    async def _drain_thinking(self, text: str) -> None:
        """Process all accumulated thinking chunks in the buffer at once."""
        try:
            # Lazily create thinking block on first chunk
            if self._thinking_block is None:
                self._thinking_block = ThinkingOutputBlock(activity=True)
                self._output.append_block(self._thinking_block, scroll=False)
            with self._batch_update():
                await self._thinking_block.append(text)
                self._thinking_block.flush()
            self._schedule_scroll()
        except Exception:
            logger.exception("Error processing thinking buffer")

    async def finalize(self) -> None:
        """Flush buffers and finalize thinking block and detector after streaming ends."""
        # Flush any remaining buffered thinking chunks
        self._thinking_buf.flush_sync()
        if self._thinking_block:
            self._thinking_block.finalize_streaming()
            self._thinking_block.mark_success()
            self._thinking_block = None

        # Flush any remaining buffered chunks and finalize detector
        self._chunk_buf.flush_sync()
        if self._current_detector:
            await self._current_detector.finish()

        # Final scroll with animation after streaming completes
        self._output.scroll_end(animate=True)
