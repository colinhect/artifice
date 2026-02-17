"""Main Artifice terminal widget."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import LoadingIndicator, Static

from .assistant import AssistantBase, create_assistant
from .execution import (
    ExecutionResult,
    ExecutionStatus,
    CodeExecutor,
    ShellExecutor,
    TmuxShellExecutor,
)
from .history import History
from .terminal_input import TerminalInput, InputTextArea
from .terminal_output import (
    TerminalOutput,
    AssistantInputBlock,
    AssistantOutputBlock,
    ThinkingOutputBlock,
    CodeInputBlock,
    CodeOutputBlock,
    WidgetOutputBlock,
    BaseBlock,
)
from .config import get_sessions_dir, ensure_sessions_dir
from .session import SessionTranscript
from .chunk_buffer import ChunkBuffer
from .fence_detector import StreamingFenceDetector
from .status_indicator import StatusIndicatorManager
from .output_callbacks import OutputCallbackHandler
from .input_mode import InputMode

if TYPE_CHECKING:
    from .app import ArtificeApp

logger = logging.getLogger(__name__)


class StreamChunk(Message):
    """Message posted when a chunk of streamed text arrives."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class StreamThinkingChunk(Message):
    """Message posted when a chunk of streamed thinking text arrives."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class ArtificeTerminal(Widget):
    """Primary widget for interacting with Artifice."""

    BINDINGS = [
        Binding("ctrl+i", "focus_input", "Focus Input", show=True),
        Binding("ctrl+l", "clear", "Clear", show=True),
        Binding("ctrl+o", "toggle_mode_markdown", "Toggle Markdown", show=True),
        Binding("ctrl+c", "cancel_execution", "Cancel", show=True),
        Binding(
            "ctrl+g", "toggle_auto_send_to_assistant", "Toggle Assistant", show=True
        ),
        Binding("ctrl+n", "clear_assistant_context", "Clear Context", show=True),
        Binding("alt+up", "navigate_up", "Navigate Up", show=True),
        Binding("alt+down", "navigate_down", "Navigate Down", show=True),
    ]

    _MARKDOWN_SETTINGS = {
        "ai": ("_assistant_markdown_enabled", "AI assistant output"),
        "shell": ("_shell_markdown_enabled", "shell command output"),
        "python": ("_python_markdown_enabled", "Python code output"),
    }

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

        self._config = app.config

        self._executor = CodeExecutor()
        if self._config.tmux_target:
            prompt_pattern = self._config.tmux_prompt_pattern or r"^\$ "
            self._shell_executor = TmuxShellExecutor(
                self._config.tmux_target,
                prompt_pattern=prompt_pattern,
                check_exit_code=self._config.tmux_echo_exit_code,
            )
        else:
            self._shell_executor = ShellExecutor()

        # Set shell init script from config (only applicable to ShellExecutor)
        if self._config.shell_init_script and isinstance(
            self._shell_executor, ShellExecutor
        ):
            self._shell_executor.init_script = self._config.shell_init_script

        # Create history manager
        self._history = History(
            history_file=history_file, max_history_size=max_history_size
        )

        self._python_markdown_enabled = self._config.python_markdown
        self._assistant_markdown_enabled = self._config.assistant_markdown
        self._shell_markdown_enabled = self._config.shell_markdown
        self._auto_send_to_assistant: bool = self._config.auto_send_to_assistant

        # Initialize session transcript if enabled
        self._session_transcript: SessionTranscript | None = None
        if self._config.save_sessions:
            try:
                ensure_sessions_dir(self._config)
                sessions_dir = get_sessions_dir(self._config)
                self._session_transcript = SessionTranscript(sessions_dir, self._config)
            except Exception as e:
                logger.error("Failed to initialize session transcript: %s", e)

        self.output = TerminalOutput(id="output")
        self.input = TerminalInput(history=self._history, id="input")
        self.assistant_loading = LoadingIndicator()
        self.connection_status = Static("◉", id="connection-status")
        self.assistant_status = Static("", id="assistant-status")

        # Status indicator manager
        self._status_manager = StatusIndicatorManager(
            self.assistant_loading,
            self.connection_status,
            self.assistant_status,
            self._config,
        )

        self._current_task: asyncio.Task | None = None
        self._context_blocks: list[BaseBlock] = []  # Blocks in assistant context
        self._current_detector: StreamingFenceDetector | None = (
            None  # Active streaming detector
        )
        self._thinking_block: ThinkingOutputBlock | None = None  # Active thinking block
        self._chunk_buf = ChunkBuffer(self.call_later, self._drain_chunks)
        self._thinking_buf = ChunkBuffer(self.call_later, self._drain_thinking)
        self._stream_paused = False

        def on_connect(_):
            self.connection_status.add_class("connected")

        # Create assistant
        self._assistant: AssistantBase | None = None
        self._assistant = create_assistant(self._config, on_connect=on_connect)
        self._status_manager.set_inactive()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.output
            yield self.input
            with Horizontal(id="status-line"):
                yield self.assistant_loading
                yield self.connection_status
                yield self.assistant_status

    def on_mount(self) -> None:
        self._status_manager.update_assistant_info()

    def _save_block_to_session(self, block: BaseBlock) -> None:
        """Save a block to the session transcript if enabled."""
        if self._session_transcript:
            try:
                self._session_transcript.append_block(block)
            except Exception as e:
                logger.error("Failed to save block to session: %s", e)

    async def _run_cancellable(self, coro, *, finally_callback=None):
        """Run a coroutine with standard cancel handling.

        On CancelledError, shows a [Cancelled] block unless the stream is paused
        (which means the cancellation was intentional for code execution).
        Always clears _current_task and calls finally_callback if provided.
        """
        try:
            await coro
        except asyncio.CancelledError:
            # Only show [Cancelled] if not paused for code execution
            if not self._stream_paused:
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

        async def do_execute():
            if event.is_assistant_prompt:
                await self._handle_assistant_prompt(code)
            elif event.is_shell_command:
                result = await self._execute_code(
                    code, language="bash", in_context=self._auto_send_to_assistant
                )
                if self._auto_send_to_assistant:
                    await self._send_execution_result_to_assistant(code, "bash", result)
            else:
                result = await self._execute_code(
                    code, language="python", in_context=self._auto_send_to_assistant
                )
                if self._auto_send_to_assistant:
                    await self._send_execution_result_to_assistant(
                        code, "python", result
                    )

        self._current_task = asyncio.create_task(self._run_cancellable(do_execute()))

    def _make_output_callbacks(
        self,
        markdown_enabled: bool,
        in_context: bool = False,
        use_code_block: bool = True,
    ):
        """Create on_output/on_error/flush callbacks that lazily create a CodeOutputBlock.

        Returns (on_output, on_error, flush) — call flush() after execution to
        ensure all buffered text is rendered.
        """
        handler = OutputCallbackHandler(
            output=self.output,
            markdown_enabled=markdown_enabled,
            in_context=in_context,
            save_callback=self._save_block_to_session,
            schedule_fn=self.call_later,
            use_code_block=use_code_block,
        )

        # Mark block in context if needed
        if in_context:
            # We need to track the block when it's created
            original_ensure = handler._ensure_block

            def ensure_and_track():
                block = original_ensure()
                if block is not None and block not in self._context_blocks:
                    self._context_blocks.append(block)
                return block

            handler._ensure_block = ensure_and_track

        return handler.on_output, handler.on_error, handler.flush

    async def _execute_code(
        self,
        code: str,
        language: str = "python",
        code_input_block: CodeInputBlock | None = None,
        in_context: bool = False,
    ) -> ExecutionResult:
        """Execute code (python or bash), optionally creating the input block.

        Args:
            code: The code/command to execute.
            language: "python" or "bash".
            code_input_block: Existing block to update status on. If None, one is created.
            in_context: Whether the output should be marked as in assistant context.
        """
        if code_input_block is None:
            code_input_block = CodeInputBlock(
                code, language=language, show_loading=True, in_context=in_context
            )
            self.output.append_block(code_input_block)
            self._save_block_to_session(code_input_block)

        # Determine markdown and code block settings
        if language == "bash":
            markdown_enabled = self._shell_markdown_enabled
            # Check if using tmux or regular shell
            use_code_block = (
                self._config.tmux_output_code_block
                if isinstance(self._shell_executor, TmuxShellExecutor)
                else self._config.shell_output_code_block
            )
        else:
            markdown_enabled = self._python_markdown_enabled
            use_code_block = self._config.python_output_code_block

        on_output, on_error, flush_output = self._make_output_callbacks(
            markdown_enabled, in_context, use_code_block
        )

        executor = self._shell_executor if language == "bash" else self._executor
        result = await executor.execute(code, on_output=on_output, on_error=on_error)
        flush_output()  # Ensure any remaining buffered output is rendered

        code_input_block.update_status(result)

        if language != "bash" and isinstance(result.result_value, Widget):
            widget_block = WidgetOutputBlock(result.result_value)
            self.output.append_block(widget_block)

        return result

    def _mark_block_in_context(self, block: BaseBlock) -> None:
        """Mark a block as being in the assistant's context."""
        if block not in self._context_blocks:
            self._context_blocks.append(block)
            block.add_class("in-context")

    def _clear_all_context_highlights(self) -> None:
        """Remove in-context highlighting from all blocks."""
        for block in self._context_blocks:
            block.remove_class("in-context")
        self._context_blocks.clear()

    def _finalize_stream(self) -> None:
        """Flush buffers and finalize thinking block and detector after streaming ends."""
        # Flush any remaining buffered thinking chunks
        self._thinking_buf.flush_sync()
        if self._thinking_block:
            self._thinking_block.finalize_streaming()
            self._thinking_block.mark_success()
            self._save_block_to_session(self._thinking_block)
            self._thinking_block = None

        # If the stream was paused (code block detected), DON'T finalize yet.
        # The detector and buffer will be finalized when the user executes/skips the code.
        if self._stream_paused:
            return

        # Flush any remaining buffered chunks and finalize detector
        self._chunk_buf.flush_sync()
        if self._current_detector:
            self._current_detector.finish()

    def _apply_assistant_response(
        self, detector: StreamingFenceDetector, response
    ) -> None:
        """Mark context, handle errors, and auto-highlight the first code block."""
        with self.app.batch_update():
            for block in detector.all_blocks:
                self._mark_block_in_context(block)

            if detector.first_assistant_block:
                if response.error:
                    detector.first_assistant_block.append(
                        f"\n**Error:** {response.error}\n"
                    )
                    detector.first_assistant_block.flush()
                    detector.first_assistant_block.mark_failed()
                else:
                    detector.first_assistant_block.flush()
                    detector.first_assistant_block.mark_success()

        # Auto-highlight the first CodeInputBlock (command #1) from this response
        last_code_block = None
        for block in reversed(detector.all_blocks):
            if isinstance(block, CodeInputBlock) and block._command_number == 1:
                last_code_block = block
                break

        if last_code_block is not None:
            idx = self.output.index_of(last_code_block)
            if idx is not None:
                self.output._highlighted_index = idx
                self.output._update_highlight()
                self.output.focus()

    async def _stream_assistant_response(
        self, assistant: AssistantBase, prompt: str
    ) -> tuple[StreamingFenceDetector, object]:
        """Stream an assistant response, splitting into prose and code blocks.

        Returns the detector (with all_blocks, first_assistant_block) and the AssistantResponse.
        """
        self.output.clear_command_numbers()

        self._current_detector = StreamingFenceDetector(
            self.output,
            save_callback=self._save_block_to_session,
            pause_after_code=True,
        )

        def on_chunk(text):
            self.post_message(StreamChunk(text))

        def on_thinking_chunk(text):
            self.post_message(StreamThinkingChunk(text))

        if self._config.prompt_prefix:
            prompt = self._config.prompt_prefix + " " + prompt

        self._status_manager.set_active()
        try:
            response = await assistant.send_prompt(
                prompt, on_chunk=on_chunk, on_thinking_chunk=on_thinking_chunk
            )
        except asyncio.CancelledError:
            self._status_manager.set_inactive()
            self._finalize_stream()
            self._current_detector = None
            raise
        self._status_manager.set_inactive()
        self._status_manager.update_assistant_info(
            usage=getattr(response, "usage", None)
        )

        self._finalize_stream()
        self._apply_assistant_response(self._current_detector, response)

        detector = self._current_detector
        self._current_detector = None
        return detector, response

    async def _handle_assistant_prompt(self, prompt: str) -> None:
        """Handle AI assistant prompt with code block detection."""
        # Create a block showing the prompt
        assistant_input_block = AssistantInputBlock(prompt)
        self.output.append_block(assistant_input_block)
        self._save_block_to_session(assistant_input_block)

        # Mark the prompt as in context
        self._mark_block_in_context(assistant_input_block)

        if self._assistant is None:
            # No assistant configured, show error
            assistant_output_block = AssistantOutputBlock("No AI assistant configured.")
            self.output.append_block(assistant_output_block)
            assistant_output_block.mark_failed()
            return

        await self._stream_assistant_response(self._assistant, prompt)

        # After sending a prompt to the assistant, enable auto-send mode
        if not self._auto_send_to_assistant:
            self._auto_send_to_assistant = True
            self.input.add_class("in-context")

    async def _send_execution_result_to_assistant(
        self, code: str, language: str, result: ExecutionResult
    ) -> None:
        """Send execution results back to the assistant and split the response."""
        if self._assistant is not None:
            prompt = (
                f"Executed: <{language}>{code}</{language}>"
                + "\n\nOutput:\n"
                + result.output
                + result.error
                + "\n"
            )
            await self._stream_assistant_response(self._assistant, prompt)

    async def on_terminal_output_block_activated(
        self, event: TerminalOutput.BlockActivated
    ) -> None:
        """Handle block activation: copy code to input with correct mode."""
        # Set the code in the input
        self.input.code = event.code
        # Set the correct mode (convert string to InputMode)
        try:
            self.input.mode = InputMode.from_name(event.mode)
            self.input._update_prompt()
        except ValueError:
            # If mode conversion fails, just keep current mode
            pass
        # Focus the input
        self.input.query_one("#code-input", InputTextArea).focus()

    async def on_terminal_output_block_execute_requested(
        self, event: TerminalOutput.BlockExecuteRequested
    ) -> None:
        """Handle block execution: execute code from a block and send output to assistant."""
        block = event.block

        # If stream is paused and this is the paused code block, use the pause handler
        if (
            self._stream_paused
            and self._current_detector
            and block is self._current_detector.last_code_block
        ):
            self._current_task = asyncio.create_task(
                self._run_cancellable(self._execute_paused_code_block())
            )
            return

        code = block.get_code()
        mode = block.get_mode()
        language = "bash" if mode == "shell" else "python"

        # Show loading indicator before execution
        block.show_loading()

        # Focus input immediately so user can continue working
        self.input.query_one("#code-input", InputTextArea).focus()

        state = {
            "result": ExecutionResult(code=code, status=ExecutionStatus.ERROR),
            "sent_to_assistant": False,
        }

        async def do_execute():
            state["result"] = await self._execute_code(
                code,
                language=language,
                code_input_block=block,
                in_context=self._auto_send_to_assistant,
            )
            block.update_status(state["result"])
            if self._auto_send_to_assistant:
                state["sent_to_assistant"] = True
                await self._send_execution_result_to_assistant(
                    code, language, state["result"]
                )

        def cleanup():
            if state["result"]:
                block.update_status(state["result"])
            block.finish_streaming()
            if not state["sent_to_assistant"]:
                self.input.focus_input()

        self._current_task = asyncio.create_task(
            self._run_cancellable(do_execute(), finally_callback=cleanup)
        )

    def on_stream_chunk(self, event: StreamChunk) -> None:
        """Handle streaming chunk message - buffer and batch process chunks."""
        if self._current_detector:
            # Start detector on first text chunk (deferred so thinking block comes first)
            self._current_detector.start()
            self._chunk_buf.append(event.text)

    def _drain_chunks(self, text: str) -> None:
        """Process all accumulated chunks in the buffer at once."""
        if not self._current_detector:
            return
        # Ensure detector is started before feeding text
        self._current_detector.start()
        try:
            with self.app.batch_update():
                self._current_detector.feed(text)
            # Schedule scroll after layout refresh so Markdown widget height is recalculated
            self.call_after_refresh(lambda: self.output.scroll_end(animate=False))

            # Check if detector paused after a code block
            if self._current_detector.is_paused:
                self._chunk_buf.pause()
                self._stream_paused = True
                # Cancel the provider task to stop streaming
                if self._current_task and not self._current_task.done():
                    self._current_task.cancel()
                # Highlight the code block that just completed
                code_block = self._current_detector.last_code_block
                if code_block is not None:
                    idx = self.output.index_of(code_block)
                    if idx is not None:
                        self.output._highlighted_index = idx
                        self.output._update_highlight()
                        self.output.focus()
        except Exception:
            logger.exception("Error processing chunk buffer")

    def on_stream_thinking_chunk(self, event: StreamThinkingChunk) -> None:
        """Handle streaming thinking chunk message - buffer and batch process."""
        self._thinking_buf.append(event.text)

    def _drain_thinking(self, text: str) -> None:
        """Process all accumulated thinking chunks in the buffer at once."""
        try:
            # Lazily create thinking block on first chunk
            if self._thinking_block is None:
                self._thinking_block = ThinkingOutputBlock(activity=True)
                self.output.append_block(self._thinking_block)
            self._thinking_block.append(text)
            self._thinking_block.flush()
            self.output.scroll_end(animate=False)
        except Exception:
            logger.exception("Error processing thinking buffer")

    def _resume_stream(self) -> None:
        """Resume streaming after a pause-on-code-block."""
        self._stream_paused = False
        # Restore assistant status
        self._status_manager.update_assistant_info()
        # Feed detector's remainder
        if self._current_detector:
            self._current_detector.resume()
        # Resume chunk buffer (will flush any accumulated chunks)
        self._chunk_buf.resume()
        # Finalize the stream since provider task was cancelled when we paused
        self._chunk_buf.flush_sync()
        if self._current_detector:
            self._current_detector.finish()
            self._current_detector = None

    async def _execute_paused_code_block(self) -> None:
        """Execute the code block that triggered the pause, then resume."""
        if not self._current_detector:
            self._resume_stream()
            return
        code_block = self._current_detector.last_code_block
        if code_block is None or not isinstance(code_block, CodeInputBlock):
            self._resume_stream()
            return
        code = code_block.get_code()
        mode = code_block.get_mode()
        language = "bash" if mode == "shell" else "python"
        result = await self._execute_code(
            code,
            language=language,
            code_input_block=code_block,
            in_context=self._auto_send_to_assistant,
        )
        self._resume_stream()
        if self._auto_send_to_assistant:
            await self._send_execution_result_to_assistant(code, language, result)

    def on_key(self, event) -> None:
        """Handle key events, including pause-state shortcuts."""
        if not self._stream_paused:
            return
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            asyncio.create_task(self._execute_paused_code_block())
        elif event.key == "s":
            event.prevent_default()
            event.stop()
            self._resume_stream()
        elif event.key == "c":
            event.prevent_default()
            event.stop()
            self._stream_paused = False
            self.assistant_status.update("")
            # Finalize without processing remainder (discard it)
            if self._current_detector:
                self._current_detector._remainder = ""
                self._current_detector.finish()
                self._current_detector = None
            self.action_cancel_execution()

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
        """Toggle markdown rendering for the current input mode (affects future blocks only)."""
        mode_name = self.input.mode.value.name
        attr, label = self._MARKDOWN_SETTINGS[mode_name]
        setattr(self, attr, not getattr(self, attr))
        enabled_str = "enabled" if getattr(self, attr) else "disabled"
        self.app.notify(f"Markdown {enabled_str} for {label}")

    def reset(self) -> None:
        """Reset the REPL state."""
        self._executor.reset()
        self.output.clear()
        self._history.clear()

    def action_navigate_up(self) -> None:
        """Navigate up: from input to output (bottom block), or up through output blocks."""
        input_area = self.input.query_one("#code-input", InputTextArea)
        if input_area.has_focus and self.output._blocks:
            # Move from input to output
            self.output.focus()
        elif self.output.has_focus:
            # Navigate up through blocks
            self.output.highlight_previous()

    def action_navigate_down(self) -> None:
        """Navigate down: through output blocks, or from output to input."""
        if self.output.has_focus:
            # Try to move to next block, or move to input if at bottom
            if not self.output.highlight_next():
                self.input.query_one("#code-input", InputTextArea).focus()

    def action_toggle_auto_send_to_assistant(self) -> None:
        """Toggle auto-send mode - when enabled, all code execution results are sent to assistant."""
        self._auto_send_to_assistant = not self._auto_send_to_assistant

        # Update visual indicator on input
        if self._auto_send_to_assistant:
            self.input.add_class("in-context")
        else:
            self.input.remove_class("in-context")

    def on_terminal_input_prompt_selected(
        self, event: TerminalInput.PromptSelected
    ) -> None:
        """Handle prompt template selection: append to assistant's system prompt."""
        if self._assistant is not None:
            if self._assistant.system_prompt:
                self._assistant.system_prompt += "\n\n" + event.content
            else:
                self._assistant.system_prompt = event.content
            self._assistant.prompt_updated()
            self.app.notify(f"Loaded prompt: {event.name}")

    def action_clear_assistant_context(self) -> None:
        """Clear the assistant's conversation context and unhighlight all in-context blocks."""
        if self._assistant and hasattr(self._assistant, "clear_conversation"):
            self._assistant.clear_conversation()

        # Remove highlighting from all context blocks
        self._clear_all_context_highlights()
