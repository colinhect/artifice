"""Mixins for block widgets."""

from __future__ import annotations

from textual.widgets import Static

from artifice.execution.base import ExecutionStatus


class StatusMixin:
    """Mixin for blocks that display execution status via an icon."""

    _status_icon: Static

    def update_status_icon(self, status: ExecutionStatus) -> None:
        """Update the status indicator based on execution result."""
        if status == ExecutionStatus.SUCCESS:
            self._status_icon.update("\u2714")
            self._status_icon.remove_class("status-error")
            self._status_icon.add_class("status-success")
        elif status == ExecutionStatus.ERROR:
            self._status_icon.update("\u2716")
            self._status_icon.remove_class("status-success")
            self._status_icon.add_class("status-error")

    def clear_status_icon(self) -> None:
        """Clear status styling and reset icon."""
        self._status_icon.remove_class("status-success")
        self._status_icon.remove_class("status-error")
        self._status_icon.update("")
