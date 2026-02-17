"""GitHub Copilot provider implementation."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .provider import ProviderBase, ProviderResponse

logger = logging.getLogger(__name__)


class CopilotProvider(ProviderBase):
    """Provider for GitHub Copilot CLI.

    Note: Copilot uses session-based conversation management, so the provider
    maintains internal state (session) unlike other providers. This is a
    compromise to accommodate Copilot's API design.
    """

    def __init__(
        self,
        model: str | None = None,
        on_connect: Callable | None = None,
    ):
        """Initialize Copilot provider.

        Args:
            model: Model identifier. Defaults to claude-haiku-4.5.
            on_connect: Optional callback called when the client first connects.
        """
        self.model = model if model else "claude-haiku-4.5"
        self.on_connect = on_connect
        self._client = None
        self._session = None

    async def _get_client(self):
        """Lazy import and create Copilot client."""
        if self._client is None:
            try:
                from copilot import CopilotClient

                self._client = CopilotClient()
                await self._client.start()

                if self.on_connect:
                    self.on_connect(f"Copilot ({self.model})")

                logger.info("Connected to Copilot CLI")
            except ImportError as e:
                error_msg = (
                    "github-copilot-sdk package not installed. "
                    "Install with: pip install github-copilot-sdk"
                )
                logger.error("%s", error_msg)
                raise ImportError(error_msg) from e
            except Exception as e:
                error_msg = f"Failed to start Copilot client: {e}"
                logger.error("%s", error_msg)
                raise RuntimeError(error_msg) from e

        return self._client

    async def _get_session(self, system_prompt: str | None):
        """Get or create a Copilot session."""
        if self._session is None:
            client = await self._get_client()

            session_config = {
                "model": self.model,
                "streaming": True,
                "tools": [],
                "available_tools": [],
                "infinite_sessions": {"enabled": False},
            }

            # Add system message if provided
            if system_prompt:
                session_config["system_message"] = {
                    "mode": "append",
                    "content": system_prompt,
                }

            self._session = await client.create_session(session_config)
            logger.info("Created session with model %s", self.model)

        return self._session

    async def reset_session(self):
        """Reset the session (for clearing conversation history)."""
        if self._session is not None:
            try:
                await self._session.destroy()
                logger.info("Session destroyed")
            except Exception as e:
                logger.error("Error destroying session: %s", e)
            finally:
                self._session = None

    async def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> ProviderResponse:
        """Send messages to Copilot and stream the response.

        Note: messages parameter is accepted for API compatibility, but Copilot
        manages conversation history via its session internally. Only the last
        user message from messages is sent.

        Args:
            messages: Full conversation history (only last user message is used)
            system_prompt: Optional system prompt
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            ProviderResponse with the complete response
        """
        try:
            session = await self._get_session(system_prompt)

            # Extract the last user message
            prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    prompt = msg.get("content", "")
                    break

            if not prompt:
                return ProviderResponse(
                    text="", error="No user message found in messages"
                )

            # Register streaming handler for delta events
            unsubscribe = None
            if on_chunk:

                def handle_delta(event):
                    try:
                        if (
                            event.type.value == "assistant.reasoning_delta"
                            and on_thinking_chunk
                        ):
                            delta = event.data.delta_content
                            if delta:
                                on_thinking_chunk(delta)
                        elif event.type.value == "assistant.message_delta":
                            delta = event.data.delta_content
                            if delta:
                                on_chunk(delta)
                    except Exception as e:
                        logger.error("Delta handler error: %s", e)

                unsubscribe = session.on(handle_delta)

            try:
                logger.info("Sending prompt (%d chars)", len(prompt))
                response = await session.send_and_wait({"prompt": prompt}, timeout=60.0)
            finally:
                if unsubscribe:
                    unsubscribe()

            if response is None:
                return ProviderResponse(
                    text="", error="Timeout waiting for Copilot response"
                )

            if response.type.value == "session.error":
                error_msg = getattr(response.data, "message", str(response.data))
                return ProviderResponse(text="", error=error_msg)

            if response.type.value == "assistant.message":
                content = response.data.content or ""
                logger.info("Response complete (%d chars)", len(content))
                # If streaming was off or no deltas arrived, send full text
                if content and on_chunk and not unsubscribe:
                    on_chunk(content)
                return ProviderResponse(text=content, stop_reason="end_turn")

            # Unexpected response type
            logger.warning("Unexpected response type: %s", response.type)
            return ProviderResponse(text="", stop_reason="end_turn")

        except (ImportError, RuntimeError, PermissionError, FileNotFoundError) as e:
            logger.error("Setup error: %s", e)
            return ProviderResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Copilot: {e}"
            logger.error("%s", error_msg)
            return ProviderResponse(text="", error=error_msg)

    async def cleanup(self):
        """Cleanup resources (for use in context managers)."""
        if self._session is not None:
            try:
                await self._session.destroy()
                logger.info("Session destroyed")
            except Exception as e:
                logger.error("Error destroying session: %s", e)

        if self._client is not None:
            try:
                await self._client.stop()
                logger.info("Client stopped")
            except Exception as e:
                logger.error("Error stopping client: %s", e)
