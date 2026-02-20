# Artifice Development Guidelines

## Important Constraints

### Do Not Execute
- **Never run the application directly** (`artifice` or `python src/artifice/terminal.py`)
- The TUI interface requires terminal interaction that won't work in in AI agent environment
- Test changes through unit tests instead

## Build & Test Commands

### Running Tests
- **Run all tests**: `pytest tests`
- **Run single test file**: `pytest tests/test_agent.py`
- **Run single test function**: `pytest tests/test_agent.py::test_agent_manages_history`
- **Run with verbose output**: `pytest -v`

### Linting & Type Checking
- **Lint**: `ruff check .`
- **Format**: `ruff format .`

## Code Style Guidelines

### Imports
- Group imports: standard library, then third-party, then local
- Use `from __future__ import annotations` at top of each file
- Use `TYPE_CHECKING` for import-time only dependencies

### Formatting
- **Indentation**: 4 spaces
- **Quotes**: Use double quotes for strings
- **Whitespace**: One blank line between top-level definitions

### Types
- Use Python 3.9+ type hints
- Use `list[dict]` instead of `List[Dict]`
- Use `str | None` instead of `Optional[str]` (Python 3.10+ compatible)
- Use `int | None` for optional integers
- Use `Path` from pathlib for file paths

### Naming Conventions
- **Classes**: PascalCase (e.g., `ArtificeApp`, `CodeExecutor`)
- **Functions/Methods**: snake_case (e.g., `send_prompt`, `execute_code`)
- **Constants**: UPPER_SNAKE_CASE
- **Variables**: snake_case
- **Private members**: Single underscore prefix (e.g., `_config`)

### Error Handling
- Use try/except for specific exceptions
- Log errors with `logger.error("message", exc_info=True)`
- Return meaningful error messages in responses
- Use `asyncio.CancelledError` for cancellation handling

### Async/Await
- Use `async def` for I/O operations
- Use `await` for all async calls
- Handle `asyncio.CancelledError` in async functions
- Use `loop.run_in_executor` for blocking operations

### Logging
- Use `logger = logging.getLogger(__name__)`
- Log at appropriate levels: debug, info, warning, error

### Documentation
- Use docstrings for all public classes and functions
- Document parameters, return values, and exceptions
- Add inline comments for complex logic

## Key Patterns

### Provider Pattern
- Providers are stateless API clients
- Receive full conversation history on each call
- Return `ProviderResponse` with streaming support
- Implement `Provider` abstract base class from `artifice.agent.providers.base`

### Agent Pattern
- Agents manage conversation history
- Delegate to providers for API calls
- Support multiple agents sharing same provider
- Handle `openai_format` for compatibility

## Project Structure

```
src/artifice/
├── __init__.py              # Public API exports
├── app.py                   # Entry point (argparse, main(), ArtificeApp)
│
├── core/                    # Domain layer - business logic
│   ├── config.py           # Configuration management
│   ├── events.py           # Event types, InputMode
│   ├── history.py          # Conversation history
│   └── prompts.py          # System prompt loading
│
├── execution/               # Code execution layer
│   ├── base.py             # ExecutionResult, ExecutionStatus
│   ├── common.py           # Backward compatibility re-exports
│   ├── python.py           # Python REPL executor
│   ├── shell.py            # Shell + Tmux executors
│   ├── callbacks.py        # Output callback handlers
│   └── coordinator.py      # Execution orchestration
│
├── agent/                   # LLM integration
│   ├── client.py           # Main Agent class
│   ├── simulated.py        # Mock agents for testing
│   ├── providers/          # LLM provider implementations
│   │   ├── base.py         # Provider base class and response types
│   │   └── anyllm.py       # Any-LLM provider implementation
│   ├── tools/              # Tool system
│   │   ├── base.py         # ToolDef, ToolCall
│   │   └── executors.py    # Tool implementations
│   └── streaming/          # Stream handling
│       ├── manager.py      # Stream coordination
│       ├── buffer.py       # Chunk buffering
│       └── detector.py     # Code fence detection
│
├── ui/                      # User interface layer
│   ├── widget.py           # Main terminal widget
│   ├── components/         # Reusable UI components
│   │   ├── blocks/         # Output blocks
│   │   │   ├── blocks.py   # Block widget implementations
│   │   │   ├── registry.py # BlockRenderer protocol and registry
│   │   │   └── factory.py  # BlockFactory for creating blocks
│   │   ├── input.py        # TerminalInput
│   │   ├── output.py       # TerminalOutput
│   │   └── status.py       # StatusIndicatorManager
│   └── controllers/        # UI coordination
│       ├── agent_coordinator.py
│       ├── nav_controller.py
│       └── search.py       # Search mode management
│
└── utils/                   # Shared utilities
    ├── text.py             # Text processing
    ├── theme.py            # Theme utilities (create_artifice_theme)
    └── fencing/            # Code fence parsing
        ├── parser.py
        └── state.py
```

## Configuration
- User config at `~/.config/artifice/init.yaml`
- Load via `load_config()` from `artifice.core.config`
- All settings have sensible defaults
- Command-line args override config

## Import Guidelines

### Core modules (business logic)
- Config: `from artifice.core.config import load_config, ArtificeConfig`
- History: `from artifice.core.history import History`
- Prompts: `from artifice.core.prompts import load_prompt, list_prompts`

### UI components
- Widget: `from artifice.ui.widget import ArtificeTerminal`
- Theme: `from artifice.utils.theme import create_artifice_theme`

### Agent & Execution
- Agent: `from artifice.agent.client import Agent`
- Streaming: `from artifice.agent.streaming.manager import StreamManager`
- Execution: `from artifice.execution.coordinator import ExecutionCoordinator`
