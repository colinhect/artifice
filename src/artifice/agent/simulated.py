"""Agent - manages LLM conversation and tool calls via any-llm."""

from __future__ import annotations

import asyncio
import re
import logging
from typing import Any, Callable

from .agent import AgentResponse, ToolCall

logger = logging.getLogger(__name__)

_RESP_PROJECT_STRUCTURE = """\
Let me take a look at the project layout.

<shell>find . -type f -name "*.py" | head -20</shell>

That will give us an overview of the Python files. While we wait, here's what I'd typically expect in a well-structured project:

- `src/` — main source code
- `tests/` — test suite
- `pyproject.toml` — build configuration

Let me also check if there's a config file:

<shell>cat pyproject.toml</shell>

Once we see the output, I can give you a more detailed breakdown of the architecture.\
"""

_RESP_DATA_ANALYSIS = """\
Sure, let me write a quick analysis of that CSV data.

<python>
import pandas as pd

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

<shell>python -m pytest tests/ --co -q</shell>

Now, the main issues I notice:

### 1. Extract repeated logic into a helper

The `process_item()` function has duplicated validation. We can pull that out:

<python>
def validate_item(item: dict) -> bool:
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

<shell>python -m pytest tests/test_parser.py -x -v 2>&1 | tail -30</shell>

Now let me check what the function is actually receiving:

<python>
import json

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

_RESP_CALCULATE = """\
Let me calculate that for you.

<python>
result = 2 + 2
print(f"2 + 2 = {result}")
</python>

The answer is 4. If you need more complex calculations, just let me know!\
"""

_RESP_SYSADMIN = """\
Let me check a few things about the system state.

<shell>df -h</shell>

<shell>free -m</shell>

Those will tell us about disk and memory usage. For a more complete picture, we can also look at running processes:

<shell>ps aux --sort=-%mem | head -10</shell>

| Resource | Warning Threshold | Critical Threshold |
|----------|------------------|--------------------|
| Disk     | 80%              | 95%                |
| Memory   | 75%              | 90%                |
| CPU      | 80% sustained    | 95% sustained      |

> **Tip**: If disk usage is high, check for old log files with `du -sh /var/log/*` — they're often the culprit.

Let me know what the output shows and I'll help you diagnose any issues.\
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

_DEFAULT_SCENARIOS: list[dict] = [
    {
        "pattern": r"structure|layout|project|files",
        "response": _RESP_PROJECT_STRUCTURE,
        "thinking": "The user wants to understand the project structure. I should explore the filesystem and explain what I find.",
    },
    {
        "pattern": r"data|csv|analy|pandas",
        "response": _RESP_DATA_ANALYSIS,
        "thinking": "They want to analyze some data. I'll use pandas to load and summarize the CSV, then suggest next steps for cleaning.",
    },
    {
        "pattern": r"refactor|clean|improve|review",
        "response": _RESP_REFACTOR,
        "thinking": "Let me look at the code quality issues. I see duplicated validation logic, old-style path handling, and missing type hints. I'll prioritize by impact.",
    },
    {
        "pattern": r"bug|error|fix|debug|crash|fail",
        "response": _RESP_DEBUG,
        "thinking": "There's a bug to track down. Let me first reproduce it, then inspect the failing input to understand the root cause before proposing a fix.",
    },
    {
        "pattern": r"disk|memory|system|server|process",
        "response": _RESP_SYSADMIN,
        "thinking": "They need system diagnostics. I'll check disk, memory, and top processes to identify any resource pressure.",
    },
    {
        "pattern": r"markdown|format|demo|test",
        "response": _RESP_MARKDOWN_DEMO,
        "thinking": "Let me put together a comprehensive markdown demo that exercises all the major formatting features — headers, lists, tables, code, and blockquotes.",
    },
    {
        "pattern": r"calculat|math|add|subtract|multiply|divide",
        "response": _RESP_CALCULATE,
        "thinking": "The user wants me to perform a calculation. I'll use Python to compute the result.",
    },
]

_DEFAULT_RESPONSE = (
    "I'd be happy to help with that. Could you give me a bit more context?\n\n"
    "Here are some things I can assist with:\n"
    "- **Project exploration** — understanding codebases and file structure\n"
    "- **Data analysis** — loading, cleaning, and summarizing datasets\n"
    "- **Debugging** — tracking down errors and writing fixes\n"
    "- **Code review** — suggesting refactors and improvements\n"
    "- **System admin** — checking disk, memory, and processes\n\n"
    "Just describe what you're working on and I'll dive in."
)

