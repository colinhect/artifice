"""GitHub Copilot SDK provider implementation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, AsyncIterator

from artifice.agent.providers.base import (
    Provider,
    StreamChunk,
)

if TYPE_CHECKING:
    from copilot.types import CopilotClientOptions

logger = logging.getLogger(__name__)


class CopilotProvider(Provider):
    """Provider implementation using GitHub Copilot SDK.

    Requires GitHub Copilot CLI installed and authenticated.
    Uses the github-copilot-sdk package for communication.
    """

    def __init__(
        self,
        model: str = "gpt-5",
        *,
        cli_path: str | None = None,
        cli_url: str | None = None,
        port: int = 0,
        use_stdio: bool = True,
    ) -> None:
        self.model = model
        self._cli_path = cli_path
        self._cli_url = cli_url
        self._port = port
        self._use_stdio = use_stdio
        self._client: Any = None
        self._session: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_client(self) -> Any:
        """Ensure the Copilot client is started."""
        if self._client is not None:
            return self._client

        from copilot import CopilotClient

        config: CopilotClientOptions = {
            "port": self._port,
            "use_stdio": self._use_stdio,
            "auto_start": True,
        }
        if self._cli_path:
            config["cli_path"] = self._cli_path
        if self._cli_url:
            config["cli_url"] = self._cli_url

        self._client = CopilotClient(config)
        await self._client.start()
        logger.info("Copilot client started")
        return self._client

    async def _create_session(
        self,
        tools: list[dict[str, Any]] | None = None,
        system_message: str | None = None,
    ) -> Any:
        """Create or resume a Copilot session."""
        client = await self._ensure_client()

        config: dict[str, Any] = {
            "model": self.model,
            "streaming": True,
        }

        if system_message:
            config["system_message"] = {
                "mode": "append",
                "content": system_message,
            }

        if tools:
            from copilot import define_tool
            from copilot.types import ToolInvocation

            copilot_tools = []
            for tool in tools:
                tool_name = tool.get("name", "")

                def make_handler(
                    t: dict[str, Any],
                ) -> Callable[[Any, ToolInvocation], Any]:
                    def handler(args: Any, inv: ToolInvocation) -> dict[str, Any]:
                        return {
                            "text_result_for_llm": f"Tool {t.get('name', '')} execution is handled externally",
                            "result_type": "success",
                        }

                    return handler

                copilot_tools.append(
                    define_tool(  # type: ignore[call-overload]
                        name=tool_name,
                        description=tool.get("description", ""),
                        handler=make_handler(tool),
                    )
                )
            config["tools"] = copilot_tools

        if self._session is None:
            self._session = await client.create_session(config)
            logger.debug("Created new Copilot session: %s", self._session.session_id)
        return self._session

    async def _handle_tool_call(
        self, tool_name: str, args: dict[str, Any], invocation: Any
    ) -> dict[str, Any]:
        """Handle a tool call from Copilot.

        This is a placeholder - actual tool execution is handled by the Agent
        layer. Copilot's tool system is different from typical LLM APIs.
        """
        logger.debug("Tool call received: %s(%s)", tool_name, args)
        return {
            "text_result_for_llm": f"Tool {tool_name} execution is handled externally",
            "result_type": "success",
        }

    async def stream_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion from GitHub Copilot."""
        async with self._lock:
            session = await self._create_session(tools)

        done = asyncio.Event()
        queue: asyncio.Queue[StreamChunk | None] = asyncio.Queue()

        def handler(event: Any) -> None:
            try:
                if event.type == "assistant.message.delta":
                    content = event.data.delta_content
                    if content:
                        chunk = StreamChunk(content=content)
                        queue.put_nowait(chunk)
                        if on_chunk:
                            on_chunk(content)

                elif event.type == "assistant.reasoning.delta":
                    reasoning = event.data.delta_content
                    if reasoning:
                        chunk = StreamChunk(reasoning=reasoning)
                        queue.put_nowait(chunk)
                        if on_thinking_chunk:
                            on_thinking_chunk(reasoning)

                elif event.type == "assistant.message":
                    content = event.data.content
                    if content:
                        chunk = StreamChunk(content=content)
                        queue.put_nowait(chunk)

                elif event.type == "assistant.reasoning":
                    reasoning = event.data.content
                    if reasoning:
                        chunk = StreamChunk(reasoning=reasoning)
                        queue.put_nowait(chunk)

                elif event.type == "tool.executionStart":
                    chunk = StreamChunk(
                        tool_calls=[
                            {
                                "id": getattr(event.data, "tool_call_id", ""),
                                "type": "function",
                                "function": {
                                    "name": getattr(event.data, "tool_name", ""),
                                    "arguments": getattr(event.data, "arguments", "{}"),
                                },
                            }
                        ]
                    )
                    queue.put_nowait(chunk)

                elif event.type == "session.idle":
                    done.set()

                elif event.type == "session.error":
                    error_msg = getattr(event.data, "message", "Unknown error")
                    logger.error("Session error: %s", error_msg)
                    done.set()

            except Exception as e:
                logger.exception("Error handling Copilot event: %s", e)
                done.set()

        unsubscribe = session.on(handler)

        try:
            prompt = self._messages_to_prompt(messages)
            await session.send({"prompt": prompt})

            while not done.is_set():
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
                    if chunk is not None:
                        yield chunk
                except asyncio.TimeoutError:
                    continue

            while not queue.empty():
                chunk = queue.get_nowait()
                if chunk is not None:
                    yield chunk

        finally:
            unsubscribe()

    def _messages_to_prompt(self, messages: list[dict[str, Any]]) -> str:
        """Convert message history to a prompt string.

        Copilot SDK uses a single prompt rather than a message array.
        We format the conversation history into a readable format.
        """
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                parts.append(f"Tool ({tool_name}): {content}")

        return "\n\n".join(parts)

    async def check_connection(self) -> bool:
        """Check connectivity to Copilot CLI."""
        try:
            client = await self._ensure_client()
            await client.ping("health check")
            return True
        except Exception as e:
            logger.error("Copilot connection check failed: %s", e)
            return False

    async def close(self) -> None:
        """Clean up resources."""
        if self._session is not None:
            try:
                await self._session.destroy()
            except Exception as e:
                logger.warning("Error destroying session: %s", e)
            self._session = None

        if self._client is not None:
            try:
                await self._client.stop()
            except Exception as e:
                logger.warning("Error stopping client: %s", e)
            self._client = None

    async def __aenter__(self) -> "CopilotProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        await self.close()
        return False
