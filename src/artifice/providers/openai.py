"""OpenAI-compatible provider implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Callable, Optional

from openai import OpenAI

from .provider import ProviderBase, ProviderResponse, TokenUsage

logger = logging.getLogger(__name__)

# Tool definitions for native tool-call support
_PYTHON_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "python",
        "description": (
            "Execute Python code in the user's REPL session. "
            "Use this to run computations, manipulate data, or produce output."
        ),
        "parameters": {
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code to execute.",
                }
            },
        },
    },
}

_SHELL_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": (
            "Execute a shell (bash) command in the user's terminal session. "
            "Use this to run system commands, file operations, or shell scripts."
        ),
        "parameters": {
            "type": "object",
            "required": ["command"],
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                }
            },
        },
    },
}


def _tool_calls_to_xml(tool_calls: list[dict]) -> str:
    """Convert a list of aggregated tool call dicts to XML code block format.

    Each tool call is converted to a <python>...</python> or <shell>...</shell>
    block that the StreamingFenceDetector can parse into executable CodeInputBlocks.

    Args:
        tool_calls: List of tool call dicts with keys: id, type, function.name,
            function.arguments (JSON-encoded string).

    Returns:
        XML string with one block per tool call, separated by newlines.
    """
    parts: list[str] = []
    for tc in tool_calls:
        name = tc.get("function", {}).get("name", "")
        raw_args = tc.get("function", {}).get("arguments", "{}")
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            logger.warning("Failed to parse tool call arguments: %r", raw_args)
            args = {}

        if name == "python":
            code = args.get("code", "")
            parts.append(f"<python>\n{code}\n</python>")
        elif name == "shell":
            command = args.get("command", "")
            parts.append(f"<shell>\n{command}\n</shell>")
        else:
            logger.warning("Unknown tool call: %r", name)

    return "\n".join(parts) + "\n" if parts else ""


class OpenAICompatibleProvider(ProviderBase):
    """Provider for OpenAI-compatible APIs.

    Supports OpenAI API and compatible services (Hugging Face, etc.).
    Handles reasoning/thinking content for o1/o3 models.

    When ``use_tools`` is True, the provider registers ``python`` and ``shell``
    as OpenAI function tools.  If the model responds with native tool calls
    instead of XML-formatted text, those calls are converted to
    ``<python>…</python>`` / ``<shell>…</shell>`` XML and returned via
    ``ProviderResponse.tool_calls_xml`` so the terminal's fence detector can
    present them as executable code blocks.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        on_connect: Callable | None = None,
        use_tools: bool = False,
    ):
        """Initialize OpenAI-compatible provider.

        Args:
            base_url: Base URL for the API endpoint
            api_key: API key for authentication
            model: Model identifier
            on_connect: Optional callback called when the client first connects
            use_tools: If True, register python/shell as native OpenAI tools so
                models that support function calling can emit structured tool
                calls instead of raw XML.
        """
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.on_connect = on_connect
        self.use_tools = use_tools
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
            ProviderResponse with the complete response.  If the model responded
            with native tool calls, ``tool_calls_xml`` will contain the
            ``<python>…</python>`` / ``<shell>…</shell>`` XML for the terminal
            to inject into the fence detector.
        """
        try:
            client = self._get_client()
            assert client

            logger.info("Sending %d messages to %s", len(messages), self.model)

            tools = [_PYTHON_TOOL, _SHELL_TOOL] if self.use_tools else []

            # Run synchronous streaming in executor to avoid blocking
            loop = asyncio.get_running_loop()
            cancelled = threading.Event()

            def sync_stream():
                """Synchronously stream from OpenAI-compatible API."""
                create_kwargs: dict = dict(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                if tools:
                    create_kwargs["tools"] = tools
                    create_kwargs["tool_choice"] = "auto"

                stream = client.chat.completions.create(**create_kwargs)

                text = ""
                thinking_text = ""
                chunk_count = 0
                usage = None
                # Accumulate tool call deltas keyed by index
                tool_calls: list[dict] = []

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

                        # Aggregate tool call deltas
                        if delta.tool_calls:
                            for tc_chunk in delta.tool_calls:
                                idx = tc_chunk.index
                                # Extend list to accommodate this index
                                while len(tool_calls) <= idx:
                                    tool_calls.append(
                                        {
                                            "id": "",
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    )
                                tc = tool_calls[idx]
                                if tc_chunk.id:
                                    tc["id"] += tc_chunk.id
                                if tc_chunk.function and tc_chunk.function.name:
                                    tc["function"]["name"] += tc_chunk.function.name
                                if tc_chunk.function and tc_chunk.function.arguments:
                                    tc["function"]["arguments"] += (
                                        tc_chunk.function.arguments
                                    )

                return text, thinking_text, chunk_count, usage, tool_calls

            try:
                text, thinking_text, chunk_count, usage, tool_calls = (
                    await loop.run_in_executor(None, sync_stream)
                )
            except asyncio.CancelledError:
                cancelled.set()
                raise

            # Convert any tool calls to XML for the fence detector
            tool_calls_xml: str | None = None
            if tool_calls:
                tool_calls_xml = _tool_calls_to_xml(tool_calls)
                logger.info(
                    "Received %d tool call(s); converted to XML (%d chars)",
                    len(tool_calls),
                    len(tool_calls_xml),
                )

            logger.info(
                "Response complete (%d chars in %d chunks, %d in/%d out tokens)",
                len(text),
                chunk_count,
                usage.input_tokens if usage else 0,
                usage.output_tokens if usage else 0,
            )
            if thinking_text:
                logger.debug("Received thinking content (%d chars)", len(thinking_text))

            return ProviderResponse(
                text=text,
                thinking=thinking_text if thinking_text else None,
                usage=usage,
                tool_calls_xml=tool_calls_xml,
                tool_calls=tool_calls if tool_calls else None,
            )

        except Exception:
            import traceback

            error_msg = f"Error communicating with model: {traceback.format_exc()}"
            logger.error("%s", error_msg)
            return ProviderResponse(text="", error=error_msg)
