"""Backward compatibility re-export for fence_detector module (now in agent.streaming)."""

from __future__ import annotations

from artifice.agent.streaming.detector import StreamingFenceDetector, _FenceState
from artifice.ui.components.blocks.blocks import AgentOutputBlock, CodeInputBlock

__all__ = [
    "StreamingFenceDetector",
    "_FenceState",
    "AgentOutputBlock",
    "CodeInputBlock",
]
