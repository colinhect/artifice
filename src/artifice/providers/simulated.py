"""Simulated provider for testing."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Optional

from .provider import ProviderBase, ProviderResponse

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


class SimulatedProvider(ProviderBase):
    """Simulated provider for testing without API costs.

    Can be configured with predefined scenarios that match patterns or
    respond sequentially.
    """

    def __init__(
        self,
        on_connect: Callable | None = None,
        response_delay: float = 0.05,
    ):
        """Initialize simulated provider.

        Args:
            on_connect: Optional callback called on initialization
            response_delay: Delay between streaming chunks (seconds) to simulate typing
        """
        self.on_connect = on_connect
        self.response_delay = response_delay

        # Configuration for responses
        self.scenarios: list[dict[str, Any]] = []
        self.current_scenario_index = 0
        self.default_response = (
            "I'm a simulated AI . I can be configured with custom responses."
        )
        self.default_thinking: str | None = None

        # Set up default scenarios
        self._setup_default_scenarios()

    def _setup_default_scenarios(self):
        """Set up default test scenarios."""
        self.scenarios = [
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

        self.default_response = (
            "I'd be happy to help with that. Could you give me a bit more context?\n\n"
            "Here are some things I can assist with:\n"
            "- **Project exploration** — understanding codebases and file structure\n"
            "- **Data analysis** — loading, cleaning, and summarizing datasets\n"
            "- **Debugging** — tracking down errors and writing fixes\n"
            "- **Code review** — suggesting refactors and improvements\n"
            "- **System admin** — checking disk, memory, and processes\n\n"
            "Just describe what you're working on and I'll dive in."
        )
        self.default_thinking = (
            "The user's request doesn't match any of my specific scenarios. "
            "I should offer some guidance on what I can help with."
        )

    def configure_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        """Configure the provider with predefined scenarios.

        Each scenario is a dict with:
        - 'response': str - The text response to stream
        - 'pattern': str - Optional regex pattern to match against prompts
        - 'thinking': str - Optional thinking text to stream before response
        """
        self.scenarios = scenarios
        self.current_scenario_index = 0

    def set_default_response(self, response: str) -> None:
        """Set the default response when no scenarios match."""
        self.default_response = response

    def set_default_thinking(self, thinking: str | None) -> None:
        """Set the default thinking text when no scenarios match."""
        self.default_thinking = thinking

    def _find_matching_scenario(self, prompt: str) -> dict[str, Any] | None:
        """Find a scenario that matches the given prompt."""
        # First, try to match patterns
        for scenario in self.scenarios:
            pattern = scenario.get("pattern")
            if pattern:
                if re.search(pattern, prompt, re.IGNORECASE):
                    return scenario

        # No pattern matched, try sequential scenarios (those without patterns)
        scenarios_without_patterns = [s for s in self.scenarios if not s.get("pattern")]
        if self.current_scenario_index < len(scenarios_without_patterns):
            scenario = scenarios_without_patterns[self.current_scenario_index]
            self.current_scenario_index += 1
            return scenario

        return None

    async def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> ProviderResponse:
        """Send messages to simulated provider and stream response.

        Args:
            messages: Full conversation history
            system_prompt: Optional system prompt (ignored for simulation)
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            ProviderResponse with the simulated response
        """
        if self.on_connect:
            self.on_connect("Artifice")
            self.on_connect = None

        # Extract last user message
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                prompt = msg.get("content", "")
                break

        logger.debug("Processing prompt: %s", prompt[:200])

        # Find matching scenario
        scenario = self._find_matching_scenario(prompt)

        if scenario:
            response_text = scenario["response"]
            thinking_text = scenario.get("thinking")
        else:
            response_text = self.default_response
            thinking_text = self.default_thinking

        # Stream thinking text if available
        if thinking_text:
            if on_thinking_chunk and self.response_delay > 0:
                # Stream with delay character-by-character
                logger.debug("Streaming thinking (%d chars)", len(thinking_text))
                for char in thinking_text:
                    on_thinking_chunk(char)
                    await asyncio.sleep(self.response_delay)
            elif on_thinking_chunk:
                # No delay but callback provided - send all at once with one yield point
                logger.debug("Streaming thinking (%d chars)", len(thinking_text))
                on_thinking_chunk(thinking_text)
                await asyncio.sleep(0)

        # Stream the response text
        if on_chunk and self.response_delay > 0:
            # Stream with delay character-by-character
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self.response_delay)
        elif on_chunk:
            # No delay but callback provided - send all at once with one yield point
            on_chunk(response_text)
            await asyncio.sleep(0)
        else:
            # No callback - just yield once to allow cancellation
            await asyncio.sleep(0)

        logger.info("Response complete (%d chars)", len(response_text))

        return ProviderResponse(
            text=response_text,
            stop_reason="end_turn",
            thinking=thinking_text,
        )
