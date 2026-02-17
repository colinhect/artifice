"""Streaming fence detector for code block extraction."""

from __future__ import annotations

import enum

from .terminal_output import (
    TerminalOutput,
    AssistantOutputBlock,
    ThinkingOutputBlock,
    CodeInputBlock,
    BaseBlock,
)
from .tag_parser import TagParser
from .backtick_tracker import BacktickTracker

_CODE_OPEN_TAGS = {"<python>": "python", "<shell>": "bash"}
_CODE_CLOSE_TAGS = {"python": "</python>", "bash": "</shell>"}
_PROSE_TAG_TARGETS = ["<think>", "<detail>", "<python>", "<shell>"]


class _FenceState(enum.Enum):
    PROSE = "prose"
    CODE = "code"
    THINKING = "thinking"


class StreamingFenceDetector:
    """Detects code tags in streaming text and splits into blocks in real-time.

    Processes chunks character-by-character using a state machine:
    PROSE -> CODE (on <python>/<shell> or ```language) -> PROSE (on </python>/</shell> or ```)
    PROSE -> THINKING (on <think>) -> PROSE (on </think>)

    Creates blocks as tags are detected, accumulating text to update once per chunk.
    """

    def __init__(
        self, output: TerminalOutput, save_callback=None, pause_after_code: bool = False
    ) -> None:
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
        # Tag detection and backtick tracking
        self._tag_parser = TagParser()
        self._backtick_tracker = BacktickTracker()
        # Markdown fence detection
        self._in_markdown_fence = False  # True if we entered CODE via markdown fence
        self._fence_backtick_count = 0  # Count backticks for fence detection
        self._fence_language_buffer = ""  # Accumulate language after ```
        self._detecting_fence_open = False  # True when we've seen ``` and reading language
        self._detecting_fence_close = False  # True when we might be seeing closing ```
        self._fence_close_backtick_count = 0  # Count backticks for closing fence
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
        elif self._state == _FenceState.THINKING:
            self._feed_thinking(ch)

    def _check_tags(self, ch: str, targets: list[str]) -> str | bool:
        """Check for matching tags using the tag parser.

        Returns:
            str: The canonical matched tag string if detected.
            True: Still accumulating (haven't seen '>' yet).
            False: No match (need to add buffered text to pending).
        """
        result = self._tag_parser.feed_char(ch, targets)

        # If False, flush the tag buffer to pending (unless it's a second '<')
        if result is False:
            if ch == "<" and len(self._tag_parser._buffer) > 1:
                # Flush everything except the new '<'
                old_buffer = self._tag_parser._buffer[:-1]
                self._tag_parser._buffer = "<"
                self._pending_buffer += old_buffer
                return True  # Still accumulating from the new '<'
            else:
                # Flush everything including the failed tag attempt
                self._pending_buffer += self._tag_parser.flush_to_text()

        return result

    def _flush_and_update_chunk(self) -> None:
        """Flush pending text and update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
            self._chunk_buffer = ""

    def _handle_backtick(self, ch: str) -> None:
        """Track backtick spans using the backtick tracker."""
        self._backtick_tracker.feed(ch)

    def _feed_prose(self, ch: str) -> None:
        """Process prose text, looking for opening code tags, think tag, or markdown fences."""
        # Strip leading whitespace after closing tags
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

                self._current_lang = lang
                self._in_markdown_fence = True
                self._detecting_fence_open = False
                self._fence_language_buffer = ""

                # Don't include the backticks or language in the prose
                # (they're already been skipped via not adding to pending_buffer)
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
                # Don't add the backticks to pending buffer
            # Don't feed to backtick tracker yet - wait to see if it's a fence
            return
        elif self._fence_backtick_count > 0:
            # We had some backticks but didn't reach 3, or got interrupted
            # Feed them to the backtick tracker and add to pending buffer
            for _ in range(self._fence_backtick_count):
                self._backtick_tracker.feed("`")
            self._pending_buffer += "`" * self._fence_backtick_count
            self._fence_backtick_count = 0
            # Continue processing current character normally

        # Track backtick spans for inline code (not fences)
        if ch != "`":  # Already handled backticks above
            self._handle_backtick(ch)

        # Check for tags (<think>, <python>, <shell>) - skip inside backtick spans
        if not self._backtick_tracker.in_span and (
            self._tag_parser.has_buffered or ch == "<"
        ):
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
        """Process code text, looking for closing tag (</python> or </shell>) or closing fence (```)."""
        # If we're in a markdown fence, look for closing ``` at start of line
        if self._in_markdown_fence:
            if ch == "`":
                # Check if we're at start of line before starting fence close detection
                # We need to look at pending_buffer to see what's on the current line
                # Split by newline and check if the last line (current line) is whitespace-only
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

                        # Mark as last completed code block
                        if isinstance(self._current_block, CodeInputBlock):
                            self._last_code_block = self._current_block
                            self._current_block.finish_streaming()

                        # Reset fence state
                        self._in_markdown_fence = False
                        self._fence_close_backtick_count = 0

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
                    # Don't add backtick to pending - we're accumulating them for fence detection
                    return
                else:
                    # Backtick not at start of line - it's part of code content
                    # First, add any accumulated fence-close backticks from start of line
                    if self._fence_close_backtick_count > 0:
                        self._pending_buffer += "`" * self._fence_close_backtick_count
                        self._fence_close_backtick_count = 0
                    # Add current backtick as regular code content
                    self._pending_buffer += ch
                    return
            elif self._fence_close_backtick_count > 0:
                # We had some backticks at start of line but got interrupted by non-backtick
                # Add them as code content
                self._pending_buffer += "`" * self._fence_close_backtick_count
                self._fence_close_backtick_count = 0
                # Fall through to add current character

        # Check for XML closing tag (if not in markdown fence)
        if not self._in_markdown_fence and (
            self._tag_parser.has_buffered or ch == "<"
        ):
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
        if self._tag_parser.has_buffered or ch == "<":
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
                current_has_content = isinstance(
                    self._current_block, ThinkingOutputBlock
                ) and (
                    self._current_block._full.strip() or self._pending_buffer.strip()
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
            elif isinstance(
                self._current_block, (AssistantOutputBlock, ThinkingOutputBlock)
            ):
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
        if self._tag_parser.has_buffered:
            self._pending_buffer += self._tag_parser.flush_to_text()

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
