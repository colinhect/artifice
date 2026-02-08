"""Main Artifice terminal widget."""

from __future__ import annotations

import asyncio
import enum
import re
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from .config import ArtificeConfig
from .execution import ExecutionResult, CodeExecutor, ShellExecutor
from .history import History
from .terminal_input import TerminalInput, InputTextArea
from .terminal_output import TerminalOutput, AgentInputBlock, AgentOutputBlock, CodeInputBlock, CodeOutputBlock, WidgetOutputBlock, PinnedOutput, BaseBlock

if TYPE_CHECKING:
    from .app import ArtificeApp


def parse_response_segments(text: str) -> list[tuple]:
    """Parse response text into text and code block segments.

    Returns list of tuples:
    - ('text', content) for text segments
    - ('code', language, code) for code blocks (python or bash)
    """
    pattern = r'```(py|python|bash|shell)?\n(.*?)```'
    segments = []
    last_end = 0
    for match in re.finditer(pattern, text, re.DOTALL):
        before = text[last_end:match.start()].strip()
        if before:
            segments.append(('text', before))
        # Default to 'python' if no language specified
        lang = match.group(1) or 'python'
        segments.append(('code', lang, match.group(2)))
        last_end = match.end()
    after = text[last_end:].strip()
    if after:
        segments.append(('text', after))
    return segments


class _FenceState(enum.Enum):
    PROSE = "prose"
    LANG_LINE = "lang_line"
    CODE = "code"


