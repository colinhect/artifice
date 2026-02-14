"""Main Artifice terminal widget."""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import LoadingIndicator, Static

from .assistant import AssistantBase, create_assistant
from .execution import ExecutionResult, ExecutionStatus, CodeExecutor, ShellExecutor
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
    PinnedOutput,
    BaseBlock,
)
from .config import get_sessions_dir, ensure_sessions_dir
from .session import SessionTranscript

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


class StreamThinkingChunk(Message):
    """Message posted when a chunk of streamed thinking text arrives."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class StringTracker:
    """Tracks whether we're inside a string literal in streaming code.

    Handles single quotes, double quotes, triple quotes, and escape sequences.
    This allows us to avoid detecting code fences that appear inside strings.
    """

    def __init__(self) -> None:
        self._in_string: str | None = None  # None, "'", '"', "'''", or '"""'
        self._escape_next = False
        self._quote_buffer = ""

    @property
    def in_string(self) -> bool:
        return self._in_string is not None

    def reset(self) -> None:
        self._in_string = None
        self._escape_next = False
        self._quote_buffer = ""

    def track(self, ch: str) -> None:
        """Update string tracking state for the given character."""
        # Handle escape sequences
        if self._escape_next:
            self._escape_next = False
            self._quote_buffer = ""
            return

        if ch == "\\":
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
            if ch == "\n" and self._in_string in ('"', "'"):
                self._in_string = None


class StreamingFenceDetector:
    """Detects code fences in streaming text and splits into blocks in real-time.

    Processes chunks character-by-character using a 3-state machine:
    PROSE -> LANG_LINE (on ```) -> CODE (on newline) -> PROSE (on closing ```)

    Creates blocks as fences are detected, accumulating text to update once per chunk.
    """

    def __init__(self, output: TerminalOutput, auto_scroll, save_callback=None) -> None:
        self._output = output
        self._auto_scroll = auto_scroll
        self._save_callback = save_callback  # Callback to save blocks to session
        self._state = _FenceState.PROSE
        self._backtick_count = 0
        self._lang_buffer = ""
        self._pending_buffer = ""  # Text to add to current block
        self._chunk_buffer = ""  # Accumulates text for current chunk to display
        self._current_lang = "python"
        self._current_block: BaseBlock | None = (
            None  # The block we're currently appending to
        )
        self.all_blocks: list[BaseBlock] = []
        self.first_assistant_block: AssistantOutputBlock | None = None
        self._string_tracker = StringTracker()
        # Factory methods for block creation (can be overridden for testing)
        self._make_prose_block = lambda activity: AssistantOutputBlock(
            activity=activity
        )
        self._make_code_block = lambda code, lang: CodeInputBlock(
            code,
            language=lang,
            show_loading=False,
            in_context=True,
            command_number=self._output.next_command_number(),
        )

    def start(self) -> None:
        """Create the initial AssistantOutputBlock for streaming prose."""
        self._current_block = self._make_prose_block(activity=True)
        self._output.append_block(self._current_block)
        self.all_blocks.append(self._current_block)
        self.first_assistant_block = self._current_block

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
            self._chunk_buffer = ""  # Clear after updating to avoid reprocessing

    def _feed_char(self, ch: str) -> None:
        if self._state == _FenceState.PROSE:
            self._feed_prose(ch)
        elif self._state == _FenceState.LANG_LINE:
            self._feed_lang_line(ch)
        elif self._state == _FenceState.CODE:
            self._feed_code(ch)

    def _flush_backticks_to_pending(self) -> None:
        """Flush accumulated backticks (that weren't a fence) to the pending buffer."""
        if self._backtick_count > 0:
            self._pending_buffer += "`" * self._backtick_count
            self._backtick_count = 0

    def _flush_and_update_chunk(self) -> None:
        """Flush pending text and update the current block with the chunk buffer."""
        if self._chunk_buffer and self._current_block:
            self._update_current_block_with_chunk()
            self._chunk_buffer = ""

    def _feed_prose(self, ch: str) -> None:
        """Process prose text, looking for opening fence."""
        if ch == "`":
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
            self._flush_backticks_to_pending()
            self._pending_buffer += ch

    def _feed_lang_line(self, ch: str) -> None:
        """Process language line after opening fence."""
        if ch == "\n":
            # Language line complete - start code block
            lang = self._lang_buffer.strip() or "python"
            # Normalize language aliases
            lang = _LANG_ALIASES.get(lang, lang)
            self._current_lang = lang

            # Update current block with accumulated chunk
            self._flush_and_update_chunk()

            # Remove empty prose block, or mark it complete
            current_is_empty = (
                isinstance(self._current_block, AssistantOutputBlock)
                and not self._current_block._full.strip()
            )
            if current_is_empty:
                if self._current_block is self.first_assistant_block:
                    self.first_assistant_block = None
                if self._current_block is not None:
                    self._remove_block(self._current_block)
            elif isinstance(self._current_block, AssistantOutputBlock):
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
        self._string_tracker.track(ch)

        # Only detect fences when not inside a string literal
        if not self._string_tracker.in_string and ch == "`":
            self._backtick_count += 1
            if self._backtick_count == 3:
                # Found closing fence - flush pending code and transition
                self._flush_pending_to_chunk()

                # Update code block with accumulated chunk
                self._flush_and_update_chunk()

                self._backtick_count = 0
                # Reset string tracking for next code block
                self._string_tracker.reset()

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
            self._flush_backticks_to_pending()
            # Always add the current character
            self._pending_buffer += ch

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
            elif isinstance(self._current_block, AssistantOutputBlock):
                self._current_block.append(self._chunk_buffer)
                self._current_block.flush()

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
            self._pending_buffer = "```" + self._lang_buffer
            self._state = _FenceState.PROSE

        # Flush trailing backticks that weren't a complete fence
        if self._backtick_count > 0:
            self._pending_buffer += "`" * self._backtick_count
            self._backtick_count = 0

        # Flush any remaining text ONLY if there's pending content
        # Don't flush _chunk_buffer as it was already processed by _process_chunk_buffer()
        if self._pending_buffer:
            self._flush_pending_to_chunk()
            if self._chunk_buffer and self._current_block:
                self._update_current_block_with_chunk()
                self._chunk_buffer = ""  # Clear to avoid double-processing

        # Mark the last block as complete
        if isinstance(self._current_block, AssistantOutputBlock):
            self._current_block.flush()  # Ensure final content is rendered
            self._current_block.mark_success()

        # Finalize all blocks: switch from streaming mode to final rendering
        for block in self.all_blocks:
            if isinstance(block, CodeInputBlock):
                block.finish_streaming()
            elif isinstance(block, AssistantOutputBlock):
                block.flush()  # Ensure all content is rendered before finalizing
                block.finalize_streaming()

        # Remove empty AssistantOutputBlocks (keep first_assistant_block for status indicator)
        for block in [
            b
            for b in self.all_blocks
            if isinstance(b, AssistantOutputBlock)
            and b is not self.first_assistant_block
            and not b._full.strip()
        ]:
            self._remove_block(block)

        # Save all blocks to session now that they're finalized
        if self._save_callback:
            for block in self.all_blocks:
                self._save_callback(block)


