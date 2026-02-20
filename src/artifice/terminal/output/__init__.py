"""Terminal output package - re-exports all public names for backward compatibility."""

from .blocks import (
    AgentInputBlock,
    AgentOutputBlock,
    BaseBlock,
    BufferedOutputBlock,
    CodeInputBlock,
    CodeOutputBlock,
    ThinkingOutputBlock,
    ToolCallBlock,
    WidgetOutputBlock,
    SystemBlock
)
from .containers import (
    HighlightableContainerMixin,
    TerminalOutput,
)

__all__ = [
    "AgentInputBlock",
    "AgentOutputBlock",
    "BaseBlock",
    "BufferedOutputBlock",
    "CodeInputBlock",
    "CodeOutputBlock",
    "HighlightableContainerMixin",
    "TerminalOutput",
    "ThinkingOutputBlock",
    "ToolCallBlock",
    "WidgetOutputBlock",
    "SystemBlock"
]
