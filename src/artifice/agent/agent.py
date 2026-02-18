"""Agent - manages LLM conversation and tool calls via any-llm."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from any_llm.types.completion import ChatCompletionChunk
    from typing import AsyncIterator

logger = logging.getLogger(__name__)

_PYTHON_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "python",
        "description": "Execute Python code in the user's REPL session.",
        "parameters": {
            "type": "object",
            "required": ["code"],
            "properties": {"code": {"type": "string"}},
        },
    },
}

_SHELL_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": "Execute a shell command in the user's terminal session.",
        "parameters": {
            "type": "object",
            "required": ["command"],
            "properties": {"command": {"type": "string"}},
        },
    },
}

_ALL_TOOLS = [_PYTHON_TOOL, _SHELL_TOOL]


# ── MiniMax tool calling helpers ──────────────────────────────────────────────


def _is_minimax_model(model: str) -> bool:
    """Return True if the model string indicates a MiniMax model."""
    return "minimax" in model.lower() or model.lower().startswith("abab")


def _minimax_tool_prompt(tools: list[dict]) -> str:
    """Build the MiniMax system-prompt section that defines available tools.

    Follows the format from the MiniMax-M2.5 tool calling guide:
    https://huggingface.co/unsloth/MiniMax-M2.5/blob/main/docs/tool_calling_guide.md
    """
    tool_entries: list[str] = []
    for tool_def in tools:
        func = tool_def.get("function", tool_def)
        entry = json.dumps(
            {
                "name": func["name"],
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            },
            ensure_ascii=False,
        )
        tool_entries.append(f"<tool>{entry}</tool>")

    tools_block = "\n".join(tool_entries)
    return (
        "\n\n# Tools\n"
        "You may call one or more tools to assist with the user query.\n"
        "Here are the tools available in JSONSchema format:\n\n"
        f"<tools>\n{tools_block}\n</tools>\n\n"
        "When making tool calls, use XML format to invoke tools and pass parameters:\n\n"
        "<minimax:tool_call>\n"
        '<invoke name="tool-name">\n'
        '<parameter name="param-key">param-value</parameter>\n'
        "</invoke>\n"
        "</minimax:tool_call>"
    )


_MINIMAX_TOOL_CALL_RE = re.compile(
    r"<minimax:tool_call>(.*?)</minimax:tool_call>", re.DOTALL
)
_MINIMAX_INVOKE_RE = re.compile(r"<invoke name=(.*?)</invoke>", re.DOTALL)
_MINIMAX_PARAM_RE = re.compile(r"<parameter name=(.*?)</parameter>", re.DOTALL)


def _parse_minimax_tool_calls(
    text: str, tools: list[dict] | None = None, start_id: int = 0
) -> tuple[str, list[ToolCall]]:
    """Parse ``<minimax:tool_call>`` XML blocks from *text*.

    Returns ``(prose, tool_calls)`` where *prose* is the text with tool call
    blocks removed and *tool_calls* is the list of parsed ``ToolCall`` objects.
    """
    if "<minimax:tool_call>" not in text:
        return text, []

    # Build param-type lookup from tool definitions
    param_config: dict[str, dict[str, str]] = {}
    for tool_def in tools or []:
        func = tool_def.get("function", tool_def)
        name = func.get("name", "")
        props = func.get("parameters", {}).get("properties", {})
        param_config[name] = {k: v.get("type", "string") for k, v in props.items()}

    tool_calls: list[ToolCall] = []
    tc_id = start_id

    for tc_block in _MINIMAX_TOOL_CALL_RE.findall(text):
        for invoke_match in _MINIMAX_INVOKE_RE.findall(tc_block):
            # Extract function name (first attribute value before ">")
            name_match = re.search(r"^([^>]+)", invoke_match)
            if not name_match:
                continue
            raw_name = name_match.group(1).strip().strip("\"'")

            # Extract parameters
            args: dict[str, Any] = {}
            types = param_config.get(raw_name, {})
            for param_match in _MINIMAX_PARAM_RE.findall(invoke_match):
                pm = re.search(r"^([^>]+)>(.*)", param_match, re.DOTALL)
                if not pm:
                    continue
                param_name = pm.group(1).strip().strip("\"'")
                param_value = pm.group(2).strip()
                # Strip leading/trailing newlines inside param value
                param_value = param_value.strip("\n")

                ptype = types.get(param_name, "string")
                args[param_name] = _convert_param_value(param_value, ptype)

            tool_calls.append(ToolCall(id=f"minimax_{tc_id}", name=raw_name, args=args))
            tc_id += 1

    # Remove tool call blocks from prose
    prose = _MINIMAX_TOOL_CALL_RE.sub("", text)
    prose = re.sub(r"\n{3,}", "\n\n", prose).strip()
    return prose, tool_calls


def _convert_param_value(value: str, param_type: str) -> Any:
    """Convert a string parameter value based on the declared JSON Schema type."""
    if value.lower() == "null":
        return None
    ptype = param_type.lower()
    if ptype in ("string", "str", "text"):
        return value
    if ptype in ("integer", "int"):
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if ptype in ("number", "float"):
        try:
            v = float(value)
            return int(v) if v == int(v) else v
        except (ValueError, TypeError):
            return value
    if ptype in ("boolean", "bool"):
        return value.lower() in ("true", "1")
    # object, array, or unknown — try JSON parse
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


@dataclass
class ToolCall:
    """A tool call requested by the model."""

    id: str
    name: str  # "python" or "shell"
    args: dict  # {"code": "..."} or {"command": "..."}

    @property
    def code(self) -> str:
        """Return the code/command string."""
        return self.args.get("code") or self.args.get("command", "")

    @property
    def language(self) -> str:
        """Return 'python' or 'bash'."""
        return "bash" if self.name == "shell" else "python"


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
        use_tools: bool = False,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        on_connect: Callable | None = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.use_tools = use_tools
        self._api_key = api_key
        self._provider = provider
        self._base_url = base_url
        self._on_connect = on_connect
        self._connected = False
        self.messages: list[dict] = []
        self._pending_tool_calls: list[ToolCall] = []
        self._minimax_tc_counter: int = 0

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

        is_minimax = _is_minimax_model(self.model)

        messages = self.messages.copy()
        sys_content = self.system_prompt or ""
        # For MiniMax models, embed tool definitions in the system prompt
        if self.use_tools and is_minimax:
            sys_content += _minimax_tool_prompt(_ALL_TOOLS)
        if sys_content and (not messages or messages[0].get("role") != "system"):
            messages = [{"role": "system", "content": sys_content}] + messages

        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, stream=True)
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._provider is not None:
            kwargs["provider"] = self._provider
        if self._base_url is not None:
            kwargs["base_url"] = self._base_url
        if self.use_tools and not is_minimax:
            kwargs["tools"] = _ALL_TOOLS
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
        if is_minimax and self.use_tools:
            # MiniMax: tool calls are XML in the response text
            text, tool_calls = _parse_minimax_tool_calls(
                text, _ALL_TOOLS, start_id=self._minimax_tc_counter
            )
            self._minimax_tc_counter += len(tool_calls)
        else:
            for rtc in raw_tool_calls:
                name = rtc["function"]["name"]
                try:
                    args = json.loads(rtc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=rtc["id"], name=name, args=args))

        # Update conversation history
        if tool_calls:
            if is_minimax:
                # MiniMax: store the full original text (with tool XML stripped)
                # plus tool calls as standard format for result tracking
                raw_tc = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.args),
                        },
                    }
                    for tc in tool_calls
                ]
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": text if text else None,
                        "tool_calls": raw_tc,
                    }
                )
            else:
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
