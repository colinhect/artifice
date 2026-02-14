"""Universal assistant that manages conversation with any provider."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .common import AssistantBase, AssistantResponse
from ..providers.provider import ProviderBase

logger = logging.getLogger(__name__)


class Assistant(AssistantBase):
    """Universal assistant managing conversation with any provider.

    The assistant maintains conversation history and delegates API calls
    to the underlying provider. Multiple assistants can share the same
    provider instance (though current usage only needs one).

    This class implements the AssistantBase interface, so it can be used as
    a drop-in replacement for existing  classes.
    """

    def __init__(
        self,
        provider: ProviderBase,
        system_prompt: str | None = None,
        openai_format: bool = False,
    ):
        """Initialize the assistant.

        Args:
            provider: The provider to use for API communication
            system_prompt: Optional system prompt to guide behavior
        """
        self.provider = provider
        self.system_prompt = system_prompt
        self.openai_format = openai_format
        self.messages: list[dict] = []  # Conversation history

        if openai_format and system_prompt:
            self.messages = [{"role": "system", "content": system_prompt}]

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> AssistantResponse:
        """Send prompt and maintain conversation history.

        Args:
            prompt: The prompt text to send
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            AssistantResponse with the complete response
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
            return AssistantResponse(text="", error=response.error)

        # Add assistant response to history
        if response.text:
            if response.content_blocks:
                # Claude's structured content (for multi-turn thinking)
                self.messages.append(
                    {"role": "assistant", "content": response.content_blocks}
                )
            else:
                self.messages.append({"role": "assistant", "content": response.text})
            logger.info(
                f"[Assistant] Received response ({len(response.text)} chars, stop_reason={response.stop_reason})"
            )

        return AssistantResponse(
            text=response.text,
            stop_reason=response.stop_reason,
            thinking=response.thinking,
        )

    def clear_conversation(self):
        """Clear conversation history."""
        self.messages = []
        if self.openai_format and self.system_prompt:
            self.messages = [{"role": "system", "content": self.system_prompt}]
        logger.info("[Assistant] Conversation history cleared")
