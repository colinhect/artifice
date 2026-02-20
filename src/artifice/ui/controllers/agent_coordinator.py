"""AgentCoordinator - manages agent communication and response handling."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from artifice.ui.components.blocks.blocks import (
    AgentInputBlock,
    ToolCallBlock,
)

if TYPE_CHECKING:
    from artifice.agent import Agent, AgentResponse, SimulatedAgent
    from artifice.agent.streaming.detector import StreamingFenceDetector
    from artifice.agent.streaming.manager import StreamManager
    from artifice.ui.components.blocks.blocks import BaseBlock
    from artifice.ui.components.output import TerminalOutput
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
        batch_update_fn: Callable,
        call_after_refresh_fn: Callable,
        mark_block_in_context_fn: Callable[[BaseBlock], None],
        set_send_user_commands_to_agent_fn: Callable[[bool], None],
        is_send_user_commands_to_agent_fn: Callable[[], bool],
        get_config_attr_fn: Callable[[str], Any],
        status_manager,
    ) -> None:
        """Initialize the agent coordinator.

        Args:
            agent: The AI agent instance (or None if not configured)
            stream_manager: Manager for streaming chunks and detectors
            output: The terminal output widget for displaying blocks
            batch_update_fn: Function to get batch_update context manager
            call_after_refresh_fn: Function to schedule work after refresh
            mark_block_in_context_fn: Function to mark blocks as in-context
            set_send_user_commands_to_agent_fn: Function to set auto-send mode
            is_send_user_commands_to_agent_fn: Function to check auto-send mode
            get_config_attr_fn: Function to get config attributes
            status_manager: Status indicator manager for updating UI
        """
        self._agent = agent
        self._stream = stream_manager
        self._output = output
        self._batch_update = batch_update_fn
        self._call_after_refresh = call_after_refresh_fn
        self._mark_block_in_context = mark_block_in_context_fn
        self._set_send_user_commands_to_agent = set_send_user_commands_to_agent_fn
        self._is_send_user_commands_to_agent = is_send_user_commands_to_agent_fn
        self._get_config_attr = get_config_attr_fn
        self._status_manager = status_manager
        self._current_task: asyncio.Task | None = None

    async def handle_agent_prompt(self, prompt: str) -> None:
        """Handle AI agent prompt with code block detection.

        Creates an AgentInputBlock, streams the agent response, and
        enables auto-send mode after first interaction.
        """
        agent_input_block = AgentInputBlock(prompt)
        self._output.append_block(agent_input_block)
        self._mark_block_in_context(agent_input_block)

        if self._agent is None:
            from artifice.ui.components.blocks.blocks import AgentOutputBlock

            agent_output_block = AgentOutputBlock("No AI agent configured.")
            self._output.append_block(agent_output_block)
            agent_output_block.mark_failed()
            return

        detector, response = await self._stream_agent_response(self._agent, prompt)
        self._apply_agent_response(detector, response)

        # After first agent interaction, enable auto-send mode
        if not self._is_send_user_commands_to_agent():
            self._set_send_user_commands_to_agent(True)

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
        self._apply_agent_response(detector, response)

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
        prompt_prefix = self._get_config_attr("prompt_prefix")
        if prompt_prefix and prompt.strip():
            prompt = prompt_prefix + " " + prompt

        self._status_manager.set_active()
        try:
            response = await agent.send(
                prompt, on_chunk=on_chunk, on_thinking_chunk=on_thinking_chunk
            )
        except asyncio.CancelledError:
            self._status_manager.set_inactive()
            self._stream.finalize()
            self._stream.current_detector = None
            raise
        self._status_manager.set_inactive()
        self._status_manager.update_agent_info(usage=getattr(response, "usage", None))

        with self._batch_update():
            self._stream.finalize()

        self._stream.current_detector = None
        # Scroll after finalization — Markdown widgets may have changed content height
        self._call_after_refresh(lambda: self._output.scroll_end(animate=True))

        # Create ToolCallBlocks directly for native tool calls
        if response.tool_calls:
            with self._batch_update():
                first_tool_block = None
                for tc in response.tool_calls:
                    tool_block = ToolCallBlock(
                        tool_call_id=tc.id,
                        name=tc.name,
                        code=tc.display_text,
                        language=tc.display_language,
                        tool_args=tc.args,
                    )
                    self._output.append_block(tool_block)
                    self._mark_block_in_context(tool_block)
                    if first_tool_block is None:
                        first_tool_block = tool_block

            # Highlight first tool call block so user can run it
            if first_tool_block is not None:
                idx = self._output.index_of(first_tool_block)
                if idx is not None:
                    previous = self._output._highlighted_index
                    self._output._highlighted_index = idx
                    self._output._update_highlight(previous)
                    self._output.focus()

        return detector, response

    def _apply_agent_response(
        self, detector: StreamingFenceDetector, response: AgentResponse
    ) -> None:
        """Mark context, handle errors, and finalize agent output blocks."""
        with self._batch_update():
            for block in detector.all_blocks:
                self._mark_block_in_context(block)

            if detector.first_agent_block:
                if response.error:
                    detector.first_agent_block.append(
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

    def on_prompt_selected(self, path: str, content: str) -> None:
        """Handle prompt template selection: append to agent's system prompt."""
        if self._agent is not None:
            self._agent.messages.append({"role": "user", "content": content})

    async def continue_after_tool_call(self) -> None:
        """Continue the conversation after pending tool calls are resolved."""
        if self._agent is not None and not self._agent.has_pending_tool_calls:
            detector, response = await self._stream_agent_response(self._agent, "")
            self._apply_agent_response(detector, response)
