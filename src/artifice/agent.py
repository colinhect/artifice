"""Agent - manages LLM conversation and tool calls via any-llm."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from any_llm.types.completion import ChatCompletionChunk
    from typing import AsyncIterator

from .config import ArtificeConfig

logger = logging.getLogger(__name__)

_PYTHON_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "python",
        "description": "Execute Python code in the user's REPL session.",
        "parameters": {
            "type": "object",
            "required": ["code"],
            "properties": {"code": {"type": "string"}},
        },
    },
}

_SHELL_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": "Execute a shell command in the user's terminal session.",
        "parameters": {
            "type": "object",
            "required": ["command"],
            "properties": {"command": {"type": "string"}},
        },
    },
}


@dataclass
class ToolCall:
    """A tool call requested by the model."""

    id: str
    name: str  # "python" or "shell"
    args: dict  # {"code": "..."} or {"command": "..."}

    @property
    def code(self) -> str:
        """Return the code/command string."""
        return self.args.get("code") or self.args.get("command", "")

    @property
    def language(self) -> str:
        """Return 'python' or 'bash'."""
        return "bash" if self.name == "shell" else "python"


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class AgentResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None
    error: str | None = None
    usage: TokenUsage | None = None


class Agent:
    """Manages LLM conversation history and streaming via any-llm.

    Supports native OpenAI-style tool calls (python/shell) and maintains
    conversation context across turns.

    Configuration is passed directly: model string, optional api_key,
    optional provider override, optional base_url. The any-llm library
    handles provider routing from the model string (e.g. "moonshot-v1-8k"
    for Kimi, "abab6.5s-chat" for MiniMax, etc.).
    """

    def __init__(
        self,
        model: str,
        system_prompt: str | None = None,
        use_tools: bool = False,
        api_key: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        on_connect: Callable | None = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.use_tools = use_tools
        self._api_key = api_key
        self._provider = provider
        self._base_url = base_url
        self._on_connect = on_connect
        self._connected = False
        self.messages: list[dict] = []
        self._pending_tool_calls: list[ToolCall] = []

    async def send(
        self,
        prompt: str,
        on_chunk: Callable | None = None,
        on_thinking_chunk: Callable | None = None,
    ) -> AgentResponse:
        """Send a prompt, stream the response, and return the full result."""
        from any_llm import acompletion

        if prompt.strip():
            self.messages.append({"role": "user", "content": prompt})

        messages = self.messages.copy()
        if self.system_prompt and (not messages or messages[0].get("role") != "system"):
            messages = [{"role": "system", "content": self.system_prompt}] + messages

        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, stream=True)
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._provider is not None:
            kwargs["provider"] = self._provider
        if self._base_url is not None:
            kwargs["base_url"] = self._base_url
        if self.use_tools:
            kwargs["tools"] = [_PYTHON_TOOL, _SHELL_TOOL]
            kwargs["tool_choice"] = "auto"

        try:
            stream = await acompletion(**kwargs)
            from typing import cast

            stream = cast("AsyncIterator[ChatCompletionChunk]", stream)
        except Exception:
            import traceback

            error = f"Connection error: {traceback.format_exc()}"
            logger.error("%s", error)
            if prompt.strip() and self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            return AgentResponse(text="", error=error)

        if not self._connected:
            self._connected = True
            if self._on_connect:
                self._on_connect("connected")

        text = ""
        thinking = ""
        usage: TokenUsage | None = None
        raw_tool_calls: list[dict] = []

        try:
            async for chunk in stream:
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = TokenUsage(
                        input_tokens=chunk.usage.prompt_tokens or 0,
                        output_tokens=chunk.usage.completion_tokens or 0,
                        total_tokens=chunk.usage.total_tokens or 0,
                    )
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning") and delta.reasoning:
                    reasoning_content = (
                        delta.reasoning.content
                        if hasattr(delta.reasoning, "content")
                        else str(delta.reasoning)
                    )
                    thinking += reasoning_content
                    if on_thinking_chunk:
                        on_thinking_chunk(reasoning_content)
                if delta.content:
                    text += delta.content
                    if on_chunk:
                        on_chunk(delta.content)
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        while len(raw_tool_calls) <= idx:
                            raw_tool_calls.append(
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }
                            )
                        rtc = raw_tool_calls[idx]
                        if tc.id:
                            rtc["id"] += tc.id
                        if tc.function and tc.function.name:
                            rtc["function"]["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            rtc["function"]["arguments"] += tc.function.arguments
        except asyncio.CancelledError:
            if prompt.strip() and self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            raise

        # Parse raw tool calls into ToolCall objects
        tool_calls: list[ToolCall] = []
        for rtc in raw_tool_calls:
            name = rtc["function"]["name"]
            try:
                args = json.loads(rtc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=rtc["id"], name=name, args=args))

        # Update conversation history
        if tool_calls:
            self.messages.append(
                {
                    "role": "assistant",
                    "content": text or "",
                    "tool_calls": raw_tool_calls,
                }
            )
            self._pending_tool_calls = list(tool_calls)
        elif text:
            self.messages.append({"role": "assistant", "content": text})

        return AgentResponse(
            text=text,
            tool_calls=tool_calls,
            thinking=thinking or None,
            usage=usage,
        )

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """Add a tool execution result to conversation history."""
        self.messages.append(
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
        self.messages = []
        self._pending_tool_calls = []


# ── Simulated agent (testing without API) ────────────────────────────────────

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
            if on_thinking_chunk and self.response_delay > 0:
                for ch in thinking_text:
                    on_thinking_chunk(ch)
                    await asyncio.sleep(self.response_delay)
            elif on_thinking_chunk:
                on_thinking_chunk(thinking_text)
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(0)

        # Parse tool calls from response text
        prose, tool_calls = _parse_tool_calls(response_text, start_id=self._tc_counter)
        self._tc_counter += len(tool_calls)

        # Stream prose text (without the tool call XML)
        if on_chunk and self.response_delay > 0:
            for ch in prose:
                on_chunk(ch)
                await asyncio.sleep(self.response_delay)
        elif on_chunk:
            if prose:
                on_chunk(prose)
            await asyncio.sleep(0)
        else:
            await asyncio.sleep(0)

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

        if thinking_text and on_thinking_chunk:
            if self.response_delay > 0:
                for ch in thinking_text:
                    on_thinking_chunk(ch)
                    await asyncio.sleep(self.response_delay)
            else:
                on_thinking_chunk(thinking_text)
                await asyncio.sleep(0)

        prose, tool_calls = _parse_tool_calls(response_text, start_id=self._tc_counter)
        self._tc_counter += len(tool_calls)

        if on_chunk:
            if self.response_delay > 0:
                for ch in prose:
                    on_chunk(ch)
                    await asyncio.sleep(self.response_delay)
            else:
                if prose:
                    on_chunk(prose)
                await asyncio.sleep(0)
        else:
            await asyncio.sleep(0)

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

        if self.echo_thinking and on_thinking_chunk:
            if self.response_delay > 0:
                for ch in self.echo_thinking:
                    on_thinking_chunk(ch)
                    await asyncio.sleep(self.response_delay)
            else:
                on_thinking_chunk(self.echo_thinking)
                await asyncio.sleep(0)

        if on_chunk:
            if self.response_delay > 0:
                for ch in response_text:
                    on_chunk(ch)
                    await asyncio.sleep(self.response_delay)
            else:
                on_chunk(response_text)
                await asyncio.sleep(0)
        else:
            await asyncio.sleep(0)

        if prompt.strip():
            self.messages.append({"role": "user", "content": prompt})
        self.messages.append({"role": "assistant", "content": response_text})

        return AgentResponse(text=response_text)


def create_agent(
    config: ArtificeConfig, on_connect: Callable | None = None
) -> Agent | SimulatedAgent | None:
    """Instantiate an agent from the user's configuration.

    Reads ``config.assistant`` (the selected assistant name) and
    ``config.assistants`` (the dict of assistant definitions). Each definition
    supports the following keys:

    - ``provider``: ``"simulated"`` or any string understood by any-llm
      (e.g. ``"openai"``, ``"moonshot"``). When omitted, ``model`` alone is
      used and any-llm auto-detects the provider.
    - ``model``: model identifier passed directly to any-llm.
    - ``api_key``: API key string. Alternatively, set ``api_key_env`` to read
      from an environment variable.
    - ``api_key_env``: Name of the environment variable holding the API key.
    - ``base_url``: Custom base URL for self-hosted or proxy endpoints.
    - ``use_tools``: Whether to register python/shell as native tools.
    - ``system_prompt``: Override the global system_prompt for this assistant.
    """
    if not config.assistants or not config.assistant:
        raise ValueError("No assistant selected in configuration")

    definition = config.assistants.get(config.assistant)
    if definition is None:
        raise ValueError(f"Unknown assistant: {config.assistant!r}")

    provider = definition.get("provider")
    model = definition.get("model")

    logger.info(
        "Creating agent %r (provider=%s, model=%s)",
        config.assistant,
        provider,
        model,
    )

    if provider and provider.lower() == "simulated":
        agent = SimulatedAgent(
            system_prompt=config.system_prompt,
            on_connect=on_connect,
        )
        agent.scenarios = []
        # Load default scenarios unless the definition says otherwise
        agent.scenarios = list(_DEFAULT_SCENARIOS)
        agent.default_response = _DEFAULT_RESPONSE
        agent.default_thinking = _DEFAULT_THINKING
        return agent

    if model is None:
        raise ValueError(
            f"Assistant {config.assistant!r} requires a 'model' key in its definition"
        )

    # Resolve API key
    api_key: str | None = definition.get("api_key")
    if api_key is None:
        env_var = definition.get("api_key_env")
        if env_var:
            api_key = os.environ.get(env_var)

    system_prompt = definition.get("system_prompt", config.system_prompt)
    use_tools = bool(definition.get("use_tools", False))
    base_url: str | None = definition.get("base_url")
    # provider here is the any-llm provider override (not "simulated")
    llm_provider: str | None = (
        provider if provider and provider.lower() != "simulated" else None
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        use_tools=use_tools,
        api_key=api_key,
        provider=llm_provider,
        base_url=base_url,
        on_connect=on_connect,
    )