class ChunkBuffer:
    """Accumulates text chunks and drains them in a single batch via call_later.

    Enforces a maximum frame rate (default 30 FPS) to prevent excessive UI updates
    during rapid streaming.

    Args:
        schedule: Callable that defers ``drain`` to the next event-loop tick
                  (e.g. ``widget.call_later``).
        drain: Callable(text) invoked with the accumulated text when flushed.
        min_interval: Minimum seconds between drain operations (default: 1/30 for 30 FPS).
    """

    def __init__(self, schedule, drain, min_interval: float = 1.0 / 30.0) -> None:
        self._schedule = schedule
        self._drain = drain
        self._buffer: str = ""
        self._scheduled: bool = False
        self._min_interval = min_interval
        self._last_drain_time: float = 0.0

    def append(self, text: str) -> None:
        """Add *text* to the buffer and schedule a drain if needed."""
        self._buffer += text
        if not self._scheduled:
            self._scheduled = True
            # Check if we need to throttle based on last drain time
            now = time.monotonic()
            elapsed = now - self._last_drain_time
            if elapsed >= self._min_interval:
                # Enough time has passed, schedule immediately
                self._schedule(self._flush)
            else:
                # Throttle: schedule for later to maintain frame rate limit
                delay = self._min_interval - elapsed
                self._schedule(lambda: self._schedule_delayed_flush(delay))

    def _schedule_delayed_flush(self, delay: float) -> None:
        """Schedule a flush after the specified delay."""
        import asyncio

        asyncio.get_event_loop().call_later(delay, self._flush)

    def _flush(self) -> None:
        self._scheduled = False
        if self._buffer:
            text = self._buffer
            self._buffer = ""
            self._last_drain_time = time.monotonic()
            self._drain(text)

    def flush_sync(self) -> None:
        """Drain any remaining buffered text immediately."""
        self._scheduled = False
        if self._buffer:
            text = self._buffer
            self._buffer = ""
            self._last_drain_time = time.monotonic()
            self._drain(text)

    @property
    def pending(self) -> bool:
        """True if the buffer has un-drained text."""
        return bool(self._buffer)


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
        self._shell_executor = ShellExecutor()

        # Set shell init script from config
        if self._config.shell_init_script:
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
                logger.error(f"Failed to initialize session transcript: {e}")

        self.output = TerminalOutput(id="output")
        self.input = TerminalInput(history=self._history, id="input")
        self.assistant_loading = LoadingIndicator()
        self.connection_status = Static("◉", id="connection-status")
        self.assistant_status = Static("", id="assistant-status")
        # self.pinned_output = PinnedOutput(id="pinned")
        self._current_task: asyncio.Task | None = None
        self._context_blocks: list[BaseBlock] = []  # Blocks in assistant context
        self._current_detector: StreamingFenceDetector | None = (
            None  # Active streaming detector
        )
        self._thinking_block: ThinkingOutputBlock | None = None  # Active thinking block
        self._chunk_buf = ChunkBuffer(self.call_later, self._drain_chunks)
        self._thinking_buf = ChunkBuffer(self.call_later, self._drain_thinking)

        def on_connect(_):
            self.connection_status.add_class("connected")

        # Create assistant
        self._assistant: AssistantBase | None = None
        self._assistant = create_assistant(self._config, on_connect=on_connect)
        self._set_assistant_inactive()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.output
            yield self.input
            # yield self.pinned_output
            with Horizontal(id="status-line"):
                yield self.assistant_loading
                yield self.connection_status
                yield self.assistant_status

    def on_mount(self) -> None:
        if self._config.models:
            model = self._config.models.get(self._config.model)
            if model:
                self.assistant_status.update(
                    f"{model.get('model').lower()} ({model.get('provider').lower()})"
                )

    def _save_block_to_session(self, block: BaseBlock) -> None:
        """Save a block to the session transcript if enabled."""
        if self._session_transcript:
            try:
                self._session_transcript.append_block(block)
            except Exception as e:
                logger.error(f"Failed to save block to session: {e}")

    async def _run_cancellable(self, coro, *, finally_callback=None):
        """Run a coroutine with standard cancel handling.

        On CancelledError, shows a [Cancelled] block. Always clears _current_task
        and calls finally_callback if provided.
        """
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

        async def do_execute():
            if event.is_assistant_prompt:
                await self._handle_assistant_prompt(code)
            elif event.is_shell_command:
                result = await self._execute_code(
                    code, language="bash", in_context=self._auto_send_to_assistant
                )
                if self._auto_send_to_assistant:
                    await self._send_execution_result_to_assistant(code, result)
            else:
                result = await self._execute_code(
                    code, language="python", in_context=self._auto_send_to_assistant
                )
                if self._auto_send_to_assistant:
                    await self._send_execution_result_to_assistant(code, result)

        self._current_task = asyncio.create_task(self._run_cancellable(do_execute()))

    def _make_output_callbacks(self, markdown_enabled: bool, in_context: bool = False):
        """Create on_output/on_error/flush callbacks that lazily create a CodeOutputBlock.

        Callbacks buffer text and schedule a single flush per event-loop tick,
        so rapid output (e.g. many lines from a shell command) gets batched.
        Returns (on_output, on_error, flush) — call flush() after execution to
        ensure all buffered text is rendered.
        """
        state = {"block": None, "flush_scheduled": False, "saved": False}

        def ensure_block():
            if state["block"] is None:
                state["block"] = CodeOutputBlock(
                    render_markdown=markdown_enabled, in_context=in_context
                )
                if in_context:
                    self._context_blocks.append(state["block"])
                self.output.append_block(state["block"])
            return state["block"]

        def flush():
            state["flush_scheduled"] = False
            if state["block"]:
                state["block"].flush()
                self.output.scroll_end(animate=False)
                # Save to session on final flush if not already saved
                if not state["saved"]:
                    self._save_block_to_session(state["block"])
                    state["saved"] = True

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

        markdown_enabled = (
            self._shell_markdown_enabled
            if language == "bash"
            else self._python_markdown_enabled
        )
        on_output, on_error, flush_output = self._make_output_callbacks(
            markdown_enabled, in_context
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

    def _set_assistant_active(self) -> None:
        """Update status indicators to show assistant is processing."""
        self.assistant_loading.classes = "assistant-active"
        self.connection_status.remove_class("assistant-inactive")
        self.connection_status.add_class("assistant-active")

    def _set_assistant_inactive(self) -> None:
        """Update status indicators to show assistant is idle."""
        self.connection_status.add_class("assistant-inactive")
        self.connection_status.remove_class("assistant-active")
        self.assistant_loading.classes = "assistant-inactive"

    def _finalize_stream(self) -> None:
        """Flush buffers and finalize thinking block and detector after streaming ends."""
        # Flush any remaining buffered thinking chunks
        self._thinking_buf.flush_sync()
        if self._thinking_block:
            self._thinking_block.finalize_streaming()
            self._thinking_block.mark_success()
            self._save_block_to_session(self._thinking_block)
            self._thinking_block = None

        # Flush any remaining buffered chunks and finalize detector
        self._chunk_buf.flush_sync()
        if not self._detector_started:
            self._detector_started = True
            self._current_detector.start()
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
            try:
                idx = self.output._blocks.index(last_code_block)
                self.output._highlighted_index = idx
                self.output._update_highlight()
                self.output.focus()
            except ValueError:
                pass

    async def _stream_assistant_response(
        self, assistant: AssistantBase, prompt: str
    ) -> tuple[StreamingFenceDetector, object]:
        """Stream an assistant response, splitting into prose and code blocks.

        Returns the detector (with all_blocks, first_assistant_block) and the AssistantResponse.
        """
        self.output.clear_command_numbers()

        self._current_detector = StreamingFenceDetector(
            self.output,
            self.output.auto_scroll,
            save_callback=self._save_block_to_session,
        )
        self._detector_started = False

        def on_chunk(text):
            self.post_message(StreamChunk(text))

        def on_thinking_chunk(text):
            self.post_message(StreamThinkingChunk(text))

        if self._config.prompt_prefix:
            prompt = self._config.prompt_prefix + " " + prompt

        self._set_assistant_active()
        response = await assistant.send_prompt(
            prompt, on_chunk=on_chunk, on_thinking_chunk=on_thinking_chunk
        )
        self._set_assistant_inactive()

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
        self, code: str, result: ExecutionResult
    ) -> None:
        """Send execution results back to the assistant and split the response."""
        if self._assistant is not None:
            prompt = (
                "Executed:\n```\n"
                + code
                + "```\n\nOutput:\n"
                + result.output
                + result.error
                + "\n"
            )
            await self._stream_assistant_response(self._assistant, prompt)

    async def on_terminal_output_pin_requested(
        self, event: TerminalOutput.PinRequested
    ) -> None:
        """Handle pin request: move widget block from output to pinned area."""
        block = event.block
        await block.remove()
        # await self.pinned_output.add_pinned_block(block)

    async def on_pinned_output_unpin_requested(
        self, event: PinnedOutput.UnpinRequested
    ) -> None:
        """Handle unpin request: remove block from pinned area."""
        pass
        # await self.pinned_output.remove_pinned_block(event.block)

    async def on_terminal_output_block_activated(
        self, event: TerminalOutput.BlockActivated
    ) -> None:
        """Handle block activation: copy code to input with correct mode."""
        # Set the code in the input
        self.input.code = event.code
        # Set the correct mode
        self.input.mode = event.mode
        self.input._update_prompt()
        # Focus the input
        self.input.query_one("#code-input", InputTextArea).focus()

    async def on_terminal_output_block_execute_requested(
        self, event: TerminalOutput.BlockExecuteRequested
    ) -> None:
        """Handle block execution: execute code from a block and send output to assistant."""
        block = event.block
        code = block.get_code()
        mode = block.get_mode()
        language = "bash" if mode == "shell" else "python"

        # Show loading indicator before execution
        await block.show_loading()

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
                await self._send_execution_result_to_assistant(code, state["result"])

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
            if not self._detector_started:
                self._detector_started = True
                self._current_detector.start()
            self._chunk_buf.append(event.text)

    def _drain_chunks(self, text: str) -> None:
        """Process all accumulated chunks in the buffer at once."""
        if not self._current_detector:
            return
        # Ensure detector is started before feeding text
        if not self._detector_started:
            self._detector_started = True
            self._current_detector.start()
        try:
            with self.app.batch_update():
                self._current_detector.feed(text)
            # Schedule scroll after layout refresh so Markdown widget height is recalculated
            self.call_after_refresh(lambda: self.output.scroll_end(animate=False))
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
        attr, label = self._MARKDOWN_SETTINGS[self.input.mode]
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

    def action_toggle_auto_send_to_assistant(self) -> None:
        """Toggle auto-send mode - when enabled, all code execution results are sent to assistant."""
        self._auto_send_to_assistant = not self._auto_send_to_assistant

        # Update visual indicator on input
        if self._auto_send_to_assistant:
            self.input.add_class("in-context")
        else:
            self.input.remove_class("in-context")

    def action_clear_assistant_context(self) -> None:
        """Clear the assistant's conversation context and unhighlight all in-context blocks."""
        if self._assistant and hasattr(self._assistant, "clear_conversation"):
            self._assistant.clear_conversation()

        # Remove highlighting from all context blocks
        self._clear_all_context_highlights()
