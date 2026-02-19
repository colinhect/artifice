# Artifice

A minimal and transparent AI agent harness with a terminal user interface. Provides direct control over model interactions, code execution, and shell commands—without complex frameworks or abstractions. Built with [Textual](https://github.com/Textualize/textual).

Artifice provides a unified interface for both building precise prompts and running full agentic flows, with support for any LLM provider through [any-llm](https://github.com/mlamina/any-llm).

## Features

### Execution Environments

- **Python** - Full interactive Python console with persistent state
- **Shell Commands** - Execute bash commands with streaming output
- **Tmux Integration** - Route shell commands to existing tmux panes, preserving shell state, environment variables, and working directory across commands
- **Textual Widgets** - Python code returning Textual objects gets mounted directly in the UI

### User Interface

- **Markdown Rendering** - AI responses rendered as formatted markdown
- **Syntax Highlighting** - Code blocks highlighted during streaming and after execution
- **Block Navigation** - Navigate, edit, and re-execute previous inputs
- **Multiline Input** - Write complex code with proper formatting
- **Command History** - Persistent history across sessions with search

## Installation

Requires Python 3.9+.

```bash
pip install -e .
```

## Running

```bash
artifice
```

## Usage

### Mode Switching

Artifice has three input modes. Switch modes by typing a special character when the input is empty:

- `>` - **AI prompt mode** - Prompt the intelligence model
- `]` - **Python mode** - Execute Python code
- `$` - **Shell mode** - Run shell commands

### Navigation

- **Alt+Up/Down** - Navigate through output blocks
- **Up/Down** - Navigate command history (when cursor is at top/bottom of input)

### Execution

- **Enter** - Execute input (single-line) or insert newline (multi-line)
- **Ctrl+S** - Submit code/command
- **Ctrl+C** - Cancel current operation

### Input Editing

- **Ctrl+J** - Insert newline
- **Ctrl+K** - Clear input
- **Ctrl+R** - History search with autocomplete
- **Escape** - Exit search mode / Return to Python mode

### Application

- **Ctrl+Q** - Exit application
- **Ctrl+O** - Toggle markdown rendering (on current block or subsequent blocks)
- **Ctrl+L** - Clear output
- **F2** - Toggle help footer

## Configuration

Copy `init.yaml.example` to `~/.config/artifice/init.yaml` and customize. Key settings:

- **agent** - Select which LLM agent to use
- **agents** - Define agents with provider, model, API key, and tool access
- **system_prompt** - Custom system prompt for the AI agent
- **tmux_target** - Target tmux pane for shell command execution (e.g. `session:window.pane`)
- **auto_send_to_agent** - Automatically send execution results back to the agent

See `init.yaml.example` for the full list of options.

### Running from Source

```bash
git clone https://github.com/colinhill/artifice.git
cd artifice
pip install -e .
artifice
```

## License

MIT

