"""Agent for OpenAI-compatible APIs (backward compatibility wrapper).

This module provides the OpenAIAgent class which delegates to the new
provider/assistant architecture while maintaining backward compatibility.
"""

from __future__ import annotations

from typing import Callable, Optional

from .assistant import Assistant
from .common import AgentBase, AgentResponse
from .providers.openai import OpenAICompatibleProvider


class OpenAIAgent(AgentBase):
    """Agent for OpenAI-compatible APIs.

    This is a backward compatibility wrapper that delegates to Assistant + OpenAICompatibleProvider.

    Supports OpenAI API and compatible services (Hugging Face, etc.).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
        thinking_budget: int | None = None,
    ):
        """Initialize OpenAI agent.

        Args:
            base_url: Base URL for the API endpoint
            api_key: API key for authentication
            model: Model identifier
            system_prompt: Optional system prompt to guide the agent's behavior
            on_connect: Optional callback called when the client first connects
            thinking_budget: Optional token budget (not used but kept for compatibility)
        """
        provider = OpenAICompatibleProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            on_connect=on_connect,
        )

        # OpenAI format requires system prompt in messages array
        self._assistant = Assistant(provider=provider, system_prompt=system_prompt)

        # Initialize with system message if provided (OpenAI format)
        if system_prompt:
            self._assistant.messages = [{"role": "system", "content": system_prompt}]

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> AgentResponse:
        """Send a prompt to the OpenAI-compatible API and stream the response.

        Args:
            prompt: The prompt text
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            AgentResponse with the complete response
        """
        return await self._assistant.send_prompt(prompt, on_chunk, on_thinking_chunk)

    def clear_conversation(self):
        """Clear the conversation history."""
        # For OpenAI, preserve system message if present
        system_prompt = self._assistant.system_prompt
        self._assistant.clear_conversation()
        if system_prompt:
            self._assistant.messages = [{"role": "system", "content": system_prompt}]

    @property
    def messages(self):
        """Expose messages for any code that accesses agent.messages."""
        return self._assistant.messages
