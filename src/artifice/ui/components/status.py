"""Status indicator management for agent state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artifice.utils.text import format_tokens

if TYPE_CHECKING:
    from textual.widgets import LoadingIndicator, Static
    from artifice.core.config import ArtificeConfig


class StatusIndicatorManager:
    """Manages visual status indicators for agent state."""

    def __init__(
        self,
        loading_indicator: LoadingIndicator,
        connection_status: Static,
        agent_status: Static,
        config: ArtificeConfig,
    ):
        self._loading = loading_indicator
        self._connection = connection_status
        self._agent = agent_status
        self._config = config

    def set_active(self) -> None:
        """Update status indicators to show agent is processing."""
        self._loading.classes = "agent-active"
        self._connection.remove_class("agent-inactive")
        self._connection.add_class("agent-active")

    def set_inactive(self) -> None:
        """Update status indicators to show agent is idle."""
        self._connection.add_class("agent-inactive")
        self._connection.remove_class("agent-active")
        self._loading.classes = "agent-inactive"

    def update_agent_info(self, usage=None) -> None:
        """Update the agent status line from config and optional token usage."""
        if self._config.agents:
            agent = self._config.agents.get(self._config.agent)
            if agent:
                model = agent.get("model", "unknown")
                provider = agent.get("provider", "unknown")
                status = f"{model.lower()} ({provider.lower()})"
                if usage:
                    context_window = agent.get("context_window")
                    if context_window and usage.input_tokens:
                        pct = usage.input_tokens / context_window * 100
                        status += (
                            f"  [{pct:.0f}% of {format_tokens(context_window)} · "
                            f"{format_tokens(usage.input_tokens)}in / "
                            f"{format_tokens(usage.output_tokens)}out]"
                        )
                    else:
                        status += (
                            f"  [{format_tokens(usage.input_tokens)}in / "
                            f"{format_tokens(usage.output_tokens)}out]"
                        )
                self._agent.update(status)
                return
        self._agent.update("")
