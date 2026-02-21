"""Streaming text handler that splits on markdown headers.

Each time a markdown header is encountered (# ## ### etc.), it starts a new block.
The header line is the first content in the new block, and the previous one is finished streaming.
"""

from __future__ import annotations

import re
from artifice.ui.components.blocks.blocks import AgentOutputBlock
from artifice.ui.components.blocks.factory import BlockFactory
from artifice.ui.components.output import TerminalOutput


# Match markdown headers: 1-6 # chars at start of line followed by space or end
HEADER_PATTERN = re.compile(r"^(#{1,6})(\s|$)")


class StreamingFenceDetector:
    """Streams text into AgentOutputBlocks, splitting on markdown headers.

    Whenever a markdown header starts at the beginning of a new line, it creates
    a new output block. The header line becomes the first content in the new block,
    and the previous block is finalized.
    """

    def __init__(self, output: TerminalOutput, pause_after_code: bool = False) -> None:
        self._output = output
        self._factory = BlockFactory(output)
        self._started = False
        self._current_block: AgentOutputBlock | None = None
        self._incomplete_line: str = ""  # Buffer for line being built
        self._block_has_content: bool = False  # Track if current block has content

        # Factory method for block creation (can be overridden for testing)
        self._make_prose_block = lambda activity: AgentOutputBlock(activity=activity)

    @property
    def all_blocks(self) -> list[AgentOutputBlock]:
        """All blocks created by this detector."""
        return self._factory.all_blocks  # type: ignore[return-value]

    @property
    def first_agent_block(self) -> AgentOutputBlock | None:
        """The first agent output block."""
        return self._factory.first_agent_block

    @first_agent_block.setter
    def first_agent_block(self, value: AgentOutputBlock | None) -> None:
        self._factory.first_agent_block = value

    def start(self) -> None:
        """Create the initial AgentOutputBlock for streaming.

        Idempotent -- safe to call multiple times; only the first call has effect.
        """
        if self._started:
            return
        self._started = True
        self._current_block = self._create_and_mount_prose(activity=True)
        self._factory.first_agent_block = self._current_block
        self._block_has_content = False

    def _create_and_mount_prose(self, activity: bool = True) -> AgentOutputBlock:
        """Create a prose block using the factory or test override."""
        block = self._make_prose_block(activity)
        self._output.append_block(block, scroll=False)
        self._factory.all_blocks.append(block)
        return block

    def _is_header_line(self, line: str) -> bool:
        """Check if a line is a markdown header.

        A markdown header is 1-6 # characters at the start of a line,
        followed by a space or end of line.
        """
        if not line:
            return False
        return HEADER_PATTERN.match(line) is not None

    async def feed(self, text: str) -> None:
        """Process a chunk of streaming text, splitting on headers.

        Text is accumulated line by line. When a line starting with a markdown
        header is encountered (and the current block has content), a new block
        is created and the header starts that new block.
        """
        if not text or self._current_block is None:
            return

        i = 0
        while i < len(text):
            # Find next newline
            newline_pos = text.find("\n", i)

            if newline_pos == -1:
                # No newline found - add remainder to incomplete line buffer
                self._incomplete_line += text[i:]
                break

            # Found a newline - complete the line
            line = self._incomplete_line + text[i:newline_pos]
            self._incomplete_line = ""

            # Check if this line is a header and we have content
            if self._is_header_line(line) and self._block_has_content:
                # Finalize current block
                self._current_block.finalize_streaming()
                self._current_block.mark_success()

                # Create new block starting with this header line
                self._current_block = self._create_and_mount_prose(activity=True)
                self._block_has_content = False

            # Add the line (plus newline) to current block
            line_with_newline = line + "\n"
            await self._current_block.append(line_with_newline)
            self._block_has_content = True

            i = newline_pos + 1

    async def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        # Ensure start() was called (handles empty stream edge case)
        self.start()

        # Flush any remaining incomplete line
        if self._incomplete_line and self._current_block is not None:
            # Check if incomplete line is a header
            if self._is_header_line(self._incomplete_line) and self._block_has_content:
                # Finalize current block first
                self._current_block.finalize_streaming()
                self._current_block.mark_success()
                # Create new block with header
                self._current_block = self._create_and_mount_prose(activity=True)
                self._block_has_content = False

            # Append the incomplete line
            await self._current_block.append(self._incomplete_line)
            self._block_has_content = True

        # Mark the current block as complete and finalize streaming
        if self._current_block is not None:
            self._current_block.mark_success()
            self._current_block.finalize_streaming()

    def resume(self) -> None:
        """No-op: resume is not needed in the simplified version."""
        pass

    @property
    def is_paused(self) -> bool:
        """Always returns False - no pause functionality in simplified version."""
        return False

    @property
    def last_code_block(self) -> None:
        """Always returns None - no code blocks in simplified version."""
        return None
