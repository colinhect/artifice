"""Output blocks components."""

from __future__ import annotations

from artifice.ui.components.blocks.blocks import (
    AgentInputBlock,
    AgentOutputBlock,
    BaseBlock,
    CodeInputBlock,
    CodeOutputBlock,
    SystemBlock,
    ThinkingOutputBlock,
    ToolCallBlock,
    WidgetOutputBlock,
)
from artifice.ui.components.blocks.factory import BlockFactory
from artifice.ui.components.blocks.registry import BlockRegistry, BlockRenderer

__all__ = [
    "AgentInputBlock",
    "AgentOutputBlock",
    "BaseBlock",
    "BlockFactory",
    "BlockRegistry",
    "BlockRenderer",
    "CodeInputBlock",
    "CodeOutputBlock",
    "SystemBlock",
    "ThinkingOutputBlock",
    "ToolCallBlock",
    "WidgetOutputBlock",
]
