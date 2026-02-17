"""Interface for AI assistant interaction."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass
from typing import Callable, Optional

from ..providers.provider import TokenUsage


@dataclass
class AssistantResponse:
    """Response from an AI assistant."""

    text: str
    stop_reason: str | None = None
    error: str | None = None
    thinking: str | None = None
    usage: TokenUsage | None = None


class AssistantBase(ABC):
    """Base class for AI s."""

    system_prompt: str | None = None

    @abstractmethod
    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> AssistantResponse:
        """Send a prompt to the assistant.

        Args:
            prompt: The prompt text to send.
            on_chunk: Optional callback for streaming text chunks.
            on_thinking_chunk: Optional callback for streaming thinking/reasoning chunks.

        Returns:
            AssistantResponse with the complete response.
        """
        pass

    @abstractmethod
    def prompt_updated(self):
        pass

    @abstractmethod
    def clear_conversation(self):
        pass

    def send_prompt_and_wait_full_response(self, prompt):
        response: str = ""

        def on_chunk(text):
            nonlocal response
            response += text

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.send_prompt(prompt, on_chunk=on_chunk))
        return response
