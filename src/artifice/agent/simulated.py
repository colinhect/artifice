"""Simulated agents for testing without API calls."""

from __future__ import annotations

import asyncio
import re
import logging
from typing import Any, Callable

from artifice.agent.client import AgentResponse
from artifice.agent.conversation import ConversationManager
from artifice.agent.tools.base import TOOLS, ToolCall

logger = logging.getLogger(__name__)

_RESP_PROJECT_STRUCTURE = """\
Let me take a look at the project layout.

<shell>command=find . -type f -name "*.py" | head -20</shell>

That will give us an overview of the Python files. While we wait, here's what I'd typically expect in a well-structured project:

- `src/` — main source code
- `tests/` — test suite
- `pyproject.toml` — build configuration

Let me also check if there's a config file:

<shell>command=cat pyproject.toml</shell>

Once we see the output, I can give you a more detailed breakdown of the architecture.\
"""

_RESP_DATA_ANALYSIS = """\
Sure, let me write a quick analysis of that CSV data.

<python>code=import pandas as pd

df = pd.read_csv("data.csv")
print(f"Shape: {df.shape}")
print(f"\\nColumns: {list(df.columns)}")
print(f"\\nFirst 5 rows:")
print(df.head())
print(f"\\nBasic statistics:")
print(df.describe())
</python>

That should give us a good starting point. If there are any **missing values** or **outliers**, we can handle those next. Common strategies include:

1. **Drop** rows with nulls (`df.dropna()`)
2. **Fill** with median/mean (`df.fillna(df.median())`)
3. **Interpolate** for time-series data

Let me know what you'd like to explore further.\
"""

_RESP_REFACTOR = """\
I see a few things we can improve here. Let me first check the current test coverage:

<shell>command=python -m pytest tests/ --co -q</shell>

Now, the main issues I notice:

### 1. Extract repeated logic into a helper

The `process_item()` function has duplicated validation. We can pull that out:

<python>code=def validate_item(item: dict) -> bool:
    \"\"\"Check that item has required fields and valid types.\"\"\"
    required = ("name", "value", "timestamp")
    if not all(k in item for k in required):
        return False
    if not isinstance(item["value"], (int, float)):
        return False
    return True
</python>

### 2. Use `pathlib` instead of `os.path`

This is more idiomatic modern Python:

```python
# Before
path = os.path.join(base_dir, "output", filename)

# After
path = Path(base_dir) / "output" / filename
```

### 3. Add type hints

The function signatures are missing type annotations, which makes it harder for editors and linters to catch bugs.

Let me know if you want me to apply these changes, or if you'd like to discuss the approach first.\
"""

_RESP_DEBUG = """\
Alright, let's track this down. First, let me reproduce the error:

<shell>command=python -m pytest tests/test_parser.py -x -v 2>&1 | tail -30</shell>

Now let me check what the function is actually receiving:

<python>code=import json

# Reproduce the failing case
test_input = {"entries": [{"id": 1, "value": None}, {"id": 2, "value": 42}]}
print(json.dumps(test_input, indent=2))

# The bug is likely here — we're not handling None values
for entry in test_input["entries"]:
    result = entry["value"] * 2  # TypeError when value is None
    print(f"Entry {entry['id']}: {result}")
</python>

As I suspected — the code crashes on `None` values. The fix is straightforward:

```python
for entry in test_input["entries"]:
    if entry["value"] is not None:
        result = entry["value"] * 2
```

But we should also think about _why_ `None` is appearing here. It could mean:
- The upstream API changed its contract
- A database migration left null values
- Input validation is missing

Want me to apply the fix and add a test case for this edge case?\
"""

_RESP_SYSADMIN = """\
Let me check the system status.

<shell>command=df -h</shell>

<shell>command=free -h</shell>

<shell>command=top -bn1 | head -15</shell>

Here's what I'm seeing:

### Disk Usage
The disk usage looks reasonable. If you're running low, consider:
- Clearing package caches (`apt clean`, `yum clean all`)
- Removing old logs in `/var/log`
- Finding large files with `du -sh /* | sort -h`

### Memory
Memory usage is within normal range. If you see high usage:
- Check for memory leaks in long-running processes
- Consider adding swap if needed

### Top Processes
The top output shows which processes are consuming the most resources. Let me know if you need me to investigate any specific process.\
"""

