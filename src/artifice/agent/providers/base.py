"""Provider abstraction layer for LLM implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable

if TYPE_CHECKING:
    from artifice.agent.tools.base import ToolCall


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class StreamChunk:
    """A chunk of streaming response from the LLM."""

    content: str = ""
    reasoning: str | None = None
    usage: TokenUsage | None = None
    tool_calls: list[dict] = field(default_factory=list)


@dataclass
class ProviderResponse:
    """Complete response from the LLM."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None
    usage: TokenUsage | None = None


class Provider(ABC):
    """Abstract base class for LLM providers.

    Providers handle the low-level communication with LLM APIs,
    while the Agent manages conversation state, prompts, and tools.
    """

    @abstractmethod
    def stream_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion chunks from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            tools: Optional list of tool schemas
            on_chunk: Callback for content chunks
            on_thinking_chunk: Callback for reasoning/thinking chunks

        Yields:
            StreamChunk objects containing content, reasoning, usage, etc.
        """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        """Send messages and return complete response.

        Args:
            messages: List of message dicts
            tools: Optional list of tool schemas

        Returns:
            ProviderResponse with text, tool_calls, thinking, and usage
        """

    async def check_connection(self) -> bool:
        """Check if the provider is reachable. Override if needed."""
        return True