_DEFAULT_THINKING = (
    "The user's request doesn't match any of my specific scenarios. "
    "I should offer some guidance on what I can help with."
)

_TOOL_TAG_RE = re.compile(r"<(python|shell)>(.*?)</(python|shell)>", re.DOTALL)


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


def _parse_tool_calls(text: str, start_id: int = 0) -> tuple[str, list[ToolCall]]:
    """Extract <python>/<shell> XML tags from text, return prose + ToolCall list."""
    tool_calls: list[ToolCall] = []
    tc_id = start_id

    def replace(m: re.Match) -> str:
        nonlocal tc_id
        tag = m.group(1)
        code = m.group(2).strip()
        name = "python" if tag == "python" else "shell"
        arg_key = "code" if name == "python" else "command"
        tool_calls.append(ToolCall(id=f"sim_{tc_id}", name=name, args={arg_key: code}))
        tc_id += 1
        return ""

    prose = _TOOL_TAG_RE.sub(replace, text)
    prose = re.sub(r"\n{3,}", "\n\n", prose).strip()
    return prose, tool_calls


class SimulatedAgent:
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
        self.system_prompt = system_prompt
        self._on_connect = on_connect
        self.response_delay = response_delay
        self.messages: list[dict] = []
        self._pending_tool_calls: list[ToolCall] = []
        self._tc_counter = 0

        self.scenarios: list[dict[str, Any]] = list(_DEFAULT_SCENARIOS)
        self.current_scenario_index = 0
        self.default_response = _DEFAULT_RESPONSE
        self.default_thinking: str | None = _DEFAULT_THINKING

    def configure_defaults(self):
        self.scenarios = list(_DEFAULT_SCENARIOS)
        self.default_response = _DEFAULT_RESPONSE
        self.default_thinking = _DEFAULT_THINKING

    def configure_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        self.scenarios = list(scenarios)
        self.current_scenario_index = 0

    def set_default_response(self, response: str) -> None:
        self.default_response = response

    def set_default_thinking(self, thinking: str | None) -> None:
        self.default_thinking = thinking

    def add_scenario(
        self, response: str, pattern: str | None = None, thinking: str | None = None
    ) -> None:
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
                return s
        sequential = [s for s in self.scenarios if not s.get("pattern")]
        if self.current_scenario_index < len(sequential):
            s = sequential[self.current_scenario_index]
            self.current_scenario_index += 1
            return s
        return None

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        if self._on_connect:
            self._on_connect("connected")
            self._on_connect = None

        if prompt.strip():
            self.messages.append({"role": "user", "content": prompt})

        last_user = prompt
        for msg in reversed(self.messages):
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

        # Stream thinking
        if thinking_text:
            await _stream_text(thinking_text, on_thinking_chunk, self.response_delay)

        # Parse tool calls from response text
        prose, tool_calls = _parse_tool_calls(response_text, start_id=self._tc_counter)
        self._tc_counter += len(tool_calls)

        # Stream prose text (without the tool call XML)
        await _stream_text(prose, on_chunk, self.response_delay)

        # Update history
        if prose:
            self.messages.append({"role": "assistant", "content": prose})
        if tool_calls:
            self._pending_tool_calls = list(tool_calls)

        return AgentResponse(
            text=prose,
            tool_calls=tool_calls,
            thinking=thinking_text,
        )

    @property
    def has_pending_tool_calls(self) -> bool:
        return len(self._pending_tool_calls) > 0

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.messages.append(
            {"role": "tool", "tool_call_id": tool_call_id, "content": content}
        )
        self._pending_tool_calls = [
            tc for tc in self._pending_tool_calls if tc.id != tool_call_id
        ]

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages = []
        self._pending_tool_calls = []

    def reset(self) -> None:
        """Clear conversation history and reset scenario index."""
        self.clear()
        self.current_scenario_index = 0
        self._tc_counter = 0

    def get_conversation_history(self) -> list[dict[str, Any]]:
        return list(self.messages)


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
            self.messages.append({"role": "user", "content": prompt})

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
            self.messages.append({"role": "assistant", "content": prose})
        if tool_calls:
            self._pending_tool_calls = list(tool_calls)

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
            self.messages.append({"role": "user", "content": prompt})
        self.messages.append({"role": "assistant", "content": response_text})

        return AgentResponse(text=response_text)
