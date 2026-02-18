"""Manages streaming state: chunk/thinking buffers, detector, and pause/resume."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from .terminal_output import ThinkingOutputBlock
from .chunk_buffer import ChunkBuffer
from .fence_detector import StreamingFenceDetector

if TYPE_CHECKING:
    from .terminal_output import TerminalOutput

logger = logging.getLogger(__name__)


class StreamManager:
    """Encapsulates streaming state and buffer management.

    Owns the chunk/thinking buffers, current detector, thinking block,
    and paused state. Delegates UI operations (batch_update, scroll,
    highlight) back to the terminal via callbacks.
    """

    def __init__(
        self,
        output: TerminalOutput,
        call_later: Callable,
        call_after_refresh: Callable,
        batch_update: Callable,
        on_pause: Callable[[], None] | None = None,
    ) -> None:
        self._output = output
        self._call_after_refresh = call_after_refresh
        self._batch_update = batch_update
        self._on_pause = on_pause

        self._current_detector: StreamingFenceDetector | None = None
        self._thinking_block: ThinkingOutputBlock | None = None
        self._chunk_buf = ChunkBuffer(call_later, self._drain_chunks)
        self._thinking_buf = ChunkBuffer(call_later, self._drain_thinking)
        self._stream_paused = False

    @property
    def is_paused(self) -> bool:
        return self._stream_paused

    @is_paused.setter
    def is_paused(self, value: bool) -> None:
        self._stream_paused = value

    @property
    def current_detector(self) -> StreamingFenceDetector | None:
        return self._current_detector

    @current_detector.setter
    def current_detector(self, value: StreamingFenceDetector | None) -> None:
        self._current_detector = value

    def create_detector(self) -> StreamingFenceDetector:
        """Create a new fence detector for an assistant response."""
        self._output.clear_command_numbers()
        self._current_detector = StreamingFenceDetector(
            self._output,
            pause_after_code=True,
        )
        return self._current_detector

    def on_chunk(self, text: str) -> None:
        """Handle an incoming stream chunk."""
        if self._current_detector:
            self._current_detector.start()
            self._chunk_buf.append(text)

    def on_thinking_chunk(self, text: str) -> None:
        """Handle an incoming thinking chunk."""
        self._thinking_buf.append(text)

    def _drain_chunks(self, text: str) -> None:
        """Process all accumulated chunks in the buffer at once."""
        if not self._current_detector:
            return
        self._current_detector.start()
        try:
            with self._batch_update():
                self._current_detector.feed(text)
            # Schedule scroll after layout refresh so Markdown widget height is recalculated
            self._call_after_refresh(lambda: self._output.scroll_end(animate=False))

            # Check if detector paused after a code block
            if self._current_detector.is_paused:
                self._chunk_buf.pause()
                self._stream_paused = True
                if self._on_pause:
                    self._on_pause()
        except Exception:
            logger.exception("Error processing chunk buffer")

    def _drain_thinking(self, text: str) -> None:
        """Process all accumulated thinking chunks in the buffer at once."""
        try:
            # Lazily create thinking block on first chunk
            if self._thinking_block is None:
                self._thinking_block = ThinkingOutputBlock(activity=True)
                self._output.append_block(self._thinking_block)
            self._thinking_block.append(text)
            self._thinking_block.flush()
            self._output.scroll_end(animate=False)
        except Exception:
            logger.exception("Error processing thinking buffer")

    def finalize(self) -> None:
        """Flush buffers and finalize thinking block and detector after streaming ends."""
        # Flush any remaining buffered thinking chunks
        self._thinking_buf.flush_sync()
        if self._thinking_block:
            self._thinking_block.finalize_streaming()
            self._thinking_block.mark_success()
            self._thinking_block = None

        # If the stream was paused (code block detected), DON'T finalize yet.
        if self._stream_paused:
            return

        # Flush any remaining buffered chunks and finalize detector
        self._chunk_buf.flush_sync()
        if self._current_detector:
            self._current_detector.finish()

    def resume(self) -> None:
        """Resume streaming after a pause-on-code-block."""
        self._stream_paused = False
        # Feed detector's remainder
        if self._current_detector:
            self._current_detector.resume()
        # Resume chunk buffer (will flush any accumulated chunks)
        self._chunk_buf.resume()
        # Finalize the stream since provider task was cancelled when we paused
        self._chunk_buf.flush_sync()
        if self._current_detector:
            self._current_detector.finish()
            self._current_detector = None
