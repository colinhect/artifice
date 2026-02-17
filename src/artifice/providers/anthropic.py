"""Anthropic (Claude) provider implementation."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Callable, Optional

from .provider import ProviderBase, ProviderResponse, TokenUsage

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
        self.model = model
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
            logger.error("No ANTHROPIC_API_KEY set")
            return ProviderResponse(
                text="",
                error="No API key found. Set ANTHROPIC_API_KEY environment variable.",
            )

        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()
            cancelled = threading.Event()
            logger.info("Sending %d messages to %s", len(messages), self.model)

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
                        client,
                        api_params,
                        chunks,
                        loop,
                        on_chunk,
                        on_thinking_chunk,
                        cancelled,
                    )
                else:
                    return self._stream_text_only(
                        client, api_params, chunks, loop, on_chunk, cancelled
                    )

            # Execute streaming in thread pool
            try:
                result = await loop.run_in_executor(None, sync_stream)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            text, stop_reason, thinking_text, content_blocks, usage = result
            logger.info(
                "Response complete (%d chars, stop_reason=%s, %d in/%d out tokens)",
                len(text), stop_reason,
                usage.input_tokens if usage else 0,
                usage.output_tokens if usage else 0,
            )

            return ProviderResponse(
                text=text,
                stop_reason=stop_reason,
                thinking=thinking_text,
                content_blocks=content_blocks,
                usage=usage,
            )

        except ImportError as e:
            logger.error("anthropic package not available: %s", e)
            return ProviderResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Claude: {e}"
            logger.error("%s", error_msg)
            return ProviderResponse(text="", error=error_msg)

    @staticmethod
    def _extract_usage(message) -> TokenUsage:
        """Extract token usage from an Anthropic message."""
        usage = message.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
        return TokenUsage(
            input_tokens=input_tokens + cache_read + cache_create,
            output_tokens=output_tokens,
            total_tokens=input_tokens + cache_read + cache_create + output_tokens,
        )

    def _stream_text_only(self, client, api_params, chunks, loop, on_chunk, cancelled):
        """Stream using text_stream (no thinking)."""
        with client.messages.stream(**api_params) as stream:
            for text in stream.text_stream:
                if cancelled.is_set():
                    break
                chunks.append(text)
                if on_chunk:
                    loop.call_soon_threadsafe(on_chunk, text)
            message = stream.get_final_message()
        usage = self._extract_usage(message)
        return "".join(chunks), message.stop_reason, None, None, usage

    def _stream_with_thinking(
        self, client, api_params, chunks, loop, on_chunk, on_thinking_chunk, cancelled
    ):
        """Stream with extended thinking support, capturing both thinking and text deltas."""
        thinking_chunks = []

        with client.messages.stream(**api_params) as stream:
            for event in stream:
                if cancelled.is_set():
                    break
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

        usage = self._extract_usage(message)
        return (
            "".join(chunks),
            message.stop_reason,
            "".join(thinking_chunks) if thinking_chunks else None,
            content_blocks,
            usage,
        )
