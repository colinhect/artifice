from __future__ import annotations

import asyncio
import inspect
import time


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

    def __init__(self, schedule, drain, min_interval: float = 1.0 / 30.0) -> None:
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
            # Check if we need to throttle based on last drain time
            now = time.monotonic()
            elapsed = now - self._last_drain_time
            if elapsed >= self._min_interval:
                # Enough time has passed, schedule immediately
                self._schedule(self._flush)
            else:
                # Throttle: schedule for later to maintain frame rate limit
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
            # If drain is async, schedule it as a task
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
            # If drain is async, schedule it as a task
            if inspect.iscoroutine(result):
                asyncio.create_task(result)

    @property
    def pending(self) -> bool:
        """True if the buffer has un-drained text."""
        return bool(self._buffer)