_RESP_GREP = """\
Let me search for that pattern in the codebase.

<grep>pattern=async def</grep>

I'll look for all async function definitions. The results will show the file paths and line numbers where matches are found.

If you need to narrow it down, I can also filter by file type:

<grep>pattern=class.*Agent
file_filter=*.py</grep>

Let me know what specific pattern you want to search for.\
"""

_RESP_REPLACE = """\
Let me make that replacement for you.

<replace>path=src/example.py
pattern=old_function
replacement=new_function
dry_run=true</replace>

I'm starting with a dry run to show you what would change. Once you confirm, I can apply the actual replacement:

<replace>path=src/example.py
pattern=old_function
replacement=new_function
dry_run=false</replace>

The key options for replace are:
- `dry_run=true` — preview changes without writing
- `dry_run=false` — apply the changes
- `case_sensitive=false` — case-insensitive matching

Would you like me to proceed with the replacement?\
"""

_RESP_CALCULATE = """\
Let me calculate that for you.

<python>code=result = 2 + 2
print(f"2 + 2 = {result}")
</python>

The answer is 4. If you need more complex calculations, just let me know!\
"""

_RESP_MARKDOWN_DEMO = """\
Here's a showcase of different formatting options:

## Text Formatting

You can use **bold**, *italic*, ~~strikethrough~~, and `inline code`. For emphasis, combine them: ***bold italic***.

## Lists

Ordered:
1. First item
2. Second item
3. Third item

Unordered:
- Alpha
- Bravo
  - Nested item
  - Another nested
- Charlie

## Code Block

```python
def fibonacci(n: int) -> list[int]:
    \"\"\"Generate the first n Fibonacci numbers.\"\"\"
    if n <= 0:
        return []
    fib = [0, 1]
    for _ in range(2, n):
        fib.append(fib[-1] + fib[-2])
    return fib[:n]

print(fibonacci(10))
```

## Blockquote

> "Any fool can write code that a computer can understand. Good programmers write code that humans can understand."
> — Martin Fowler

## Table

| Language   | Typing     | Use Case          |
|------------|------------|-------------------|
| Python     | Dynamic    | Data science, web |
| Rust       | Static     | Systems, CLI      |
| TypeScript | Static     | Web frontends     |
| Go         | Static     | Cloud, networking |

That covers the basics. Markdown is expressive enough for most documentation needs without being overwhelming.\
"""

_RESP_READ = """\
Let me read the file and see what we're working with.

<read>path=src/main.py</read>

I'll take a look at the contents and walk you through the key parts once it loads.\
"""

_RESP_WRITE = """\
I'll create that file for you now.

<write>path=output/results.txt
content=# Analysis Results

Summary of findings:
- Total records processed: 1,247
- Valid entries: 1,198 (96.1%)
- Anomalies detected: 49 (3.9%)
</write>

The file has been written. Let me verify it looks correct:

<read>path=output/results.txt</read>

Everything looks good. Let me know if you need any changes.\
"""

_RESP_GLOB = """\
Let me find those files for you.

<glob>pattern=**/*.py</glob>

That will locate all Python files in the project. If you need to narrow it down, I can also search for specific patterns:

<glob>pattern=**/test_*.py</glob>

Once we see the results, I can help you navigate to the right file.\
"""

_RESP_WEB_SEARCH = """\
Let me search for that information.

<web_search>query=python asyncio best practices 2025</web_search>

I'll summarize the key findings once the results come back. In the meantime, here are some general tips:

- Use `asyncio.TaskGroup` for structured concurrency
- Prefer `async with` for resource management
- Avoid blocking calls in async functions

Let me know if you want me to dig deeper into any specific topic.\
"""

_RESP_WEB_FETCH = """\
Let me grab that page for you.

<web_fetch>url=https://docs.python.org/3/library/asyncio.html</web_fetch>

I'll pull out the most relevant sections once the content loads. The asyncio documentation covers:

1. **High-level API** — tasks, streams, synchronization
2. **Low-level API** — event loops, transports, protocols
3. **Policies** — customizing the event loop

Want me to focus on any particular section?\
"""

