from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable

from .common import AgentBase, AgentResponse

logger = logging.getLogger(__name__)


class CopilotAgent(AgentBase):
    """Agent for connecting to GitHub Copilot CLI with streaming responses.

    This agent uses the GitHub Copilot SDK to communicate with the Copilot CLI
    server. It supports streaming responses and maintains conversation history.

    Requirements:
    - GitHub Copilot CLI must be installed and accessible in PATH
    - GitHub authentication (via `copilot auth login` or GITHUB_TOKEN env var)

    Thread Safety: The agent manages its own async session and event loop
    coordination for streaming responses.
    """

    def __init__(
        self,
        model: str | None,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
    ):
        """Initialize Copilot agent.

        Args:
            model: Model identifier to use. Defaults to gpt-5.
            system_prompt: Optional system prompt to guide the agent's behavior.
            on_connect: Optional callback called when the client first connects.
        """
        if model:
            self.model = model
        else:
            self.model = "claude-haiku-4.5"
        self.system_prompt = system_prompt
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

                logger.info("[CopilotAgent] Connected to Copilot CLI")
            except ImportError as e:
                error_msg = (
                    "github-copilot-sdk package not installed. "
                    "Install with: pip install github-copilot-sdk"
                )
                logger.error(f"[CopilotAgent] {error_msg}")
                raise ImportError(error_msg) from e
            except Exception as e:
                error_msg = f"Failed to start Copilot client: {e}"
                logger.error(f"[CopilotAgent] {error_msg}")
                raise RuntimeError(error_msg) from e

        return self._client

    async def _get_session(self):
        """Get or create a Copilot session."""
        if self._session is None:
            client = await self._get_client()

            session_config = {
                "model": self.model,
                "streaming": True,
                "tools": [],
                "available_tools": [],
                "infinite_sessions": {"enabled":False}
            }

            # Add system message if provided
            if self.system_prompt:
                session_config["system_message"] = {
                    "mode": "append",
                    "content": self.system_prompt,
                }

            self._session = await client.create_session(session_config)
            logger.info(f"[CopilotAgent] Created session with model {self.model}")

        return self._session

    def clear_conversation(self):
        """Clear the conversation history by destroying the current session."""
        if self._session is not None:
            session = self._session
            self._session = None
            asyncio.create_task(self._destroy_session(session))

    async def _destroy_session(self, session=None):
        """Async helper to destroy session."""
        session = session or self._session
        if session is not None:
            try:
                await session.destroy()
                logger.info("[CopilotAgent] Session destroyed")
            except Exception as e:
                logger.error(f"[CopilotAgent] Error destroying session: {e}")

    async def send_prompt(
        self, prompt: str, on_chunk: Optional[Callable] = None
    ) -> AgentResponse:
        """Send a prompt to Copilot and stream the response.

        Args:
            prompt: The prompt text.
            on_chunk: Optional callback for streaming text chunks.

        Returns:
            AgentResponse with the complete response.
        """
        try:
            session = await self._get_session()

            # Register streaming handler for delta events
            unsubscribe = None
            if on_chunk:
                def handle_delta(event):
                    if event.type.value == "assistant.message_delta":
                        try:
                            delta = event.data.delta_content
                            if delta:
                                on_chunk(delta)
                        except Exception as e:
                            logger.error(f"[CopilotAgent] Delta handler error: {e}")

                unsubscribe = session.on(handle_delta)

            try:
                logger.info(f"[CopilotAgent] Sending prompt: {prompt[:100]}...")
                response = await session.send_and_wait(
                    {"prompt": prompt}, timeout=60.0
                )
            finally:
                if unsubscribe:
                    unsubscribe()

            if response is None:
                return AgentResponse(
                    text="", error="Timeout waiting for Copilot response"
                )

            if response.type.value == "session.error":
                error_msg = getattr(
                    response.data, "message", str(response.data)
                )
                return AgentResponse(text="", error=error_msg)

            if response.type.value == "assistant.message":
                content = response.data.content or ""
                # If streaming was off or no deltas arrived, send full text
                if content and on_chunk and not unsubscribe:
                    on_chunk(content)
                return AgentResponse(text=content, stop_reason="end_turn")

            # Unexpected response type
            logger.warning(
                f"[CopilotAgent] Unexpected response type: {response.type}"
            )
            return AgentResponse(text="", stop_reason="end_turn")

        except (ImportError, RuntimeError, PermissionError, FileNotFoundError) as e:
            logger.error(f"[CopilotAgent] Setup error: {e}")
            return AgentResponse(text="", error=str(e))
        except Exception as e:
            error_msg = f"Error communicating with Copilot: {e}"
            logger.error(f"[CopilotAgent] {error_msg}")
            return AgentResponse(text="", error=error_msg)

    async def __aenter__(self):
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources."""
        if self._session is not None:
            await self._destroy_session()

        if self._client is not None:
            try:
                await self._client.stop()
                logger.info("[CopilotAgent] Client stopped")
            except Exception as e:
                logger.error(f"[CopilotAgent] Error stopping client: {e}")
