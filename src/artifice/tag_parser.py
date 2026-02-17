"""XML-style tag parsing with liberal syntax support."""

from __future__ import annotations

# Aliases: normalize alternative tag names to canonical ones
TAG_ALIASES = {
    "py": "python",
    "code": "python",
    "tool_call": "shell",
    "bash": "shell",
    "sh": "shell",
    "cmd": "shell",
}

# Maximum length for a tag buffer before we give up
MAX_TAG_LEN = 50


class TagParser:
    """Handles XML-style tag detection with liberal syntax support.

    Supports:
    - Whitespace inside tags: < shell >, < /python >
    - Namespace prefixes: <minimax:tool_call>, <ns:shell>
    - Aliases: <tool_call> treated as <shell>
    """

    def __init__(self):
        self._buffer = ""

    def feed_char(self, ch: str, targets: list[str]) -> str | bool:
        """Accumulate characters and check for matching tags.

        Returns:
            str: The canonical matched tag string if a complete tag was detected.
            True: Still accumulating (haven't seen '>' yet).
            False: No match (caller should flush buffer via flush_to_text()).
        """
        self._buffer += ch

        if ch == ">":
            # Complete tag — normalize and check
            canonical = self.normalize(self._buffer)
            if canonical and canonical in targets:
                self._buffer = ""
                return canonical
            # Not a matching tag — leave buffer for caller to flush
            return False

        # Bail on a second '<' (means the first wasn't a real tag)
        if ch == "<" and len(self._buffer) > 1:
            # Caller should flush everything except the new '<'
            # We keep the new '<' for potential new tag
            return False

        # Bail on newline inside a tag
        if ch == "\n":
            return False

        # Bail if buffer is too long
        if len(self._buffer) > MAX_TAG_LEN:
            return False

        return True

    @staticmethod
    def normalize(raw_tag: str) -> str | None:
        """Normalize a raw tag like '< minimax:tool_call >' to canonical '<shell>'.

        Strips outer angle brackets, whitespace, namespace prefixes, and maps aliases.
        """
        if not raw_tag or len(raw_tag) < 2:
            return None

        inner = raw_tag[1:-1].strip()  # Strip < > and whitespace

        # Handle closing tag
        is_closing = inner.startswith("/")
        if is_closing:
            inner = inner[1:].strip()

        # Strip namespace prefix (e.g. "minimax:tool_call" -> "tool_call")
        if ":" in inner:
            inner = inner.split(":", 1)[1].strip()

        # Map aliases
        name = TAG_ALIASES.get(inner, inner)

        if is_closing:
            return f"</{name}>"
        return f"<{name}>"

    def flush_to_text(self) -> str:
        """Return accumulated buffer that wasn't a complete tag."""
        text = self._buffer
        self._buffer = ""
        return text

    @property
    def has_buffered(self) -> bool:
        """True if there's text in the tag buffer."""
        return bool(self._buffer)
