"""Input block widgets."""

from __future__ import annotations

from textual import highlight
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, LoadingIndicator

from artifice.execution.base import ExecutionResult
from artifice.ui.components.blocks.base import BaseBlock
from artifice.ui.components.blocks.mixins import StatusMixin


class CodeInputBlock(BaseBlock, StatusMixin):
    """Block for displaying code input with syntax highlighting and status indicator."""

    def __init__(
        self,
        code: str,
        language: str,
        show_loading: bool = True,
        in_context=False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._loading_indicator = LoadingIndicator(classes="status-indicator")
        if show_loading:
            self._loading_indicator.styles.display = "block"
        else:
            self._loading_indicator.styles.display = "none"
        self._streaming = show_loading
        self._language = language
        self._status_icon = Static("", classes="status-indicator")
        self._status_icon.add_class("status-unexecuted")
        self._original_code = code
        self._code = Static(
            highlight.highlight(code, language=language), classes="code"
        )
        self._status_container = Horizontal(classes="status-indicator")
        if in_context:
            self.add_class("in-context")

    def compose(self) -> ComposeResult:
        with Horizontal():
            with self._status_container:
                yield self._loading_indicator
                yield self._status_icon
            yield self._code

    def update_status(self, result: ExecutionResult) -> None:
        """Update the status indicator based on execution result."""
        self._loading_indicator.styles.display = "none"
        self.update_status_icon(result.status)

    def show_loading(self) -> None:
        """Show the loading indicator (for re-execution)."""
        self._loading_indicator.styles.display = "block"
        self.clear_status_icon()

    def finish_streaming(self) -> None:
        """End streaming: show status indicator (code already highlighted)."""
        self._loading_indicator.styles.display = "none"
        self._streaming = False

    def update_code(self, code: str) -> None:
        """Update the displayed code with syntax highlighting (used during streaming)."""
        self._original_code = code
        self._code.update(highlight.highlight(code.strip(), language=self._language))

    def get_code(self) -> str:
        """Get the original code."""
        return self._original_code

    def get_mode(self) -> str:
        """Get the mode for this code block (python or shell)."""
        return "shell" if self._language == "bash" else "python"


class AgentInputBlock(BaseBlock):
    """Block for displaying user input prompts."""

    def __init__(self, prompt: str, in_context: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status_indicator = Static(">", classes="status-indicator status-success")
        self._prompt = Static(prompt, classes="prompt")
        self._original_prompt = prompt
        if in_context:
            self.add_class("in-context")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield self._status_indicator
            with Vertical():
                yield self._prompt

    def get_prompt(self) -> str:
        """Get the original prompt."""
        return self._original_prompt

    def get_mode(self) -> str:
        """Get the mode for this block (ai)."""
        return "ai"
