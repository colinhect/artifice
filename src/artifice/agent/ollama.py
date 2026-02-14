"""Agent for Ollama (backward compatibility wrapper).

This module provides the OllamaAgent class which delegates to the new
provider/assistant architecture while maintaining backward compatibility.
"""

from __future__ import annotations

from typing import Callable, Optional

from .assistant import Assistant
from .common import AgentBase, AgentResponse
from .providers.ollama import OllamaProvider


class OllamaAgent(AgentBase):
    """Agent for connecting to Ollama locally with streaming responses.

    This is a backward compatibility wrapper that delegates to Assistant + OllamaProvider.

    Ollama URL: Defaults to http://localhost:11434 but can be overridden via
    OLLAMA_HOST environment variable.

    Thread Safety: The agent uses lazy client initialization and runs API calls
    in a thread pool executor to avoid blocking the async event loop.
    """

    def __init__(
        self,
        model: str | None,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
        host: str | None = None,
        thinking_budget: int | None = None,
    ):
        """Initialize Ollama agent.

        Args:
            model: Model identifier to use. Defaults to llama3.2:1b.
            system_prompt: Optional system prompt to guide the agent's behavior.
            on_connect: Optional callback called when the client first connects.
            host: Optional Ollama host URL. Falls back to OLLAMA_HOST env var.
            thinking_budget: Optional token budget for thinking mode.
        """
        provider = OllamaProvider(
            model=model,
            host=host,
            thinking_budget=thinking_budget,
            on_connect=on_connect,
        )
        self._assistant = Assistant(provider=provider, system_prompt=system_prompt)

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> AgentResponse:
        """Send a prompt to Ollama and stream the response.

        Args:
            prompt: The prompt text.
            on_chunk: Optional callback for streaming text chunks.
            on_thinking_chunk: Optional callback for streaming thinking chunks.

        Returns:
            AgentResponse with the complete response.
        """
        return await self._assistant.send_prompt(prompt, on_chunk, on_thinking_chunk)

    def clear_conversation(self):
        """Clear the conversation history."""
        self._assistant.clear_conversation()

    @property
    def messages(self):
        """Expose messages for any code that accesses agent.messages."""
        return self._assistant.messages
