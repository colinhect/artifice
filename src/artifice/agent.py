"""Interface for AI agent interaction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class ToolCall:
    """Represents a tool call made by the agent."""
    
    id: str
    name: str
    input: dict[str, Any]
    output: str | None = None
    error: str | None = None


@dataclass
class AgentResponse:
    """Response from an AI agent."""

    text: str
    stop_reason: str | None = None
    error: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class AgentBase(ABC):
    """Base class for AI agents."""

    @abstractmethod
    async def send_prompt(
        self, prompt: str, on_chunk: Optional[callable] = None
    ) -> AgentResponse:
        """Send a prompt to the agent.

        Args:
            prompt: The prompt text to send.
            on_chunk: Optional callback for streaming text chunks.

        Returns:
            AgentResponse with the complete response.
        """
        pass
