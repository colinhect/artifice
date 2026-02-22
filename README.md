# Artifice

A GNU-style command-line tool for LLM interactions, plus an experimental agentic TUI.

## art - The CLI Tool

`art` is a simple input/output tool for prompting LLMs from the command line. It reads from stdin or an argument and outputs to stdout—designed to compose with other Unix tools.

### Installation

```bash
pip install artifice
```

### Quick Start

```bash
# Simple prompt
art -a glm4 "What is 2+2?"

# Pipe input
echo "Explain this:" | cat - README.md | art -a glm4

# Use in pipelines
cat error.log | art -a debug "What's causing this error?"
```

### Configuration

Create `~/.config/artifice/init.yaml`:

```yaml
agent: glm4

agents:
  glm4:
    api_key_env: HF_TOKEN
    provider: openai
    model: zai-org/GLM-4.7-Flash:novita
    base_url: https://router.huggingface.co/v1

  minimax:
    api_key_env: HF_TOKEN
    provider: openai
    model: MiniMaxAI/MiniMax-M2.5
    base_url: https://router.huggingface.co/v1

prompts:
  summarize: |
    Summarize the input concisely. Use bullet points for key items.

  review: |
    Review the code for bugs, security issues, and improvements.
    Be concise and actionable.
```

### Usage Patterns

```bash
# Use default agent
art "Write a haiku about recursion"

# Specify agent
art -a minimax "Explain quantum computing"

# Use named prompt
cat ARCHITECTURE.md | art -p summarize

# Combine agent and prompt
cat src/main.py | art -a minimax -p review

# Explain code
git diff HEAD~1 | art -a minimax "Explain these changes"

# Convert formats
cat data.csv | art "Convert to JSON"

# Generate tests
cat mymodule.py | art "Write pytest tests for this module"

# Documentation
cat lib.rs | art "Write rustdoc comments for all public functions"

# Brainstorm
art "10 creative names for a CLI tool that pipes data to LLMs"

# Combine with other tools
grep -r "TODO" src/ | art "Prioritize and categorize these TODOs"

# Process multiple files
cat README.md CHANGELOG.md | art -p summarize
```

### Command Reference

```
art [OPTIONS] [PROMPT]

Arguments:
  PROMPT              Prompt string (reads from stdin if not provided)

Options:
  -a, --agent AGENT   Agent name from config (default: configured default)
  -p, --prompt-name NAME
                      Named prompt from config to use as system prompt
  -s, --system-prompt SYSTEM_PROMPT
                      Override system prompt
  --logging           Enable debug logging to stderr
```

---

## artifice - Experimental Agentic TUI

`artifice` is an interactive terminal interface with full agentic capabilities—Python/Shell execution, tool calls, and persistent conversation.

> **Note**: The TUI is experimental. For most use cases, `art` is the recommended interface.

### Running

```bash
artifice
```

### Features

- **Python REPL** - Full interactive Python console with persistent state
- **Shell Commands** - Execute bash commands with streaming output
- **Tmux Integration** - Route commands to existing tmux panes
- **Tool Calls** - File operations, web fetch, code execution
- **Markdown Rendering** - Responses rendered as formatted markdown
- **Block Navigation** - Navigate, edit, and re-execute previous inputs

### Mode Switching

Type a special character when input is empty to switch modes:

- `>` - AI prompt mode
- `]` - Python mode
- `$` - Shell mode

### Key Bindings

| Key | Action |
|-----|--------|
| Enter | Execute (single-line) or newline (multi-line) |
| Ctrl+S | Submit |
| Ctrl+C | Cancel |
| Alt+Up/Down | Navigate output blocks |
| Ctrl+R | History search |
| Ctrl+Q | Quit |

---

## Configuration Reference

Configuration file: `~/.config/artifice/init.yaml`

```yaml
# Default agent
agent: glm4

# Agent definitions
agents:
  glm4:
    api_key_env: HF_TOKEN           # Env var name for API key
    provider: openai                # Provider type
    model: zai-org/GLM-4.7-Flash:novita  # Model name
    base_url: https://router.huggingface.co/v1
    system_prompt: "You are helpful." # Optional system prompt
    tools: ["*"]                      # Optional: tool access

  minimax:
    api_key_env: HF_TOKEN
    provider: openai
    model: MiniMaxAI/MiniMax-M2.5
    base_url: https://router.huggingface.co/v1

# Named prompts (use with -p option)
prompts:
  summarize: |
    Summarize the input concisely. Use bullet points for key items.
  review: |
    Review the code for bugs, security issues, and improvements.
    Be concise and actionable.

# Global settings
system_prompt: null
prompt_prefix: null
show_tool_output: true
```

## Running from Source

```bash
git clone https://github.com/colinhill/artifice.git
cd artifice
pip install -e .
art -a glm4 "Hello"
```

## License

MIT
