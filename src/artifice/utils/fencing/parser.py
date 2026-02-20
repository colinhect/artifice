"""Pure parsing logic for markdown code fences (no UI dependencies)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from artifice.utils.fencing.state import FenceState


@dataclass
class ParsedChunk:
    """Result of parsing a chunk of text."""

    text: str
    state: FenceState
    is_code_block_start: bool = False
    is_code_block_end: bool = False
    language: str | None = None


@dataclass
class ParserState:
    """Internal state of the fence parser."""

    state: FenceState = FenceState.PROSE
    remainder: str = ""
    pending_buffer: str = ""
    chunk_buffer: str = ""
    current_language: str = "bash"
    current_line_buffer: str = ""
    strip_leading_whitespace: bool = False
    # Fence detection state
    fence_backtick_count: int = 0
    fence_language_buffer: str = ""
    detecting_fence_open: bool = False
    fence_close_backtick_count: int = 0


class FenceParser:
    """Pure parser for markdown code fences with no UI dependencies.

    Processes text character-by-character using a state machine to detect
    code fences (```language) and track transitions between prose and code.

    Usage:
        parser = FenceParser()
        for chunk in chunks:
            result = parser.feed(chunk)
            if result.is_code_block_start:
                # Handle code block start
                pass
            elif result.is_code_block_end:
                # Handle code block end
                pass
            else:
                # Handle prose or code text
                process_text(result.text, result.state)
    """

    def __init__(
        self,
        on_code_start: Callable[[str], None] | None = None,
        on_code_end: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the parser.

        Args:
            on_code_start: Callback when a code block starts, receives language
            on_code_end: Callback when a code block ends
        """
        self._on_code_start = on_code_start
        self._on_code_end = on_code_end
        self._state = ParserState()
        self._started = False
        self._paused = False
        self._last_code_text: str | None = None

    @property
    def is_paused(self) -> bool:
        """True if parser is paused after a code block closed."""
        return self._paused

    @property
    def current_state(self) -> FenceState:
        """Current state of the parser (PROSE or CODE)."""
        return self._state.state

    @property
    def current_language(self) -> str:
        """Language of the current code block (if in CODE state)."""
        return self._state.current_language

    @property
    def last_code_text(self) -> str | None:
        """Text content of the most recently completed code block."""
        return self._last_code_text

    @property
    def remainder(self) -> str:
        """Current remainder text (set when paused)."""
        return self._state.remainder

    def start(self) -> None:
        """Mark the parser as started. Idempotent."""
        self._started = True

    def resume(self) -> str:
        """Resume after pause, returning any saved remainder text."""
        self._paused = False
        remainder = self._state.remainder
        self._state.remainder = ""
        return remainder

    def finish(self) -> str | None:
        """Finish parsing, returning any remaining text."""
        # Flush any pending text
        if self._state.pending_buffer:
            self._state.chunk_buffer += self._state.pending_buffer
            self._state.pending_buffer = ""
        remainder = self._state.chunk_buffer if self._state.chunk_buffer else None
        self._state.chunk_buffer = ""
        return remainder

    def feed(self, text: str) -> list[ParsedChunk]:
        """Process a chunk of text and return parsed segments.

        Args:
            text: Text chunk to parse

        Returns:
            List of parsed chunks with state information
        """
        self._state.chunk_buffer = ""
        results: list[ParsedChunk] = []

        for i, ch in enumerate(text):
            result = self._feed_char(ch)
            if result:
                results.append(result)
            if self._paused:
                # Save unprocessed remainder
                raw_remainder = text[i + 1 :]
                newline_pos = raw_remainder.find("\n")
                if newline_pos >= 0:
                    self._state.remainder = raw_remainder[newline_pos + 1 :]
                else:
                    self._state.remainder = ""
                break

        # Flush any pending text to chunk buffer
        if self._state.pending_buffer:
            self._state.chunk_buffer += self._state.pending_buffer
            self._state.pending_buffer = ""

        # Return accumulated text as a chunk if any
        if self._state.chunk_buffer:
            results.append(
                ParsedChunk(
                    text=self._state.chunk_buffer,
                    state=self._state.state,
                )
            )
            self._state.chunk_buffer = ""

        return results

    def _feed_char(self, ch: str) -> ParsedChunk | None:
        """Process a single character, returning any state change events."""
        if self._state.state == FenceState.PROSE:
            return self._feed_prose(ch)
        else:  # CODE state
            return self._feed_code(ch)

    def _feed_prose(self, ch: str) -> ParsedChunk | None:
        """Process prose text, looking for markdown fences or empty lines."""
        # Strip leading whitespace after closing fences
        if self._state.strip_leading_whitespace:
            if ch.isspace():
                return None
            self._state.strip_leading_whitespace = False

        # Check for markdown fence opening (```language)
        if self._state.detecting_fence_open:
            if ch == "\n":
                lang = self._process_language()
                self._state.detecting_fence_open = False
                self._state.fence_language_buffer = ""
                return self._transition_to_code(lang)
            else:
                self._state.fence_language_buffer += ch
                return None

        # Check if we're starting a fence (```)
        if ch == "`":
            self._state.fence_backtick_count += 1
            if self._state.fence_backtick_count == 3:
                self._state.detecting_fence_open = True
                self._state.fence_backtick_count = 0
                return None
            return None
        elif self._state.fence_backtick_count > 0:
            # We had some backticks but didn't reach 3
            self._state.pending_buffer += "`" * self._state.fence_backtick_count
            self._state.fence_backtick_count = 0

        # Check for empty lines to split blocks
        if ch == "\n":
            self._state.pending_buffer += ch

            if self._state.current_line_buffer.strip() == "":
                # Empty line detected - finalize current prose
                text = self._state.pending_buffer
                self._state.pending_buffer = ""
                self._state.current_line_buffer = ""
                return ParsedChunk(
                    text=text,
                    state=FenceState.PROSE,
                    is_code_block_end=False,
                )

            self._state.current_line_buffer = ""
            return None
        else:
            self._state.pending_buffer += ch
            self._state.current_line_buffer += ch
            return None

    def _feed_code(self, ch: str) -> ParsedChunk | None:
        """Process code text, looking for closing fence (```)."""
        if ch == "`":
            # Only detect closing fence if at start of line
            lines = self._state.pending_buffer.split("\n")
            current_line_in_pending = lines[-1] if lines else ""

            if current_line_in_pending.strip() == "":
                self._state.fence_close_backtick_count += 1
                if self._state.fence_close_backtick_count == 3:
                    # Closing fence detected
                    if self._state.pending_buffer.endswith("\n"):
                        self._state.pending_buffer = self._state.pending_buffer[:-1]

                    text = self._state.pending_buffer
                    self._state.pending_buffer = ""
                    self._state.fence_close_backtick_count = 0
                    return self._transition_to_prose(text)
                return None
            else:
                # Backtick not at start of line
                if self._state.fence_close_backtick_count > 0:
                    self._state.pending_buffer += (
                        "`" * self._state.fence_close_backtick_count
                    )
                    self._state.fence_close_backtick_count = 0
                self._state.pending_buffer += ch
                return None
        elif self._state.fence_close_backtick_count > 0:
            # Interrupted fence close detection
            self._state.pending_buffer += "`" * self._state.fence_close_backtick_count
            self._state.fence_close_backtick_count = 0

        # Regular code character
        self._state.pending_buffer += ch
        return None

    def _process_language(self) -> str:
        """Process and normalize the language identifier."""
        lang = self._state.fence_language_buffer.strip().lower()

        if lang in ("bash", "sh", "shell"):
            return "bash"
        elif lang in ("python", "py"):
            return "python"
        elif lang == "":
            return "bash"  # Default
        else:
            return "python"  # Default for other languages

    def _transition_to_code(self, lang: str) -> ParsedChunk:
        """Transition from PROSE to CODE state."""
        # Save the prose text that triggered this transition
        prose_text = self._state.chunk_buffer + self._state.pending_buffer
        self._state.chunk_buffer = ""
        self._state.pending_buffer = ""
        self._state.current_line_buffer = ""
        self._state.current_language = lang
        self._state.state = FenceState.CODE

        if self._on_code_start:
            self._on_code_start(lang)

        return ParsedChunk(
            text=prose_text,
            state=FenceState.PROSE,
            is_code_block_start=True,
            language=lang,
        )

    def _transition_to_prose(self, code_text: str) -> ParsedChunk:
        """Transition from CODE back to PROSE state."""
        self._last_code_text = code_text
        self._state.current_line_buffer = ""
        self._state.strip_leading_whitespace = True
        self._state.state = FenceState.PROSE

        if self._on_code_end:
            self._on_code_end(code_text)

        return ParsedChunk(
            text=code_text,
            state=FenceState.CODE,
            is_code_block_end=True,
        )

    def pause(self) -> None:
        """Pause the parser after a code block closes."""
        self._paused = True
