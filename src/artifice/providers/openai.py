"""OpenAI-compatible provider implementation."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

from openai import OpenAI

from .provider import ProviderBase, ProviderResponse, TokenUsage

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(ProviderBase):
    """Provider for OpenAI-compatible APIs.

    Supports OpenAI API and compatible services (Hugging Face, etc.).
    Handles reasoning/thinking content for o1/o3 models.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        on_connect: Callable | None = None,
    ):
        """Initialize OpenAI-compatible provider.

        Args:
            base_url: Base URL for the API endpoint
            api_key: API key for authentication
            model: Model identifier
            on_connect: Optional callback called when the client first connects
        """
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.on_connect = on_connect
        self._client: OpenAI | None = None

    def _get_client(self):
        """Lazy client initialization."""
        if self._client is None:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            if self.on_connect:
                self.on_connect("...")
        return self._client

    async def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> ProviderResponse:
        """Send messages to OpenAI-compatible API and stream the response.

        Args:
            messages: Full conversation history (system prompt already in messages if present)
            system_prompt: Optional system prompt (for compatibility, typically already in messages)
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            ProviderResponse with the complete response
        """
        try:
            client = self._get_client()
            assert client

            logger.info("Sending %d messages to %s", len(messages), self.model)

            # Run synchronous streaming in executor to avoid blocking
            loop = asyncio.get_running_loop()
            cancelled = threading.Event()

            def sync_stream():
                """Synchronously stream from OpenAI-compatible API."""
                stream = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                )

                text = ""
                thinking_text = ""
                chunk_count = 0
                usage = None
                for chunk in stream:
                    if cancelled.is_set():
                        break

                    # Capture usage from the final chunk
                    if chunk.usage:
                        usage = TokenUsage(
                            input_tokens=chunk.usage.prompt_tokens or 0,
                            output_tokens=chunk.usage.completion_tokens or 0,
                            total_tokens=chunk.usage.total_tokens or 0,
                        )

                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta

                        # Handle reasoning/thinking content (o1, o3 models)
                        if (
                            hasattr(delta, "reasoning_content")
                            and delta.reasoning_content
                        ):
                            thinking_text += delta.reasoning_content
                            if on_thinking_chunk:
                                loop.call_soon_threadsafe(
                                    on_thinking_chunk, delta.reasoning_content
                                )

                        # Handle regular content
                        if delta.content:
                            chunk_count += 1
                            text += delta.content
                            if on_chunk:
                                loop.call_soon_threadsafe(on_chunk, delta.content)

                return text, thinking_text, chunk_count, usage

            try:
                text, thinking_text, chunk_count, usage = await loop.run_in_executor(
                    None, sync_stream
                )
            except asyncio.CancelledError:
                cancelled.set()
                raise

            logger.info(
                "Response complete (%d chars in %d chunks, %d in/%d out tokens)",
                len(text), chunk_count,
                usage.input_tokens if usage else 0,
                usage.output_tokens if usage else 0,
            )
            if thinking_text:
                logger.debug("Received thinking content (%d chars)", len(thinking_text))

            return ProviderResponse(
                text=text,
                thinking=thinking_text if thinking_text else None,
                usage=usage,
            )

        except Exception:
            import traceback

            error_msg = f"Error communicating with model: {traceback.format_exc()}"
            logger.error("%s", error_msg)
            return ProviderResponse(text="", error=error_msg)
