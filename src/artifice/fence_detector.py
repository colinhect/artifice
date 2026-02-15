"""Main Artifice terminal widget."""

from __future__ import annotations

import enum

from .string_tracker import StringTracker

from .terminal_output import (
    TerminalOutput,
    AssistantOutputBlock,
    ThinkingOutputBlock,
    CodeInputBlock,
    BaseBlock,
)

_LANG_ALIASES = {"py": "python", "shell": "bash", "sh": "bash", "zsh": "bash"}


class _FenceState(enum.Enum):
    PROSE = "prose"
    LANG_LINE = "lang_line"
    CODE = "code"
    THINKING = "thinking"


class StreamingFenceDetector:
    """Detects code fences in streaming text and splits into blocks in real-time.

    Processes chunks character-by-character using a 3-state machine:
    PROSE -> LANG_LINE (on ```) -> CODE (on newline) -> PROSE (on closing ```)

    Creates blocks as fences are detected, accumulating text to update once per chunk.
    """

    def __init__(self, output: TerminalOutput, auto_scroll, save_callback=None) -> None:
        self._output = output
        self._auto_scroll = auto_scroll
        self._save_callback = save_callback  # Callback to save blocks to session
        self._state = _FenceState.PROSE
        self._backtick_count = 0
        self._lang_buffer = ""
        self._pending_buffer = ""  # Text to add to current block
        self._chunk_buffer = ""  # Accumulates text for current chunk to display
        self._current_lang = "bash"
        self._current_block: BaseBlock | None = (
            None  # The block we're currently appending to
        )
        self.all_blocks: list[BaseBlock] = []
        self.first_assistant_block: AssistantOutputBlock | None = None
        self._string_tracker = StringTracker()
        self._current_line_buffer = (
            ""  # Tracks current line in PROSE for blank line detection
        )
        # Think tag detection
        self._tag_buffer = ""  # Buffer for detecting <think> and </think> tags
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

    def start(self) -> None:
        """Create the initial AssistantOutputBlock for streaming prose."""
        self._current_block = self._make_prose_block(activity=True)
        self._output.append_block(self._current_block)
        self.all_blocks.append(self._current_block)
        self.first_assistant_block = self._current_block

    def feed(self, text: str) -> None:
        """Process a chunk of streaming text, creating blocks as needed."""
        self._chunk_buffer = ""  # Reset for this chunk
        for ch in text:
            self._feed_char(ch)
        # Flush any pending text to the chunk buffer for display
        self._flush_pending_to_chunk()
        # Update current block with accumulated chunk text
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
            self._chunk_buffer = ""  # Clear after updating to avoid reprocessing

    def _feed_char(self, ch: str) -> None:
        if self._state == _FenceState.PROSE:
            self._feed_prose(ch)
        elif self._state == _FenceState.LANG_LINE:
            self._feed_lang_line(ch)
        elif self._state == _FenceState.CODE:
            self._feed_code(ch)
        elif self._state == _FenceState.THINKING:
            self._feed_thinking(ch)

    def _flush_backticks_to_pending(self) -> None:
        """Flush accumulated backticks (that weren't a fence) to the pending buffer."""
        if self._backtick_count > 0:
            self._pending_buffer += "`" * self._backtick_count
            self._backtick_count = 0

    def _flush_tag_buffer_to_pending(self) -> None:
        """Flush accumulated tag buffer (that wasn't a complete tag) to the pending buffer."""
        if self._tag_buffer:
            self._pending_buffer += self._tag_buffer
            self._tag_buffer = ""

    def _check_tag_match(self, ch: str, target: str) -> bool:
        """Check if ch continues building toward target tag.

        Returns True if we should continue accumulating, False if there's a mismatch.
        If we complete the tag, returns True and transitions state.
        """
        self._tag_buffer += ch

        # Check if tag_buffer is a prefix of target
        if not target.startswith(self._tag_buffer):
            # Mismatch - flush and return False
            self._flush_tag_buffer_to_pending()
            return False

        # Check if we completed the tag
        if self._tag_buffer == target:
            return True

        # Still building the tag
        return True

    def _flush_and_update_chunk(self) -> None:
        """Flush pending text and update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
            self._chunk_buffer = ""

    def _feed_prose(self, ch: str) -> None:
        """Process prose text, looking for opening fence or think tag."""
        # Check for code fence
        if ch == "`":
            self._backtick_count += 1
            if self._backtick_count == 3:
                # Found opening fence - flush pending prose and transition
                # Flush pending without the backticks
                self._flush_pending_to_chunk()
                self._backtick_count = 0
                self._lang_buffer = ""
                self._current_line_buffer = ""  # Reset line tracking
                self._state = _FenceState.LANG_LINE
            return

        # Not a backtick - flush any accumulated backticks
        self._flush_backticks_to_pending()

        # Check for <think> tag
        if self._tag_buffer or ch == "<":
            if self._check_tag_match(ch, "<think>"):
                if self._tag_buffer == "<think>":
                    # Complete <think> tag detected
                    self._tag_buffer = ""
                    self._flush_pending_to_chunk()
                    self._flush_and_update_chunk()

                    # Mark current prose block as complete
                    if isinstance(self._current_block, AssistantOutputBlock):
                        self._current_block.mark_success()

                    # Create new thinking block
                    self._current_block = self._make_thinking_block()
                    self._output.append_block(self._current_block)
                    self.all_blocks.append(self._current_block)

                    self._current_line_buffer = ""
                    self._state = _FenceState.THINKING
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

    def _feed_lang_line(self, ch: str) -> None:
        """Process language line after opening fence."""
        if ch == "\n":
            # Language line complete - start code block
            lang = self._lang_buffer.strip() or "bash"
            # Normalize language aliases
            lang = _LANG_ALIASES.get(lang, lang)
            self._current_lang = lang

            # Update current block with accumulated chunk
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
            self._state = _FenceState.CODE
        else:
            self._lang_buffer += ch

    def _feed_code(self, ch: str) -> None:
        """Process code text, looking for closing fence (but not in strings)."""
        # Track string literals to avoid detecting fences inside strings
        self._string_tracker.track(ch)

        # Only detect fences when not inside a string literal
        if not self._string_tracker.in_string and ch == "`":
            self._backtick_count += 1
            if self._backtick_count == 3:
                # Found closing fence - flush pending code and transition
                self._flush_pending_to_chunk()

                # Update code block with accumulated chunk
                self._flush_and_update_chunk()

                self._backtick_count = 0
                # Reset string tracking for next code block
                self._string_tracker.reset()

                # Start new prose block
                if isinstance(self._current_block, CodeInputBlock):
                    self._current_block.finish_streaming()
                self._current_block = self._make_prose_block(activity=True)
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

                self._current_line_buffer = (
                    ""  # Reset line tracking for new prose block
                )
                self._state = _FenceState.PROSE
            # Don't add character to pending buffer yet - we're accumulating backticks
        else:
            # Not a backtick, or we're in a string
            self._flush_backticks_to_pending()
            # Always add the current character
            self._pending_buffer += ch

    def _feed_thinking(self, ch: str) -> None:
        """Process thinking text, looking for closing </think> tag."""
        # Check for </think> tag
        if self._tag_buffer or ch == "<":
            if self._check_tag_match(ch, "</think>"):
                if self._tag_buffer == "</think>":
                    # Complete </think> tag detected
                    self._tag_buffer = ""
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
        if block in self._output._blocks:
            self._output._blocks.remove(block)
        block.remove()

    def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        # Handle incomplete fences
        if self._state == _FenceState.LANG_LINE:
            self._pending_buffer = "```" + self._lang_buffer
            self._state = _FenceState.PROSE

        # Handle incomplete think tags
        if self._state == _FenceState.THINKING:
            # If we're still in thinking state, treat remaining content as thinking
            # (the closing tag may come later or be missing)
            pass

        # Flush trailing backticks that weren't a complete fence
        if self._backtick_count > 0:
            self._pending_buffer += "`" * self._backtick_count
            self._backtick_count = 0

        # Flush any incomplete tag buffer
        self._flush_tag_buffer_to_pending()

        # Flush any remaining text ONLY if there's pending content
        # Don't flush _chunk_buffer as it was already processed by _process_chunk_buffer()
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