class StreamChunk(Message):
    """Message posted when a chunk of streamed text arrives."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class StreamComplete(Message):
    """Message posted when streaming is complete."""
    pass


class StreamingFenceDetector:
    """Detects code fences in streaming text and splits into blocks in real-time.

    Processes chunks character-by-character using a 3-state machine:
    PROSE -> LANG_LINE (on ```) -> CODE (on newline) -> PROSE (on closing ```)

    Creates blocks as fences are detected, accumulating text to update once per chunk.
    """

    def __init__(self, output: TerminalOutput, auto_scroll) -> None:
        self._output = output
        self._auto_scroll = auto_scroll
        self._state = _FenceState.PROSE
        self._backtick_count = 0
        self._lang_buffer = ""
        self._pending_buffer = ""  # Text to add to current block
        self._chunk_buffer = ""  # Accumulates text for current chunk to display
        self._current_lang = "python"
        self._current_block: BaseBlock | None = None  # The block we're currently appending to
        self.all_blocks: list[BaseBlock] = []
        self.first_agent_block: AgentOutputBlock | None = None
        # Factory methods for block creation (can be overridden for testing)
        self._make_prose_block = lambda activity: AgentOutputBlock(activity=activity)
        self._make_code_block = lambda code, lang: CodeInputBlock(code, language=lang, show_loading=False, use_markdown=True)

    def start(self) -> None:
        """Create the initial AgentOutputBlock for streaming prose."""
        self._current_block = self._make_prose_block(activity=True)
        self._output.append_block(self._current_block)
        self.all_blocks.append(self._current_block)
        self.first_agent_block = self._current_block

    def feed(self, text: str) -> None:
        """Process a chunk of streaming text, creating blocks as needed."""
        self._chunk_buffer = ""  # Reset for this chunk
        for ch in text:
            self._feed_char(ch)
        # Flush any pending text to the chunk buffer for display
        self._flush_pending_to_chunk()
        # Update current block with accumulated chunk text
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
        self._output.call_after_refresh(self._auto_scroll)

    def _feed_char(self, ch: str) -> None:
        if self._state == _FenceState.PROSE:
            self._feed_prose(ch)
        elif self._state == _FenceState.LANG_LINE:
            self._feed_lang_line(ch)
        elif self._state == _FenceState.CODE:
            self._feed_code(ch)

    def _feed_prose(self, ch: str) -> None:
        """Process prose text, looking for opening fence."""
        if ch == '`':
            self._backtick_count += 1
            if self._backtick_count == 3:
                # Found opening fence - flush pending prose and transition
                # Flush pending without the backticks
                self._flush_pending_to_chunk()
                self._backtick_count = 0
                self._lang_buffer = ""
                self._state = _FenceState.LANG_LINE
        else:
            # Not a fence marker
            if self._backtick_count > 0:
                # We had some backticks that weren't a fence
                self._pending_buffer += '`' * self._backtick_count
                self._backtick_count = 0
            self._pending_buffer += ch

    def _feed_lang_line(self, ch: str) -> None:
        """Process language line after opening fence."""
        if ch == '\n':
            # Language line complete - start code block
            lang = self._lang_buffer.strip()
            if not lang:
                lang = "python"
            # Normalize language aliases
            if lang in ("py",):
                lang = "python"
            elif lang in ("shell", "sh", "zsh"):
                lang = "bash"
            self._current_lang = lang

            # Update current block with accumulated chunk
            if self._chunk_buffer and self._current_block:
                self._update_current_block_with_chunk()
                self._chunk_buffer = ""

            # End current prose block (mark as no longer active)
            if hasattr(self._current_block, 'mark_success'):
                self._current_block.mark_success()

            # Create new code block
            self._current_block = self._make_code_block("", lang)
            self._output.append_block(self._current_block)
            self.all_blocks.append(self._current_block)

            self._pending_buffer = ""
            self._state = _FenceState.CODE
        else:
            self._lang_buffer += ch

    def _feed_code(self, ch: str) -> None:
        """Process code text, looking for closing fence."""
        if ch == '`':
            self._backtick_count += 1
            if self._backtick_count == 3:
                # Found closing fence - flush pending code and transition
                self._flush_pending_to_chunk()

                # Update code block with accumulated chunk
                if self._chunk_buffer and self._current_block:
                    self._update_current_block_with_chunk()
                    self._chunk_buffer = ""

                self._backtick_count = 0

                # Start new prose block
                self._current_block = self._make_prose_block(activity=True)
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

                self._state = _FenceState.PROSE
        else:
            # Not a fence marker
            if self._backtick_count > 0:
                # We had some backticks that weren't a fence
                self._pending_buffer += '`' * self._backtick_count
                self._backtick_count = 0
            self._pending_buffer += ch

    def _flush_pending_to_chunk(self) -> None:
        """Move pending buffer to chunk buffer."""
        self._chunk_buffer += self._pending_buffer
        self._pending_buffer = ""

    def _update_current_block_with_chunk(self) -> None:
        """Update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            if hasattr(self._current_block, 'update_code'):
                # Code block - update with accumulated code
                existing = self._current_block.get_code()
                self._current_block.update_code(existing + self._chunk_buffer)
            elif hasattr(self._current_block, 'append'):
                # Prose block - append text
                self._current_block.append(self._chunk_buffer)

    def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        # Handle incomplete fences
        if self._state == _FenceState.LANG_LINE:
            # Incomplete opening fence - treat as prose
            self._pending_buffer = '```' + self._lang_buffer
            self._state = _FenceState.PROSE
        elif self._state == _FenceState.CODE:
            # Incomplete closing fence - flush what we have
            if self._backtick_count > 0:
                self._pending_buffer += '`' * self._backtick_count
                self._backtick_count = 0
        elif self._state == _FenceState.PROSE:
            if self._backtick_count > 0:
                self._pending_buffer += '`' * self._backtick_count
                self._backtick_count = 0

        # Flush any remaining text
        self._flush_pending_to_chunk()
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()

        # Mark the last block as complete
        if self._current_block and hasattr(self._current_block, 'mark_success'):
            self._current_block.mark_success()


