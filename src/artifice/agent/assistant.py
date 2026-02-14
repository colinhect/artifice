"""Universal assistant that manages conversation with any provider."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .common import AgentBase, AgentResponse
from .provider import ProviderBase

logger = logging.getLogger(__name__)


class Assistant(AgentBase):
    """Universal assistant managing conversation with any provider.

    The assistant maintains conversation history and delegates API calls
    to the underlying provider. Multiple assistants can share the same
    provider instance (though current usage only needs one).

    This class implements the AgentBase interface, so it can be used as
    a drop-in replacement for existing agent classes.
    """

    def __init__(
        self,
        provider: ProviderBase,
        system_prompt: str | None = None,
    ):
        """Initialize the assistant.

        Args:
            provider: The provider to use for API communication
            system_prompt: Optional system prompt to guide behavior
        """
        self.provider = provider
        self.system_prompt = system_prompt
        self.messages: list[dict] = []  # Conversation history

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> AgentResponse:
        """Send prompt and maintain conversation history.

        Args:
            prompt: The prompt text to send
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            AgentResponse with the complete response
        """
        # Add user message to history (only if non-empty)
        if prompt.strip():
            self.messages.append({"role": "user", "content": prompt})
            logger.info(f"[Assistant] Sending prompt: {prompt[:100]}...")

        # Delegate to provider
        response = await self.provider.send(
            messages=self.messages,
            system_prompt=self.system_prompt,
            on_chunk=on_chunk,
            on_thinking_chunk=on_thinking_chunk,
        )

        # Handle errors
        if response.error:
            logger.error(f"[Assistant] Provider error: {response.error}")
            return AgentResponse(text="", error=response.error)

        # Add assistant response to history
        if response.text:
            if response.content_blocks:
                # Claude's structured content (for multi-turn thinking)
                self.messages.append({"role": "assistant", "content": response.content_blocks})
            else:
                self.messages.append({"role": "assistant", "content": response.text})
            logger.info(
                f"[Assistant] Received response ({len(response.text)} chars, stop_reason={response.stop_reason})"
            )

        return AgentResponse(
            text=response.text,
            stop_reason=response.stop_reason,
            thinking=response.thinking,
        )

    def clear_conversation(self):
        """Clear conversation history."""
        self.messages = []
        logger.info("[Assistant] Conversation history cleared")
