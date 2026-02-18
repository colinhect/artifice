"""Streaming fence detector for code block extraction."""

from __future__ import annotations

import enum

from .terminal.output import (
    TerminalOutput,
    AgentOutputBlock,
    CodeInputBlock,
    BaseBlock,
)
from .block_factory import BlockFactory


class _FenceState(enum.Enum):
    PROSE = "prose"
    CODE = "code"


class StreamingFenceDetector:
    """Detects code fences in streaming text and splits into blocks in real-time.

    Processes chunks character-by-character using a state machine:
    PROSE -> CODE (on ```language) -> PROSE (on ```)

    Empty lines in prose split into separate AgentOutputBlocks.
    """

    def __init__(self, output: TerminalOutput, pause_after_code: bool = False) -> None:
        self._output = output
        self._factory = BlockFactory(output)
        self._pause_after_code = pause_after_code
        self._started = False
        self._paused = False
        self._remainder = ""
        self._last_code_block: BaseBlock | None = None
        self._state = _FenceState.PROSE
        self._pending_buffer = ""  # Text to add to current block
        self._chunk_buffer = ""  # Accumulates text for current chunk to display
        self._current_lang = "bash"
        self._current_block: BaseBlock | None = (
            None  # The block we're currently appending to
        )
        self._current_line_buffer = (
            ""  # Tracks current line in PROSE for blank line detection
        )
        self._strip_leading_whitespace = False  # Strip whitespace after closing fences
        # Markdown fence detection
        self._fence_backtick_count = 0  # Count backticks for fence detection
        self._fence_language_buffer = ""  # Accumulate language after ```
        self._detecting_fence_open = (
            False  # True when we've seen ``` and reading language
        )
        self._fence_close_backtick_count = 0  # Count backticks for closing fence
        # Factory methods for block creation (can be overridden for testing)
        self._make_prose_block = lambda activity: AgentOutputBlock(activity=activity)
        self._make_code_block = lambda code, lang: CodeInputBlock(
            code,
            language=lang,
            show_loading=False,
            in_context=True,
        )

    @property
    def all_blocks(self) -> list[BaseBlock]:
        return self._factory.all_blocks

    @property
    def first_agent_block(self) -> AgentOutputBlock | None:
        return self._factory.first_agent_block

    @first_agent_block.setter
    def first_agent_block(self, value: AgentOutputBlock | None) -> None:
        self._factory.first_agent_block = value

    @property
    def is_paused(self) -> bool:
        """True if processing paused after a code block closed."""
        return self._paused

    @property
    def last_code_block(self) -> BaseBlock | None:
        """The most recently completed CodeInputBlock."""
        return self._last_code_block

    def resume(self) -> None:
        """Resume processing after a pause, feeding any saved remainder."""
        self._paused = False
        remainder = self._remainder
        self._remainder = ""
        if remainder:
            self.feed(remainder)

    def start(self) -> None:
        """Create the initial AgentOutputBlock for streaming prose.

        Idempotent -- safe to call multiple times; only the first call has effect.
        """
        if self._started:
            return
        self._started = True
        self._current_block = self._create_and_mount_prose(activity=True)
        self._factory.first_agent_block = self._current_block

    def _create_and_mount_prose(self, activity: bool = True) -> AgentOutputBlock:
        """Create a prose block using the factory or test override."""
        block = self._make_prose_block(activity)
        self._output.append_block(block)
        self._factory.all_blocks.append(block)
        return block

    def _create_and_mount_code(self, code: str, lang: str) -> CodeInputBlock:
        """Create a code block using the factory or test override."""
        block = self._make_code_block(code, lang)
        self._output.append_block(block)
        self._factory.all_blocks.append(block)
        return block

    def feed(self, text: str) -> None:
        """Process a chunk of streaming text, creating blocks as needed.

        If pause_after_code is enabled and a code block closes, processing
        stops early and remaining text is saved in _remainder.
        """
        self._chunk_buffer = ""  # Reset for this chunk
        for i, ch in enumerate(text):
            self._feed_char(ch)
            if self._paused:
                # Save unprocessed remainder (chars after current one),
                # stripping any trailing junk on the same line as the closing fence
                raw_remainder = text[i + 1 :]
                newline_pos = raw_remainder.find("\n")
                if newline_pos >= 0:
                    self._remainder = raw_remainder[newline_pos + 1 :]
                else:
                    self._remainder = ""
                break
        # Flush any pending text to the chunk buffer for display
        self._flush_pending_to_chunk()
        # Update current block with accumulated chunk text
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
            self._chunk_buffer = ""  # Clear after updating to avoid reprocessing

    def _feed_char(self, ch: str) -> None:
        if self._state == _FenceState.PROSE:
            self._feed_prose(ch)
        elif self._state == _FenceState.CODE:
            self._feed_code(ch)

    def _flush_and_update_chunk(self) -> None:
        """Flush pending text and update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
            self._chunk_buffer = ""

    def _transition_to_code(self, lang: str) -> None:
        """Handle the transition from PROSE to CODE state."""
        self._current_lang = lang

        self._flush_pending_to_chunk()
        self._flush_and_update_chunk()

        # Remove empty prose block, or mark it complete
        current_is_empty = (
            isinstance(self._current_block, AgentOutputBlock)
            and not self._current_block._output_str.strip()
        )
        if current_is_empty:
            if self._current_block is self._factory.first_agent_block:
                self._factory.first_agent_block = None
            if self._current_block is not None:
                self._factory.remove_block(self._current_block)
        elif isinstance(self._current_block, AgentOutputBlock):
            self._current_block.mark_success()

        # Create new code block
        self._current_block = self._create_and_mount_code("", lang)

        self._pending_buffer = ""
        self._current_line_buffer = ""
        self._state = _FenceState.CODE

    def _transition_to_prose_from_code(self) -> None:
        """Handle the transition from CODE back to PROSE state."""
        # Capture as the last completed code block
        if isinstance(self._current_block, CodeInputBlock):
            self._last_code_block = self._current_block
            self._current_block.finish_streaming()

        # Start new prose block
        self._current_block = self._create_and_mount_prose(activity=True)

        self._current_line_buffer = ""
        self._strip_leading_whitespace = True
        self._state = _FenceState.PROSE

        # Pause after code block if enabled
        if self._pause_after_code:
            self._paused = True

    def _feed_prose(self, ch: str) -> None:
        """Process prose text, looking for markdown fences or empty lines to split blocks."""
        # Strip leading whitespace after closing fences
        if self._strip_leading_whitespace:
            if ch.isspace():
                return
            self._strip_leading_whitespace = False

        # Check for markdown fence opening (```language)
        if self._detecting_fence_open:
            # We've seen ``` and are now reading the language identifier
            if ch == "\n":
                # End of language line - transition to CODE state
                lang = self._fence_language_buffer.strip().lower()
                # Map common language names to our internal names
                if lang in ("bash", "sh", "shell"):
                    lang = "bash"
                elif lang in ("python", "py"):
                    lang = "python"
                elif lang == "":
                    # Default to bash if no language specified
                    lang = "bash"
                else:
                    # For other languages, default to python for syntax highlighting
                    lang = "python"

                self._detecting_fence_open = False
                self._fence_language_buffer = ""

                # Don't include the backticks or language in the prose
                self._transition_to_code(lang)
            else:
                # Accumulate language name
                self._fence_language_buffer += ch
            return

        # Check if we're starting a fence (```)
        if ch == "`":
            self._fence_backtick_count += 1
            if self._fence_backtick_count == 3:
                # We've seen ``` - now read the language
                self._detecting_fence_open = True
                self._fence_backtick_count = 0
            return
        elif self._fence_backtick_count > 0:
            # We had some backticks but didn't reach 3, or got interrupted
            self._pending_buffer += "`" * self._fence_backtick_count
            self._fence_backtick_count = 0
            # Continue processing current character normally

        # Check for empty lines to split blocks
        if ch == "\n":
            # Add newline to pending buffer
            self._pending_buffer += ch

            # Check if the line we just completed was empty/whitespace-only
            if self._current_line_buffer.strip() == "":
                # Empty line detected - finalize current block and start new one
                self._flush_pending_to_chunk()
                self._flush_and_update_chunk()

                # Finalize current prose block (renders as Markdown immediately)
                if isinstance(self._current_block, AgentOutputBlock):
                    self._current_block.finalize_streaming()
                    self._current_block.mark_success()

                # Create new prose block
                self._current_block = self._create_and_mount_prose(activity=True)

            # Reset line buffer for next line
            self._current_line_buffer = ""
        else:
            self._pending_buffer += ch
            self._current_line_buffer += ch

    def _feed_code(self, ch: str) -> None:
        """Process code text, looking for closing fence (```)."""
        if ch == "`":
            # Check if we're at start of line before starting fence close detection
            lines = self._pending_buffer.split("\n")
            current_line_in_pending = lines[-1] if lines else ""

            # Only detect closing fence if at start of line
            if current_line_in_pending.strip() == "":
                self._fence_close_backtick_count += 1
                if self._fence_close_backtick_count == 3:
                    # We've seen three backticks at start of line - this closes the fence
                    # Remove any trailing newline from code before the closing fence
                    if self._pending_buffer.endswith("\n"):
                        self._pending_buffer = self._pending_buffer[:-1]

                    # Flush pending code (without the closing backticks)
                    self._flush_pending_to_chunk()
                    self._flush_and_update_chunk()

                    # Reset fence state
                    self._fence_close_backtick_count = 0

                    self._transition_to_prose_from_code()
                # Don't add backtick to pending - we're accumulating them for fence detection
                return
            else:
                # Backtick not at start of line - it's part of code content
                if self._fence_close_backtick_count > 0:
                    self._pending_buffer += "`" * self._fence_close_backtick_count
                    self._fence_close_backtick_count = 0
                # Add current backtick as regular code content
                self._pending_buffer += ch
                return
        elif self._fence_close_backtick_count > 0:
            # We had some backticks at start of line but got interrupted by non-backtick
            self._pending_buffer += "`" * self._fence_close_backtick_count
            self._fence_close_backtick_count = 0
            # Fall through to add current character

        # Regular code character
        self._pending_buffer += ch

    def _flush_pending_to_chunk(self) -> None:
        """Move pending buffer to chunk buffer."""
        self._chunk_buffer += self._pending_buffer
        self._pending_buffer = ""

    def _update_current_block_with_chunk(self) -> None:
        """Update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            if isinstance(self._current_block, CodeInputBlock):
                existing = self._current_block.get_code()
                self._current_block.update_code(existing + self._chunk_buffer)
            elif isinstance(self._current_block, AgentOutputBlock):
                self._current_block.append(self._chunk_buffer)
                self._current_block.flush()

    def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        # Ensure start() was called (handles empty stream edge case)
        self.start()

        # Flush any remaining text ONLY if there's pending content
        if self._pending_buffer:
            self._flush_pending_to_chunk()
            if self._chunk_buffer and self._current_block:
                self._update_current_block_with_chunk()
                self._chunk_buffer = ""  # Clear to avoid double-processing

        # Mark the last block as complete
        if isinstance(self._current_block, AgentOutputBlock):
            self._current_block.flush()  # Ensure final content is rendered
            self._current_block.mark_success()

        # Finalize all blocks: switch from streaming mode to final rendering
        for block in self._factory.all_blocks:
            if isinstance(block, CodeInputBlock):
                block.finish_streaming()
            elif isinstance(block, AgentOutputBlock):
                block.flush()  # Ensure all content is rendered before finalizing
                block.finalize_streaming()

        # Remove empty AgentOutputBlocks (including first_agent_block)
        for block in [
            b
            for b in self._factory.all_blocks
            if isinstance(b, AgentOutputBlock) and not b._output_str.strip()
        ]:
            if block is self._factory.first_agent_block:
                self._factory.first_agent_block = None
            self._factory.remove_block(block)
