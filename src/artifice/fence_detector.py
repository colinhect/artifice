"""Main Artifice terminal widget."""

from __future__ import annotations

import enum

from .terminal_output import (
    TerminalOutput,
    AssistantOutputBlock,
    ThinkingOutputBlock,
    CodeInputBlock,
    BaseBlock,
)

_CODE_OPEN_TAGS = {"<python>": "python", "<shell>": "bash"}
_CODE_CLOSE_TAGS = {"python": "</python>", "bash": "</shell>"}
_PROSE_TAG_TARGETS = ["<think>", "<detail>", "<python>", "<shell>"]

# Aliases: normalize alternative tag names to canonical ones
_TAG_NAME_ALIASES = {
    "py": "python",
    "code": "python",
    "tool_call": "shell",
    "bash": "shell",
    "sh": "shell",
    "cmd": "shell",
}

# Maximum length for a tag buffer before we give up (e.g. "< prefix:tool_call >")
_MAX_TAG_LEN = 50


class _FenceState(enum.Enum):
    PROSE = "prose"
    CODE = "code"
    THINKING = "thinking"


class StreamingFenceDetector:
    """Detects code tags in streaming text and splits into blocks in real-time.

    Processes chunks character-by-character using a state machine:
    PROSE -> CODE (on <python>/<shell>) -> PROSE (on </python>/</shell>)
    PROSE -> THINKING (on <think>) -> PROSE (on </think>)

    Creates blocks as tags are detected, accumulating text to update once per chunk.
    """

    def __init__(self, output: TerminalOutput, save_callback=None, pause_after_code: bool = False) -> None:
        self._output = output
        self._save_callback = save_callback  # Callback to save blocks to session
        self._pause_after_code = pause_after_code
        self._started = False
        self._paused = False
        self._remainder = ""
        self._last_code_block: BaseBlock | None = None
        self._state = _FenceState.PROSE
        self._pending_buffer = ""  # Text to add to current block
        self._chunk_buffer = ""  # Accumulates text for current chunk to display
        self._current_lang = "bash"
        self._current_close_tag = "</shell>"  # Closing tag to look for in CODE state
        self._current_block: BaseBlock | None = (
            None  # The block we're currently appending to
        )
        self.all_blocks: list[BaseBlock] = []
        self.first_assistant_block: AssistantOutputBlock | None = None
        self._current_line_buffer = (
            ""  # Tracks current line in PROSE for blank line detection
        )
        self._strip_leading_whitespace = False  # Strip whitespace after closing tags
        self._current_thinking_close_tag = "</think>"  # Tracks which close tag to match
        # Backtick tracking - skip tag detection inside inline code spans
        self._in_backtick = False
        self._backtick_count = 0  # Counts consecutive backticks for opening
        self._backtick_closer = 0  # Number of backticks needed to close
        # Tag detection
        self._tag_buffer = ""  # Buffer for detecting tags
        # Factory methods for block creation (can be overridden for testing)
        self._make_prose_block = lambda activity: AssistantOutputBlock(
            activity=activity
        )
        self._make_code_block = lambda code, lang: CodeInputBlock(
            code,
            language=lang,
            show_loading=False,
            in_context=True,
            command_number=self._output.next_command_number(),
        )
        self._make_thinking_block = lambda: ThinkingOutputBlock(activity=True)

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
        """Create the initial AssistantOutputBlock for streaming prose.

        Idempotent — safe to call multiple times; only the first call has effect.
        """
        if self._started:
            return
        self._started = True
        self._current_block = self._make_prose_block(activity=True)
        self._output.append_block(self._current_block)
        self.all_blocks.append(self._current_block)
        self.first_assistant_block = self._current_block

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
                # stripping any trailing junk on the same line as the closing tag
                raw_remainder = text[i + 1:]
                newline_pos = raw_remainder.find("\n")
                if newline_pos >= 0:
                    self._remainder = raw_remainder[newline_pos + 1:]
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
        elif self._state == _FenceState.THINKING:
            self._feed_thinking(ch)

    def _flush_tag_buffer_to_pending(self) -> None:
        """Flush accumulated tag buffer (that wasn't a complete tag) to the pending buffer."""
        if self._tag_buffer:
            self._pending_buffer += self._tag_buffer
            self._tag_buffer = ""

    def _check_tags(self, ch: str, targets: list[str]) -> str | bool:
        """Accumulate characters between < and >, then normalize and check targets.

        Handles liberal tag syntax:
        - Whitespace inside tags: < shell >, < /python >
        - Namespace prefixes: <minimax:tool_call>, <ns:shell>
        - Aliases: <tool_call> treated as <shell>

        Returns:
            str: The canonical matched tag string if a complete tag was detected.
            True: Still accumulating (haven't seen '>' yet).
            False: No match (buffer was flushed to pending).
        """
        self._tag_buffer += ch

        if ch == ">":
            # Complete tag — normalize and check
            canonical = self._normalize_tag(self._tag_buffer)
            if canonical and canonical in targets:
                self._tag_buffer = ""
                return canonical
            # Not a matching tag — flush raw text to pending
            self._flush_tag_buffer_to_pending()
            return False

        # Bail on a second '<' (means the first wasn't a real tag)
        if ch == "<" and len(self._tag_buffer) > 1:
            # Flush everything except the new '<', which starts a new potential tag
            old = self._tag_buffer[:-1]
            self._tag_buffer = "<"
            self._pending_buffer += old
            return True  # Still accumulating from the new '<'

        # Bail on newline inside a tag
        if ch == "\n":
            self._flush_tag_buffer_to_pending()
            return False

        # Bail if buffer is too long
        if len(self._tag_buffer) > _MAX_TAG_LEN:
            self._flush_tag_buffer_to_pending()
            return False

        return True

    @staticmethod
    def _normalize_tag(raw_tag: str) -> str | None:
        """Normalize a raw tag like '< minimax:tool_call >' to canonical '<shell>'.

        Strips outer angle brackets, whitespace, namespace prefixes, and maps aliases.
        """
        inner = raw_tag[1:-1].strip()  # Strip < > and whitespace

        # Handle closing tag
        is_closing = inner.startswith("/")
        if is_closing:
            inner = inner[1:].strip()

        # Strip namespace prefix (e.g. "minimax:tool_call" -> "tool_call")
        if ":" in inner:
            inner = inner.split(":", 1)[1].strip()

        # Map aliases
        name = _TAG_NAME_ALIASES.get(inner, inner)

        if is_closing:
            return f"</{name}>"
        return f"<{name}>"

    def _flush_and_update_chunk(self) -> None:
        """Flush pending text and update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
            self._chunk_buffer = ""

    def _handle_backtick(self, ch: str) -> bool:
        """Track backtick spans. Returns True if the character was consumed."""
        if ch == "`":
            if self._in_backtick:
                # Inside a backtick span - count consecutive backticks
                self._backtick_count += 1
                if self._backtick_count >= self._backtick_closer:
                    # Closing backtick sequence found
                    self._in_backtick = False
                    self._backtick_count = 0
                    self._backtick_closer = 0
                return False  # Still add to pending buffer
            else:
                # Not inside a span - count opening backticks
                self._backtick_count += 1
                return False
        else:
            if not self._in_backtick and self._backtick_count > 0:
                # We had backticks followed by non-backtick - enter backtick span
                self._backtick_closer = self._backtick_count
                self._backtick_count = 0
                self._in_backtick = True
            elif self._in_backtick:
                # Non-backtick inside span - reset consecutive backtick count
                self._backtick_count = 0
            return False

    def _feed_prose(self, ch: str) -> None:
        """Process prose text, looking for opening code tags or think tag."""
        # Strip leading whitespace after closing tags
        if self._strip_leading_whitespace:
            if ch.isspace():
                return
            self._strip_leading_whitespace = False

        # Track backtick spans
        self._handle_backtick(ch)

        # Check for tags (<think>, <python>, <shell>) - skip inside backtick spans
        if not self._in_backtick and (self._tag_buffer or ch == "<"):
            result = self._check_tags(ch, _PROSE_TAG_TARGETS)
            if result in ("<think>", "<detail>"):
                # Complete thinking/detail tag detected
                self._flush_pending_to_chunk()
                self._flush_and_update_chunk()

                # Mark current prose block as complete
                if isinstance(self._current_block, AssistantOutputBlock):
                    self._current_block.mark_success()

                # Track which close tag to match
                self._current_thinking_close_tag = (
                    "</think>" if result == "<think>" else "</detail>"
                )

                # Create new thinking block
                self._current_block = self._make_thinking_block()
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

                self._current_line_buffer = ""
                self._state = _FenceState.THINKING
            elif isinstance(result, str) and result in _CODE_OPEN_TAGS:
                # Complete code opening tag detected
                lang = _CODE_OPEN_TAGS[result]
                self._current_lang = lang
                self._current_close_tag = _CODE_CLOSE_TAGS[lang]

                self._flush_pending_to_chunk()
                self._flush_and_update_chunk()

                # Remove empty prose block, or mark it complete
                current_is_empty = (
                    isinstance(self._current_block, AssistantOutputBlock)
                    and not self._current_block._full.strip()
                )
                if current_is_empty:
                    if self._current_block is self.first_assistant_block:
                        self.first_assistant_block = None
                    if self._current_block is not None:
                        self._remove_block(self._current_block)
                elif isinstance(self._current_block, AssistantOutputBlock):
                    self._current_block.mark_success()

                # Create new code block
                self._current_block = self._make_code_block("", lang)
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

                self._pending_buffer = ""
                self._current_line_buffer = ""
                self._state = _FenceState.CODE
            return

        # Check for empty lines to split blocks
        if ch == "\n":
            # Add newline to pending buffer
            self._pending_buffer += ch

            # Check if the line we just completed was empty/whitespace-only
            if self._current_line_buffer.strip() == "":
                # Empty line detected - split to new block
                self._flush_pending_to_chunk()
                self._flush_and_update_chunk()

                # Mark current prose block as complete
                if isinstance(self._current_block, AssistantOutputBlock):
                    self._current_block.mark_success()

                # Create new prose block
                self._current_block = self._make_prose_block(activity=True)
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

            # Reset line buffer for next line
            self._current_line_buffer = ""
        else:
            self._pending_buffer += ch
            self._current_line_buffer += ch

    def _feed_code(self, ch: str) -> None:
        """Process code text, looking for closing tag (</python> or </shell>)."""
        # Check for closing tag
        if self._tag_buffer or ch == "<":
            result = self._check_tags(ch, [self._current_close_tag])
            if isinstance(result, str):
                # Found closing tag - flush pending code and transition
                self._flush_pending_to_chunk()
                self._flush_and_update_chunk()

                # Capture as the last completed code block
                if isinstance(self._current_block, CodeInputBlock):
                    self._last_code_block = self._current_block
                    self._current_block.finish_streaming()

                # Start new prose block
                self._current_block = self._make_prose_block(activity=True)
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

                self._current_line_buffer = ""
                self._strip_leading_whitespace = True
                self._state = _FenceState.PROSE

                # Pause after code block if enabled
                if self._pause_after_code:
                    self._paused = True
            return

        # Regular code character
        self._pending_buffer += ch

    def _feed_thinking(self, ch: str) -> None:
        """Process thinking text, looking for closing </think> or </detail> tag."""
        # Check for the matching close tag
        if self._tag_buffer or ch == "<":
            result = self._check_tags(ch, [self._current_thinking_close_tag])
            if result == self._current_thinking_close_tag:
                # Complete </think> tag detected
                self._flush_pending_to_chunk()
                self._flush_and_update_chunk()

                # Mark thinking block as complete
                if isinstance(self._current_block, ThinkingOutputBlock):
                    self._current_block.mark_success()

                # Start new prose block
                self._current_block = self._make_prose_block(activity=True)
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

                self._current_line_buffer = ""
                self._strip_leading_whitespace = True
                self._state = _FenceState.PROSE
            return

        # Check for empty lines to split thinking blocks
        if ch == "\n":
            # Add newline to pending buffer
            self._pending_buffer += ch

            # Check if the line we just completed was empty/whitespace-only
            # Only split if the current block has accumulated some content
            if self._current_line_buffer.strip() == "":
                # Check if current thinking block has content (including pending)
                current_has_content = (
                    isinstance(self._current_block, ThinkingOutputBlock)
                    and (self._current_block._full.strip() or self._pending_buffer.strip())
                )

                if current_has_content:
                    # Empty line detected - split to new thinking block
                    self._flush_pending_to_chunk()
                    self._flush_and_update_chunk()

                    # Mark current thinking block as complete
                    if isinstance(self._current_block, ThinkingOutputBlock):
                        self._current_block.mark_success()

                    # Create new thinking block
                    self._current_block = self._make_thinking_block()
                    self._output.append_block(self._current_block)
                    self.all_blocks.append(self._current_block)

            # Reset line buffer for next line
            self._current_line_buffer = ""
        else:
            self._pending_buffer += ch
            self._current_line_buffer += ch

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
            elif isinstance(self._current_block, (AssistantOutputBlock, ThinkingOutputBlock)):
                self._current_block.append(self._chunk_buffer)
                self._current_block.flush()

    def _remove_block(self, block: BaseBlock) -> None:
        """Remove a block from tracking lists and the DOM."""
        if block in self.all_blocks:
            self.all_blocks.remove(block)
        self._output.remove_block(block)

    def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        # Ensure start() was called (handles empty stream edge case)
        self.start()

        # Flush any incomplete tag buffer
        self._flush_tag_buffer_to_pending()

        # Flush any remaining text ONLY if there's pending content
        if self._pending_buffer:
            self._flush_pending_to_chunk()
            if self._chunk_buffer and self._current_block:
                self._update_current_block_with_chunk()
                self._chunk_buffer = ""  # Clear to avoid double-processing

        # Mark the last block as complete
        if isinstance(self._current_block, AssistantOutputBlock):
            self._current_block.flush()  # Ensure final content is rendered
            self._current_block.mark_success()
        elif isinstance(self._current_block, ThinkingOutputBlock):
            self._current_block.flush()
            self._current_block.mark_success()

        # Finalize all blocks: switch from streaming mode to final rendering
        for block in self.all_blocks:
            if isinstance(block, CodeInputBlock):
                block.finish_streaming()
            elif isinstance(block, AssistantOutputBlock):
                block.flush()  # Ensure all content is rendered before finalizing
                block.finalize_streaming()
            elif isinstance(block, ThinkingOutputBlock):
                block.flush()
                block.finalize_streaming()

        # Remove empty AssistantOutputBlocks (keep first_assistant_block for status indicator)
        for block in [
            b
            for b in self.all_blocks
            if isinstance(b, AssistantOutputBlock)
            and b is not self.first_assistant_block
            and not b._full.strip()
        ]:
            self._remove_block(block)

        # Save all blocks to session now that they're finalized
        if self._save_callback:
            for block in self.all_blocks:
                self._save_callback(block)
