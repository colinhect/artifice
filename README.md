# Artifice

A minimal and transparent AI agent harness with a terminal user interface built with [Textual](https://github.com/Textualize/textual).

Artifice provides a unified interface for both building precise prompts and running full agentic flows, with support for any LLM provider through [any-llm](https://github.com/mlamina/any-llm).

## Features

### Execution Environments

- **Python** - Full interactive Python console with persistent global state
- **Shell Commands** - Execute bash commands with streaming output
- **Tmux Integration** - Route shell commands to existing tmux panes, preserving shell state, environment variables, and working directory across commands
- **Textual Widgets** - Python code returning Textual objects gets mounted directly in the UI

### Tools

- **System Tools** - Built-in tools for file operations (read_file, write_file, file_search), web operations (web_search, web_fetch), and system info (system_info)
- **Code Tools** - `python` and `shell` tools that execute code via the REPL

### User Interface

- **Markdown Rendering** - AI responses rendered as formatted markdown with section headers
- **Syntax Highlighting** - Code blocks highlighted during streaming and after execution
- **Block Navigation** - Navigate, edit, and re-execute previous inputs
- **Multiline Input** - Write complex code with proper formatting
- **Command History** - Persistent history across sessions with search (Ctrl+R)
- **Prompt Templates** - Select pre-defined prompts for quick setup (Ctrl+R)
- **Context Tracking** - Blocks marked as in-agent context are highlighted when auto-send is enabled
- **Full Prompt Visibility** - All prompts used in completion requests are visible
- **Tool Call Display** - Show tool execution results with proper formatting

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

### Block Actions

- **Alt+Up/Down** - Navigate through output blocks
- **Enter** - Re-execute selected code block
- **Ctrl+O** - Toggle markdown rendering (on current block or subsequent blocks)
- **Ctrl+N** - Clear the agent's conversation context
- **F2** - Toggle help footer

### Application

- **Ctrl+Q** - Exit application
- **Ctrl+O** - Toggle markdown rendering (on current block or subsequent blocks)
- **Ctrl+L** - Clear output
- **F2** - Toggle help footer

## Configuration

Copy `config/init.yaml` to `~/.config/artifice/init.yaml` and customize. Key settings:

- **agent** - Select which LLM agent to use
- **agents** - Define agents with provider, model, API key, and tool access
- **system_prompt** - Custom system prompt for the AI agent
- **prompt_prefix** - Text prefix for AI prompts
- **show_tool_output** - Show/hide tool execution results in UI (default: true)
- **send_user_commands_to_agent** - Automatically send execution results back to the agent
- **agent_markdown**, **python_markdown**, **shell_markdown** - Toggle markdown rendering per mode (default: true, false, false)
- **tmux_target** - Target tmux pane for shell command execution (e.g. `session:window.pane`)
- **tmux_prompt_pattern** - Pattern matching shell prompt in tmux (default: `^\S+@\S+:\S+\$ `)
- **streaming_fps** - Performance: Target FPS for streaming UI updates (default: 60)
- **shell_poll_interval** - Performance: Shell command polling interval in seconds (default: 0.02)
- **python_executor_sleep** - Performance: Python execution sleep interval in seconds (default: 0.005)
- **python_output_code_block**, **shell_output_code_block** - Use code blocks for output (default: true for python, false for shell)

See `config/init.yaml` for the full list of options.

### Running from Source

```bash
git clone https://github.com/colinhill/artifice.git
cd artifice
pip install -e .
artifice
```

## License

MIT

