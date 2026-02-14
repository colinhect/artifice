"""Agent for Claude (backward compatibility wrapper).

This module provides the ClaudeAgent class which delegates to the new
provider/assistant architecture while maintaining backward compatibility.
"""

from __future__ import annotations

from typing import Callable, Optional

from .assistant import Assistant
from .common import AgentBase, AgentResponse
from .providers.anthropic import AnthropicProvider


class ClaudeAgent(AgentBase):
    """Agent for connecting to Claude via Anthropic API with streaming responses.

    This is a backward compatibility wrapper that delegates to Assistant + AnthropicProvider.

    API Key: Reads from ANTHROPIC_API_KEY environment variable.

    Thread Safety: The agent uses lazy client initialization and runs API calls
    in a thread pool executor to avoid blocking the async event loop.
    """

    def __init__(
        self,
        model: str | None,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
        thinking_budget: int | None = None,
    ):
        """Initialize Claude agent.

        Args:
            model: Model identifier to use. Defaults to Claude Sonnet 4.5.
            system_prompt: Optional system prompt to guide the agent's behavior.
            on_connect: Optional callback called when the client first connects.
            thinking_budget: Optional token budget for extended thinking.
        """
        provider = AnthropicProvider(
            model=model,
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
        """Send a prompt to Claude and stream the response.

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
