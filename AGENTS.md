# Artifice Development Guidelines

## Important Constraints

### Do Not Execute
- **Never run the application directly** (`artifice` or `python src/artifice/terminal.py`)
- The TUI interface requires terminal interaction that won't work in in AI agent environment
- Test changes through unit tests instead

## Build & Test Commands

### Running Tests
- **Run all tests**: `pytest tests`
- **Run single test file**: `pytest tests/test_assistant.py`
- **Run single test function**: `pytest tests/test_assistant.py::test_assistant_manages_history`
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

## Project Structure

```
src/artifice/
├── app.py              # Textual app entry point
├── terminal.py         # Main terminal widget
├── config.py           # Configuration management
├── prompts.py          # Prompt template loading
├── theme.py            # Textual theme definitions
├── assistant/          # AI assistant implementations
├── providers/          # AI provider implementations
├── execution/          # Code execution (Python/shell)
├── terminal_input.py   # Input widget
├── terminal_output.py  # Output widget
├── history.py          # Command history
└── utils.py            # Utility functions

tests/                  # pytest test suite
```

## Key Patterns

### Provider Pattern
- Providers are stateless API clients
- Receive full conversation history on each call
- Return `ProviderResponse` with streaming support
- Implement `ProviderBase` interface

### Assistant Pattern
- Assistants manage conversation history
- Delegate to providers for API calls
- Support multiple assistants sharing same provider
- Handle `openai_format` for compatibility

### Streaming Pattern
- Use `ChunkBuffer` for batching streamed chunks
- Post messages for UI updates
- Handle thinking chunks separately
- Finalize streams properly on completion/cancellation

## Testing Guidelines
- Test each module in isolation
- Use pytest fixtures for common setup
- Test async functions with `@pytest.mark.asyncio`
- Mock external dependencies
- Test edge cases: empty inputs, errors, cancellations

## Configuration
- User config at `~/.config/artifice/init.yaml`
- Load via `load_config()` from `artifice.config`
- All settings have sensible defaults
- Command-line args override config
