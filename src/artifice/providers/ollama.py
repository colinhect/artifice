"""Ollama provider implementation."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Callable, Optional

from .provider import ProviderBase, ProviderResponse

logger = logging.getLogger(__name__)


class OllamaProvider(ProviderBase):
    """Provider for Ollama local API.

    Handles client initialization, streaming, and thinking support.
    """

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        thinking_budget: int | None = None,
        on_connect: Callable | None = None,
    ):
        """Initialize Ollama provider.

        Args:
            model: Model identifier. Defaults to llama3.2:1b.
            host: Optional Ollama host URL. Falls back to OLLAMA_HOST env var.
            thinking_budget: Optional token budget for thinking mode.
            on_connect: Optional callback called when the client first connects.
        """
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model if model else "llama3.2:1b"
        self.thinking_budget = thinking_budget
        self.on_connect = on_connect
        self._client = None

    def _get_client(self):
        """Lazy import and create Ollama client."""
        if self._client is None:
            try:
                import ollama

                self._client = ollama.Client(host=self.host)
                if self.on_connect:
                    self.on_connect(f"Ollama ({self.model})")
            except ImportError:
                raise ImportError(
                    "ollama package not installed. Install with: pip install ollama"
                )
        return self._client

    async def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> ProviderResponse:
        """Send messages to Ollama and stream the response.

        Args:
            messages: Full conversation history
            system_prompt: Optional system prompt
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            ProviderResponse with the complete response
        """
        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()
            cancelled = threading.Event()
            logger.info("Sending %d messages to %s", len(messages), self.model)

            def sync_stream():
                """Synchronously stream from Ollama with thinking support."""
                chunks = []
                thinking_chunks = []

                # Build message list with system prompt if provided
                # Ollama requires system prompt to be injected into messages array
                message_list = []
                if system_prompt and len(messages) == 1:
                    # Only add system prompt at the start of conversation
                    message_list.append({"role": "system", "content": system_prompt})
                message_list.extend(messages)

                # Stream response from Ollama
                stream = client.chat(
                    model=self.model,
                    messages=message_list,
                    stream=True,
                    think=self.thinking_budget is not None and self.thinking_budget > 0,
                )

                stop_reason = None
                for chunk in stream:
                    if cancelled.is_set():
                        break

                    if "message" in chunk:
                        # Regular content
                        content = chunk["message"].get("content", "")
                        if content:
                            chunks.append(content)
                            if on_chunk:
                                loop.call_soon_threadsafe(on_chunk, content)

                        # Thinking content (separate field from Ollama API)
                        thinking = chunk["message"].get("thinking", "")
                        if thinking:
                            thinking_chunks.append(thinking)
                            if on_thinking_chunk:
                                loop.call_soon_threadsafe(on_thinking_chunk, thinking)

                    # Check if this is the final chunk
                    if chunk.get("done", False):
                        stop_reason = chunk.get("done_reason", "end_turn")

                thinking_text = "".join(thinking_chunks) if thinking_chunks else None
                return "".join(chunks), stop_reason, thinking_text

            # Execute streaming in thread pool
            try:
                text, stop_reason, thinking_text = await loop.run_in_executor(
                    None, sync_stream
                )
            except asyncio.CancelledError:
                cancelled.set()
                raise

            logger.info("Response complete (%d chars, stop_reason=%s)", len(text), stop_reason)

            return ProviderResponse(
                text=text,
                stop_reason=stop_reason,
                thinking=thinking_text,
            )

        except ImportError as e:
            logger.error("ollama package not available: %s", e)
            return ProviderResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Ollama: {e}"
            logger.error("%s", error_msg)
            return ProviderResponse(text="", error=error_msg)
