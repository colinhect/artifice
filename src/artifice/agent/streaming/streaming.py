"""Streaming support for LLM responses - buffers, detectors, and managers."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time
from typing import TYPE_CHECKING, Callable

from artifice.ui.components.blocks.blocks import (
    AgentOutputBlock,
    BaseBlock,
    ThinkingOutputBlock,
)

if TYPE_CHECKING:
    from artifice.ui.components.output import TerminalOutput

logger = logging.getLogger(__name__)


HEADER_PATTERN = re.compile(r"^(#{1,6})(\s|$)")


class ChunkBuffer:
    """Accumulates text chunks and drains them in a single batch via call_later.

    Enforces a maximum frame rate (default 30 FPS) to prevent excessive UI updates
    during rapid streaming.

    Args:
        schedule: Callable that defers ``drain`` to the next event-loop tick
                  (e.g. ``widget.call_later``).
        drain: Callable(text) invoked with the accumulated text when flushed.
        min_interval: Minimum seconds between drain operations (default: 1/60 for 60 FPS).
    """

    def __init__(
        self, schedule: Callable, drain: Callable, min_interval: float = 1.0 / 60.0
    ) -> None:
        self._schedule = schedule
        self._drain = drain
        self._buffer: str = ""
        self._scheduled: bool = False
        self._min_interval = min_interval
        self._last_drain_time: float = 0.0
        self._paused: bool = False

    def append(self, text: str) -> None:
        """Add *text* to the buffer and schedule a drain if needed."""
        self._buffer += text
        if not self._scheduled:
            self._scheduled = True
            now = time.monotonic()
            elapsed = now - self._last_drain_time
            if elapsed >= self._min_interval:
                self._schedule(self._flush)
            else:
                delay = self._min_interval - elapsed
                self._schedule(lambda: self._schedule_delayed_flush(delay))

    def _schedule_delayed_flush(self, delay: float) -> None:
        """Schedule a flush after the specified delay."""
        asyncio.get_running_loop().call_later(delay, self._flush)

    def pause(self) -> None:
        """Pause draining - buffer keeps accumulating but won't flush."""
        self._paused = True

    def resume(self) -> None:
        """Resume draining - triggers a flush if buffer has content."""
        self._paused = False
        if self._buffer:
            self._flush()

    def _flush(self) -> None:
        self._scheduled = False
        if self._paused:
            return
        if self._buffer:
            text = self._buffer
            self._buffer = ""
            self._last_drain_time = time.monotonic()
            result = self._drain(text)
            if inspect.iscoroutine(result):
                asyncio.create_task(result)

    def flush_sync(self) -> None:
        """Drain any remaining buffered text immediately."""
        self._scheduled = False
        if self._buffer:
            text = self._buffer
            self._buffer = ""
            self._last_drain_time = time.monotonic()
            result = self._drain(text)
            if inspect.iscoroutine(result):
                asyncio.create_task(result)

    @property
    def pending(self) -> bool:
        """True if the buffer has un-drained text."""
        return bool(self._buffer)


class StreamingFenceDetector:
    """Streams text into AgentOutputBlocks, splitting on markdown headers.

    Whenever a markdown header starts at the beginning of a new line, it creates
    a new output block. The header line becomes the first content in the new block,
    and the previous block is finalized.
    """

    def __init__(self, output: TerminalOutput) -> None:
        self._output = output
        self.all_blocks: list[BaseBlock] = []
        self.first_agent_block: AgentOutputBlock | None = None
        self._started = False
        self._current_block: AgentOutputBlock | None = None
        self._incomplete_line: str = ""
        self._block_has_content: bool = False
        self._make_prose_block = lambda activity: AgentOutputBlock(activity=activity)

    def start(self) -> None:
        """Create the initial AgentOutputBlock for streaming.

        Idempotent -- safe to call multiple times; only the first call has effect.
        """
        if self._started:
            return
        self._started = True
        self._current_block = self._create_and_mount_prose(activity=True)
        self.first_agent_block = self._current_block
        self._block_has_content = False

    def _create_and_mount_prose(self, activity: bool = True) -> AgentOutputBlock:
        """Create a prose block using the factory or test override."""
        block = self._make_prose_block(activity)
        self._output.append_block(block, scroll=False)
        self.all_blocks.append(block)
        return block

    def _is_header_line(self, line: str) -> bool:
        """Check if a line is a markdown header.

        A markdown header is 1-6 # characters at the start of a line,
        followed by a space or end of line.
        """
        if not line:
            return False
        return HEADER_PATTERN.match(line) is not None

    async def feed(self, text: str) -> None:
        """Process a chunk of streaming text, splitting on headers.

        Text is accumulated line by line. When a line starting with a markdown
        header is encountered (and the current block has content), a new block
        is created and the header starts that new block.
        """
        if not text or self._current_block is None:
            return

        i = 0
        while i < len(text):
            newline_pos = text.find("\n", i)

            if newline_pos == -1:
                self._incomplete_line += text[i:]
                break

            line = self._incomplete_line + text[i:newline_pos]
            self._incomplete_line = ""

            if self._is_header_line(line) and self._block_has_content:
                self._current_block.finalize_streaming()
                self._current_block.mark_success()

                self._current_block = self._create_and_mount_prose(activity=True)
                self._block_has_content = False

            line_with_newline = line + "\n"
            await self._current_block.append(line_with_newline)
            self._block_has_content = True

            i = newline_pos + 1

    async def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        self.start()

        if self._incomplete_line and self._current_block is not None:
            if self._is_header_line(self._incomplete_line) and self._block_has_content:
                self._current_block.finalize_streaming()
                self._current_block.mark_success()
                self._current_block = self._create_and_mount_prose(activity=True)
                self._block_has_content = False

            if self._current_block is not None:
                await self._current_block.append(self._incomplete_line)
                self._block_has_content = True

        if self._current_block is not None:
            self._current_block.mark_success()
            self._current_block.finalize_streaming()


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
        streaming_fps: int = 60,
    ) -> None:
        self._output = output
        self._call_after_refresh = call_after_refresh
        self._batch_update = batch_update

        self._current_detector: StreamingFenceDetector | None = None
        self._thinking_block: ThinkingOutputBlock | None = None
        min_interval = 1.0 / streaming_fps
        self._chunk_buf = ChunkBuffer(call_later, self._drain_chunks, min_interval)
        self._thinking_buf = ChunkBuffer(call_later, self._drain_thinking, min_interval)
        self._scroll_scheduled = False

    @property
    def current_detector(self) -> StreamingFenceDetector | None:
        """Get the current fence detector."""
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
        self._thinking_buf.flush_sync()
        if self._thinking_block:
            self._thinking_block.finalize_streaming()
            self._thinking_block.mark_success()
            self._thinking_block = None

        self._chunk_buf.flush_sync()
        if self._current_detector:
            await self._current_detector.finish()

        self._output.scroll_end(animate=True)


__all__ = ["ChunkBuffer", "StreamingFenceDetector", "StreamManager"]
