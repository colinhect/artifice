from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable

from openai import OpenAI

from .common import AgentBase, AgentResponse

logger = logging.getLogger(__name__)


class OpenAIAgent(AgentBase):

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
        thinking_budget: int | None = None,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.on_connect = on_connect
        self.thinking_budget = thinking_budget
        self._client: OpenAI | None = None
        # Initialize with system message if provided
        if system_prompt:
            self.messages = [{"role": "system", "content": system_prompt}]
        else:
            self.messages = []

    def _get_client(self):
        if self._client is None:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            if self.on_connect:
                self.on_connect("...")
        return self._client

    def clear_conversation(self):
        """Clear the conversation history."""
        # Reset to just system message if present
        if self.system_prompt:
            self.messages = [{"role": "system", "content": self.system_prompt}]
        else:
            self.messages = []

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> AgentResponse:
        try:
            client = self._get_client()
            assert client

            # Add new user message to conversation history (only if non-empty)
            if prompt.strip():
                self.messages.append({"role": "user", "content": prompt})
                logger.info(f"[OpenAIAgent] Sending prompt to {self.model}: {prompt[:100]}...")

            logger.info(f"[OpenAIAgent] Messages history length: {len(self.messages)}")

            # Run synchronous streaming in executor to avoid blocking
            loop = asyncio.get_running_loop()

            def sync_stream():
                """Synchronously stream from OpenAI-compatible API."""
                stream = client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    stream=True,
                )

                text = ""
                thinking_text = ""
                chunk_count = 0
                for chunk in stream:
                    if chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta

                        # Handle reasoning/thinking content (o1, o3 models)
                        if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                            thinking_text += delta.reasoning_content
                            if on_thinking_chunk:
                                loop.call_soon_threadsafe(on_thinking_chunk, delta.reasoning_content)

                        # Handle regular content
                        if delta.content:
                            chunk_count += 1
                            text += delta.content
                            if on_chunk:
                                loop.call_soon_threadsafe(on_chunk, delta.content)

                return text, thinking_text, chunk_count

            text, thinking_text, chunk_count = await loop.run_in_executor(None, sync_stream)

            if thinking_text:
                logger.info(f"[OpenAIAgent] Received thinking content, length: {len(thinking_text)}")
            logger.info(f"[OpenAIAgent] Received {chunk_count} chunks, total length: {len(text)}")

            # Add assistant's response to conversation history
            if text:
                self.messages.append({"role": "assistant", "content": text})
            else:
                logger.warning("[OpenAIAgent] No text received from model")

            return AgentResponse(
                text=text,
            )

        except Exception as e:
            import traceback
            error_msg = f"Error communicating with model: {traceback.format_exc()}"
            logger.error(f"[OpenAIAgent] {error_msg}")
            return AgentResponse(text="", error=error_msg)
