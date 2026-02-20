"""Streaming fence detector for code block extraction."""

from __future__ import annotations

from artifice.ui.components.blocks.blocks import (
    AgentOutputBlock,
    BaseBlock,
    CodeInputBlock,
)
from artifice.ui.components.blocks.factory import BlockFactory
from artifice.ui.components.output import TerminalOutput
from artifice.utils.fencing import FenceParser, FenceState


class StreamingFenceDetector:
    """Detects code fences in streaming text and splits into blocks in real-time.

    Uses a FenceParser for pure parsing logic, handling UI coordination
    separately. Processes chunks character-by-character:
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
        self._current_block: BaseBlock | None = None
        self._pending_prose_text: str = ""  # Text accumulated for current prose block
        self._pending_code_text: str = ""  # Text accumulated for current code block
        self._pending_prose_dirty: bool = False  # Whether prose needs flush
        self._pending_code_dirty: bool = False  # Whether code needs flush

        # Create parser with callbacks for state transitions
        self._parser = FenceParser(
            on_code_start=self._on_code_start,
            on_code_end=self._on_code_end,
        )
        self._current_code_block: CodeInputBlock | None = (
            None  # Track current code block for updates
        )

        # Factory methods for block creation (can be overridden for testing)
        self._make_prose_block = lambda activity: AgentOutputBlock(activity=activity)
        self._make_code_block = lambda code, lang: CodeInputBlock(
            code,
            language=lang,
            show_loading=False,
            in_context=True,
        )

    # Callbacks for parser state transitions
    def _on_code_start(self, lang: str) -> None:
        """Handle transition from PROSE to CODE state.

        Called by the parser when a code fence is detected.
        The prose text has already been flushed by the parser.
        """
        # Flush any pending prose text to the current block
        if self._pending_prose_text and isinstance(
            self._current_block, AgentOutputBlock
        ):
            self._current_block.append(self._pending_prose_text)
            self._current_block.flush()
            self._current_block.mark_success()
        self._pending_prose_text = ""
        self._pending_prose_dirty = False

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
        self._current_code_block = self._current_block  # Track for updates
        self._pending_code_text = ""
        self._pending_code_dirty = False

    def _on_code_end(self, code_text: str) -> None:
        """Handle transition from CODE to PROSE state.

        Called by the parser when a closing fence is detected.
        Receives the code text that was in the block.
        """
        # Flush any pending code text + the received code text to the current block
        full_code = self._pending_code_text + code_text
        if full_code and isinstance(self._current_block, CodeInputBlock):
            existing = self._current_block.get_code()
            # Apply final syntax highlight at the end of code block
            self._current_block.update_code(existing + full_code)
        self._pending_code_text = ""
        self._pending_code_dirty = False

        # Capture as the last completed code block
        if isinstance(self._current_block, CodeInputBlock):
            self._last_code_block = self._current_block
            self._current_block.finish_streaming()

        # Clear current code block tracking
        self._current_code_block = None

        # Start new prose block
        self._current_block = self._create_and_mount_prose(activity=True)
        self._pending_prose_text = ""
        self._pending_prose_dirty = False

        # Pause after code block if enabled
        if self._pause_after_code:
            self._paused = True
            self._parser.pause()  # Also pause the parser so it saves the remainder

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
        self._parser.resume()  # Clear parser remainder
        if self._remainder:
            remainder = self._remainder
            self._remainder = ""
            self.feed(remainder)

    def start(self) -> None:
        """Create the initial AgentOutputBlock for streaming prose.

        Idempotent -- safe to call multiple times; only the first call has effect.
        """
        if self._started:
            return
        self._started = True
        self._parser.start()
        self._current_block = self._create_and_mount_prose(activity=True)
        self._factory.first_agent_block = self._current_block

    def _create_and_mount_prose(self, activity: bool = True) -> AgentOutputBlock:
        """Create a prose block using the factory or test override."""
        block = self._make_prose_block(activity)
        self._output.append_block(block, scroll=False)
        self._factory.all_blocks.append(block)
        return block

    def _create_and_mount_code(self, code: str, lang: str) -> CodeInputBlock:
        """Create a code block using the factory or test override."""
        block = self._make_code_block(code, lang)
        self._output.append_block(block, scroll=False)
        self._factory.all_blocks.append(block)
        return block

    def feed(self, text: str) -> None:
        """Process a chunk of streaming text, creating blocks as needed.

        If pause_after_code is enabled and a code block closes, processing
        stops early and remaining text is saved in _remainder.
        """
        # Feed to parser and handle results
        results = self._parser.feed(text)

        for chunk in results:
            if chunk.is_code_block_start:
                # Transition already handled by callback, but we need to handle the prose text
                # The text in this chunk is the prose that triggered the transition
                if chunk.text and self._current_block:
                    # Add to the OLD prose block (before transition happened)
                    if isinstance(self._current_block, AgentOutputBlock):
                        self._current_block.append(chunk.text)
                        self._pending_prose_dirty = True
            elif chunk.is_code_block_end:
                # Code block completed - text already handled in _on_code_end callback
                # No need to process here since callback receives code_text directly
                pass
            else:
                # Regular prose or code text - accumulate based on state
                if chunk.state == FenceState.PROSE:
                    self._pending_prose_text += chunk.text
                    self._pending_prose_dirty = True
                    # Check for empty line finalization - only check the end of buffer
                    if "\n\n" in self._pending_prose_text:
                        # Find the last empty line to split on
                        last_empty = self._pending_prose_text.rfind("\n\n")
                        if last_empty >= 0:
                            before_empty = self._pending_prose_text[: last_empty + 1]
                            after_empty = self._pending_prose_text[last_empty + 2 :]

                            # Flush what we have so far
                            if before_empty and isinstance(
                                self._current_block, AgentOutputBlock
                            ):
                                self._current_block.append(before_empty)
                                self._current_block.finalize_streaming()
                                self._current_block.mark_success()

                            # Create new prose block
                            self._current_block = self._create_and_mount_prose(
                                activity=True
                            )
                            self._pending_prose_text = after_empty
                            self._pending_prose_dirty = bool(after_empty)
                else:  # CODE state
                    self._pending_code_text += chunk.text
                    self._pending_code_dirty = True

        # Handle pause and remainder
        if self._parser.is_paused:
            self._paused = True
            # Save the remainder from parser (don't call resume which clears it)
            self._remainder = self._parser.remainder

        # Batch flush all pending text at the end of the feed call
        self._flush_pending()

    def _flush_pending(self) -> None:
        """Flush any pending text to the UI in a single batch."""
        # Flush prose text
        if self._pending_prose_dirty and self._pending_prose_text:
            if isinstance(self._current_block, AgentOutputBlock):
                self._current_block.append(self._pending_prose_text)
                self._current_block.flush()
            self._pending_prose_text = ""
            self._pending_prose_dirty = False

        # Flush code text
        if self._pending_code_dirty and self._pending_code_text:
            if isinstance(self._current_block, CodeInputBlock):
                existing = self._current_block.get_code()
                full_code = existing + self._pending_code_text
                self._current_block.update_code(full_code)
            self._pending_code_text = ""
            self._pending_code_dirty = False

    def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        # Ensure start() was called (handles empty stream edge case)
        self.start()

        # Flush any pending text from parser
        remainder = self._parser.finish()
        if remainder:
            if self._parser.current_state == FenceState.PROSE:
                self._pending_prose_text += remainder
                self._pending_prose_dirty = True
            else:
                self._pending_code_text += remainder
                self._pending_code_dirty = True

        # Flush any accumulated text using the batched flush method
        self._flush_pending()

        # Mark the last block as complete
        if isinstance(self._current_block, AgentOutputBlock):
            self._current_block.mark_success()

        # Finalize all blocks: switch from streaming mode to final rendering
        for block in self._factory.all_blocks:
            if isinstance(block, CodeInputBlock):
                # Apply final syntax highlighting at the end
                block.update_code(block.get_code())
                block.finish_streaming()
            elif isinstance(block, AgentOutputBlock):
                block.finalize_streaming()

        # Remove empty AgentOutputBlocks
        for block in [
            b
            for b in self._factory.all_blocks
            if isinstance(b, AgentOutputBlock) and not b._output_str.strip()
        ]:
            if block is self._factory.first_agent_block:
                self._factory.first_agent_block = None
            self._factory.remove_block(block)
