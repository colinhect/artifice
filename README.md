# Artifice

A minimal and transparent intelligence agent harness with a terminal user interface. Provides control over intelligence model interactions, code execution, and shell commands—without complex frameworks, protocols, or abstractions. Built with [Textual](https://github.com/Textualize/textual).

The intention is to provide a unified interface for both building and experimenting with precise prompts as well as full agentic flows.

## Features

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

### Tmux Integration

Artifice can execute shell commands in existing tmux sessions instead of isolated subprocesses. This allows:

- **Persistent shell state** - Environment variables, working directory, and shell history maintained
- **Real terminal sessions** - Commands run in actual terminal panes with full terminal capabilities
- **Visual debugging** - Watch command execution in real-time in the tmux pane
- **Stateful workflows** - Build on previous command state (activated virtualenvs, cd'd directories, etc.)
- **SSH sessions** - Target an active SSH session

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

### Running from Source

```bash
git clone <repository-url>
cd artifice/src
python -m artifice.app
```

## Roadmap

Future enhancements while maintaining the minimal harness philosophy:

- [ ] Additional model providers (OpenAI, Gemini, local models)
- [ ] Session export/import in portable formats
- [ ] Language Server Protocol (LSP) integration for code intelligence
- [ ] Additional language REPLs (Node.js, Ruby, etc.)
- [ ] Shell history export for executed commands
- [ ] Tab-completion in Python and shell modes
- [ ] Block annotations and selective history export
- [ ] VIM keybinding mode for text editing

