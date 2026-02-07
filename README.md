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

Set your API key for AI features:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Running

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

- **Ctrl+Up/Down** - Navigate through blocks
- **Enter** - Execute input
- **Ctrl+C** - Cancel current operation
- **Ctrl+Q** - Exit application
- **Ctrl+O** - Toggle markdown rendering (on current block or subsequent blocks)
- **Ctrl+L** - Clear

## AI Agent Integration

### Architecture

Artifice decouples AI suggestions from execution. When an AI agent makes a tool call to execute Python or shell commands, you are prompted to review the proposed action. You can:

1. **Execute** - Run the code as suggested
2. **Edit** - Modify the code before running
3. **Skip** - Reject the suggestion and continue

This design enables agentic workflows while keeping you fully responsible and in control of all code execution.

### Supported Agents

- **Claude** (via Anthropic API) - Streaming support with tool calling
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
- [ ] Additional AI provider support (OpenAI, local models)
- [ ] Session export/import
- [ ] LSP integration with agent
- [ ] Other programming languages
- [ ] Export commands to shell history

