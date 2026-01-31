# Artifice
Human in the loop agentic AI for interactive coding implemented using [Textual](https://github.com/Textualize/textual).

## Features

- Interactive coding console (Python)
- Interactive shell
- AI agent integration (Claude, Copilot, etc.)
    - **Tool calling** - AI agent can execute Python code or shell commands to answer questions
    - **Agentic loops** - Multiple tool calls in a single conversation
- Markdown rendering and syntax highlighting
- Multiline input support
    - Auto-complete for Python
    - Optional VIM keybinding edit mode (not implemented yet)
- Block navigation (Ctrl+Up/Down)
    - Pinning blocks
    - Editing blocks
    - Saving/restoring blocks
- Command history with persistent storage
- Persistent context
    - Tools execute in the same Python session
- Visual feedback
    - See tool calls and results in the UI

## User Input

Typing special characters with empty input will change the mode of the input text area.
- `!` to switch to shell mode
- `>` to switch to coding (Python) mode
- `?` to switch to AI agent prompt mode

## AI Agent Integration

The review and execution of any action is decoupled from the AI agent itself. When an AI agent makes a tool call
to perform an action (like executing Python or shell command) the user will be prompted to review and choose to
execute the code (or not). This allows for agent flows but helps encourage the user to be fully responsibly and
skillful in the execution of commands.

### Quick Start

Install with AI support:
```bash
pip install -e ".[ai]"
```

Set your API key:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

Running:
```bash
python src/artifice/terminal.py
```

### Supported Agents

- **Claude** (via Anthropic API) - Streaming support + tool calling
- **Copilot** (placeholder - not yet implemented)

You can also create custom agents with custom tools by subclassing `AgentBase`.

