from __future__ import annotations

import asyncio
import os
from typing import Optional, Callable

from .common import AgentBase, AgentResponse

class ClaudeAgent(AgentBase):
    """Agent for connecting to Claude via Anthropic API with streaming responses.

    API Key: Reads from ANTHROPIC_API_KEY environment variable.

    Thread Safety: The agent uses lazy client initialization and runs API calls
    in a thread pool executor to avoid blocking the async event loop.
    """

    def __init__(
        self,
        #model: str = "claude-sonnet-4-5-20250929",
        model: str = "claude-haiku-4-5-20251001",
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
    ):
        """Initialize Claude agent.

        Args:
            model: Model identifier to use. Defaults to Claude Sonnet 4.5.
            system_prompt: Optional system prompt to guide the agent's behavior.
            on_connect: Optional callback called when the client first connects.
        """
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.system_prompt = system_prompt
        self.on_connect = on_connect
        self._client = None
        self.messages = []  # Persistent conversation history

    def _get_client(self):
        """Lazy import and create Anthropic client."""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
                if self.on_connect:
                    self.on_connect("Claude")
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. Install with: pip install anthropic"
                )
        return self._client

    def clear_conversation(self):
        """Clear the conversation history."""
        self.messages = []

    async def send_prompt(
        self, prompt: str, on_chunk: Optional[Callable] = None
    ) -> AgentResponse:
        """Send a prompt to Claude and stream the response.

        Args:
            prompt: The prompt text.
            on_chunk: Optional callback for streaming text chunks.

        Returns:
            AgentResponse with the complete response.
        """
        if not self.api_key:
            return AgentResponse(
                text="",
                error="No API key found. Set ANTHROPIC_API_KEY environment variable.",
            )

        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()

            # Add new user message to conversation history (only if non-empty)
            if prompt.strip():
                self.messages.append({"role": "user", "content": prompt})

            def sync_stream():
                """Synchronously stream from Claude."""
                chunks = []

                # Build API call parameters
                api_params = {
                    "model": self.model,
                    "max_tokens": 4096,
                    "messages": self.messages,
                }

                # Add system prompt if available
                if self.system_prompt:
                    api_params["system"] = self.system_prompt

                with client.messages.stream(**api_params) as stream:
                    for text in stream.text_stream:
                        chunks.append(text)
                        if on_chunk:
                            loop.call_soon_threadsafe(on_chunk, text)

                    message = stream.get_final_message()

                return "".join(chunks), message.stop_reason

            # Execute streaming in thread pool
            text, stop_reason = await loop.run_in_executor(None, sync_stream)

            # Add assistant's response to conversation history
            if text:
                self.messages.append({"role": "assistant", "content": text})

            return AgentResponse(
                text=text,
                stop_reason=stop_reason,
            )

        except ImportError as e:
            return AgentResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Claude: {e}"
            return AgentResponse(text="", error=error_msg)
