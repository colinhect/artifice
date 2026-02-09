# Artifice

A minimal Python-based terminal user interface for interacting with intelligence models to write and execute code or system commands. Built with [Textual](https://github.com/Textualize/textual).

## Features

### Core Features
- **Minimal Interface to AI Models** - Uses concise simple prompting without using MCP or ACP
- **Interactive Python Console** - Full REPL with persistent session
- **Interactive Shell** - Execute shell commands without leaving the environment
- **Markdown Rendering** - AI responses rendered with syntax highlighting
    - Output from Python or shell commands can be rendered as markdown
- **Multiline Input** - Write complex code with Python auto-complete
- **Command History** - Persistent history across sessions
- **Textual Integration** - Python commands that result in Textual objects are mounted directly in the output, allowing on-the-fly interface generation

### Block Navigation
- **Ctrl+Up/Down** - Navigate between previous inputs and outputs (blocks)
- **Edit Blocks** - Modify and re-execute previous inputs
- **Save/Restore** - Persist important blocks across sessions

### AI Agent Integration
- **Code/command Execution** - AI can propose Python code or shell commands
- **Human Approval** - Review/edit actions before execution
- **Selective Context** - Mark which blocks should be given as context to AI

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

- `>` - **AI prompt mode** - Prompt the intellegence model
- `]` - **Python mode** - Execute Python code
- `$` - **Shell mode** - Run shell commands

## Keybindings

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

### Mode Switching (when input is empty)
- **>** - Switch to AI Agent mode
- **$** - Switch to Shell mode
- **]** - Switch to Python mode

### Application
- **Ctrl+Q** - Exit application
- **Ctrl+O** - Toggle markdown rendering (on current block or subsequent blocks)
- **Ctrl+L** - Clear output
- **F2** - Toggle help footer

## AI Agent Integration

### Architecture

Artifice decouples AI suggestions from execution. When an AI agent makes a tool call to execute Python or shell commands, you are prompted to review the proposed action. You can:

1. **Execute** - Run the code as suggested
2. **Edit** - Modify the code before running
3. **Skip** - Reject the suggestion and continue

This design enables agentic workflows while keeping you fully responsible and in control of all code execution.

### Supported Agents

- **Claude** (via Anthropic API) - Streaming support with tool calling
- **Ollama** (local models) - Run models locally with streaming support
- Custom agents via `AgentBase` subclass

### Running from Source

```bash
git clone <repository-url>
cd artifice 
python src/artifice/app.py
```

## Configuration

### Claude (Anthropic)
Set your API key for Claude:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

### Ollama (Local Models)
Install and run Ollama locally:
```bash
# Install Ollama from https://ollama.ai
ollama pull llama3.1  # or any other model
ollama serve  # runs on localhost:11434 by default
```

Optionally set custom Ollama host:
```bash
export OLLAMA_HOST="http://localhost:11434"
```

## Roadmap

Planned features and improvements:

- [ ] VIM keybinding mode for text editing
- [ ] Additional AI provider support (OpenAI, Gemini)
    - [ ] GitHub Copilot integration
- [ ] Session export/import
- [ ] LSP integration with agent
- [ ] Other programming languages
- [ ] Export commands to shell history
- [ ] Tab-completion in Python and shell mode
- [ ] Ability to remove history entry or annotate/export