class ArtificeTerminal(Widget):
    """Primary widget for interacting with Artifice."""

    DEFAULT_CSS = """
    ArtificeTerminal {
        height: auto;
    }

    ArtificeTerminal Vertical {
        height: auto;
    }

    ArtificeTerminal TerminalOutput {
        height: auto;
        max-height: 90vh;
        overflow-y: auto;
    }

    ArtificeTerminal TerminalInput {
        height: auto;
        padding-left: 1;
    }

    ArtificeTerminal TerminalInput.in-context {
        padding-left: 0;
    }

    ArtificeTerminal .highlighted {
        background: $surface-lighten-2;
    }

    ArtificeTerminal .in-context {
        border-left: solid $primary;
    }

    ArtificeTerminal PinnedOutput {
        height: auto;
        max-height: 30vh;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear", "Clear Output", show=True),
        Binding("ctrl+o", "toggle_mode_markdown", "Toggle Markdown Output", show=True),
        Binding("ctrl+c", "cancel_execution", "Cancel", show=True),
        Binding("ctrl+g", "toggle_auto_send_to_agent", "Toggle Auto Send to Agent", show=True),
        Binding("ctrl+n", "clear_agent_context", "Clear Agent Context", show=True),
        Binding("alt+up", "navigate_up", "Navigate Up", show=True),
        Binding("alt+down", "navigate_down", "Navigate Down", show=True),
    ]

    def __init__(
        self,
        app: ArtificeApp,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        history_file: str | Path | None = None,
        max_history_size: int = 1000,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._executor = CodeExecutor()
        
        # Load configuration and create shell executor with init script
        config = ArtificeConfig.load()
        self._shell_executor = ShellExecutor(init_script=config.shell_init_script)

        # Create history manager
        self._history = History(history_file=history_file, max_history_size=max_history_size)

        # Per-mode markdown rendering settings
        self._python_markdown_enabled = False  # Default: no markdown for Python output
        self._agent_markdown_enabled = True    # Default: markdown for agent responses
        self._shell_markdown_enabled = False   # Default: no markdown for shell output

        # System prompt to guide the agent's behavior
        system_prompt = (
            "You are collaborating with the user to interface with his Linux system with access to a bash shell and a Python session. "
            "Any Python code or shell commands in your responses are interpreted as requests by you to execute that code. Make one request at a time. "
            "Do not over explain unless asked to. Always use ```python or ```shell to mark code or shell command."

            #"You are a coding assistant with Python and shell access. To run code, end your "
            #"response with a fenced code demarcated by:\n"
            #"```python\n"
            #"for python commands, or:\n"
            #"```shell\n"
            #"for shell commands.\n"
            ##"Ending with ```\n\n"
            #"Put explainations before the code or command. "
            #"Only give one code or command per response and always at the end."
        )
        
        def on_agent_connect(agent_name):
            pass
            #app.notify(f"Connected to {agent_name}")

        # Create agent
        self._agent = None
        if app.agent_type.lower() == "claude":
            from .agent import ClaudeAgent
            self._agent = ClaudeAgent(
                system_prompt=system_prompt,
                on_connect=on_agent_connect,
            )
        elif app.agent_type.lower() == "simulated":
            from artifice.agent.simulated import SimulatedAgent
            self._agent = SimulatedAgent(
                response_delay=0.01,
                on_connect=on_agent_connect,
            )

            # Configure scenarios with pattern matching
            self._agent.configure_scenarios([
                {
                    'pattern': r'hello|hi|hey',
                    'response': 'Hello! I\'m a **simulated** agent. How can I help you today?'
                },
                {
                    'pattern': r'calculate|math|sum|add',
                    'response': 'I can help with that calculation!\n\n```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nI can help with that calculation!\n\n```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nThere it is, leave it or not',
                },
                {
                    'pattern': r'goodbye|bye|exit',
                    'response': 'Goodbye! Thanks for chatting with me.'
                },
            ])

            self._agent.set_default_response("I'm not sure how to respond to that. Try asking about math or saying hello!")
        elif app.agent_type.lower() == "ollama":
            from .agent import OllamaAgent
            self._agent = OllamaAgent(
                system_prompt=system_prompt,
                on_connect=on_agent_connect,
            )
        elif app.agent_type:
            raise Exception(f"Unsupported agent {app.agent_type}")
        self._auto_send_to_agent: bool = False  # Persistent mode for auto-sending execution results

        self.output = TerminalOutput(id="output")
        self.input = TerminalInput(history=self._history, id="input")
        self.pinned_output = PinnedOutput(id="pinned")
        self._current_task: asyncio.Task | None = None
        self._context_blocks: list[BaseBlock] = []  # Blocks in agent context
        self._current_detector: StreamingFenceDetector | None = None  # Active streaming detector

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.output
            yield Static(id="flash")
            yield self.input
            yield self.pinned_output

    async def on_terminal_input_submitted(self, event: TerminalInput.Submitted) -> None:
        """Handle code submission from input."""
        code = event.code

        # Clear input
        self.input.clear()

        # Create a task to track execution
        async def execute():
            try:
                if event.is_agent_prompt:
                    await self._handle_agent_prompt(code)
                elif event.is_shell_command:
                    result = await self._handle_shell_execution(code)

                    if self._auto_send_to_agent:
                        await self._send_execution_result_to_agent(code, result)
                else:
                    result = await self._handle_python_execution(code)

                    if self._auto_send_to_agent:
                        await self._send_execution_result_to_agent(code, result)
            except asyncio.CancelledError:
                # Task was cancelled - show message
                code_output_block = CodeOutputBlock(render_markdown=False)
                self.output.append_block(code_output_block)
                code_output_block.append_error("\n[Cancelled]\n")
                raise
            finally:
                self._current_task = None

        self._current_task = asyncio.create_task(execute())
    
    async def on_terminal_input_decline_requested(self, event: TerminalInput.DeclineRequested) -> None:
        """Handle decline request from input (escape key)."""
        # If no pending execution, just ignore the escape key
        pass

    async def _handle_python_execution(self, code: str) -> ExecutionResult:
        """Execute Python code."""
        code_input_block = CodeInputBlock(code, language="python")
        self.output.append_block(code_input_block)

        code_output_block = CodeOutputBlock(render_markdown=self._python_markdown_enabled)
        self.output.append_block(code_output_block)

        def on_output(text):
            code_output_block.append_output(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        def on_error(text):
            code_output_block.append_error(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        result = await self._executor.execute(
            code,
            on_output=on_output,
            on_error=on_error,
        )

        code_input_block.update_status(result)

        if isinstance(result.result_value, Widget):
            widget_block = WidgetOutputBlock(result.result_value)
            self.output.append_block(widget_block)

        return result

    async def _execute_block_python(self, code_input_block: CodeInputBlock, code: str) -> ExecutionResult:
        """Execute Python code from an existing block."""
        code_output_block = CodeOutputBlock(render_markdown=self._agent_markdown_enabled)
        self.output.append_block(code_output_block)

        def on_output(text):
            code_output_block.append_output(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        def on_error(text):
            code_output_block.append_error(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        result = await self._executor.execute(
            code,
            on_output=on_output,
            on_error=on_error,
        )

        code_input_block.update_status(result)

        if isinstance(result.result_value, Widget):
            widget_block = WidgetOutputBlock(result.result_value)
            self.output.append_block(widget_block)

        return result

    async def _handle_shell_execution(self, command: str) -> ExecutionResult:
        """Execute shell command."""
        command_input_block = CodeInputBlock(command, language="bash")
        self.output.append_block(command_input_block)

        code_output_block = CodeOutputBlock(render_markdown=self._shell_markdown_enabled)
        self.output.append_block(code_output_block)

        def on_output(text):
            code_output_block.append_output(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        def on_error(text):
            code_output_block.append_error(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        # Execute asynchronously with streaming callbacks
        result = await self._shell_executor.execute(
            command,
            on_output=on_output,
            on_error=on_error,
        )

        command_input_block.update_status(result)
        return result

    async def _execute_block_shell(self, code_input_block: CodeInputBlock, command: str) -> ExecutionResult:
        """Execute shell command from an existing block."""
        code_output_block = CodeOutputBlock(render_markdown=self._agent_markdown_enabled)
        self.output.append_block(code_output_block)

        def on_output(text):
            code_output_block.append_output(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        def on_error(text):
            code_output_block.append_error(text)
            self.output.call_after_refresh(self.output.auto_scroll)

        # Execute asynchronously with streaming callbacks
        result = await self._shell_executor.execute(
            command,
            on_output=on_output,
            on_error=on_error,
        )

        code_input_block.update_status(result)
        return result

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

    async def _stream_agent_response(self, prompt: str) -> tuple[StreamingFenceDetector, object]:
        """Stream an agent response, splitting into prose and code blocks.

        Returns the detector (with all_blocks, first_agent_block) and the AgentResponse.
        """
        # Create detector and store it so message handlers can access it
        self._current_detector = StreamingFenceDetector(self.output, self.output.auto_scroll)
        self._current_detector.start()

        # Post messages from streaming callback (runs in background thread)
        def on_chunk(text):
            self.post_message(StreamChunk(text))

        response = await self._agent.send_prompt(prompt, on_chunk=on_chunk)

        # Post completion message
        self.post_message(StreamComplete())

        # Wait a moment for messages to be processed
        await asyncio.sleep(0.01)

        with self.app.batch_update():
            # Mark all blocks as in context
            for block in self._current_detector.all_blocks:
                self._mark_block_in_context(block)

            # Mark the first agent output block with success/failure
            if self._current_detector.first_agent_block:
                if response.error:
                    self._current_detector.first_agent_block.mark_failed()
                else:
                    self._current_detector.first_agent_block.mark_success()

        detector = self._current_detector
        self._current_detector = None
        return detector, response

    async def _handle_agent_prompt(self, prompt: str) -> None:
        """Handle AI agent prompt with code block detection."""
        # Create a block showing the prompt
        agent_input_block = AgentInputBlock(prompt)
        self.output.append_block(agent_input_block)

        # Mark the prompt as in context
        self._mark_block_in_context(agent_input_block)

        if self._agent is None:
            # No agent configured, show error
            agent_output_block = AgentOutputBlock("No AI agent configured.")
            self.output.append_block(agent_output_block)
            agent_output_block.mark_failed()
            return

        await self._stream_agent_response(prompt)

        # After sending a prompt to the agent, enable auto-send mode
        if not self._auto_send_to_agent:
            self._auto_send_to_agent = True
            self.input.add_class("in-context")

    async def _send_execution_result_to_agent(self, code: str, result: ExecutionResult) -> None:
        """Send execution results back to the agent and split the response."""
        # Find the most recent code input block and output block to mark as in-context
        if len(self.output._blocks) >= 2:
            # The last two blocks should be the code input and code output
            code_input_block = self.output._blocks[-2]
            code_output_block = self.output._blocks[-1]
            self._mark_block_in_context(code_input_block)
            self._mark_block_in_context(code_output_block)

        prompt = "Executed:\n```\n" + code + "```\n\nOutput:\n```\n" + result.output + result.error + "\n```\n"

        await self._stream_agent_response(prompt)

    async def on_terminal_output_pin_requested(self, event: TerminalOutput.PinRequested) -> None:
        """Handle pin request: move widget block from output to pinned area."""
        block = event.block
        await block.remove()
        await self.pinned_output.add_pinned_block(block)

    async def on_pinned_output_unpin_requested(self, event: PinnedOutput.UnpinRequested) -> None:
        """Handle unpin request: remove block from pinned area."""
        await self.pinned_output.remove_pinned_block(event.block)

    async def on_terminal_output_block_activated(self, event: TerminalOutput.BlockActivated) -> None:
        """Handle block activation: copy code to input with correct mode."""
        # Set the code in the input
        self.input.code = event.code
        # Set the correct mode
        self.input.mode = event.mode
        self.input._update_prompt()
        # Focus the input
        self.input.query_one("#code-input", InputTextArea).focus()

    async def on_terminal_output_block_execute_requested(self, event: TerminalOutput.BlockExecuteRequested) -> None:
        """Handle block execution: execute code from a block and send output to agent."""
        block = event.block
        code = block.get_code()
        mode = block.get_mode()

        # Show loading indicator on the block
        block.show_loading()

        # Create a task to track execution
        async def execute():
            try:
                if mode == "shell":
                    result = await self._execute_block_shell(block, code)
                else:  # python
                    result = await self._execute_block_python(block, code)

                # Always send to agent for block execution
                await self._send_execution_result_to_agent(code, result)
            except asyncio.CancelledError:
                # Task was cancelled
                code_output_block = CodeOutputBlock(render_markdown=False)
                self.output.append_block(code_output_block)
                code_output_block.append_error("\n[Cancelled]\n")
                raise
            finally:
                self._current_task = None

        self._current_task = asyncio.create_task(execute())

    def on_stream_chunk(self, event: StreamChunk) -> None:
        """Handle streaming chunk message - process text and update blocks in real-time."""
        if self._current_detector:
            self._current_detector.feed(event.text)

    def on_stream_complete(self, event: StreamComplete) -> None:
        """Handle stream completion message - finalize the detector state."""
        if self._current_detector:
            self._current_detector.finish()

    def action_clear(self) -> None:
        """Clear the output."""
        self.output.clear()

    def action_cancel_execution(self) -> None:
        """Cancel the currently executing code or AI prompt."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._current_task = None

    async def action_toggle_mode_markdown(self) -> None:
        """Toggle markdown rendering for the current input mode (affects future blocks only)."""
        # Determine current mode and toggle its setting
        if self.input.mode == "ai":
            self._agent_markdown_enabled = not self._agent_markdown_enabled
            #enabled_str = "enabled" if self._agent_markdown_enabled else "disabled"
            #self.app.notify(f"Markdown {enabled_str} for AI agent output")
        elif self.input.mode == "shell":
            self._shell_markdown_enabled = not self._shell_markdown_enabled
            #enabled_str = "enabled" if self._shell_markdown_enabled else "disabled"
            #self.app.notify(f"Markdown {enabled_str} for shell command output")
        else:
            self._python_markdown_enabled = not self._python_markdown_enabled
            #enabled_str = "enabled" if self._python_markdown_enabled else "disabled"
            #self.app.notify(f"Markdown {enabled_str} for Python code output")

    def reset(self) -> None:
        """Reset the REPL state."""
        self._executor.reset()
        self.output.clear()
        self._history.clear()

    def action_navigate_up(self) -> None:
        """Navigate up: from input to output (bottom block), or up through output blocks."""
        # Check if input has focus
        input_area = self.input.query_one("#code-input", InputTextArea)
        if input_area.has_focus:
            # Move focus to output and highlight the bottom block
            if self.output._blocks:
                self.output.focus()
        elif self.output.has_focus:
            # Navigate up through blocks
            self.output.highlight_previous()

    def action_navigate_down(self) -> None:
        """Navigate down: through output blocks, or from output to input."""
        # Check if output has focus
        if self.output.has_focus:
            # Try to move to next block
            moved = self.output.highlight_next()
            if not moved:
                # At the bottom, move to input
                self.input.query_one("#code-input", InputTextArea).focus()
        # If input has focus, do nothing (already at the bottom)

    def action_toggle_auto_send_to_agent(self) -> None:
        """Toggle auto-send mode - when enabled, all code execution results are sent to agent."""
        self._auto_send_to_agent = not self._auto_send_to_agent

        # Update visual indicator on input
        if self._auto_send_to_agent:
            self.input.add_class("in-context")
        else:
            self.input.remove_class("in-context")

    def action_clear_agent_context(self) -> None:
        """Clear the agent's conversation context and unhighlight all in-context blocks."""
        if self._agent and hasattr(self._agent, "clear_conversation"):
            self._agent.clear_conversation()

        # Remove highlighting from all context blocks
        self._clear_all_context_highlights()

