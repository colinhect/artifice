"""Tool call block widget."""

from __future__ import annotations

import json

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from artifice.ui.components.blocks.input import CodeInputBlock


def _format_value(value) -> str:
    """Format a parameter value for display."""
    if isinstance(value, str):
        if len(value) > 60:
            return f'"{value[:57]}..."'
        return f'"{value}"'
    elif isinstance(value, (dict, list)):
        formatted = json.dumps(value, indent=None)
        if len(formatted) > 60:
            return formatted[:57] + "..."
        return formatted
    else:
        return str(value)


class ToolCallBlock(CodeInputBlock):
    """Block for an AI-requested tool call.

    Created directly from AgentResponse.tool_calls — bypasses the fence
    detector XML hack used previously. Displays a tool-name label above
    the syntax-highlighted code so the user can inspect and execute it.

    For tools with a direct executor (read, write, glob, web_fetch, etc.) the
    ``tool_args`` dict carries the full arguments so the executor can be
    invoked without reparsing the display text.
    """

    def __init__(
        self,
        tool_call_id: str,
        name: str,
        code: str,
        language: str,
        tool_args: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(
            code=code,
            language=language,
            show_loading=False,
            in_context=True,
            **kwargs,
        )
        self.tool_call_id = tool_call_id
        self._tool_name = name
        self.tool_args: dict = tool_args or {}
        self._label = Static(name, classes="tool-name")
        self._params_container = Vertical(classes="tool-params")

    @property
    def tool_name(self) -> str:
        """Get the tool name."""
        return self._tool_name

    def compose(self) -> ComposeResult:
        yield self._label
        if self.tool_args:
            with self._params_container:
                for key, value in self.tool_args.items():
                    param_line = Static(
                        f"  {key}: {_format_value(value)}",
                        classes="tool-param",
                    )
                    yield param_line
        with Horizontal():
            with self._status_container:
                yield self._loading_indicator
                yield self._status_icon
            yield self._code
