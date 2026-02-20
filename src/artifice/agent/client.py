"""Agent - manages LLM conversation and tool calls via any-llm."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from artifice.agent.tools.base import ToolCall, get_schemas_for

if TYPE_CHECKING:
    from any_llm.types.completion import ChatCompletionChunk
    from typing import AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None
    error: str | None = None
    usage: TokenUsage | None = None


class Agent:
    """Manages LLM conversation history and streaming via any-llm.

    Supports native OpenAI-style tool calls (python/shell) and maintains
    conversation context across turns.

    Configuration is passed directly: model string, optional api_key,
    optional provider override, optional base_url. The any-llm library
    handles provider routing from the model string (e.g. "moonshot-v1-8k"
    for Kimi, "abab6.5s-chat" for MiniMax, etc.).
    """

    def __init__(
        self,
        model: str,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        on_connect: Callable | None = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools
        self._api_key = api_key
        self._provider = provider
        self._base_url = base_url
        self._on_connect = on_connect
        self._connected = False
        self.messages: list[dict] = []
        self._pending_tool_calls: list[ToolCall] = []

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        """Send a prompt, stream the response, and return the full result."""
        from any_llm import acompletion

        if prompt.strip():
            self.messages.append({"role": "user", "content": prompt})

        messages = self.messages.copy()
        sys_content = self.system_prompt or ""
        if sys_content and (not messages or messages[0].get("role") != "system"):
            messages = [{"role": "system", "content": sys_content}] + messages

        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, stream=True)
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._provider is not None:
            kwargs["provider"] = self._provider
        if self._base_url is not None:
            kwargs["api_base"] = self._base_url
        if self.tools is not None:
            kwargs["tools"] = get_schemas_for(self.tools)
            kwargs["tool_choice"] = "auto"

        try:
            stream = await acompletion(**kwargs)
            from typing import cast

            stream = cast("AsyncIterator[ChatCompletionChunk]", stream)
        except Exception:
            import traceback

            error = f"Connection error: {traceback.format_exc()}"
            logger.error("%s", error)
            if prompt.strip() and self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            return AgentResponse(text="", error=error)

        if not self._connected:
            self._connected = True
            if self._on_connect:
                self._on_connect("connected")

        text = ""
        thinking = ""
        usage: TokenUsage | None = None
        raw_tool_calls: list[dict] = []

        try:
            async for chunk in stream:
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = TokenUsage(
                        input_tokens=chunk.usage.prompt_tokens or 0,
                        output_tokens=chunk.usage.completion_tokens or 0,
                        total_tokens=chunk.usage.total_tokens or 0,
                    )
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning") and delta.reasoning:
                    reasoning_content = (
                        delta.reasoning.content
                        if hasattr(delta.reasoning, "content")
                        else str(delta.reasoning)
                    )
                    thinking += reasoning_content
                    if on_thinking_chunk:
                        on_thinking_chunk(reasoning_content)
                if delta.content:
                    text += delta.content
                    if on_chunk:
                        on_chunk(delta.content)
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        while len(raw_tool_calls) <= idx:
                            raw_tool_calls.append(
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            )
                        rtc = raw_tool_calls[idx]
                        if tc.id:
                            rtc["id"] += tc.id
                        if tc.function and tc.function.name:
                            rtc["function"]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            rtc["function"]["arguments"] += tc.function.arguments
        except asyncio.CancelledError:
            if prompt.strip() and self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            raise

        # Parse raw tool calls into ToolCall objects
        tool_calls: list[ToolCall] = []
        for rtc in raw_tool_calls:
            name = rtc["function"]["name"]
            try:
                args = json.loads(rtc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=rtc["id"], name=name, args=args))

        # Update conversation history
        if tool_calls:
            self.messages.append(
                {
                    "role": "assistant",
                    "content": text if text else None,
                    "tool_calls": raw_tool_calls,
                }
            )
            self._pending_tool_calls = list(tool_calls)
        elif text:
            self.messages.append({"role": "assistant", "content": text})

        return AgentResponse(
            text=text,
            tool_calls=tool_calls,
            thinking=thinking or None,
            usage=usage,
        )

    @property
    def has_pending_tool_calls(self) -> bool:
        return len(self._pending_tool_calls) > 0

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Add a tool execution result to conversation history."""
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        )
        self._pending_tool_calls = [
            tc for tc in self._pending_tool_calls if tc.id != tool_call_id
        ]

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []
        self._pending_tool_calls = []
