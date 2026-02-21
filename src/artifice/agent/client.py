"""Agent - manages LLM conversation and tool calls via provider abstraction."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from artifice.agent.conversation import ConversationManager
from artifice.agent.providers.base import Provider, TokenUsage
from artifice.agent.tools.base import ToolCall, get_schemas_for

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from an Agent completion request."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None
    error: str | None = None
    usage: TokenUsage | None = None


class Agent(ConversationManager):
    """Manages LLM conversation history and streaming via provider abstraction.

    Supports native OpenAI-style tool calls (python/shell) and maintains
    conversation context across turns. Uses a Provider for low-level
    LLM communication.

    Configuration can be passed either via a Provider instance or directly
    (for backward compatibility with any-llm style config).
    """

    def __init__(
        self,
        provider: Provider,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        on_connect: Callable | None = None,
    ) -> None:
        super().__init__()
        self.system_prompt = system_prompt
        self.tools = tools
        self._on_connect = on_connect
        self._connected = False
        self._provider = provider

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        """Send a prompt, stream the response, and return the full result."""
        if prompt.strip():
            self.add_user_message(prompt)
            if self._pending_tool_calls:
                logger.debug(
                    "Clearing %d pending tool calls due to new user message",
                    len(self._pending_tool_calls),
                )
                self.clear_pending_tool_calls()

        messages = self._messages.copy()
        sys_content = self.system_prompt or ""
        if sys_content and (not messages or messages[0].get("role") != "system"):
            messages = [{"role": "system", "content": sys_content}, *messages]

        tool_schemas = get_schemas_for(self.tools) if self.tools else None

        try:
            text = ""
            thinking = ""
            usage: TokenUsage | None = None
            raw_tool_calls: list[dict] = []

            async for chunk in self._provider.stream_completion(
                messages=messages,
                tools=tool_schemas,
                on_chunk=on_chunk,
                on_thinking_chunk=on_thinking_chunk,
            ):
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

        except asyncio.CancelledError:
            if prompt.strip():
                self.pop_last_user_message()
            raise
        except Exception:
            import traceback

            error = f"Connection error: {traceback.format_exc()}"
            logger.error("%s", error)
            if prompt.strip():
                self.pop_last_user_message()
            return AgentResponse(text="", error=error)

        if not self._connected:
            self._connected = True
            logger.debug("First successful connection to provider")
            if self._on_connect:
                self._on_connect("connected")

        tool_calls: list[ToolCall] = []
        logger.debug("Parsing %d raw tool calls", len(raw_tool_calls))
        for i, rtc in enumerate(raw_tool_calls):
            name = rtc["function"]["name"]
            args_str = rtc["function"]["arguments"]
            logger.debug(
                "Raw tool call %d: id=%s name=%s args=%s", i, rtc["id"], name, args_str
            )
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse tool call arguments: %s (args_str=%s)", e, args_str
                )
                args = {}
            tool_calls.append(ToolCall(id=rtc["id"], name=name, args=args))
        logger.debug("Parsed %d tool calls", len(tool_calls))

        if tool_calls:
            self.add_assistant_message(text if text else None, raw_tool_calls)
            self.set_pending_tool_calls(tool_calls)
        elif text:
            self.add_assistant_message(text)

        return AgentResponse(
            text=text,
            tool_calls=tool_calls,
            thinking=thinking or None,
            usage=usage,
        )
