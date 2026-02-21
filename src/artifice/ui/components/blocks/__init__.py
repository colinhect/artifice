"""Block widgets for the terminal display.

This module re-exports all block classes from their respective modules
for backward compatibility.
"""

from __future__ import annotations

from artifice.ui.components.blocks.base import BaseBlock
from artifice.ui.components.blocks.input import AgentInputBlock, CodeInputBlock
from artifice.ui.components.blocks.mixins import StatusMixin
from artifice.ui.components.blocks.output import (
    AgentOutputBlock,
    BufferedOutputBlock,
    CodeOutputBlock,
    StreamingMarkdownBlock,
    ThinkingOutputBlock,
)
from artifice.ui.components.blocks.system import SystemBlock, WidgetOutputBlock
from artifice.ui.components.blocks.tool import ToolCallBlock

__all__ = [
    "BaseBlock",
    "StatusMixin",
    "CodeInputBlock",
    "AgentInputBlock",
    "StreamingMarkdownBlock",
    "AgentOutputBlock",
    "ThinkingOutputBlock",
    "BufferedOutputBlock",
    "CodeOutputBlock",
    "WidgetOutputBlock",
    "SystemBlock",
    "ToolCallBlock",
]
