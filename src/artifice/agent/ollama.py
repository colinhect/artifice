from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable

from .common import AgentBase, AgentResponse

logger = logging.getLogger(__name__)


class OllamaAgent(AgentBase):
    """Agent for connecting to Ollama locally with streaming responses.

    Ollama URL: Defaults to http://localhost:11434 but can be overridden via
    OLLAMA_HOST environment variable.

    Thread Safety: The agent uses lazy client initialization and runs API calls
    in a thread pool executor to avoid blocking the async event loop.
    """

    def __init__(
        self,
        model: str | None,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
        host: str | None = None,
    ):
        """Initialize Ollama agent.

        Args:
            model: Model identifier to use. Defaults to llama3.1.
            system_prompt: Optional system prompt to guide the agent's behavior.
            on_connect: Optional callback called when the client first connects.
            host: Optional Ollama host URL. Falls back to OLLAMA_HOST env var.
        """
        import os
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if model:
            self.model = model
        else:
            self.model = "llama3.2:1b"
        self.system_prompt = system_prompt
        self.on_connect = on_connect
        self._client = None
        self.messages = []  # Persistent conversation history

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

    def clear_conversation(self):
        """Clear the conversation history."""
        self.messages = []

    async def send_prompt(
        self, prompt: str, on_chunk: Optional[Callable] = None
    ) -> AgentResponse:
        """Send a prompt to Ollama and stream the response.

        Args:
            prompt: The prompt text.
            on_chunk: Optional callback for streaming text chunks.

        Returns:
            AgentResponse with the complete response.
        """
        try:
            client = self._get_client()
            loop = asyncio.get_running_loop()

            # Add new user message to conversation history (only if non-empty)
            if prompt.strip():
                self.messages.append({"role": "user", "content": prompt})
                logger.info(f"[OllamaAgent] Sending prompt: {prompt}")

            def sync_stream():
                """Synchronously stream from Ollama."""
                chunks = []

                # Build message list with system prompt if provided
                messages = []
                if self.system_prompt and len(self.messages) == 1:
                    # Only add system prompt at the start of conversation
                    messages.append({"role": "system", "content": self.system_prompt})
                messages.extend(self.messages)

                # Stream response from Ollama
                stream = client.chat(
                    model=self.model,
                    messages=messages,
                    stream=True,
                )

                stop_reason = None
                for chunk in stream:
                    if "message" in chunk:
                        content = chunk["message"].get("content", "")
                        if content:
                            chunks.append(content)
                            if on_chunk:
                                loop.call_soon_threadsafe(on_chunk, content)

                    # Check if this is the final chunk
                    if chunk.get("done", False):
                        stop_reason = chunk.get("done_reason", "end_turn")

                return "".join(chunks), stop_reason

            # Execute streaming in thread pool
            text, stop_reason = await loop.run_in_executor(None, sync_stream)

            # Log and add assistant's response to conversation history
            if text:
                logger.info(f"[OllamaAgent] Received response ({len(text)} chars, stop_reason={stop_reason}): {text}")
                self.messages.append({"role": "assistant", "content": text})

            return AgentResponse(
                text=text,
                stop_reason=stop_reason,
            )

        except ImportError as e:
            return AgentResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Ollama: {e}"
            return AgentResponse(text="", error=error_msg)
