# Development Guide

**Version:** 0.1.0
**Last Updated:** 2026-02-12

## Overview

This document provides guidelines for developing Artifice, including project structure, coding conventions, testing strategies, debugging techniques, and contribution workflows.

---

## Project Structure

```
artifice/
├── src/artifice/           # Main source code
│   ├── __init__.py        # Package exports
│   ├── app.py             # Application entry point
│   ├── terminal.py        # Main terminal widget
│   ├── terminal_input.py  # Input component
│   ├── terminal_output.py # Output blocks
│   ├── config.py          # Configuration system
│   ├── history.py         # Command history
│   ├── session.py         # Session transcript
│   ├── ansi_handler.py    # ANSI escape code handling
│   ├── agent/             # AI agent integrations
│   │   ├── __init__.py
│   │   ├── common.py      # Base agent interface
│   │   ├── claude.py      # Anthropic Claude
│   │   ├── ollama.py      # Ollama local models
│   │   ├── copilot.py     # GitHub Copilot
│   │   └── simulated.py   # Testing agent
│   └── execution/         # Code execution engines
│       ├── __init__.py
│       ├── common.py      # Execution interfaces
│       ├── python.py      # Python REPL
│       └── shell.py       # Bash shell
├── tests/                  # Test suite
│   ├── test_execution.py
│   ├── test_agent.py
│   ├── test_streaming.py
│   └── ...
├── docs/                   # Documentation
│   ├── ARCHITECTURE.md
│   ├── COMPONENTS.md
│   ├── STREAMING.md
│   ├── EXECUTION_MODEL.md
│   ├── CONFIGURATION.md
│   └── DEVELOPMENT.md
├── pyproject.toml         # Project metadata & dependencies
├── README.md              # User documentation
└── CLAUDE.md              # AI assistant instructions
```

---

## Development Setup

### Install for Development

```bash
# Clone repository
git clone <repository-url>
cd artifice

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

**Dev Dependencies:**
- `pytest`: Testing framework
- `pytest-asyncio`: Async test support

### Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_execution.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=artifice
```

### Run Application

```bash
# From source
python src/artifice/app.py

# With arguments
python src/artifice/app.py --provider simulated --banner
```

**Note:** Never run from CI/CD (TUI requires terminal). See `CLAUDE.md` constraints.

---

## Coding Conventions

### Style Guide

**Follow PEP 8** with these specifics:

**Imports:**
```python
# Standard library
from __future__ import annotations
import asyncio
import logging
from pathlib import Path

# Third-party
from textual.app import ComposeResult
from textual.widget import Widget

# Local
from .agent import AgentBase
from .execution import ExecutionResult
```

**Type Hints:**
```python
def execute(self, code: str, on_output: Callable | None = None) -> ExecutionResult:
    ...
```

Use `from __future__ import annotations` for forward references.

**Docstrings:**
```python
def send_prompt(self, prompt: str, on_chunk: Callable | None = None) -> AgentResponse:
    """Send a prompt to the agent.

    Args:
        prompt: The prompt text to send.
        on_chunk: Optional callback for streaming text chunks.

    Returns:
        AgentResponse with the complete response.
    """
```

**Naming:**
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private members: `_leading_underscore`

### Async Conventions

**Always use async for I/O:**
```python
async def execute_code(self, code: str) -> ExecutionResult:
    result = await loop.run_in_executor(None, self._execute_sync, code)
    return result
```

**Don't block the event loop:**
```python
# ❌ BAD
def execute(self, code):
    time.sleep(5)  # Blocks event loop!

# ✅ GOOD
async def execute(self, code):
    await asyncio.sleep(5)  # Non-blocking
```

### Widget Conventions

**Use Textual best practices:**

**Compose method:**
```python
def compose(self) -> ComposeResult:
    with Horizontal():
        yield Static("Label")
        yield self._widget
```

**CSS in DEFAULT_CSS:**
```python
DEFAULT_CSS = """
WidgetName {
    border: solid $primary;
}
"""
```

**Message handling:**
```python
class MyMessage(Message):
    def __init__(self, value: str):
        super().__init__()
        self.value = value

# Posting
self.post_message(MyMessage("test"))

# Handling
def on_my_message(self, event: MyMessage):
    print(event.value)
```

---

## Testing Strategy

### Test Structure

