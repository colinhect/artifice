"""Factory for creating and managing streaming output blocks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artifice.ui.components.blocks.blocks import BaseBlock

if TYPE_CHECKING:
    from artifice.ui.components.blocks.blocks import AgentOutputBlock
    from artifice.ui.components.output import TerminalOutput


class BlockFactory:
    """Creates, mounts, and tracks blocks for the streaming fence detector.

    Centralizes the repeated create-mount-track pattern that was previously
    duplicated across _feed_prose and _feed_code.
    """

    def __init__(self, output: TerminalOutput) -> None:
        self._output = output
        self.all_blocks: list[BaseBlock] = []
        self.first_agent_block: AgentOutputBlock | None = None

    def remove_block(self, block: BaseBlock) -> None:
        """Remove a block from tracking lists and the DOM."""
        if block in self.all_blocks:
            self.all_blocks.remove(block)
        self._output.remove_block(block)
