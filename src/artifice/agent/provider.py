"""Base classes for AI providers.

Providers handle the low-level API communication and streaming for different
AI services (Anthropic, Ollama, OpenAI, etc.). They are stateless and receive
the full conversation history as a parameter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class ProviderResponse:
    """Raw response from a provider.

    Attributes:
        text: The main text content of the response
        stop_reason: Why the model stopped generating (e.g., "end_turn", "max_tokens")
        thinking: Optional thinking/reasoning text (for models that support extended thinking)
        content_blocks: Optional structured content blocks (e.g., for Claude's multi-turn thinking)
        error: Optional error message if the request failed
    """

    text: str
    stop_reason: str | None = None
    thinking: str | None = None
    content_blocks: list[dict[str, Any]] | None = None
    error: str | None = None


class ProviderBase(ABC):
    """Base class for API providers (stateless).

    Providers are responsible for:
    - Initializing API clients
    - Handling API credentials
    - Streaming responses
    - Converting provider-specific formats to ProviderResponse

    Providers do NOT manage conversation history - they receive the full
    message history as a parameter to send().
    """

    @abstractmethod
    async def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> ProviderResponse:
        """Send messages to provider and stream response.

        Args:
            messages: Full conversation history in OpenAI format
            system_prompt: Optional system prompt to guide behavior
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            ProviderResponse with the complete response data
        """
        pass
