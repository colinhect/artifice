"""Conversation management mixin for agents."""

from __future__ import annotations

from artifice.agent.tools.base import ToolCall


class ConversationManager:
    """Mixin for managing conversation history and pending tool calls.

    Provides shared functionality between Agent and SimulatedAgent for
    managing message history, pending tool calls, and common operations.
    """

    def __init__(self) -> None:
        self._messages: list[dict] = []
        self._pending_tool_calls: list[ToolCall] = []

    @property
    def messages(self) -> list[dict]:
        """Access the conversation history."""
        return self._messages

    @messages.setter
    def messages(self, value: list[dict]) -> None:
        """Set the conversation history."""
        self._messages = value

    @property
    def has_pending_tool_calls(self) -> bool:
        """Check if there are pending tool calls to execute."""
        return len(self._pending_tool_calls) > 0

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Add a tool execution result to conversation history."""
        self._messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
        )
        self._pending_tool_calls = [
            tc for tc in self._pending_tool_calls if tc.id != tool_call_id
        ]

    def clear(self) -> None:
        """Clear conversation history."""
        self._messages = []
        self._pending_tool_calls = []

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation."""
        self._messages.append({"role": "user", "content": content})

    def add_assistant_message(
        self, content: str | None, tool_calls: list[dict] | None = None
    ) -> None:
        """Add an assistant message to the conversation."""
        msg: dict = {"role": "assistant"}
        if content:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._messages.append(msg)

    def get_messages(self) -> list[dict]:
        """Return a copy of the conversation history."""
        return list(self._messages)

    def pop_last_user_message(self) -> bool:
        """Remove the last user message if it exists. Returns True if removed."""
        if self._messages and self._messages[-1].get("role") == "user":
            self._messages.pop()
            return True
        return False

    def set_pending_tool_calls(self, tool_calls: list[ToolCall]) -> None:
        """Set the pending tool calls."""
        self._pending_tool_calls = list(tool_calls)

    def clear_pending_tool_calls(self) -> None:
        """Clear pending tool calls."""
        self._pending_tool_calls.clear()
