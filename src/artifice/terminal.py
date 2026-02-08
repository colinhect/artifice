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
from textual.widget import Widget

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


class StreamingFenceDetector:
    """Detects code fences in streaming text and splits into blocks.

    Processes chunks character-by-character using a 3-state machine:
    PROSE -> LANG_LINE (on ```) -> CODE (on newline) -> PROSE (on closing ```)

    During streaming, all text is displayed via a single AgentOutputBlock.
    When streaming ends, the display block is replaced with split
    AgentOutputBlock (prose) and CodeInputBlock (code) blocks.
    """

    def __init__(self, output: TerminalOutput, auto_scroll) -> None:
        self._output = output
        self._auto_scroll = auto_scroll
        self._state = _FenceState.PROSE
        self._backtick_count = 0
        self._lang_buffer = ""
        self._code_buffer = ""
        self._prose_buffer = ""
        self._current_lang = "python"
        self._segments: list[tuple] = []
        self._display_block = None
        self.all_blocks: list[BaseBlock] = []
        self.first_agent_block: AgentOutputBlock | None = None
        self._make_prose_block = lambda activity: AgentOutputBlock(activity=activity)
        self._make_code_block = lambda code, lang: CodeInputBlock(code, language=lang, show_loading=False)

    def start(self) -> None:
        """Create the display block for real-time streaming feedback."""
        self._display_block = self._make_prose_block(activity=True)
        self._output.append_block(self._display_block)

    def feed(self, text: str) -> None:
        """Process a chunk of streaming text."""
        for ch in text:
            self._feed_char(ch)
        # Update display block for real-time feedback
        self._display_block.append(text)
        self._output.call_after_refresh(self._auto_scroll)

    def _feed_char(self, ch: str) -> None:
        if self._state == _FenceState.PROSE:
            self._feed_prose(ch)
        elif self._state == _FenceState.LANG_LINE:
            self._feed_lang_line(ch)
        elif self._state == _FenceState.CODE:
            self._feed_code(ch)

    def _feed_prose(self, ch: str) -> None:
        if ch == '`':
            self._backtick_count += 1
            if self._backtick_count == 3:
                self._backtick_count = 0
                self._lang_buffer = ""
                self._state = _FenceState.LANG_LINE
        else:
            if self._backtick_count > 0:
                self._prose_buffer += '`' * self._backtick_count
                self._backtick_count = 0
            self._prose_buffer += ch

    def _feed_lang_line(self, ch: str) -> None:
        if ch == '\n':
            lang = self._lang_buffer.strip()
            if not lang:
                lang = "python"
            # Normalize language aliases
            if lang in ("py",):
                lang = "python"
            elif lang in ("shell", "sh", "zsh"):
                lang = "bash"
            # Flush prose segment
            if self._prose_buffer:
                self._segments.append(('prose', self._prose_buffer))
                self._prose_buffer = ""
            self._code_buffer = ""
            self._current_lang = lang
            self._state = _FenceState.CODE
        else:
            self._lang_buffer += ch

    def _feed_code(self, ch: str) -> None:
        if ch == '`':
            self._backtick_count += 1
            if self._backtick_count == 3:
                self._backtick_count = 0
                self._segments.append(('code', self._current_lang, self._code_buffer))
                self._code_buffer = ""
                self._state = _FenceState.PROSE
        else:
            if self._backtick_count > 0:
                self._code_buffer += '`' * self._backtick_count
                self._backtick_count = 0
            self._code_buffer += ch

    def finish(self) -> None:
        """Flush state, remove display block, and create split blocks."""
        # Flush remaining state
        if self._state == _FenceState.LANG_LINE:
            self._prose_buffer += '```' + self._lang_buffer
        elif self._state == _FenceState.CODE:
            if self._backtick_count > 0:
                self._code_buffer += '`' * self._backtick_count
                self._backtick_count = 0
            self._segments.append(('code', self._current_lang, self._code_buffer))
        elif self._state == _FenceState.PROSE:
            if self._backtick_count > 0:
                self._prose_buffer += '`' * self._backtick_count
                self._backtick_count = 0

        # Flush any remaining prose
        if self._prose_buffer:
            self._segments.append(('prose', self._prose_buffer))

        # Remove display block
        if self._display_block in self._output._blocks:
            self._output._blocks.remove(self._display_block)
        self._display_block.remove()

        # Create blocks from accumulated segments
        for seg in self._segments:
            if seg[0] == 'prose':
                block = self._make_prose_block(activity=False)
                self._output.append_block(block)
                block.append(seg[1])
                self.all_blocks.append(block)
                if self.first_agent_block is None:
                    self.first_agent_block = block
            elif seg[0] == 'code':
                block = self._make_code_block(seg[2], seg[1])
                self._output.append_block(block)
                self.all_blocks.append(block)


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
        max-height: 95vh;
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
            "You are a coding assistant with Python and shell access. To run code, end your "
            "response with a fenced code demarcated by:\n"
            "```python\n"
            "for python commands, or:\n"
            "```shell\n"
            "for shell commands.\n"
            "Ending with ```\n"
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
                    'response': 'I can help with that calculation!\n\n```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```',
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

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.output
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
        detector = StreamingFenceDetector(self.output, self.output.auto_scroll)
        detector.start()

        def on_chunk(text):
            detector.feed(text)

        response = await self._agent.send_prompt(prompt, on_chunk=on_chunk)
        detector.finish()

        # Mark all blocks as in context
        for block in detector.all_blocks:
            self._mark_block_in_context(block)

        # Mark the first agent output block with success/failure
        if detector.first_agent_block:
            if response.error:
                detector.first_agent_block.mark_failed()
            else:
                detector.first_agent_block.mark_success()

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

