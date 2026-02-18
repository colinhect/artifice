"""Assistant for GitHub Copilot.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from .assistant import Assistant
from .common import AssistantBase, AssistantResponse
from ..providers.copilot import CopilotProvider


class CopilotAssistant(AssistantBase):
    """Assistant for connecting to GitHub Copilot CLI with streaming responses.

    Note: Copilot uses session-based conversation management, so conversation history
    is managed by the provider's session rather than the assistant.

    Requirements:
    - GitHub Copilot CLI must be installed and accessible in PATH
    - GitHub authentication (via `copilot auth login` or GITHUB_TOKEN env var)
    """

    def __init__(
        self,
        model: str | None,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
    ):
        """Initialize Copilot .

        Args:
            model: Model identifier to use. Defaults to claude-haiku-4.5.
            system_prompt: Optional system prompt to guide the 's behavior.
            on_connect: Optional callback called when the client first connects.
        """
        self._provider = CopilotProvider(
            model=model,
            on_connect=on_connect,
        )
        self._assistant = Assistant(
            provider=self._provider, system_prompt=system_prompt
        )

    def prompt_updated(self):
        self._assistant.prompt_updated()

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> AssistantResponse:
        """Send a prompt to Copilot and stream the response.

        Args:
            prompt: The prompt text
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            AssistantResponse with the complete response
        """
        return await self._assistant.send_prompt(prompt, on_chunk, on_thinking_chunk)

    def clear_conversation(self):
        """Clear the conversation history by destroying the current session."""
        # Clear assistant history (though Copilot manages its own session)
        self._assistant.clear_conversation()
        # Reset the provider's session
        if self._provider._session is not None:
            self._provider._session = None
            asyncio.create_task(self._provider.reset_session())

    @property
    def messages(self):
        """Expose messages for any code that accesses .messages.

        Note: For Copilot, the assistant messages may not reflect the actual
        session history since Copilot manages conversation internally.
        """
        return self._assistant.messages

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources."""
        await self._provider.cleanup()
