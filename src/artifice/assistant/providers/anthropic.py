"""Anthropic (Claude) provider implementation."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Optional

from ..provider import ProviderBase, ProviderResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(ProviderBase):
    """Provider for Anthropic's Claude API.

    Handles API client initialization, streaming, and extended thinking support.
    """

    def __init__(
        self,
        model: str | None = None,
        thinking_budget: int | None = None,
        on_connect: Callable | None = None,
    ):
        """Initialize Anthropic provider.

        Args:
            model: Model identifier. Defaults to Claude Haiku 4.5.
            thinking_budget: Optional token budget for extended thinking.
            on_connect: Optional callback called when the client first connects.
        """
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = model if model else "claude-haiku-4-5"
        self.thinking_budget = thinking_budget
        self.on_connect = on_connect
        self._client = None

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

    async def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> ProviderResponse:
        """Send messages to Claude and stream the response.

        Args:
            messages: Full conversation history
            system_prompt: Optional system prompt
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            ProviderResponse with the complete response
        """
        if not self.api_key:
            return ProviderResponse(
                text="",
                error="No API key found. Set ANTHROPIC_API_KEY environment variable.",
            )

        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()

            def sync_stream():
                """Synchronously stream from Claude."""
                chunks = []

                # Build API call parameters
                api_params = {
                    "model": self.model,
                    "max_tokens": 4096,
                    "messages": messages,
                }

                # Add system prompt if available
                if system_prompt:
                    api_params["system"] = system_prompt

                # Add extended thinking if configured
                if self.thinking_budget:
                    api_params["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": self.thinking_budget,
                    }
                    api_params["max_tokens"] = max(8192, self.thinking_budget + 4096)

                if self.thinking_budget:
                    return self._stream_with_thinking(
                        client, api_params, chunks, loop, on_chunk, on_thinking_chunk
                    )
                else:
                    return self._stream_text_only(
                        client, api_params, chunks, loop, on_chunk
                    )

            # Execute streaming in thread pool
            result = await loop.run_in_executor(None, sync_stream)
            text, stop_reason, thinking_text, content_blocks = result

            return ProviderResponse(
                text=text,
                stop_reason=stop_reason,
                thinking=thinking_text,
                content_blocks=content_blocks,
            )

        except ImportError as e:
            return ProviderResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Claude: {e}"
            return ProviderResponse(text="", error=error_msg)

    def _stream_text_only(self, client, api_params, chunks, loop, on_chunk):
        """Stream using text_stream (no thinking)."""
        with client.messages.stream(**api_params) as stream:
            for text in stream.text_stream:
                chunks.append(text)
                if on_chunk:
                    loop.call_soon_threadsafe(on_chunk, text)
            message = stream.get_final_message()
        return "".join(chunks), message.stop_reason, None, None

    def _stream_with_thinking(
        self, client, api_params, chunks, loop, on_chunk, on_thinking_chunk
    ):
        """Stream with extended thinking support, capturing both thinking and text deltas."""
        thinking_chunks = []

        with client.messages.stream(**api_params) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "thinking_delta":
                        thinking_chunks.append(delta.thinking)
                        if on_thinking_chunk:
                            loop.call_soon_threadsafe(on_thinking_chunk, delta.thinking)
                    elif delta.type == "text_delta":
                        chunks.append(delta.text)
                        if on_chunk:
                            loop.call_soon_threadsafe(on_chunk, delta.text)

            message = stream.get_final_message()

        # Extract structured content blocks for conversation history
        content_blocks = []
        for block in message.content:
            if block.type == "thinking":
                content_blocks.append(
                    {
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    }
                )
            elif block.type == "text":
                content_blocks.append(
                    {
                        "type": "text",
                        "text": block.text,
                    }
                )

        return (
            "".join(chunks),
            message.stop_reason,
            "".join(thinking_chunks) if thinking_chunks else None,
            content_blocks,
        )
