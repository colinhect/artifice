"""Factory for creating and managing streaming output blocks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .terminal.output import (
    AgentOutputBlock,
    CodeInputBlock,
    BaseBlock,
)

if TYPE_CHECKING:
    from .terminal.output import TerminalOutput


class BlockFactory:
    """Creates, mounts, and tracks blocks for the streaming fence detector.

    Centralizes the repeated create-mount-track pattern that was previously
    duplicated across _feed_prose and _feed_code.
    """

    def __init__(self, output: TerminalOutput) -> None:
        self._output = output
        self.all_blocks: list[BaseBlock] = []
        self.first_agent_block: AgentOutputBlock | None = None

    def create_prose_block(self, activity: bool = True) -> AgentOutputBlock:
        """Create a new prose (agent output) block, mount it, and track it."""
        block = AgentOutputBlock(activity=activity)
        self._output.append_block(block)
        self.all_blocks.append(block)
        return block

    def create_code_block(self, code: str, language: str) -> CodeInputBlock:
        """Create a new code input block, mount it, and track it."""
        block = CodeInputBlock(
            code, language=language, show_loading=False, in_context=True
        )
        self._output.append_block(block)
        self.all_blocks.append(block)
        return block

    def remove_block(self, block: BaseBlock) -> None:
        """Remove a block from tracking lists and the DOM."""
        if block in self.all_blocks:
            self.all_blocks.remove(block)
        self._output.remove_block(block)
