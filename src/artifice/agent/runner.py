"""Agent execution loop and tool approval.

Extracted from cli.py to be reusable across different frontends
(plain streaming, Textual markdown app, etc.).
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from artifice.agent.tools.base import execute_tool_call

if TYPE_CHECKING:
    from artifice.agent.client import Agent
    from artifice.agent.providers.base import TokenUsage
    from artifice.agent.tools.base import ToolCall

logger = logging.getLogger(__name__)


class ToolApprover:
    """Manages tool call approval decisions."""

    def __init__(self, approval_mode: str, allowlist: list[str] | None = None) -> None:
        self.approval_mode = approval_mode
        self.allowlist = allowlist or []
        self.always_allowed: set[str] = set()

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed based on approval mode and lists."""
        if self.approval_mode == "auto":
            return True
        if self.approval_mode == "deny":
            return False

        from fnmatch import fnmatch

        for pattern in self.allowlist:
            if fnmatch(tool_name, pattern):
                return True

        return tool_name in self.always_allowed

    def request_approval(self, tool_call: ToolCall) -> str:
        """Prompt user for tool call approval.

        Returns one of: "allow", "always", "deny", "abort"
        """
        print(f"\nTool Call: {tool_call.name}", file=sys.stderr)
        print(f"   Arguments: {json.dumps(tool_call.args, indent=4)}", file=sys.stderr)

        while True:
            print(
                "\nApprove this tool call? [Y]es [N]o [A]lways [C]ancel: ",
                end="",
                flush=True,
                file=sys.stderr,
            )
            try:
                response = input().strip().lower()
                if response in ("y", "yes"):
                    return "allow"
                if response in ("n", "no"):
                    return "deny"
                if response in ("a", "always"):
                    return "always"
                if response in ("c", "cancel"):
                    return "abort"
                print("Invalid response. Please enter Y, N, A, or C.", file=sys.stderr)
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled.", file=sys.stderr)
                return "abort"

    def approve_tool(self, tool_call: ToolCall) -> tuple[bool, bool]:
        """Approve or deny a tool call.

        Returns:
            tuple of (is_allowed, continue_session)
        """
        if self.is_allowed(tool_call.name):
            return True, True

        decision = self.request_approval(tool_call)

        if decision == "allow":
            return True, True
        if decision == "always":
            self.always_allowed.add(tool_call.name)
            return True, True
        if decision == "deny":
            return False, True  # deny this call but continue the session

        return False, False  # abort


def format_tool_args(tool_call: ToolCall) -> str:
    """Format tool arguments for display on one line."""
    if not tool_call.args:
        return ""
    parts = []
    for key, value in tool_call.args.items():
        if isinstance(value, str):
            if len(value) > 40:
                value = value[:37] + "..."
            value = f'"{value}"'
        elif isinstance(value, dict):
            keys = ", ".join(value.keys())
            value = "{" + keys + "}"
        elif isinstance(value, list):
            value = f"[{len(value)} items]"
        parts.append(f"{key}={value}")
    return " ".join(parts)


def format_token_usage(
    input_tokens: int, output_tokens: int, context_window: int | None = None
) -> str:
    """Format token usage for display."""
    parts = [f"in:{input_tokens}", f"out:{output_tokens}"]
    if context_window:
        used_pct = (input_tokens + output_tokens) / context_window * 100
        parts.append(f"{used_pct:.0f}%")
    return " ".join(parts)


def get_message_char_count(messages: list[dict]) -> int:
    """Calculate total character length of message content."""
    total = 0
    for msg in messages:
        if isinstance(msg.get("content"), str):
            total += len(msg["content"])
        elif isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part.get("text"), str):
                    total += len(part["text"])
    return total


@dataclass
class ToolResult:
    """Result of executing a single tool call."""

    success: bool
    message: str


async def execute_tool(
    tool_call: ToolCall,
    agent: Agent,
    tool_output: bool = False,
) -> ToolResult:
    """Execute a single tool call and add result to agent."""
    try:
        before_len = get_message_char_count(agent.messages)
        result = await execute_tool_call(tool_call)
        if result is None:
            result = f"Tool {tool_call.name} not executed (no executor)"

        agent.add_tool_result(tool_call.id, result)
        after_len = get_message_char_count(agent.messages)
        added = after_len - before_len

        if tool_output:
            print(result, file=sys.stderr)

        logger.debug("Tool %s executed successfully", tool_call.name)
        return ToolResult(success=True, message=f"+{added} chars")
    except Exception:
        logger.error("Error executing tool %s", tool_call.name, exc_info=True)
        error = f"Error executing tool {tool_call.name}"
        agent.add_tool_result(tool_call.id, error)
        return ToolResult(success=False, message="error")


async def process_tool_calls(
    tool_calls: list[ToolCall],
    agent: Agent,
    approver: ToolApprover,
    tool_output: bool = False,
    on_tool_call: Callable[[str], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> bool:
    """Process a list of tool calls with approval.

    Returns:
        True if processing should continue, False if cancelled.
    """
    if log is None:
        log = lambda msg: print(msg, end="", file=sys.stderr)  # noqa: E731

    if tool_calls:
        log("\n")
    for tool_call in tool_calls:
        is_allowed, continue_session = approver.approve_tool(tool_call)

        if not continue_session:
            log("\nOperation cancelled by user.\n")
            return False

        args_str = format_tool_args(tool_call)
        log(f"{tool_call.name}({args_str})")

        if is_allowed:
            result = await execute_tool(tool_call, agent, tool_output)
            log(f" → {result.message}\n")
            msg = result.message
        else:
            agent.add_tool_result(
                tool_call.id, f"Tool call {tool_call.name} was denied by user"
            )
            msg = "denied"
            log(f" → {msg}\n")
            logger.debug("Tool %s denied by user", tool_call.name)

        if on_tool_call is not None:
            on_tool_call(f"\n\n`{tool_call.name}({args_str})` → {msg}\n\n")

    return True


async def run_agent_loop(
    agent: Agent,
    prompt: str,
    on_chunk: Callable[[str], None],
    tool_approval: str | None = None,
    tool_allowlist: list[str] | None = None,
    tool_output: bool = False,
    on_tool_call: Callable[[str], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[str, TokenUsage]:
    """Core agent loop shared by streaming and non-streaming modes.

    Returns (final_text, total_usage).
    """
    from artifice.agent.providers.base import TokenUsage

    final_text = ""
    total_usage = TokenUsage()

    def collecting_chunk(chunk: str) -> None:
        nonlocal final_text
        final_text += chunk
        on_chunk(chunk)

    response = await agent.send(prompt, on_chunk=collecting_chunk)

    if response.usage:
        total_usage.input_tokens += response.usage.input_tokens
        total_usage.output_tokens += response.usage.output_tokens
        total_usage.total_tokens += response.usage.total_tokens

    approver = ToolApprover(tool_approval or "ask", tool_allowlist)

    while response.tool_calls:
        should_continue = await process_tool_calls(
            response.tool_calls, agent, approver, tool_output, on_tool_call, log
        )
        if not should_continue:
            return final_text, total_usage

        response = await agent.send("", on_chunk=collecting_chunk)

        if response.usage:
            total_usage.input_tokens += response.usage.input_tokens
            total_usage.output_tokens += response.usage.output_tokens
            total_usage.total_tokens += response.usage.total_tokens

    return final_text, total_usage
