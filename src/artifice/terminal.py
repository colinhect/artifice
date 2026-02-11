"""Main Artifice terminal widget."""

from __future__ import annotations

import asyncio
import enum
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from .execution import ExecutionResult, ExecutionStatus, CodeExecutor, ShellExecutor
from .history import History
from .terminal_input import TerminalInput, InputTextArea
from .terminal_output import TerminalOutput, AgentInputBlock, AgentOutputBlock, CodeInputBlock, CodeOutputBlock, WidgetOutputBlock, PinnedOutput, BaseBlock

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .app import ArtificeApp


_LANG_ALIASES = {"py": "python", "shell": "bash", "sh": "bash", "zsh": "bash"}


class _FenceState(enum.Enum):
    PROSE = "prose"
    LANG_LINE = "lang_line"
    CODE = "code"


class StreamChunk(Message):
    """Message posted when a chunk of streamed text arrives."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text



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
        # String literal tracking for smart fence detection
        self._in_string: str | None = None  # None, "'", '"', "'''", or '"""'
        self._escape_next = False  # Track if next char is escaped
        self._quote_buffer = ""  # Buffer for detecting triple quotes
        # Factory methods for block creation (can be overridden for testing)
        self._make_prose_block = lambda activity: AgentOutputBlock(activity=activity)
        self._make_code_block = lambda code, lang: CodeInputBlock(code, language=lang, show_loading=True, in_context=True)

    def start(self) -> None:
        """Create the initial AgentOutputBlock for streaming prose."""
        self._current_block = self._make_prose_block(activity=True)
        self._output.append_block(self._current_block)
        self.all_blocks.append(self._current_block)
        self.first_agent_block = self._current_block

    def feed(self, text: str, auto_scroll: bool = True) -> None:
        """Process a chunk of streaming text, creating blocks as needed."""
        self._chunk_buffer = ""  # Reset for this chunk
        for ch in text:
            self._feed_char(ch)
        # Flush any pending text to the chunk buffer for display
        self._flush_pending_to_chunk()
        # Update current block with accumulated chunk text
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
        # Optionally scroll to bottom after updating content
        if auto_scroll:
            self._output.scroll_end(animate=False)

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
            lang = self._lang_buffer.strip() or "python"
            # Normalize language aliases
            lang = _LANG_ALIASES.get(lang, lang)
            self._current_lang = lang

            # Update current block with accumulated chunk
            if self._chunk_buffer and self._current_block:
                self._update_current_block_with_chunk()
                self._chunk_buffer = ""

            # Remove empty prose block, or mark it complete
            current_is_empty = (
                isinstance(self._current_block, AgentOutputBlock)
                and not self._current_block._full.strip()
            )
            if current_is_empty:
                if self._current_block is self.first_agent_block:
                    self.first_agent_block = None
                self._remove_block(self._current_block)
            elif isinstance(self._current_block, AgentOutputBlock):
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
        """Process code text, looking for closing fence (but not in strings)."""
        # Track string literals to avoid detecting fences inside strings
        self._update_string_state(ch)
        
        # Only detect fences when not inside a string literal
        if not self._in_string and ch == '`':
            self._backtick_count += 1
            if self._backtick_count == 3:
                # Found closing fence - flush pending code and transition
                self._flush_pending_to_chunk()

                # Update code block with accumulated chunk
                if self._chunk_buffer and self._current_block:
                    self._update_current_block_with_chunk()
                    self._chunk_buffer = ""

                self._backtick_count = 0
                # Reset string tracking for next code block
                self._in_string = None
                self._escape_next = False
                self._quote_buffer = ""

                # Start new prose block
                if isinstance(self._current_block, CodeInputBlock):
                    self._current_block.finish_streaming()
                self._current_block = self._make_prose_block(activity=True)
                self._output.append_block(self._current_block)
                self.all_blocks.append(self._current_block)

                self._state = _FenceState.PROSE
            # Don't add character to pending buffer yet - we're accumulating backticks
        else:
            # Not a backtick, or we're in a string
            if self._backtick_count > 0:
                # We had some backticks that weren't a fence - add them
                self._pending_buffer += '`' * self._backtick_count
                self._backtick_count = 0
            # Always add the current character
            self._pending_buffer += ch

    def _update_string_state(self, ch: str) -> None:
        """Track whether we're inside a string literal.
        
        Handles single quotes, double quotes, triple quotes, and escape sequences.
        This allows us to avoid detecting code fences that appear inside strings.
        """
        # Handle escape sequences
        if self._escape_next:
            self._escape_next = False
            self._quote_buffer = ""
            return
        
        if ch == '\\':
            self._escape_next = True
            self._quote_buffer = ""
            return
        
        # Track quotes to detect string boundaries
        if ch in ('"', "'"):
            # Build up quote buffer to detect triple quotes
            if self._quote_buffer and self._quote_buffer[0] == ch:
                self._quote_buffer += ch
            else:
                self._quote_buffer = ch
            
            # Check if we're entering or exiting a string
            if self._in_string:
                # Currently in a string - check if this closes it
                if self._in_string == self._quote_buffer:
                    # Closing the current string
                    self._in_string = None
                    self._quote_buffer = ""
            else:
                # Not in a string - check if this opens one
                # For triple quotes, wait until we have all three
                if len(self._quote_buffer) == 3:
                    # Opening triple-quoted string
                    self._in_string = self._quote_buffer
                    self._quote_buffer = ""
                elif len(self._quote_buffer) == 1:
                    # Could be single quote or start of triple quote
                    # We'll resolve this on the next character
                    pass
        else:
            # Non-quote character
            if self._quote_buffer and not self._in_string:
                # We had 1 or 2 quotes followed by a non-quote
                # This means it was a single or double quote string
                if len(self._quote_buffer) <= 2:
                    self._in_string = self._quote_buffer[0]
                    self._quote_buffer = ""
            elif self._quote_buffer:
                # We're in a string and hit a non-quote, reset buffer
                self._quote_buffer = ""
            
            # Newlines can end single-line strings in most languages
            # but not triple-quoted strings
            if ch == '\n' and self._in_string in ('"', "'"):
                self._in_string = None

    def _flush_pending_to_chunk(self) -> None:
        """Move pending buffer to chunk buffer."""
        self._chunk_buffer += self._pending_buffer
        self._pending_buffer = ""

    def _update_current_block_with_chunk(self) -> None:
        """Update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            if isinstance(self._current_block, CodeInputBlock):
                existing = self._current_block.get_code()
                self._current_block.update_code(existing + self._chunk_buffer)
            elif isinstance(self._current_block, AgentOutputBlock):
                self._current_block.append(self._chunk_buffer)

    def _remove_block(self, block: BaseBlock) -> None:
        """Remove a block from tracking lists and the DOM."""
        if block in self.all_blocks:
            self.all_blocks.remove(block)
        if block in self._output._blocks:
            self._output._blocks.remove(block)
        block.remove()

    def finish(self) -> None:
        """Flush any remaining state at end of stream."""
        # Handle incomplete fences
        if self._state == _FenceState.LANG_LINE:
            self._pending_buffer = '```' + self._lang_buffer
            self._state = _FenceState.PROSE

        # Flush trailing backticks that weren't a complete fence
        if self._backtick_count > 0:
            self._pending_buffer += '`' * self._backtick_count
            self._backtick_count = 0

        # Flush any remaining text
        self._flush_pending_to_chunk()
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()

        # Mark the last block as complete
        if isinstance(self._current_block, AgentOutputBlock):
            self._current_block.mark_success()

        # Finalize all blocks: switch from streaming mode to final rendering
        for block in self.all_blocks:
            if isinstance(block, CodeInputBlock):
                block.finish_streaming()
            elif isinstance(block, AgentOutputBlock):
                block.finalize_streaming()

        # Remove empty AgentOutputBlocks (keep first_agent_block for status indicator)
        for block in [
            b for b in self.all_blocks
            if isinstance(b, AgentOutputBlock) and b is not self.first_agent_block and not b._full.strip()
        ]:
            self._remove_block(block)


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

    ArtificeTerminal .highlighted > Horizontal > .status-indicator {
        background: $surface-lighten-2;
    }

    ArtificeTerminal .in-context {
        border-left: solid $primary;
    }

    ArtificeTerminal PinnedOutput {
        height: auto;
        max-height: 30vh;
    }

    ArtificeTerminal #flash {
        height: 0;
        display: none;
    }
    """

    BINDINGS = [
        Binding("ctrl+i", "focus_input", "Focus Input", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("ctrl+o", "toggle_mode_markdown", "Toggle Markdown", show=True),
        Binding("ctrl+c", "cancel_execution", "Cancel", show=True),
        Binding("ctrl+g", "toggle_auto_send_to_agent", "Toggle Agent", show=True),
        Binding("ctrl+n", "clear_agent_context", "Clear Context", show=True),
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
        self._shell_executor = ShellExecutor()

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
        )
        
        # Create agent
        self._agent = None
        if app.agent_type.lower() == "claude":
            from .agent import ClaudeAgent
            self._agent = ClaudeAgent(system_prompt=system_prompt)
        elif app.agent_type.lower() == "copilot":
            from .agent import CopilotAgent
            self._agent = CopilotAgent(system_prompt=system_prompt)
        elif app.agent_type.lower() == "simulated":
            from artifice.agent.simulated import SimulatedAgent
            self._agent = SimulatedAgent(response_delay=0.001)

            # Configure scenarios with pattern matching
            self._agent.configure_scenarios([
                {
                    'pattern': r'hello|hi|hey',
                    'response': 'Hello! I\'m a **simulated** agent. How can I help you today?'
                },
                {
                    'pattern': r'blank',
                    'response': '```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nI can help with that calculation!\n\n```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nThere it is, leave it or not',
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
            self._agent = OllamaAgent(system_prompt=system_prompt)
        elif app.agent_type:
            raise Exception(f"Unsupported agent {app.agent_type}")
        self._auto_send_to_agent: bool = True  # Persistent mode for auto-sending execution results

        self.output = TerminalOutput(id="output")
        self.input = TerminalInput(history=self._history, id="input")
        self.pinned_output = PinnedOutput(id="pinned")
        self._current_task: asyncio.Task | None = None
        self._context_blocks: list[BaseBlock] = []  # Blocks in agent context
        self._current_detector: StreamingFenceDetector | None = None  # Active streaming detector
        self._chunk_buffer: str = ""  # Buffer for batching StreamChunk messages
        self._chunk_processing_scheduled: bool = False  # Flag to avoid duplicate batch processing

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.output
            yield Static(id="flash")
            yield self.input
            yield self.pinned_output

    async def on_terminal_input_submitted(self, event: TerminalInput.Submitted) -> None:
        """Handle code submission from input."""
        code = event.code

        self.input.clear()

        # Create a task to track execution
        async def execute():
            try:
                if event.is_agent_prompt:
                    await self._handle_agent_prompt(code)
                elif event.is_shell_command:
                    result = await self._execute_code(code, language="bash")
                    if self._auto_send_to_agent:
                        await self._send_execution_result_to_agent(code, result)
                else:
                    result = await self._execute_code(code, language="python")
                    if self._auto_send_to_agent:
                        await self._send_execution_result_to_agent(code, result)
            except asyncio.CancelledError:
                # Task was cancelled - show message
                code_output_block = CodeOutputBlock(render_markdown=False)
                self.output.append_block(code_output_block)
                code_output_block.append_error("\n[Cancelled]\n")
                code_output_block.flush()
                raise
            finally:
                self._current_task = None

        self._current_task = asyncio.create_task(execute())

    def _make_output_callbacks(self, markdown_enabled: bool, in_context: bool = False):
        """Create on_output/on_error/flush callbacks that lazily create a CodeOutputBlock.

        Callbacks buffer text and schedule a single flush per event-loop tick,
        so rapid output (e.g. many lines from a shell command) gets batched.
        Returns (on_output, on_error, flush) — call flush() after execution to
        ensure all buffered text is rendered.
        """
        state = {"block": None, "flush_scheduled": False}

        def ensure_block():
            if state["block"] is None:
                state["block"] = CodeOutputBlock(render_markdown=markdown_enabled, in_context=in_context)
                if in_context:
                    self._context_blocks.append(state["block"])
                self.output.append_block(state["block"])
            return state["block"]

        def flush():
            state["flush_scheduled"] = False
            if state["block"]:
                state["block"].flush()
                self.output.scroll_end(animate=False)

        def _schedule_flush():
            if not state["flush_scheduled"]:
                state["flush_scheduled"] = True
                self.call_later(flush)

        def on_output(text):
            ensure_block().append_output(text)
            _schedule_flush()

        def on_error(text):
            ensure_block().append_error(text)
            _schedule_flush()

        return on_output, on_error, flush

    async def _execute_code(
        self, code: str, language: str = "python",
        code_input_block: CodeInputBlock | None = None,
        in_context: bool = False,
    ) -> ExecutionResult:
        """Execute code (python or bash), optionally creating the input block.

        Args:
            code: The code/command to execute.
            language: "python" or "bash".
            code_input_block: Existing block to update status on. If None, one is created.
            in_context: Whether the output should be marked as in agent context.
        """
        if code_input_block is None:
            code_input_block = CodeInputBlock(code, language=language)
            self.output.append_block(code_input_block)

        markdown_enabled = self._shell_markdown_enabled if language == "bash" else self._python_markdown_enabled
        on_output, on_error, flush_output = self._make_output_callbacks(markdown_enabled, in_context)

        executor = self._shell_executor if language == "bash" else self._executor
        result = await executor.execute(code, on_output=on_output, on_error=on_error)
        flush_output()  # Ensure any remaining buffered output is rendered

        code_input_block.update_status(result)

        if language != "bash" and isinstance(result.result_value, Widget):
            widget_block = WidgetOutputBlock(result.result_value)
            self.output.append_block(widget_block)

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

        # Flush any remaining buffered chunks and finalize directly
        # (no message-based race — send_prompt has returned, no more chunks coming)
        if self._chunk_buffer:
            self._process_chunk_buffer()
        self._current_detector.finish()

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

        # Auto-highlight the last CodeInputBlock from this agent response
        # Search backward through the blocks created in this response
        last_code_block = None
        for block in reversed(self._current_detector.all_blocks):
            if isinstance(block, CodeInputBlock):
                last_code_block = block
                break

        if last_code_block is not None:
            # Find its index in the output blocks
            try:
                last_code_block_index = self.output._blocks.index(last_code_block)
                # Set the index BEFORE focusing to avoid on_focus overwriting it
                self.output._highlighted_index = last_code_block_index
                self.output._update_highlight()
                self.output.focus()
            except ValueError:
                # Block not found in output (shouldn't happen, but be safe)
                pass

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
        prompt = "Executed:\n```\n" + code + "```\n\nOutput:\n" + result.output + result.error + "\n"
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
        executed_input_block = AgentInputBlock("Executed:", in_context=True)
        self._context_blocks.append(executed_input_block)
        self.output.append_block(executed_input_block)
        language = "bash" if mode == "shell" else "python"
        code_input_block = CodeInputBlock(code, language=language, show_loading=True, in_context=True)
        self._context_blocks.append(code_input_block)
        self.output.append_block(code_input_block)

        # Focus input immediately so user can continue working
        self.input.query_one("#code-input", InputTextArea).focus()

        # Create a task to track execution
        async def execute():
            result = ExecutionResult(code=code, status=ExecutionStatus.ERROR)
            try:
                result = await self._execute_code(
                    code, language=language,
                    code_input_block=block, in_context=self._auto_send_to_agent,
                )
                code_input_block.update_status(result)
                await self._send_execution_result_to_agent(code, result)
            except asyncio.CancelledError:
                code_output_block = CodeOutputBlock(render_markdown=False)
                self.output.append_block(code_output_block)
                code_output_block.append_error("\n[Cancelled]\n")
                code_output_block.flush()
                raise
            finally:
                if result:
                    code_input_block.update_status(result)
                code_input_block.finish_streaming()
                self._current_task = None
                self.input.focus_input()

        self._current_task = asyncio.create_task(execute())

    def on_stream_chunk(self, event: StreamChunk) -> None:
        """Handle streaming chunk message - buffer and batch process chunks."""
        if self._current_detector:
            # Add chunk to buffer
            self._chunk_buffer += event.text

            # Schedule batch processing if not already scheduled
            if not self._chunk_processing_scheduled:
                self._chunk_processing_scheduled = True
                # Schedule on next tick to allow chunks to accumulate
                self.call_later(self._process_chunk_buffer)

    def _process_chunk_buffer(self) -> None:
        """Process all accumulated chunks in the buffer at once."""
        if self._current_detector and self._chunk_buffer:
            text = self._chunk_buffer
            self._chunk_buffer = ""
            try:
                with self.app.batch_update():
                    self._current_detector.feed(text, auto_scroll=False)
                self.output.scroll_end(animate=False)
            except Exception:
                logger.exception("Error processing chunk buffer")
        # Reset scheduling flag to allow next batch
        self._chunk_processing_scheduled = False


    def action_clear(self) -> None:
        """Clear the output."""
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
        """Toggle markdown rendering for the current input mode (affects future blocks only)."""
        # Determine current mode and toggle its setting
        if self.input.mode == "ai":
            self._agent_markdown_enabled = not self._agent_markdown_enabled
            enabled_str = "enabled" if self._agent_markdown_enabled else "disabled"
            self.app.notify(f"Markdown {enabled_str} for AI agent output")
        elif self.input.mode == "shell":
            self._shell_markdown_enabled = not self._shell_markdown_enabled
            enabled_str = "enabled" if self._shell_markdown_enabled else "disabled"
            self.app.notify(f"Markdown {enabled_str} for shell command output")
        else:
            self._python_markdown_enabled = not self._python_markdown_enabled
            enabled_str = "enabled" if self._python_markdown_enabled else "disabled"
            self.app.notify(f"Markdown {enabled_str} for Python code output")

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

