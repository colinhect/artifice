"""AgentCoordinator - manages agent communication and response handling."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from artifice.ui.components.blocks.blocks import (
    ToolCallBlock,
)
from artifice.ui.components.status import StatusIndicatorManager

if TYPE_CHECKING:
    from artifice.agent import Agent, AgentResponse, SimulatedAgent
    from artifice.agent.streaming import StreamingFenceDetector, StreamManager
    from artifice.ui.components.output import TerminalOutput
    from artifice.ui.widget import ArtificeTerminal
    from typing import Union

    AnyAgent = Union[Agent, SimulatedAgent]

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """Coordinates all agent communication, streaming, and response handling.

    This class encapsulates all agent-related logic from the main terminal widget,
    including:
    - Agent prompt handling
    - Response streaming
    - Tool call processing
    - Context tracking
    """

    def __init__(
        self,
        agent: AnyAgent | None,
        stream_manager: StreamManager,
        output: TerminalOutput,
        terminal: ArtificeTerminal,
        status_manager: StatusIndicatorManager,
    ) -> None:
        """Initialize the agent coordinator.

        Args:
            agent: The AI agent instance (or None if not configured)
            stream_manager: Manager for streaming chunks and detectors
            output: The terminal output widget for displaying blocks
            terminal: The main terminal widget (provides callbacks via methods)
            status_manager: Status indicator manager for updating UI
        """
        self._agent = agent
        self._stream = stream_manager
        self._output = output
        self._terminal = terminal
        self._status_manager = status_manager
        self._current_task: asyncio.Task | None = None

    async def handle_agent_prompt(self, prompt: str) -> None:
        """Handle AI agent prompt with code block detection.

        Streams the agent response and enables auto-send mode after first interaction.
        Note: The AgentInputBlock should already be created and displayed by the caller
        for immediate responsiveness.
        """
        if self._agent is None:
            from artifice.ui.components.blocks.blocks import AgentOutputBlock

            agent_output_block = AgentOutputBlock("No AI agent configured.")
            self._output.append_block(agent_output_block)
            agent_output_block.mark_failed()
            return

        detector, response = await self._stream_agent_response(self._agent, prompt)
        await self._apply_agent_response(detector, response)

        # After first agent interaction, enable auto-send mode
        if not self._terminal._is_send_user_commands_to_agent():
            self._terminal._set_send_user_commands_to_agent(True)

    async def send_execution_result_to_agent(
        self, code: str, language: str, output: str, error: str
    ) -> None:
        """Send execution results back to the agent and get its response.

        Args:
            code: The code that was executed
            language: The programming language (python or bash)
            output: Standard output from execution
            error: Standard error from execution
        """
        if self._agent is None:
            return

        result_text = output + error
        prompt = (
            f"Executed: <{language}>{code}</{language}>"
            + "\n\nOutput:\n"
            + result_text
            + "\n"
        )
        detector, response = await self._stream_agent_response(self._agent, prompt)
        await self._apply_agent_response(detector, response)

    async def _stream_agent_response(
        self, agent: AnyAgent, prompt: str
    ) -> tuple[StreamingFenceDetector, AgentResponse]:
        """Stream an agent response, splitting into prose and code blocks.

        Returns the detector (with all_blocks, first_agent_block) and AgentResponse.
        After streaming, ToolCallBlocks are created directly from response.tool_calls.
        """

        detector = self._stream.create_detector()
        # NOTE: We intentionally do NOT call detector.start() here.
        # Starting the detector eagerly would mount the AgentOutputBlock before
        # any thinking block, causing a race condition where thinking content
        # (which arrives first from the agent) appears after the prose block.
        # Instead, detector.start() is called lazily in _drain_chunks (via
        # call_later) so block ordering matches the arrival order of content.

        def on_chunk(text):
            self._stream.on_chunk(text)

        def on_thinking_chunk(text):
            self._stream.on_thinking_chunk(text)

        # Apply prompt prefix if configured
        prompt_prefix = self._terminal._get_config_attr("prompt_prefix")
        if prompt_prefix and prompt.strip():
            prompt = prompt_prefix + " " + prompt

        self._status_manager.set_active()
        try:
            response = await agent.send(
                prompt, on_chunk=on_chunk, on_thinking_chunk=on_thinking_chunk
            )
        except asyncio.CancelledError:
            self._status_manager.set_inactive()
            await self._stream.finalize()
            self._stream.current_detector = None
            raise
        self._status_manager.set_inactive()
        self._status_manager.update_agent_info(usage=getattr(response, "usage", None))

        with self._terminal._batch_update_ctx():
            await self._stream.finalize()

        self._stream.current_detector = None
        # Scroll after finalization — Markdown widgets may have changed content height
        self._terminal.call_after_refresh(lambda: self._output.scroll_end(animate=True))

        # Create ToolCallBlocks directly for native tool calls
        logger.debug("Response has %d tool calls", len(response.tool_calls))
        if response.tool_calls:
            with self._terminal._batch_update_ctx():
                first_tool_block = None
                for tc in response.tool_calls:
                    logger.debug(
                        "Creating ToolCallBlock for %s with args %s", tc.name, tc.args
                    )
                    tool_block = ToolCallBlock(
                        tool_call_id=tc.id,
                        name=tc.name,
                        code=tc.display_text,
                        language=tc.display_language,
                        tool_args=tc.args,
                    )
                    self._output.append_block(tool_block)
                    self._terminal._mark_block_in_context(tool_block)
                    if first_tool_block is None:
                        first_tool_block = tool_block

            # Highlight first tool call block so user can run it
            if first_tool_block is not None:
                idx = self._output.index_of(first_tool_block)
                if idx is not None:
                    self._output.highlight_block_at(idx)
                    self._output.focus()

        return detector, response

    async def _apply_agent_response(
        self, detector: StreamingFenceDetector, response: AgentResponse
    ) -> None:
        """Mark context, handle errors, and finalize agent output blocks."""
        with self._terminal._batch_update_ctx():
            for block in detector.all_blocks:
                self._terminal._mark_block_in_context(block)

            if detector.first_agent_block:
                if response.error:
                    await detector.first_agent_block.append(
                        f"\n**Error:** {response.error}\n"
                    )
                    detector.first_agent_block.flush()
                    detector.first_agent_block.mark_failed()
                else:
                    detector.first_agent_block.flush()
                    detector.first_agent_block.mark_success()

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Add a tool execution result to the agent's conversation history."""
        if self._agent is not None:
            self._agent.add_tool_result(tool_call_id, content)

    @property
    def has_pending_tool_calls(self) -> bool:
        """Check if the agent has pending tool calls."""
        return self._agent.has_pending_tool_calls if self._agent else False

    def clear(self) -> None:
        """Clear the agent's conversation context."""
        if self._agent is not None:
            self._agent.clear()

    @property
    def current_task(self) -> asyncio.Task | None:
        """Get the current agent task for cancellation."""
        return self._current_task

    @current_task.setter
    def current_task(self, value: asyncio.Task | None) -> None:
        self._current_task = value

    def on_prompt_selected(self, _path: str, content: str) -> None:
        """Handle prompt template selection: append to agent's system prompt."""
        if self._agent is not None:
            self._agent.messages.append({"role": "user", "content": content})

    async def continue_after_tool_call(self) -> None:
        """Continue the conversation after pending tool calls are resolved."""
        if self._agent is not None and not self._agent.has_pending_tool_calls:
            detector, response = await self._stream_agent_response(self._agent, "")
            await self._apply_agent_response(detector, response)
