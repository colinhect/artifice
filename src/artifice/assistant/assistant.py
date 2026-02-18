"""Universal assistant that manages conversation with any provider."""

from __future__ import annotations

import asyncio
import json
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
        self._pending_tool_calls: list[dict] = []
        self.prompt_updated()

    def prompt_updated(self):
        if self.openai_format and self.system_prompt:
            self.messages = [{"role": "system", "content": self.system_prompt}]

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
            logger.info(
                "Sending prompt (%d chars, %d messages)",
                len(prompt),
                len(self.messages),
            )
            logger.debug("Prompt text: %s", prompt[:200])

        # Delegate to provider
        try:
            response = await self.provider.send(
                messages=self.messages,
                system_prompt=self.system_prompt,
                on_chunk=on_chunk,
                on_thinking_chunk=on_thinking_chunk,
            )
        except asyncio.CancelledError:
            # Remove the orphaned user message on cancellation
            if self.messages and self.messages[-1].get("role") == "user":
                self.messages.pop()
            raise

        # Handle errors
        if response.error:
            logger.error("Provider error: %s", response.error)
            return AssistantResponse(text="", error=response.error)

        # Add assistant response to history
        history_text = response.text or response.tool_calls_xml or ""
        if history_text:
            if response.content_blocks and not self.openai_format:
                # Claude's structured content (for multi-turn thinking)
                self.messages.append(
                    {"role": "assistant", "content": response.content_blocks}
                )
            elif response.tool_calls and self.openai_format:
                # Store proper OpenAI tool_calls format so the model understands
                # its previous turn was a tool call (not plain XML text).
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": response.text or "",
                        "tool_calls": response.tool_calls,
                    }
                )
                self._pending_tool_calls = list(response.tool_calls)
            else:
                self.messages.append({"role": "assistant", "content": history_text})
            logger.info(
                "Received response (%d chars, stop_reason=%s)",
                len(history_text),
                response.stop_reason,
            )

        return AssistantResponse(
            text=response.text,
            stop_reason=response.stop_reason,
            thinking=response.thinking,
            usage=response.usage,
            tool_calls_xml=response.tool_calls_xml,
            tool_calls=response.tool_calls,
        )

    def add_tool_result(self, code: str, language: str, content: str) -> bool:
        """Add a tool result message to history if there is a matching pending call.

        Returns True when the result was added (caller should then send an empty
        prompt to get the model's follow-up response).  Returns False when there
        are no pending tool calls; the caller should fall back to a plain user
        message.
        """
        if not self._pending_tool_calls or not self.openai_format:
            return False

        code_key = "code" if language == "python" else "command"
        for i, tc in enumerate(self._pending_tool_calls):
            name = tc.get("function", {}).get("name", "")
            try:
                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            if name == language and args.get(code_key) == code:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": content,
                    }
                )
                self._pending_tool_calls.pop(i)
                return True

        return False

    def clear_conversation(self):
        """Clear conversation history."""
        self.messages = []
        self._pending_tool_calls = []
        self.prompt_updated()
        logger.info("Conversation history cleared")
