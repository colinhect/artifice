"""Backtick code span tracking for markdown."""

from __future__ import annotations


class BacktickTracker:
    """Tracks backtick code spans to skip tag detection inside them.

    Handles both single ` and triple ``` code spans in markdown.
    """

    def __init__(self):
        self._in_span = False
        self._opening_count = 0
        self._closing_needed = 0

    def feed(self, ch: str) -> None:
        """Process a character and update backtick span state."""
        if ch == "`":
            if self._in_span:
                # Inside a backtick span - count consecutive backticks
                self._opening_count += 1
                if self._opening_count >= self._closing_needed:
                    # Closing backtick sequence found
                    self._in_span = False
                    self._opening_count = 0
                    self._closing_needed = 0
            else:
                # Not inside a span - count opening backticks
                self._opening_count += 1
        else:
            if not self._in_span and self._opening_count > 0:
                # We had backticks followed by non-backtick - enter backtick span
                self._closing_needed = self._opening_count
                self._opening_count = 0
                self._in_span = True
            elif self._in_span:
                # Non-backtick inside span - reset consecutive backtick count
                self._opening_count = 0

    @property
    def in_span(self) -> bool:
        """True if currently inside a backtick code span."""
        return self._in_span