```
tests/
├── test_execution.py       # Executor tests
├── test_agent.py          # Agent tests
├── test_streaming.py      # Fence detector tests
├── test_terminal.py       # Terminal widget tests
└── test_config.py         # Config loading tests
```

### Unit Tests

**Test executors:**
```python
import pytest
from artifice.execution import CodeExecutor, ExecutionStatus

@pytest.mark.asyncio
async def test_python_execution():
    executor = CodeExecutor()
    result = await executor.execute("x = 2 + 2")

    assert result.status == ExecutionStatus.SUCCESS
    assert "x" in executor._namespace
    assert executor._namespace["x"] == 4
```

**Test agents:**
```python
import pytest
from artifice.agent.simulated import SimulatedAgent

@pytest.mark.asyncio
async def test_simulated_agent():
    agent = SimulatedAgent(response_delay=0.001)
    agent.set_response("Test response")

    chunks = []
    def on_chunk(text):
        chunks.append(text)

    response = await agent.send_prompt("Test", on_chunk=on_chunk)

    assert response.text == "Test response"
    assert len(chunks) > 0
```

**Test fence detector:**
```python
from artifice.terminal import StreamingFenceDetector
from artifice.terminal_output import CodeInputBlock, AgentOutputBlock

def test_fence_detection():
    # Mock output and callbacks
    output = MockTerminalOutput()
    detector = StreamingFenceDetector(output, auto_scroll=True)

    detector.start()
    detector.feed("Text\n```python\ncode\n```\nMore text")
    detector.finish()

    assert len(detector.all_blocks) == 3
    assert isinstance(detector.all_blocks[0], AgentOutputBlock)
    assert isinstance(detector.all_blocks[1], CodeInputBlock)
    assert isinstance(detector.all_blocks[2], AgentOutputBlock)
```

### Integration Tests

**Test full workflow:**
```python
@pytest.mark.asyncio
async def test_code_execution_workflow(tmp_path):
    app = ArtificeApp(config=test_config)
    terminal = app.query_one(ArtificeTerminal)

    # Submit Python code
    terminal.input.code = "x = 42"
    terminal.input.mode = "python"
    terminal.input.submit()

    # Wait for execution
    await asyncio.sleep(0.1)

    # Verify block created
    assert len(terminal.output._blocks) >= 1
    block = terminal.output._blocks[0]
    assert isinstance(block, CodeInputBlock)
```

### Test Fixtures

**Common fixtures:**
```python
@pytest.fixture
def mock_agent():
    """Simulated agent for testing."""
    agent = SimulatedAgent(response_delay=0.001)
    agent.set_response("Test response")
    return agent

@pytest.fixture
def executor():
    """Fresh executor instance."""
    return CodeExecutor()

@pytest.fixture
def config():
    """Test configuration."""
    config = ArtificeConfig()
    config.provider = "simulated"
    config.save_sessions = False
    return config
```

### Mocking

**Mock agent API calls:**
```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_agent_error_handling():
    with patch("anthropic.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.stream.side_effect = Exception("API error")

        agent = ClaudeAgent(model="claude-sonnet-4-5")
        response = await agent.send_prompt("Test")

        assert response.error is not None
        assert "API error" in response.error
```

**Mock file I/O:**
```python
from unittest.mock import mock_open, patch

def test_session_save():
    with patch("builtins.open", mock_open()) as mock_file:
        session = SessionTranscript(Path("/tmp/sessions"), config)
        session.append_block(test_block)

        mock_file.assert_called()
```

---

## Debugging

### Logging

**Enable logging:**
```bash
python src/artifice/app.py --logging
```

**Log file:** `artifice_agent.log`

**Add logging:**
```python
import logging

logger = logging.getLogger(__name__)

async def send_prompt(self, prompt):
    logger.debug(f"Sending prompt: {prompt}")
    response = await self._api_call(prompt)
    logger.debug(f"Received response: {response.text}")
    return response
```

**Log levels:**
- `DEBUG`: Detailed diagnostic info
- `INFO`: General informational messages
- `WARNING`: Warning messages
- `ERROR`: Error messages

### Textual DevTools

**Run with console:**
```bash
textual console
python src/artifice/app.py
```

**Log to console:**
```python
self.app.log("Debug message")
self.app.log.error("Error message")
```

### Breakpoints

**Standard breakpoint:**
```python
import pdb; pdb.set_trace()
```

**Async breakpoint:**
```python
import asyncio
await asyncio.sleep(0)  # Yield to event loop
import pdb; pdb.set_trace()
```

