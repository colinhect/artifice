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

__all__ = [
    "AgentInputBlock",
    "AgentOutputBlock",
    "BaseBlock",
    "BlockFactory",
    "CodeInputBlock",
    "CodeOutputBlock",
    "SystemBlock",
    "ThinkingOutputBlock",
    "ToolCallBlock",
    "WidgetOutputBlock",
]
