"""Status indicator management for assistant state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .utils import format_tokens

if TYPE_CHECKING:
    from textual.widgets import LoadingIndicator, Static
    from .config import Config


class StatusIndicatorManager:
    """Manages visual status indicators for assistant state."""

    def __init__(
        self,
        loading_indicator: LoadingIndicator,
        connection_status: Static,
        assistant_status: Static,
        config: Config,
    ):
        self._loading = loading_indicator
        self._connection = connection_status
        self._assistant = assistant_status
        self._config = config

    def set_active(self) -> None:
        """Update status indicators to show assistant is processing."""
        self._loading.classes = "assistant-active"
        self._connection.remove_class("assistant-inactive")
        self._connection.add_class("assistant-active")

    def set_inactive(self) -> None:
        """Update status indicators to show assistant is idle."""
        self._connection.add_class("assistant-inactive")
        self._connection.remove_class("assistant-active")
        self._loading.classes = "assistant-inactive"

    def update_assistant_info(self, usage=None) -> None:
        """Update the assistant status line from config and optional token usage."""
        if self._config.assistants:
            assistant = self._config.assistants.get(self._config.assistant)
            if assistant:
                status = f"{assistant.get('model').lower()} ({assistant.get('provider').lower()})"
                if usage:
                    context_window = assistant.get("context_window")
                    if context_window and usage.input_tokens:
                        pct = usage.input_tokens / context_window * 100
                        status += f"  [{pct:.0f}% of {format_tokens(context_window)} · {format_tokens(usage.input_tokens)}in / {format_tokens(usage.output_tokens)}out]"
                    else:
                        status += f"  [{format_tokens(usage.input_tokens)}in / {format_tokens(usage.output_tokens)}out]"
                self._assistant.update(status)
                return
        self._assistant.update("")
