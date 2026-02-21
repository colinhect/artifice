"""Main Artifice terminal widget."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import LoadingIndicator, Static

from artifice.core.events import InputMode
from artifice.core.history import History
from artifice.core.prompts import load_prompt
from artifice.agent import Agent, SimulatedAgent, create_agent
from artifice.agent.streaming import StreamManager
from artifice.execution import ExecutionResult, ExecutionStatus
from artifice.execution.coordinator import ExecutionCoordinator
from artifice.ui.components.input import TerminalInput, InputTextArea
from artifice.ui.components.output import TerminalOutput
from artifice.ui.components.blocks.blocks import (
    AgentInputBlock,
    BaseBlock,
    CodeOutputBlock,
    SystemBlock,
    ToolCallBlock,
)
from artifice.ui.components.status import StatusIndicatorManager
from artifice.ui.controllers import AgentCoordinator, NavigationController

if TYPE_CHECKING:
    from artifice.app import ArtificeApp
    from typing import Union

    AnyAgent = Union[Agent, SimulatedAgent]

logger = logging.getLogger(__name__)


class ArtificeTerminal(Widget):
    """Primary widget for interacting with Artifice."""

    BINDINGS = [
        Binding("ctrl+i", "focus_input", "Focus Input", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("ctrl+o", "toggle_mode_markdown", "Toggle Markdown", show=True),
        Binding("ctrl+c", "cancel_execution", "Cancel", show=True),
        Binding(
            "ctrl+g", "toggle_send_user_commands_to_agent", "Toggle Agent", show=True
        ),
        Binding("ctrl+n", "clear_agent_context", "Clear Context", show=True),
        Binding("alt+up", "navigate_up", "Navigate Up", show=True),
        Binding("alt+down", "navigate_down", "Navigate Down", show=True),
        Binding("pageup", "scroll_output_up", "Page Up", show=False),
        Binding("pagedown", "scroll_output_down", "Page Down", show=False),
    ]

    _MARKDOWN_SETTINGS = {
        "ai": ("agent_markdown_enabled", "AI agent output"),
        "shell": ("shell_markdown_enabled", "shell command output"),
        "python": ("python_markdown_enabled", "Python code output"),
    }

    def __init__(
        self,
        app: ArtificeApp,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        history_file: str | Path | None = None,
        max_history_size: int = 1000,
        *,
        agent: AnyAgent | None = None,
        execution_coordinator: ExecutionCoordinator | None = None,
        agent_coordinator: AgentCoordinator | None = None,
        navigation_controller: NavigationController | None = None,
        stream_manager: StreamManager | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

        self._config = app.config
        self._send_user_commands_to_agent: bool = (
            self._config.send_user_commands_to_agent
        )

        # Create history manager
        self._history = History(
            history_file=history_file, max_history_size=max_history_size
        )

        self.output = TerminalOutput(id="output")
        self.input = TerminalInput(history=self._history, id="input")
        self.agent_loading = LoadingIndicator()
        self.connection_status = Static("\u25c9", id="connection-status")
        self.agent_status = Static("", id="agent-status")

        # Context tracking
        self._context_blocks: list[BaseBlock] = []

        # Execution coordinator (injected or created)
        if execution_coordinator is not None:
            self._exec = execution_coordinator
        else:
            self._exec = ExecutionCoordinator(
                config=self._config,
                output=self.output,
                schedule_fn=self.call_later,
                context_tracker=self._mark_block_in_context,
            )

        # Status indicator manager
        self._status_manager = StatusIndicatorManager(
            self.agent_loading,
            self.connection_status,
            self.agent_status,
            self._config,
        )

        self._current_task: asyncio.Task | None = None

        # Stream manager (injected or created)
        if stream_manager is not None:
            self._stream = stream_manager
        else:
            self._stream = StreamManager(
                output=self.output,
                call_later=self.call_later,
                call_after_refresh=self.call_after_refresh,
                batch_update=self._batch_update_ctx,
                streaming_fps=self._config.streaming_fps,
            )

        def on_connect(_):
            self.connection_status.add_class("connected")

        self._system_prompt_path: Path | None = None
        prompt = load_prompt("system")
        if prompt is not None:
            (self._system_prompt_path, content) = prompt
            self._config.system_prompt = content

        # Create agent (injected or created)
        self._agent: AnyAgent | None = None
        if agent is not None:
            self._agent = agent
        else:
            self._agent = create_agent(self._config, on_connect=on_connect)
        self._status_manager.set_inactive()

        # Agent coordinator (injected or created)
        if agent_coordinator is not None:
            self._agent_coord = agent_coordinator
        else:
            self._agent_coord = AgentCoordinator(
                agent=self._agent,
                stream_manager=self._stream,
                output=self.output,
                terminal=self,
                status_manager=self._status_manager,
            )

        # Navigation controller (injected or created)
        if navigation_controller is not None:
            self._nav = navigation_controller
        else:
            self._nav = NavigationController(
                input_widget=self.input,
                output_widget=self.output,
                terminal=self,
            )

    def _batch_update_ctx(self):
        """Return the app's batch_update context manager."""
        return self.app.batch_update()

    def _set_send_user_commands_to_agent(self, value: bool) -> None:
        """Set auto-send to agent mode."""
        self._send_user_commands_to_agent = value
        if value:
            self.input.add_class("in-context")
        else:
            self.input.remove_class("in-context")

    def _is_send_user_commands_to_agent(self) -> bool:
        """Check if auto-send to agent mode is enabled."""
        return self._send_user_commands_to_agent

    def _get_config_attr(self, name: str) -> Any:
        """Get a config attribute by name."""
        return getattr(self._config, name, None)

    def _focus_input(self) -> None:
        """Focus the input text area."""
        self.input.query_one("#code-input", InputTextArea).focus()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.output
            yield self.input
            with Horizontal(id="status-line"):
                yield self.agent_loading
                yield self.connection_status
                yield self.agent_status

    def _append_system_block(self, path: str | Path, content: str) -> None:
        """Append a SystemBlock with formatted path and content info.

        Path formatting:
        - If under ~/.artifice/prompts: show as ~/.artifice/prompts/...
        - Otherwise if under home: show relative to current directory
        - Otherwise: show as-is
        """
        path_obj = Path(path).expanduser().resolve()
        home = Path.home()
        artifice_prompts = home / ".artifice" / "prompts"

        try:
            if path_obj.is_relative_to(artifice_prompts):
                display_path = (
                    f"~/.artifice/prompts/{path_obj.relative_to(artifice_prompts)}"
                )
            elif path_obj.is_relative_to(home):
                display_path = os.path.relpath(path_obj, os.getcwd())
            else:
                display_path = os.path.relpath(path_obj, os.getcwd())
        except ValueError:
            display_path = str(path_obj)

        block = SystemBlock(
            output=f"{display_path} (_{len(content)} characters_)",
            render_markdown=True,
        )
        block.flush()
        if self._send_user_commands_to_agent:
            self._mark_block_in_context(block)
        self.output.append_block(block)

    def on_mount(self) -> None:
        """Initialize the terminal on mount."""
        self._status_manager.update_agent_info()
        if (
            self._system_prompt_path is not None
            and self._config.system_prompt is not None
        ):
            self._append_system_block(
                self._system_prompt_path, self._config.system_prompt
            )

    async def _run_cancellable(self, coro, *, finally_callback=None):
        """Run a coroutine with standard cancel handling."""
        try:
            await coro
        except asyncio.CancelledError:
            block = CodeOutputBlock(render_markdown=False)
            self.output.append_block(block)
            block.append_error("\n[Cancelled]\n")
            block.flush()
            raise
        finally:
            self._current_task = None
            if finally_callback:
                finally_callback()

    async def on_terminal_input_submitted(self, event: TerminalInput.Submitted) -> None:
        """Handle code submission from input."""
        code = event.code
        self.input.clear()

        # Immediately display the submitted input for responsiveness
        if event.is_agent_prompt:
            agent_input_block = AgentInputBlock(code)
            self.output.append_block(agent_input_block)
            self._mark_block_in_context(agent_input_block)

        async def do_execute():
            if event.is_agent_prompt:
                await self._handle_agent_prompt(code)
            elif event.is_shell_command:
                result = await self._exec.execute(
                    code, language="bash", in_context=self._send_user_commands_to_agent
                )
                if self._send_user_commands_to_agent:
                    await self._send_execution_result_to_agent(code, "bash", result)
            else:
                result = await self._exec.execute(
                    code,
                    language="python",
                    in_context=self._send_user_commands_to_agent,
                )
                if self._send_user_commands_to_agent:
                    await self._send_execution_result_to_agent(code, "python", result)

        self._current_task = asyncio.create_task(self._run_cancellable(do_execute()))

    def _mark_block_in_context(self, block: BaseBlock) -> None:
        """Mark a block as being in the agent's context."""
        if block not in self._context_blocks:
            self._context_blocks.append(block)
            block.add_class("in-context")

    def _clear_all_context_highlights(self) -> None:
        """Remove in-context highlighting from all blocks."""
        for block in self._context_blocks:
            block.remove_class("in-context")
        self._context_blocks.clear()

    async def _handle_agent_prompt(self, prompt: str) -> None:
        """Handle AI agent prompt with code block detection."""
        await self._agent_coord.handle_agent_prompt(prompt)

    async def _send_execution_result_to_agent(
        self, code: str, language: str, result: ExecutionResult
    ) -> None:
        """Send execution results back to the agent and get its response."""
        await self._agent_coord.send_execution_result_to_agent(
            code, language, result.output, result.error
        )

    async def on_terminal_output_block_activated(
        self, event: TerminalOutput.BlockActivated
    ) -> None:
        """Handle block activation: copy code to input with correct mode."""
        self.input.code = event.code
        try:
            self.input.mode = InputMode.from_name(event.mode)
            self.input._update_prompt()
        except ValueError:
            pass
        self.input.query_one("#code-input", InputTextArea).focus()

    async def on_terminal_output_block_execute_requested(
        self, event: TerminalOutput.BlockExecuteRequested
    ) -> None:
        """Handle block execution: execute code from a block."""
        block = event.block

        # Check if this is a tool call with a direct executor (read_file, etc.)
        if isinstance(block, ToolCallBlock) and block.tool_args:
            from artifice.agent.tools.base import TOOLS

            tool_def = TOOLS.get(block.tool_name)
            if tool_def and tool_def.executor:
                self._execute_tool_with_executor(block)
                return

        code = block.get_code()
        mode = block.get_mode()
        language = "bash" if mode == "shell" else "python"

        block.show_loading()
        self.input.query_one("#code-input", InputTextArea).focus()

        tool_call_id = block.tool_call_id if isinstance(block, ToolCallBlock) else None
        state = {
            "result": ExecutionResult(code=code, status=ExecutionStatus.ERROR),
            "sent_to_agent": False,
        }

        async def do_execute():
            state["result"] = await self._exec.execute(
                code,
                language=language,
                code_input_block=block,
                in_context=self._send_user_commands_to_agent,
            )
            block.update_status(state["result"])
            if self._send_user_commands_to_agent and self._agent is not None:
                state["sent_to_agent"] = True
                output = state["result"].output + state["result"].error
                if tool_call_id is not None:
                    # Structured tool result — agent knows which call this answers
                    self._agent_coord.add_tool_result(tool_call_id, output)
                    if not self._agent_coord.has_pending_tool_calls:
                        await self._agent_coord.continue_after_tool_call()
                else:
                    await self._send_execution_result_to_agent(
                        code, language, state["result"]
                    )

        def cleanup():
            if state["result"]:
                block.update_status(state["result"])
            block.finish_streaming()
            if not state["sent_to_agent"]:
                self.input.focus_input()

        self._current_task = asyncio.create_task(
            self._run_cancellable(do_execute(), finally_callback=cleanup)
        )

    def _execute_tool_with_executor(self, block: ToolCallBlock) -> None:
        """Execute a tool call that has a direct executor (not code execution)."""
        block.show_loading()
        self.input.query_one("#code-input", InputTextArea).focus()

        state: dict = {"sent_to_agent": False}

        async def do_execute():
            from artifice.agent.tools.base import (
                ToolCall as _ToolCall,
                execute_tool_call,
            )

            tc = _ToolCall(
                id=block.tool_call_id, name=block._tool_name, args=block.tool_args
            )
            result_text = await execute_tool_call(tc)
            if result_text is None:
                result_text = "(no executor for this tool)"

            # Show result as a success
            result = ExecutionResult(
                code=block.get_code(),
                status=ExecutionStatus.SUCCESS,
                output=result_text,
            )
            block.update_status(result)

            # Display result in an output block
            output_block = CodeOutputBlock(
                result_text,
                in_context=self._send_user_commands_to_agent,
            )
            if not self._config.show_tool_output:
                output_block.add_class("hide-tool-output")
            self.output.append_block(output_block)
            self._mark_block_in_context(output_block)

            # Send result back to agent
            if self._send_user_commands_to_agent and self._agent is not None:
                state["sent_to_agent"] = True
                self._agent_coord.add_tool_result(block.tool_call_id, result_text)
                if not self._agent_coord.has_pending_tool_calls:
                    await self._agent_coord.continue_after_tool_call()

        def cleanup():
            block.finish_streaming()
            if not state["sent_to_agent"]:
                self.input.focus_input()

        self._current_task = asyncio.create_task(
            self._run_cancellable(do_execute(), finally_callback=cleanup)
        )

    def action_clear(self) -> None:
        """Clear the output."""
        self._context_blocks.clear()
        self.output.clear()

    def action_focus_input(self) -> None:
        """Focus the input text area."""
        self.input.focus_input()

    def action_cancel_execution(self) -> None:
        """Cancel the currently executing code or AI prompt."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._current_task = None

    async def action_toggle_mode_markdown(self) -> None:
        """Toggle markdown rendering for the current input mode."""
        mode_name = self.input.mode.value.name
        attr, label = self._MARKDOWN_SETTINGS[mode_name]
        current = getattr(self._exec, attr)
        setattr(self._exec, attr, not current)
        enabled_str = "enabled" if not current else "disabled"
        self.app.notify(f"Markdown {enabled_str} for {label}")

    def reset(self) -> None:
        """Reset the REPL state."""
        self._exec.reset()
        self.output.clear()
        self._history.clear()

    def action_navigate_up(self) -> None:
        """Navigate up: from input to output, or up through output blocks."""
        self._nav.navigate_up()

    def action_navigate_down(self) -> None:
        """Navigate down: through output blocks, or from output to input."""
        self._nav.navigate_down()

    def action_toggle_send_user_commands_to_agent(self) -> None:
        """Toggle auto-send mode."""
        self._send_user_commands_to_agent = not self._send_user_commands_to_agent

        if self._send_user_commands_to_agent:
            self.input.add_class("in-context")
            for block in self.output.children:
                if isinstance(block, BaseBlock) and block not in self._context_blocks:
                    self._mark_block_in_context(block)
        else:
            self.input.remove_class("in-context")
            self._clear_all_context_highlights()

    def on_terminal_input_prompt_selected(
        self, event: TerminalInput.PromptSelected
    ) -> None:
        """Handle prompt template selection: append to agent's system prompt."""
        if self._agent is not None:
            self._agent.messages.append({"role": "user", "content": event.content})
            self._append_system_block(event.path, event.content)

    def action_scroll_output_up(self) -> None:
        """Scroll the output window up by one page."""
        self._nav.scroll_output_up()

    def action_scroll_output_down(self) -> None:
        """Scroll the output window down by one page."""
        self._nav.scroll_output_down()

    def action_clear_agent_context(self) -> None:
        """Clear the agent's conversation context."""
        if self._agent is not None:
            self._agent.clear()
        self._clear_all_context_highlights()
