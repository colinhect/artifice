# Artifice

Experimental Python-based terminal user interface for interacting with intelligence models to write and execute code or system commands. Built with [Textual](https://github.com/Textualize/textual).

## Installation

Install with AI support:
```bash
pip install -e ".[ai]"
```

For basic usage without AI features:
```bash
pip install -e .
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

## Running

Run with Claude:
```bash
artifice --agent-type claude
```

Run with Ollama:
```bash
artifice --agent-type ollama
```

Run without AI:
```bash
artifice
```

## Usage

### Mode Switching

Artifice has three input modes. Switch modes by typing a special character when the input is empty:

- `?` - **AI Agent mode** - Ask questions and get AI assistance
- `>` - **Python mode** - Execute Python code interactively
- `$` - **Shell mode** - Run shell commands

### Example: Python Session

```
> x = [1, 2, 3, 4, 5]
> sum(x)
15
```

### Example: AI Interaction

```
? What's the average of the list x?
```

The AI might suggest:
```python
sum(x) / len(x)
```

You'll see the proposed code and can choose to execute it, modify it, or skip it.

### Example: Shell Commands

```
$ ls -la
$ git status
```

## Features

### Core Features
- **Interactive Python Console** - Full REPL with persistent session
- **Interactive Shell** - Execute shell commands without leaving the environment
- **Markdown Rendering** - AI responses rendered with syntax highlighting
- **Multiline Input** - Write complex code with Python auto-complete
- **Command History** - Persistent history across sessions
- **Textual Integration** - Python commands that result in Textual objects are mounted directly in the output, allowing on-the-fly interface generation

### Block Navigation
- **Ctrl+Up/Down** - Navigate between previous inputs and outputs (blocks)
- **Edit Blocks** - Modify and re-execute previous inputs
- **Save/Restore** - Persist important blocks across sessions

### AI Agent Integration
- **Tool Calling** - AI can propose Python code or shell commands
- **Agentic Loops** - Multiple tool calls in a single conversation
- **Human Approval** - Review every action before execution
- **Selective Context** - Mark which blocks should be given as context to AI.

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
- **?** - Switch to AI Agent mode
- **$** - Switch to Shell mode
- **>** - Switch to Python mode

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

## Roadmap

Planned features and improvements:

- [ ] VIM keybinding mode for text editing
- [ ] GitHub Copilot integration
- [ ] Additional AI provider support (OpenAI, Gemini)
- [ ] Session export/import
- [ ] LSP integration with agent
- [ ] Other programming languages
- [ ] Export commands to shell history
- [ ] Tab-completion in Python and shell mode
- [ ] CTRL+R fuzzy history search
- [ ] Ability to remove history entry or annotate/export