_DEFAULT_SCENARIOS: list[dict] = [
    {
        "pattern": r"structure|layout|project|files",
        "response": _RESP_PROJECT_STRUCTURE,
        "thinking": (
            "The user wants to understand the project structure. "
            "I should explore the filesystem and explain what I find."
        ),
    },
    {
        "pattern": r"data|csv|analy|pandas",
        "response": _RESP_DATA_ANALYSIS,
        "thinking": (
            "They want to analyze some data. I'll use pandas to load and summarize "
            "the CSV, then suggest next steps for cleaning."
        ),
    },
    {
        "pattern": r"refactor|clean|improve|review",
        "response": _RESP_REFACTOR,
        "thinking": (
            "Let me look at the code quality issues. I see duplicated validation logic, "
            "old-style path handling, and missing type hints. I'll prioritize by impact."
        ),
    },
    {
        "pattern": r"bug|error|fix|debug|crash|fail",
        "response": _RESP_DEBUG,
        "thinking": (
            "There's a bug to track down. Let me first reproduce it, then inspect "
            "the failing input to understand the root cause before proposing a fix."
        ),
    },
    {
        "pattern": r"disk|memory|system|server|process",
        "response": _RESP_SYSADMIN,
        "thinking": (
            "They need system diagnostics. I'll check disk, memory, "
            "and top processes to identify any resource pressure."
        ),
    },
    {
        "pattern": r"markdown|format|demo|test",
        "response": _RESP_MARKDOWN_DEMO,
        "thinking": (
            "Let me put together a comprehensive markdown demo that exercises "
            "all the major formatting features — headers, lists, tables, code, and blockquotes."
        ),
    },
    {
        "pattern": r"calculat|math|add|subtract|multiply|divide",
        "response": _RESP_CALCULATE,
        "thinking": (
            "The user wants me to perform a calculation. I'll use Python to compute the result."
        ),
    },
    {
        "pattern": r"read|open|view|show|cat|contents",
        "response": _RESP_READ,
        "thinking": (
            "The user wants to read a file. I'll use the read tool to fetch its contents."
        ),
    },
    {
        "pattern": r"write|create|save|output|generate file",
        "response": _RESP_WRITE,
        "thinking": (
            "The user wants to create or write a file. I'll use write to create it, "
            "then verify with read."
        ),
    },
    {
        "pattern": r"find|search file|locate|glob|where",
        "response": _RESP_GLOB,
        "thinking": (
            "The user wants to find files in the project. I'll use glob "
            "with glob patterns to locate them."
        ),
    },
    {
        "pattern": r"search|google|look up|research|web search",
        "response": _RESP_WEB_SEARCH,
        "thinking": (
            "The user wants to search the web for information. "
            "I'll use web_search to find relevant results."
        ),
    },
    {
        "pattern": r"fetch|url|http|webpage|download|web page",
        "response": _RESP_WEB_FETCH,
        "thinking": (
            "The user wants to fetch content from a URL. "
            "I'll use web_fetch to retrieve and summarize the page."
        ),
    },
    {
        "pattern": r"grep|search.*pattern|search.*code|find.*pattern|regex",
        "response": _RESP_GREP,
        "thinking": (
            "The user wants to search for a pattern in the codebase. "
            "I'll use grep to find matching lines with file and line number."
        ),
    },
    {
        "pattern": r"replace|substitute|rename.*variable|change.*to",
        "response": _RESP_REPLACE,
        "thinking": (
            "The user wants to replace text in a file. I'll use the replace tool "
            "with a dry run first to preview the changes."
        ),
    },
]

_DEFAULT_RESPONSE = (
    "I'd be happy to help with that. Could you give me a bit more context?\n\n"
    "Here are some things I can assist with:\n"
    "- **Project exploration** — understanding codebases and file structure\n"
    "- **Data analysis** — loading, cleaning, and summarizing datasets\n"
    "- **Debugging** — tracking down errors and writing fixes\n"
    "- **Code review** — suggesting refactors and improvements\n"
    "- **System admin** — checking disk, memory, and system info\n"
    "- **File operations** — reading, writing, and searching for files\n"
    "- **Code search** — grep for patterns across files\n"
    "- **Text replacement** — find and replace in files\n"
    "- **Web research** — searching the web and fetching page content\n\n"
    "Just describe what you're working on and I'll dive in."
)

_DEFAULT_THINKING = (
    "The user's request doesn't match any of my specific scenarios. "
    "I should offer some guidance on what I can help with."
)


def _build_tool_tag_re() -> re.Pattern:
    """Build regex matching XML tags for all registered tool names."""
    names = "|".join(re.escape(name) for name in TOOLS)
    return re.compile(rf"<({names})>(.*?)</({names})>", re.DOTALL)


_TOOL_TAG_RE = _build_tool_tag_re()


async def _stream_text(
    text: str,
    on_chunk: Callable | None,
    delay: float,
) -> None:
    """Stream text character by character with optional delay."""
    if on_chunk and delay > 0:
        for ch in text:
            on_chunk(ch)
            await asyncio.sleep(delay)
    elif on_chunk:
        if text:
            on_chunk(text)
        await asyncio.sleep(0)
    else:
        await asyncio.sleep(0)


