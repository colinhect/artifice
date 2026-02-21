"""Provider abstraction layer for LLM implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable


@dataclass
class TokenUsage:
    """Token usage statistics from LLM responses."""

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

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """Send messages and complete the request.

        This method is primarily used for connection testing. Streaming
        via stream_completion() is the recommended approach for normal use.

        Args:
            messages: List of message dicts
            tools: Optional list of tool schemas
        """
        async for _ in self.stream_completion(messages, tools):
            pass
