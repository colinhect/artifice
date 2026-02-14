from __future__ import annotations


class StringTracker:
    """Tracks whether we're inside a string literal in streaming code.

    Handles single quotes, double quotes, triple quotes, and escape sequences.
    This allows us to avoid detecting code fences that appear inside strings.
    """

    def __init__(self) -> None:
        self._in_string: str | None = None  # None, "'", '"', "'''", or '"""'
        self._escape_next = False
        self._quote_buffer = ""

    @property
    def in_string(self) -> bool:
        return self._in_string is not None

    def reset(self) -> None:
        self._in_string = None
        self._escape_next = False
        self._quote_buffer = ""

    def track(self, ch: str) -> None:
        """Update string tracking state for the given character."""
        # Handle escape sequences
        if self._escape_next:
            self._escape_next = False
            self._quote_buffer = ""
            return

        if ch == "\\":
            self._escape_next = True
            self._quote_buffer = ""
            return

        # Track quotes to detect string boundaries
        if ch in ('"', "'"):
            # Build up quote buffer to detect triple quotes
            if self._quote_buffer and self._quote_buffer[0] == ch:
                self._quote_buffer += ch
            else:
                self._quote_buffer = ch

            # Check if we're entering or exiting a string
            if self._in_string:
                # Currently in a string - check if this closes it
                if self._in_string == self._quote_buffer:
                    # Closing the current string
                    self._in_string = None
                    self._quote_buffer = ""
            else:
                # Not in a string - check if this opens one
                # For triple quotes, wait until we have all three
                if len(self._quote_buffer) == 3:
                    # Opening triple-quoted string
                    self._in_string = self._quote_buffer
                    self._quote_buffer = ""
                elif len(self._quote_buffer) == 1:
                    # Could be single quote or start of triple quote
                    # We'll resolve this on the next character
                    pass
        else:
            # Non-quote character
            if self._quote_buffer and not self._in_string:
                # We had 1 or 2 quotes followed by a non-quote
                # This means it was a single or double quote string
                if len(self._quote_buffer) <= 2:
                    self._in_string = self._quote_buffer[0]
                    self._quote_buffer = ""
            elif self._quote_buffer:
                # We're in a string and hit a non-quote, reset buffer
                self._quote_buffer = ""

            # Newlines can end single-line strings in most languages
            # but not triple-quoted strings
            if ch == "\n" and self._in_string in ('"', "'"):
                self._in_string = None