def _parse_tag_args(name: str, content: str) -> dict:
    """Parse ``key=value`` tag content into tool call args.

    All tool tags use the format ``<tool>key=value</tool>``.  For multi-arg
    tools the content has one ``key=value`` per line; the last key's value
    spans all remaining lines (allowing multi-line content like file bodies
    or code).

    Only identifiers that match a known parameter name for the tool are
    treated as keys — so ``result = 2 + 2`` inside Python code won't start
    a new arg because ``result`` isn't a parameter of the ``python`` tool.

    Array-typed parameters (detected from the tool schema) are split on
    commas so ``categories=os,disk`` becomes ``["os", "disk"]``.
    """
    tool_def = TOOLS.get(name)
    param_names = set(tool_def.parameters.get("properties", {})) if tool_def else set()

    args: dict = {}
    lines = content.split("\n")
    current_key: str | None = None
    current_lines: list[str] = []
    for line in lines:
        eq_pos = line.find("=")
        candidate = line[:eq_pos] if eq_pos > 0 else ""
        if candidate and candidate.isidentifier() and candidate in param_names:
            if current_key is not None:
                args[current_key] = "\n".join(current_lines)
            current_key = candidate
            current_lines = [line[eq_pos + 1 :]]
        elif current_key is not None:
            current_lines.append(line)
    if current_key is not None:
        args[current_key] = "\n".join(current_lines)

    # Convert typed parameters from strings
    if tool_def and args:
        schema_props = tool_def.parameters.get("properties", {})
        for key, val in args.items():
            prop = schema_props.get(key, {})
            prop_type = prop.get("type")
            if prop_type == "array" and isinstance(val, str):
                args[key] = [v.strip() for v in val.split(",")]
            elif prop_type == "boolean" and isinstance(val, str):
                args[key] = val.lower() in ("true", "1", "yes")
            elif prop_type == "integer" and isinstance(val, str):
                try:
                    args[key] = int(val)
                except ValueError:
                    pass

    return args


def _parse_tool_calls(text: str, start_id: int = 0) -> tuple[str, list[ToolCall]]:
    """Extract tool XML tags from text, return prose + ToolCall list."""
    tool_calls: list[ToolCall] = []
    tc_id = start_id

    def replace(m: re.Match) -> str:
        nonlocal tc_id
        name = m.group(1)
        content = m.group(2).strip()
        args = _parse_tag_args(name, content)
        tool_calls.append(ToolCall(id=f"sim_{tc_id}", name=name, args=args))
        tc_id += 1
        return ""

    prose = _TOOL_TAG_RE.sub(replace, text)
    prose = re.sub(r"\n{3,}", "\n\n", prose).strip()
    return prose, tool_calls


