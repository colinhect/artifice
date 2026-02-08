"""Main Artifice terminal widget."""

from __future__ import annotations

import asyncio
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
from .terminal_output import TerminalOutput, AgentInputBlock, AgentOutputBlock, CodeInputBlock, CodeOutputBlock, WidgetOutputBlock, PinnedOutput

if TYPE_CHECKING:
    from .app import ArtificeApp


def parse_response_segments(text: str) -> list[tuple]:
    """Parse response text into text and code block segments.

    Returns list of tuples:
    - ('text', content) for text segments
    - ('code', language, code) for code blocks (python or bash)
    """
    pattern = r'```(python|bash)\n(.*?)```'
    segments = []
    last_end = 0
    for match in re.finditer(pattern, text, re.DOTALL):
        before = text[last_end:match.start()].strip()
        if before:
            segments.append(('text', before))
        segments.append(('code', match.group(1), match.group(2)))
        last_end = match.end()
    after = text[last_end:].strip()
    if after:
        segments.append(('text', after))
    return segments


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
    }

    ArtificeTerminal .highlighted {
        background: $surface-lighten-2;
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
        Binding("ctrl+t", "use_last_agent_code", "Use Agent Code", show=True),
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
            "response with a fenced code block tagged `python` or `bash`. The user will "
            "review and may execute it. Be brief."
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
        self._agent_requested_execution: bool = False
        self._last_agent_code_block: tuple[str, str] | None = None  # (language, code)

        self.output = TerminalOutput(id="output")
        self.input = TerminalInput(history=self._history, id="input")
        self.pinned_output = PinnedOutput(id="pinned")
        self._current_task: asyncio.Task | None = None

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

                    if self._agent_requested_execution:
                        self._agent_requested_execution = False
                        await self._send_execution_result_to_agent(code, result)
                else:
                    result = await self._handle_python_execution(code)

                    if self._agent_requested_execution:
                        self._agent_requested_execution = False
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

    async def _stream_agent_response(self, prompt: str) -> None:
        """Stream an agent response with real-time code block detection.

        Creates AgentOutputBlock for text and CodeInputBlock for code blocks
        as they are detected during streaming.
        """
        initial_block = AgentOutputBlock()
        self.output.append_block(initial_block)

        state = {
            'text_block': initial_block,
            'text_has_content': False,
            'in_code': False,
            'code_block': None,
            'code_language': None,
            'code_accum': '',
            'buf': '',
        }

        def flush_text(text):
            if text:
                state['text_has_content'] = True
                state['text_block'].append(text)
                self.output.call_after_refresh(self.output.auto_scroll)

        def start_code(language):
            if state['text_has_content']:
                state['text_block'].mark_success()
            else:
                state['text_block'].remove()
                self.output._blocks.remove(state['text_block'])

            code_block = CodeInputBlock('', language=language)
            self.output.append_block(code_block)
            code_block._loading_indicator.styles.display = 'none'
            prompt_char = '>' if language == 'python' else '$'
            code_block._status_indicator.update(prompt_char)
            code_block._status_indicator.add_class('status-pending')

            state['code_block'] = code_block
            state['code_language'] = language
            state['code_accum'] = ''
            state['text_block'] = None
            state['text_has_content'] = False
            state['in_code'] = True

        def append_code(text):
            state['code_accum'] += text
            if state['code_block']:
                state['code_block'].update_code(state['code_accum'].rstrip('\n'))
                self.output.call_after_refresh(self.output.auto_scroll)

        def end_code():
            code_text = state['code_accum'].rstrip('\n')
            if state['code_block']:
                state['code_block'].update_code(code_text)
            if state['code_language']:
                self._last_agent_code_block = (state['code_language'], code_text)

            text_block = AgentOutputBlock()
            self.output.append_block(text_block)
            state['text_block'] = text_block
            state['text_has_content'] = False
            state['in_code'] = False
            state['code_block'] = None

        def on_chunk(chunk):
            state['buf'] += chunk

            while '\n' in state['buf']:
                nl = state['buf'].index('\n')
                line = state['buf'][:nl]
                state['buf'] = state['buf'][nl + 1:]

                if not state['in_code']:
                    stripped = line.strip()
                    if stripped in ('```python', '```bash'):
                        start_code(stripped[3:])
                    else:
                        flush_text(line + '\n')
                else:
                    stripped = line.strip()
                    if stripped == '```':
                        end_code()
                    else:
                        append_code(line + '\n')

        response = await self._agent.send_prompt(prompt, on_chunk=on_chunk)

        # Flush remaining buffer
        if state['buf']:
            if state['in_code']:
                # Check if the remaining buffer is just the closing ```
                if state['buf'].strip() == '```':
                    end_code()
                    state['buf'] = ''
                else:
                    append_code(state['buf'])
            else:
                flush_text(state['buf'])

        # Finalize last block
        if state['in_code']:
            code_text = state['code_accum'].rstrip('\n')
            if state['code_block']:
                state['code_block'].update_code(code_text)
            if state['code_language'] and code_text:
                self._last_agent_code_block = (state['code_language'], code_text)
        elif state['text_block']:
            if response.error:
                state['text_block'].mark_failed()
            elif state['text_has_content']:
                state['text_block'].mark_success()
            else:
                state['text_block'].remove()
                self.output._blocks.remove(state['text_block'])

    async def _handle_agent_prompt(self, prompt: str) -> None:
        """Handle AI agent prompt with code block detection."""
        agent_input_block = AgentInputBlock(prompt)
        self.output.append_block(agent_input_block)

        if self._agent is None:
            agent_output_block = AgentOutputBlock("No AI agent configured.")
            self.output.append_block(agent_output_block)
            agent_output_block.mark_failed()
            return

        await self._stream_agent_response(prompt)

    async def _send_execution_result_to_agent(self, code: str, result: ExecutionResult) -> None:
        """Send execution results back to the agent with streaming code block detection."""
        prompt = "Executed:\n```\n" + code + "```\n\nOutput:\n```\n" + result.output + result.error + "\n```\n"
        await self._stream_agent_response(prompt)

    def action_use_last_agent_code(self) -> None:
        """Load the last code block suggested by the AI agent into the input."""
        if self._last_agent_code_block is None:
            return
        language, code = self._last_agent_code_block
        self._agent_requested_execution = True
        self.input.code = code
        self.input.mode = "python" if language == "python" else "shell"
        self.input._update_prompt()
        self.input.query_one("#code-input", InputTextArea).focus()

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
    
