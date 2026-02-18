"""Coordinates code execution with output display and context tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from textual.widget import Widget

from .execution import (
    ExecutionResult,
    CodeExecutor,
    ShellExecutor,
    TmuxShellExecutor,
)
from .terminal.output import (
    CodeInputBlock,
    WidgetOutputBlock,
    BaseBlock,
)
from .output_callbacks import OutputCallbackHandler

if TYPE_CHECKING:
    from .config import ArtificeConfig
    from .terminal.output import TerminalOutput


class ExecutionCoordinator:
    """Manages code execution, output callbacks, and markdown/code-block settings.

    Extracts the execution logic that was previously inline in ArtificeTerminal.
    """

    def __init__(
        self,
        config: ArtificeConfig,
        output: TerminalOutput,
        schedule_fn: Callable,
        context_tracker: Callable[[BaseBlock], None] | None = None,
    ) -> None:
        self._config = config
        self._output = output
        self._schedule_fn = schedule_fn
        self._context_tracker = context_tracker

        # Create executors
        self._executor = CodeExecutor()
        if config.tmux_target:
            prompt_pattern = config.tmux_prompt_pattern or r"^\$ "
            self._shell_executor: ShellExecutor | TmuxShellExecutor = TmuxShellExecutor(
                config.tmux_target,
                prompt_pattern=prompt_pattern,
                check_exit_code=config.tmux_echo_exit_code,
            )
        else:
            self._shell_executor = ShellExecutor()

        # Set shell init script from config (only applicable to ShellExecutor)
        if config.shell_init_script and isinstance(self._shell_executor, ShellExecutor):
            self._shell_executor.init_script = config.shell_init_script

        # Markdown settings
        self.python_markdown_enabled: bool = config.python_markdown
        self.assistant_markdown_enabled: bool = config.assistant_markdown
        self.shell_markdown_enabled: bool = config.shell_markdown

    def reset(self) -> None:
        """Reset the Python executor state."""
        self._executor.reset()

    def _make_output_callbacks(
        self,
        markdown_enabled: bool,
        in_context: bool = False,
        use_code_block: bool = True,
    ):
        """Create on_output/on_error/flush callbacks that lazily create a CodeOutputBlock.

        Returns (on_output, on_error, flush).
        """
        handler = OutputCallbackHandler(
            output=self._output,
            markdown_enabled=markdown_enabled,
            in_context=in_context,
            schedule_fn=self._schedule_fn,
            use_code_block=use_code_block,
        )

        # Track output block in context if needed
        if in_context and self._context_tracker:
            original_ensure = handler._ensure_block
            tracker = self._context_tracker

            def ensure_and_track():
                block = original_ensure()
                if block is not None:
                    tracker(block)
                return block

            handler._ensure_block = ensure_and_track

        return handler.on_output, handler.on_error, handler.flush

    async def execute(
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
            self._output.append_block(code_input_block)

        # Determine markdown and code block settings
        if language == "bash":
            markdown_enabled = self.shell_markdown_enabled
            use_code_block = (
                self._config.tmux_output_code_block
                if isinstance(self._shell_executor, TmuxShellExecutor)
                else self._config.shell_output_code_block
            )
        else:
            markdown_enabled = self.python_markdown_enabled
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
            self._output.append_block(widget_block)

        return result
