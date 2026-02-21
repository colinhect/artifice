"""Agent - manages LLM conversation and tool calls via provider abstraction."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from artifice.agent.providers.base import Provider, TokenUsage
from artifice.agent.tools.base import ToolCall, get_schemas_for

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from an Agent completion request."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None
    error: str | None = None
    usage: TokenUsage | None = None


class Agent:
    """Manages LLM conversation history and streaming via provider abstraction.

    Supports native OpenAI-style tool calls (python/shell) and maintains
    conversation context across turns. Uses a Provider for low-level
    LLM communication.

    Configuration can be passed either via a Provider instance or directly
    (for backward compatibility with any-llm style config).
    """

    def __init__(
        self,
        model: str | None = None,
        system_prompt: str | None = None,
        tools: list[str] | None = None,
        provider: Provider | None = None,
        api_key: str | None = None,
        provider_name: str | None = None,
        base_url: str | None = None,
        on_connect: Callable | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = tools
        self._on_connect = on_connect
        self._connected = False
        self.messages: list[dict] = []
        self._pending_tool_calls: list[ToolCall] = []

        # Initialize provider
        if provider is not None:
            self._provider = provider
        elif model is not None:
            # Backward compatibility: create AnyLLMProvider
            from artifice.agent.providers.anyllm import AnyLLMProvider

            self._provider = AnyLLMProvider(
                model=model,
                api_key=api_key,
                provider=provider_name,
                base_url=base_url,
            )
        else:
            error = "Either 'provider' or 'model' must be provided"
            raise ValueError(error)

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        """Send a prompt, stream the response, and return the full result."""
        if prompt.strip():
            self.messages.append({"role": "user", "content": prompt})
            # If user sends a new message while there are pending tool calls,
            # clear them - the user is choosing to respond instead of executing
            if self._pending_tool_calls:
                logger.debug(
                    "Clearing %d pending tool calls due to new user message",
                    len(self._pending_tool_calls),
                )
                self._pending_tool_calls.clear()

        messages = self.messages.copy()
        sys_content = self.system_prompt or ""
        if sys_content and (not messages or messages[0].get("role") != "system"):
            messages = [{"role": "system", "content": sys_content}, *messages]

        tool_schemas = get_schemas_for(self.tools) if self.tools else None

        try:
            # Stream via provider
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
            if prompt.strip() and self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            raise
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

        # Parse raw tool calls into ToolCall objects
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
        """Check if there are pending tool calls to execute."""
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
