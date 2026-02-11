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
        model: str = "gpt-5",
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
    ):
        """Initialize Copilot agent.

        Args:
            model: Model identifier to use. Defaults to gpt-5.
            system_prompt: Optional system prompt to guide the agent's behavior.
            on_connect: Optional callback called when the client first connects.
        """
        self.model = model
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

                logger.info(f"[CopilotAgent] Connected to Copilot CLI")
            except ImportError:
                raise ImportError(
                    "github-copilot-sdk package not installed. "
                    "Install with: pip install github-copilot-sdk"
                )
            except Exception as e:
                logger.error(f"[CopilotAgent] Failed to start client: {e}")
                raise

        return self._client

    async def _get_session(self):
        """Get or create a Copilot session."""
        if self._session is None:
            client = await self._get_client()

            session_config = {
                "model": self.model,
                "streaming": True,
            }

            # Add system message if provided
            if self.system_prompt:
                session_config["system_message"] = {
                    "content": self.system_prompt,
                }

            self._session = await client.create_session(session_config)
            logger.info(f"[CopilotAgent] Created session with model {self.model}")

        return self._session

    def clear_conversation(self):
        """Clear the conversation history by destroying the current session."""
        if self._session is not None:
            # Schedule session destruction
            asyncio.create_task(self._destroy_session())
            self._session = None

    async def _destroy_session(self):
        """Async helper to destroy session."""
        if self._session is not None:
            try:
                await self._session.destroy()
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
            loop = asyncio.get_running_loop()

            # Track the response
            response_chunks = []
            done_event = asyncio.Event()
            error_message = None
            stop_reason = None

            def handle_event(event):
                """Handle session events.

                May be called from a background thread, so use
                call_soon_threadsafe to schedule callbacks on the event loop.
                """
                nonlocal error_message, stop_reason

                event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)

                if event_type == "assistant.message_delta":
                    # Streaming chunk
                    delta = event.data.delta_content or ""
                    if delta:
                        response_chunks.append(delta)
                        if on_chunk:
                            loop.call_soon_threadsafe(on_chunk, delta)

                elif event_type == "assistant.message":
                    # Final message
                    content = event.data.content or ""
                    logger.info(
                        f"[CopilotAgent] Received final message ({len(content)} chars)"
                    )
                    # Use final content if we didn't get deltas
                    if not response_chunks and content:
                        response_chunks.append(content)
                        if on_chunk:
                            loop.call_soon_threadsafe(on_chunk, content)

                elif event_type == "session.idle":
                    # Session finished processing
                    logger.info("[CopilotAgent] Session idle")
                    loop.call_soon_threadsafe(done_event.set)

                elif event_type == "error":
                    # Error occurred
                    error_message = str(event.data) if hasattr(event, 'data') else "Unknown error"
                    logger.error(f"[CopilotAgent] Error event: {error_message}")
                    loop.call_soon_threadsafe(done_event.set)

            # Register event handler
            session.on(handle_event)

            # Send the prompt
            logger.info(f"[CopilotAgent] Sending prompt: {prompt}")
            await session.send({"prompt": prompt})

            # Wait for completion
            await done_event.wait()

            # Combine response chunks
            full_text = "".join(response_chunks)

            if error_message:
                return AgentResponse(text="", error=error_message)

            return AgentResponse(
                text=full_text,
                stop_reason=stop_reason or "end_turn",
            )

        except ImportError as e:
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
