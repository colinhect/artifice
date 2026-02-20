"""Tool definitions and registry for agent tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


# Type alias for tool executor functions: async (args) -> result string
ToolExecutor = Callable[[dict[str, Any]], Awaitable[str]]


@dataclass
class ToolCall:
    """A tool call requested by the model."""

    id: str
    name: str
    args: dict

    @property
    def display_text(self) -> str:
        """Return the primary text to display (code, path, query, etc.)."""
        tool_def = TOOLS.get(self.name)
        if tool_def:
            return self.args.get(tool_def.display_arg, str(self.args))
        return str(self.args)

    @property
    def display_language(self) -> str:
        """Return syntax highlighting language."""
        tool_def = TOOLS.get(self.name)
        return tool_def.display_language if tool_def else "text"


@dataclass
class ToolDef:
    """Self-contained definition of a tool available to the agent.

    Tools with an ``executor`` are invoked directly when the user approves
    execution.  Tools without one (python, shell) go through the existing
    code-execution path in the terminal widget.
    """

    name: str
    description: str
    parameters: dict
    display_language: str
    display_arg: str
    executor: ToolExecutor | None = field(default=None, repr=False)

    def to_schema(self) -> dict:
        """Serialize to OpenAI function-call format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


TOOLS: dict[str, ToolDef] = {}


def _register(tool: ToolDef) -> ToolDef:
    TOOLS[tool.name] = tool
    return tool


async def execute_tool_call(tool_call: ToolCall) -> str | None:
    """Execute a tool call if it has a registered executor.

    Returns the result string, or None if the tool has no executor
    (meaning it should be handled by the code-execution path).
    """
    tool_def = TOOLS.get(tool_call.name)
    if tool_def and tool_def.executor:
        return await tool_def.executor(tool_call.args)
    return None


# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------

# --- Code-execution tools (no executor — handled by terminal widget) ---

_register(
    ToolDef(
        name="python",
        description="Execute Python code in the user's REPL session.",
        parameters={
            "type": "object",
            "required": ["code"],
            "properties": {"code": {"type": "string"}},
        },
        display_language="python",
        display_arg="code",
    )
)

_register(
    ToolDef(
        name="shell",
        description="Execute a shell command in the user's terminal session.",
        parameters={
            "type": "object",
            "required": ["command"],
            "properties": {"command": {"type": "string"}},
        },
        display_language="bash",
        display_arg="command",
    )
)

# --- Tools with direct executors ---

# Imports are deferred to avoid circular imports and keep this module fast
# to import.  The executor functions live in tool_executors.py.
from artifice.agent.tools.executors import (  # noqa pyright:ignore
    execute_file_search,
    execute_read_file,
    execute_system_info,
    execute_web_fetch,
    execute_web_search,
    execute_write_file,
)

_register(
    ToolDef(
        name="read_file",
        description="Read the contents of a file.",
        parameters={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-based).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read.",
                },
            },
        },
        display_language="text",
        display_arg="path",
        executor=execute_read_file,
    )
)

_register(
    ToolDef(
        name="write_file",
        description="Write or create a file with the given content.",
        parameters={
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path.",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file.",
                },
            },
        },
        display_language="text",
        display_arg="path",
        executor=execute_write_file,
    )
)

_register(
    ToolDef(
        name="file_search",
        description="Search for files matching a glob pattern.",
        parameters={
            "type": "object",
            "required": ["pattern"],
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (supports ** for recursive).",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: current directory).",
                },
            },
        },
        display_language="text",
        display_arg="pattern",
        executor=execute_file_search,
    )
)

_register(
    ToolDef(
        name="web_search",
        description="Search the web for information.",
        parameters={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "Search query."},
            },
        },
        display_language="text",
        display_arg="query",
        executor=execute_web_search,
    )
)

_register(
    ToolDef(
        name="web_fetch",
        description="Fetch the contents of a URL.",
        parameters={
            "type": "object",
            "required": ["url"],
            "properties": {
                "url": {"type": "string", "description": "URL to fetch."},
            },
        },
        display_language="text",
        display_arg="url",
        executor=execute_web_fetch,
    )
)

_register(
    ToolDef(
        name="system_info",
        description="Get system information.",
        parameters={
            "type": "object",
            "required": ["categories"],
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["os", "env", "cwd", "disk"]},
                    "description": "Categories of system info to retrieve.",
                },
            },
        },
        display_language="text",
        display_arg="categories",
        executor=execute_system_info,
    )
)


def get_all_schemas() -> list[dict]:
    """Return OpenAI function-call schemas for all registered tools."""
    return [tool.to_schema() for tool in TOOLS.values()]


def get_schemas_for(patterns: list[str]) -> list[dict]:
    """Return schemas for tools whose names match any of the given patterns.

    Supports fnmatch-style wildcards (e.g. ``"*"``, ``"web_*"``).
    """
    from fnmatch import fnmatch

    return [
        tool.to_schema()
        for tool in TOOLS.values()
        if any(fnmatch(tool.name, pat) for pat in patterns)
    ]
