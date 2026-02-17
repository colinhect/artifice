# Artifice

A minimal intelligence agent harness with a terminal user interface. Provides control over AI model interactions, code execution, and shell commands—without complex frameworks, protocols, or abstractions. Built with [Textual](https://github.com/Textualize/textual).

## Philosophy

Artifice is built on the principle that agent harnesses should be **minimal and transparent**.

### Self-Bootstrapping Design

Artifice is designed to bootstrap itself. Once the minimal feature set is in place, the tool itself becomes the development environment for its own evolution.

This is currently aspirational.

## Features

### Intelligence Agent Harness
- **Direct Model Prompting** - Simple, transparent prompting without MCP/ACP protocols
- **Tool Calling** - AI can propose Python code or shell commands as executable tools
- **Selective Context** - Explicitly mark which blocks to include in agent context
- **Session Transcripts** - Full conversation and execution history saved locally

### Execution Environments
- **Python** - Full interactive Python console
- **Shell Commands** - Execute bash commands with streaming output
- **Tmux Integration** - Route shell commands to existing tmux panes for real terminal state
- **Textual Widgets** - Python code returning Textual objects gets mounted directly in the UI

### User Interface
- **Markdown Rendering** - AI responses and output can be rendered as formatted markdown
- **Syntax Highlighting** - Code blocks highlighted during streaming and after execution
- **Block Navigation** - Navigate, edit, and re-execute previous inputs (Ctrl+Up/Down)
- **Multiline Input** - Write complex code with proper formatting
- **Command History** - Persistent history across sessions with search (Ctrl+R)

## Tmux Integration

Artifice can execute shell commands in existing tmux sessions instead of isolated subprocesses. This allows:

- **Persistent shell state** - Environment variables, working directory, and shell history maintained
- **Real terminal sessions** - Commands run in actual terminal panes with full terminal capabilities
- **Visual debugging** - Watch command execution in real-time in the tmux pane
- **Stateful workflows** - Build on previous command state (activated virtualenvs, cd'd directories, etc.)

### Configuration

Add to `~/.config/artifice/init.yaml`:

```yaml
# Target an existing tmux session
tmux_target: "my-session:0"  # or "session:window.pane"

# Regex pattern matching your shell prompt (used to detect command completion)
tmux_prompt_pattern: "^\\$ "  # Match prompts like "$ "
# or: "^user@host:\\S+\\$ "  # Match prompts like "user@host:~$ "
```

### Command Line

```bash
# Target specific tmux session
artifice --tmux "my-session:0"

# With custom prompt pattern
artifice --tmux "dev:1.0" --tmux-prompt "^➜ "
```

### How It Works

1. Commands are sent to the target tmux pane via `tmux send-keys`
2. Output is captured via `tmux pipe-pane` streaming to a temporary file
3. Command completion is detected by the reappearance of the shell prompt
4. Exit code is retrieved with a follow-up `echo $?` command

### Requirements

- `tmux` must be installed and accessible in PATH
- Target tmux session must exist before launching Artifice
- Prompt pattern must reliably match your shell prompt for command completion detection

## Installation

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

## Intelligence Model Integration

Artifice supports multiple model providers with a minimal, direct prompting approach:

### Supported Providers

- **Claude** (Anthropic API) - Streaming responses with native tool calling support
- **Ollama** (local models) - Run models locally with streaming, tool use via prompt engineering

### Configuration

Configure your default assistant in `~/.config/artifice/init.yaml`:

```yaml
# Default assistant
assistant: "claude"

# Optional: Define multiple assistants with custom settings
assistants:
  claude:
    provider: "anthropic"
    model: "claude-sonnet-4.5-20250929"
  local:
    provider: "ollama"
    model: "qwen2.5-coder:32b"
    host: "http://localhost:11434"

# Optional: Custom system prompt for agent behavior
system_prompt: |
  You are a helpful coding assistant. When proposing code changes,
  always explain your reasoning clearly.

# Optional: Prepend text to every user message
prompt_prefix: "Context: working on Python project.\n\n"

# Optional: Extended thinking budget for complex tasks (Claude)
thinking_budget: 10000
```

### Tool Calling

The agent harness exposes two tools to AI models:

- **python** - Execute Python code in the persistent REPL session
- **bash** - Execute shell commands (in subprocess or tmux session)

Models receive:
- Current conversation context (with selective block inclusion)
- Execution results from previous tool calls
- Ability to propose code/commands for human review

No complex protocols or intermediate formats—just direct prompting with tool definitions.

### Running from Source

```bash
git clone <repository-url>
cd artifice/src
python -m artifice.app
```

## Design Principles

### Minimal & Transparent
- No complex frameworks or protocols (MCP, ACP, etc.)
- Every AI action visible and editable before execution
- Simple tool definitions directly in prompts
- No hidden state or magic behavior

### Human-in-the-Loop
- Explicit approval for every execution
- Edit proposed code before running
- Clear separation between AI proposals and executed actions
- Full control over context provided to models

### Real Execution Environments
- Python REPL with actual state persistence
- Shell commands in real terminals (via tmux)
- Not sandboxed or simulated environments
- Direct integration with your development workflow

## Roadmap

Future enhancements while maintaining the minimal harness philosophy:

- [ ] VIM keybinding mode for text editing
- [ ] Additional model providers (OpenAI, Gemini, local models)
- [ ] Session export/import in portable formats
- [ ] Language Server Protocol (LSP) integration for code intelligence
- [ ] Additional language REPLs (Node.js, Ruby, etc.)
- [ ] Shell history export for executed commands
- [ ] Tab-completion in Python and shell modes
- [ ] Block annotations and selective history export