### Print Debugging

**Avoid in async code:**
```python
# ❌ BAD (may not appear in terminal)
async def execute(self, code):
    print(f"Executing: {code}")
```

**Use logging instead:**
```python
# ✅ GOOD
async def execute(self, code):
    logger.debug(f"Executing: {code}")
```

---

## Common Development Tasks

### Adding a New Agent

1. **Create agent file:**
```python
# src/artifice/agent/custom.py
from .common import AgentBase, AgentResponse

class CustomAgent(AgentBase):
    async def send_prompt(self, prompt, on_chunk=None, on_thinking_chunk=None):
        # Implement streaming logic
        ...

    def clear_conversation(self):
        # Reset state
        ...
```

2. **Register in terminal.py:**
```python
elif app.provider.lower() == "custom":
    from .agent import CustomAgent
    self._agent = CustomAgent(model=model, system_prompt=system_prompt)
```

3. **Add to config:**
```python
parser.add_argument(
    "--provider",
    choices=["anthropic", "copilot", "ollama", "simulated", "custom"],
    ...
)
```

4. **Write tests:**
```python
# tests/test_agent.py
@pytest.mark.asyncio
async def test_custom_agent():
    agent = CustomAgent(model="test-model")
    response = await agent.send_prompt("Test")
    assert response.text is not None
```

### Adding a New Executor

1. **Create executor file:**
```python
# src/artifice/execution/javascript.py
from .common import ExecutionResult, ExecutionStatus

class JavaScriptExecutor:
    async def execute(self, code, on_output=None, on_error=None):
        # Execute JavaScript via Node.js
        ...
```

2. **Integrate in terminal.py:**
```python
self._js_executor = JavaScriptExecutor()

# In execute code:
if language == "javascript":
    result = await self._js_executor.execute(code, ...)
```

3. **Add language mode:**
```python
# In terminal_input.py
if ch == "j" and self._code_input.text == "":
    self._mode = "javascript"
    self._update_prompt()
```

4. **Write tests:**
```python
@pytest.mark.asyncio
async def test_javascript_execution():
    executor = JavaScriptExecutor()
    result = await executor.execute("console.log('hello')")
    assert result.status == ExecutionStatus.SUCCESS
    assert "hello" in result.output
```

### Adding a New Block Type

1. **Create block class:**
```python
# src/artifice/terminal_output.py
class CustomBlock(BaseBlock):
    DEFAULT_CSS = """
    CustomBlock {
        border: solid $accent;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self._content)
```

2. **Use in terminal:**
```python
custom_block = CustomBlock(content="...")
self.output.append_block(custom_block)
```

3. **Add to session serialization:**
```python
# In session.py
elif isinstance(block, CustomBlock):
    return f"## Custom\n\n{block._content}"
```

### Adding Configuration Option

1. **Add to ArtificeConfig:**
```python
# src/artifice/config.py
class ArtificeConfig:
    def __init__(self):
        ...
        self.new_setting: bool = False
```

2. **Add CLI argument:**
```python
# src/artifice/app.py
parser.add_argument("--new-setting", action="store_true", help="...")
```

3. **Apply in code:**
```python
if self._config.new_setting:
    # Use new setting
    ...
```

4. **Document:**
```python
# docs/CONFIGURATION.md
### New Setting

```python
config.new_setting = True
```
```

---

## Performance Optimization

### Profiling

**Profile execution:**
```bash
python -m cProfile -o profile.stats src/artifice/app.py
```

**Analyze:**
```python
import pstats
p = pstats.Stats('profile.stats')
p.sort_stats('cumulative').print_stats(20)
```

### Rendering Optimization

**Batch updates:**
```python
with self.app.batch_update():
    # Multiple DOM changes
    block1.update(...)
    block2.update(...)
```

**Throttle renders:**
```python
_FLUSH_INTERVAL = 0.1

def flush(self):
    now = time.monotonic()
    if now - self._last_flush < self._FLUSH_INTERVAL:
        self._schedule_deferred_flush()
        return
    self._do_flush()
```

**Defer scrolling:**
```python
self.call_after_refresh(lambda: self.output.scroll_end())
```

### Memory Optimization

**Limit history:**
```python
MAX_HISTORY = 1000
if len(self._history) > MAX_HISTORY:
    self._history = self._history[-MAX_HISTORY:]
```