class SimulatedAgent(ConversationManager):
    """Test double for Agent — no API calls, configurable scripted responses.

    Scenarios are matched against the last user message. Each scenario is a
    dict with optional 'pattern' (regex), required 'response', and optional
    'thinking'. Scenarios without a pattern are used sequentially.

    Tool calls embedded as <python>...</python> or <shell>...</shell> in
    response text are extracted and returned as ToolCall objects so the
    terminal can create ToolCallBlocks directly (same as real Agent).
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
        response_delay: float = 0.001,
    ):
        super().__init__()
        self.system_prompt = system_prompt
        self._on_connect = on_connect
        self.response_delay = response_delay
        self._tc_counter = 0

        self.scenarios: list[dict[str, Any]] = list(_DEFAULT_SCENARIOS)
        self.current_scenario_index = 0
        self.default_response = _DEFAULT_RESPONSE
        self.default_thinking: str | None = _DEFAULT_THINKING

    def configure_defaults(self):
        """Reset to default scenarios and responses."""
        self.scenarios = list(_DEFAULT_SCENARIOS)
        self.default_response = _DEFAULT_RESPONSE
        self.default_thinking = _DEFAULT_THINKING

    def configure_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        """Replace scenarios with a custom list."""
        self.scenarios = list(scenarios)
        self.current_scenario_index = 0

    def set_default_response(self, response: str) -> None:
        """Set the default response for unmatched prompts."""
        self.default_response = response

    def set_default_thinking(self, thinking: str | None) -> None:
        """Set the default thinking text for unmatched prompts."""
        self.default_thinking = thinking

    def add_scenario(
        self, response: str, pattern: str | None = None, thinking: str | None = None
    ) -> None:
        """Add a scenario with optional pattern matching and thinking text."""
        scenario: dict[str, Any] = {"response": response}
        if pattern is not None:
            scenario["pattern"] = pattern
        if thinking is not None:
            scenario["thinking"] = thinking
        self.scenarios.append(scenario)

    def _find_scenario(self, prompt: str) -> dict[str, Any] | None:
        for s in self.scenarios:
            pattern = s.get("pattern")
            if pattern and re.search(pattern, prompt, re.IGNORECASE):
                logger.debug("Matched scenario with pattern: %s", pattern)
                return s
        sequential = [s for s in self.scenarios if not s.get("pattern")]
        if self.current_scenario_index < len(sequential):
            s = sequential[self.current_scenario_index]
            self.current_scenario_index += 1
            logger.debug("Using sequential scenario %d", self.current_scenario_index)
            return s
        logger.debug("No matching scenario found")
        return None

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        """Send a prompt and return a simulated response."""
        logger.debug("SimulatedAgent.send: %s", prompt[:100] if prompt else "(empty)")
        if self._on_connect:
            self._on_connect("connected")
            self._on_connect = None

        if prompt.strip():
            self.add_user_message(prompt)

        last_user = prompt
        for msg in reversed(self._messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        scenario = self._find_scenario(last_user)
        if scenario:
            response_text = scenario["response"]
            thinking_text = scenario.get("thinking")
        else:
            response_text = self.default_response
            thinking_text = self.default_thinking

        if thinking_text:
            await _stream_text(thinking_text, on_thinking_chunk, self.response_delay)

        prose, tool_calls = _parse_tool_calls(response_text, start_id=self._tc_counter)
        self._tc_counter += len(tool_calls)

        await _stream_text(prose, on_chunk, self.response_delay)

        if prose:
            self.add_assistant_message(prose)
        if tool_calls:
            self.set_pending_tool_calls(tool_calls)
            logger.debug("SimulatedAgent returning %d tool calls", len(tool_calls))

        return AgentResponse(
            text=prose,
            tool_calls=tool_calls,
            thinking=thinking_text,
        )

    def reset(self) -> None:
        """Clear conversation history and reset scenario index."""
        self.clear()
        self.current_scenario_index = 0
        self._tc_counter = 0

    def get_conversation_history(self) -> list[dict[str, Any]]:
        """Return a copy of the conversation history."""
        return self.get_messages()


class ScriptedAgent(SimulatedAgent):
    """SimulatedAgent that follows a fixed script regardless of input."""

    def __init__(
        self,
        script: list[dict[str, Any]],
        system_prompt: str | None = None,
        response_delay: float = 0.05,
    ):
        super().__init__(system_prompt=system_prompt, response_delay=response_delay)
        self.configure_scenarios(script)

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        if prompt.strip():
            self.add_user_message(prompt)

        if self.current_scenario_index < len(self.scenarios):
            scenario = self.scenarios[self.current_scenario_index]
            self.current_scenario_index += 1
        else:
            scenario = {"response": "[Script completed]"}

        response_text = scenario["response"]
        thinking_text = scenario.get("thinking")

        if thinking_text:
            await _stream_text(thinking_text, on_thinking_chunk, self.response_delay)

        prose, tool_calls = _parse_tool_calls(response_text, start_id=self._tc_counter)
        self._tc_counter += len(tool_calls)

        await _stream_text(prose, on_chunk, self.response_delay)

        if prose:
            self.add_assistant_message(prose)
        if tool_calls:
            self.set_pending_tool_calls(tool_calls)

        return AgentResponse(
            text=prose,
            tool_calls=tool_calls,
            thinking=thinking_text,
        )


class EchoAgent(SimulatedAgent):
    """SimulatedAgent that echoes back user input with an optional prefix."""

    def __init__(
        self,
        prefix: str = "You said: ",
        system_prompt: str | None = None,
        thinking_text: str | None = None,
    ):
        super().__init__(system_prompt=system_prompt, response_delay=0.05)
        self.prefix = prefix
        self.echo_thinking = thinking_text

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        response_text = f"{self.prefix}{prompt}"

        if self.echo_thinking:
            await _stream_text(
                self.echo_thinking, on_thinking_chunk, self.response_delay
            )

        await _stream_text(response_text, on_chunk, self.response_delay)

        if prompt.strip():
            self.add_user_message(prompt)
        self.add_assistant_message(response_text)

        return AgentResponse(text=response_text)
