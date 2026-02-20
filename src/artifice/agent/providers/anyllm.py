"""Any-LLM provider implementation."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable

from artifice.agent.providers.base import (
    Provider,
    ProviderResponse,
    StreamChunk,
    TokenUsage,
)

if TYPE_CHECKING:
    from artifice.agent.tools.base import ToolCall

logger = logging.getLogger(__name__)


class AnyLLMProvider(Provider):
    """Provider implementation using the any-llm library.

    Supports any model compatible with any-llm including:
    - OpenAI (GPT-4, GPT-3.5, etc.)
    - Anthropic (Claude)
    - Google (Gemini)
    - MiniMax, Kimi, and many others
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._provider = provider
        self._base_url = base_url

    async def stream_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion from any-llm."""
        from any_llm import acompletion

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            stream=True,
        )

        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._provider is not None:
            kwargs["provider"] = self._provider
        if self._base_url is not None:
            kwargs["api_base"] = self._base_url
        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            stream = await acompletion(**kwargs)
        except Exception:
            import traceback

            error = f"Connection error: {traceback.format_exc()}"
            logger.error("%s", error)
            raise ConnectionError(error)

        async for chunk in stream:
            stream_chunk = StreamChunk()

            # Extract usage if available
            if hasattr(chunk, "usage") and chunk.usage:
                stream_chunk.usage = TokenUsage(
                    input_tokens=chunk.usage.prompt_tokens or 0,
                    output_tokens=chunk.usage.completion_tokens or 0,
                    total_tokens=chunk.usage.total_tokens or 0,
                )

            if not chunk.choices:
                yield stream_chunk
                continue

            delta = chunk.choices[0].delta

            # Extract reasoning/thinking content
            if hasattr(delta, "reasoning") and delta.reasoning:
                reasoning_content = (
                    delta.reasoning.content
                    if hasattr(delta.reasoning, "content")
                    else str(delta.reasoning)
                )
                stream_chunk.reasoning = reasoning_content
                if on_thinking_chunk:
                    on_thinking_chunk(reasoning_content)

            # Extract content
            if delta.content:
                stream_chunk.content = delta.content
                if on_chunk:
                    on_chunk(delta.content)

            # Extract tool calls
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                stream_chunk.tool_calls = [
                    {
                        "index": tc.index,
                        "id": tc.id or "",
                        "function": {
                            "name": tc.function.name if tc.function else "",
                            "arguments": tc.function.arguments if tc.function else "",
                        },
                    }
                    for tc in delta.tool_calls
                ]
                logger.debug(
                    "Extracted tool calls from chunk: %s", stream_chunk.tool_calls
                )

            yield stream_chunk

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        """Complete request and aggregate response."""
        text = ""
        thinking = ""
        usage: TokenUsage | None = None
        raw_tool_calls: list[dict] = []

        async for chunk in self.stream_completion(messages, tools):
            if chunk.usage:
                usage = chunk.usage
            if chunk.content:
                text += chunk.content
            if chunk.reasoning:
                thinking += chunk.reasoning
            if chunk.tool_calls:
                for tc in chunk.tool_calls:
                    idx = tc["index"]
                    while len(raw_tool_calls) <= idx:
                        raw_tool_calls.append(
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        )
                    rtc = raw_tool_calls[idx]
                    if tc["id"]:
                        rtc["id"] += tc["id"]
                    if tc["function"]["name"]:
                        rtc["function"]["name"] += tc["function"]["name"]
                    if tc["function"]["arguments"]:
                        rtc["function"]["arguments"] += tc["function"]["arguments"]

        # Parse tool calls
        from artifice.agent.tools.base import ToolCall

        tool_calls: list[ToolCall] = []
        for rtc in raw_tool_calls:
            name = rtc["function"]["name"]
            try:
                args = json.loads(rtc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=rtc["id"], name=name, args=args))

        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            thinking=thinking or None,
            usage=usage,
        )

    async def check_connection(self) -> bool:
        """Check connectivity by attempting a minimal request."""
        try:
            test_messages = [{"role": "user", "content": "Hi"}]
            await self.complete(test_messages)
            return True
        except Exception:
            return False
