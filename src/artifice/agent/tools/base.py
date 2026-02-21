"""Tool definitions and registry for agent tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from artifice.agent.tools.executors import (
    execute_glob,
    execute_grep,
    execute_read,
    execute_replace,
    execute_web_fetch,
    execute_web_search,
    execute_write,
)


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
            return str(self.args.get(tool_def.display_arg, self.args))
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
    """Register a tool in the global TOOLS dict. Internal use only."""
    TOOLS[tool.name] = tool
    return tool


def tool(
    name: str,
    description: str,
    params: dict,
    display_arg: str | None = None,
    language: str = "text",
    executor: ToolExecutor | None = None,
    required: list[str] | None = None,
) -> ToolDef:
    """Simplified tool registration helper.

    Args:
        name: Tool name (e.g., "read").
        description: Human-readable description.
        params: Parameter properties dict ({"param_name": {"type": "string", ...}}).
        display_arg: Parameter to display in the UI (defaults to first param).
        language: Syntax highlighting language for display.
        executor: Optional async executor function.
        required: List of required parameter names (defaults to all params).

    Returns:
        The registered ToolDef.
    """
    if display_arg is None:
        display_arg = list(params.keys())[0] if params else ""
    if required is None:
        required = list(params.keys())

    parameters = {
        "type": "object",
        "required": required,
        "properties": params,
    }

    return _register(
        ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            display_language=language,
            display_arg=display_arg,
            executor=executor,
        )
    )


async def execute_tool_call(tool_call: ToolCall) -> str | None:
    """Execute a tool call if it has a registered executor.

    Returns the result string, or None if the tool has no executor
    (meaning it should be handled by the code-execution path).
    """
    tool_def = TOOLS.get(tool_call.name)
    if tool_def and tool_def.executor:
        return await tool_def.executor(tool_call.args)
    return None


tool(
    name="python",
    description="Execute Python code in the user's REPL session.",
    params={"code": {"type": "string"}},
    language="python",
)

tool(
    name="shell",
    description="Execute a shell command in the user's terminal session.",
    params={"command": {"type": "string"}},
    language="bash",
)

tool(
    name="read",
    description="Read the contents of a file.",
    params={
        "path": {"type": "string", "description": "Absolute or relative file path."},
        "offset": {
            "type": "integer",
            "description": "Line number to start reading from (0-based).",
        },
        "limit": {"type": "integer", "description": "Maximum number of lines to read."},
    },
    required=["path"],
    executor=execute_read,
)

tool(
    name="write",
    description="Write or create a file with the given content.",
    params={
        "path": {"type": "string", "description": "Absolute or relative file path."},
        "content": {"type": "string", "description": "Content to write to the file."},
    },
    executor=execute_write,
)

tool(
    name="glob",
    description="Search for files matching a glob pattern.",
    params={
        "pattern": {
            "type": "string",
            "description": "Glob pattern (supports ** for recursive).",
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (default: current directory).",
        },
    },
    required=["pattern"],
    executor=execute_glob,
)

tool(
    name="grep",
    description="Search for regex patterns in files.",
    params={
        "pattern": {
            "type": "string",
            "description": "Regular expression pattern to search for.",
        },
        "path": {
            "type": "string",
            "description": "Directory to search in (default: current directory).",
        },
        "file_filter": {
            "type": "string",
            "description": "Glob pattern to filter files (default: *).",
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "Whether the search is case sensitive (default: true).",
        },
        "context_before": {
            "type": "integer",
            "description": "Number of lines of context before each match (default: 0).",
        },
        "context_after": {
            "type": "integer",
            "description": "Number of lines of context after each match (default: 0).",
        },
    },
    required=["pattern"],
    executor=execute_grep,
)

tool(
    name="replace",
    description="Replace string occurrences in files with regex support.",
    params={
        "path": {"type": "string", "description": "Absolute or relative file path."},
        "pattern": {
            "type": "string",
            "description": "Regular expression pattern to match.",
        },
        "replacement": {
            "type": "string",
            "description": "Replacement string (supports backreferences).",
        },
        "case_sensitive": {
            "type": "boolean",
            "description": "Whether the search is case sensitive (default: true).",
        },
        "dry_run": {
            "type": "boolean",
            "description": "If true, only show what would be changed without writing (default: true).",
        },
    },
    required=["path", "pattern", "replacement"],
    executor=execute_replace,
)

tool(
    name="web_search",
    description="Search the web for information.",
    params={"query": {"type": "string", "description": "Search query."}},
    executor=execute_web_search,
)

tool(
    name="web_fetch",
    description="Fetch the contents of a URL.",
    params={"url": {"type": "string", "description": "URL to fetch."}},
    executor=execute_web_fetch,
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