**Clear blocks:**
```python
def clear(self):
    for block in self._blocks:
        block.remove()
    self._blocks.clear()
```

---

## Common Pitfalls

### Widget Mount in Callbacks

**Problem:**
```python
def on_chunk(text):
    # ❌ WRONG: NoActiveAppError
    widget.mount(new_block)
```

**Solution:**
```python
def on_chunk(text):
    # ✅ CORRECT: Post message
    loop.call_soon_threadsafe(lambda: self.post_message(StreamChunk(text)))

def on_stream_chunk(self, event):
    # Safe to mount here
    self.mount(new_block)
```

**Reference:** See MEMORY.md critical lesson.

### Blocking the Event Loop

**Problem:**
```python
async def execute(self, code):
    # ❌ WRONG: Blocks event loop
    time.sleep(5)
```

**Solution:**
```python
async def execute(self, code):
    # ✅ CORRECT: Run in executor
    await loop.run_in_executor(None, time.sleep, 5)
```

### Inconsistent Rendering

**Problem:**
```python
# Different widgets during streaming vs finalization
if streaming:
    yield Static(text)  # Plain
else:
    yield Markdown(text)  # Markdown
# Result: visual "jump" on finalization
```

**Solution:**
```python
# Same widget throughout
if render_markdown:
    yield Markdown(text)  # Always Markdown
else:
    yield Static(text)  # Always Static
```

**Reference:** See MEMORY.md critical lesson.

### String Tracking Edge Cases

**Problem:**
```python
# Triple-quote inside string not handled
code = '"""```python"""'  # May break fence detection
```

**Solution:** Implement robust string tracking (see `StringTracker` in terminal.py).

---

## Release Process

### Version Bumping

1. **Update version:**
```toml
# pyproject.toml
version = "0.2.0"
```

2. **Update docs:**
```markdown
# All docs/*.md
**Version:** 0.2.0
**Last Updated:** YYYY-MM-DD
```

3. **Commit:**
```bash
git commit -am "Bump version to 0.2.0"
git tag v0.2.0
```

### Build Distribution

```bash
pip install build
python -m build
```

**Output:**
- `dist/artifice-0.2.0.tar.gz`
- `dist/artifice-0.2.0-py3-none-any.whl`

### Publish to PyPI

```bash
pip install twine
twine upload dist/*
```

---

## Contribution Guidelines

### Workflow

1. **Fork repository**
2. **Create feature branch:**
   ```bash
   git checkout -b feature/new-feature
   ```
3. **Make changes with tests**
4. **Run tests:**
   ```bash
   pytest
   ```
5. **Commit with descriptive message**
6. **Push and create pull request**

### Commit Messages

**Format:**
```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `test`: Tests
- `refactor`: Code refactoring
- `perf`: Performance improvement

**Example:**
```
feat: Add GitHub Copilot integration

- Implement CopilotAgent class
- Add copilot provider to config
- Add tests for copilot agent

Closes #123
```

### Code Review

**Check:**
- [ ] Tests pass
- [ ] Code follows style guide
- [ ] Documentation updated
- [ ] No regressions
- [ ] Performance acceptable

---

## Troubleshooting Development Issues

### Tests Fail

**Check:**
- Dependencies installed: `pip install -e ".[dev]"`
- Python version: `python --version` (requires 3.9+)
- Async tests use `@pytest.mark.asyncio`

### Import Errors

**Check:**
- Installed in editable mode: `pip install -e .`
- Virtual environment activated
- Module structure correct (no circular imports)

### Textual App Won't Start

**Check:**
- Terminal supports colors: `echo $TERM`
- No conflicting keybindings
- Running in interactive terminal (not CI/CD)

### Agent Not Working

**Check:**
- API key set: `echo $ANTHROPIC_API_KEY`
- Package installed: `pip show anthropic`
- Network connectivity
- Model name correct

---

## Resources

### Documentation
- [Textual Docs](https://textual.textualize.io/)
- [Anthropic API Docs](https://docs.anthropic.com/)
- [Ollama Docs](https://ollama.ai/docs)

### Tools
- [Textual DevTools](https://textual.textualize.io/guide/devtools/)
- [pytest](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)

### Internal Docs
- `ARCHITECTURE.md`: System architecture
- `COMPONENTS.md`: Component design
- `STREAMING.md`: Streaming architecture
- `EXECUTION_MODEL.md`: Execution design
- `CONFIGURATION.md`: Configuration guide
