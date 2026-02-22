# Artifice

A GNU-style command-line tool for LLM interactions, plus an experimental agentic TUI.

## art - The CLI Tool

`art` is a simple input/output tool for prompting LLMs from the command line. It reads from stdin or an argument and outputs to stdout—designed to compose with other Unix tools.

Tool support allows agents to execute operations like reading files, running shell commands, and searching code—all with interactive approval.

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

# Tool configuration (optional)
tools: ["*"]                       # Enable all tools
tool_approval: ask                 # "ask", "auto", or "deny"
tool_allowlist: ["read", "glob"]  # Always allow these tools
```

**Tool Configuration Options:**

- `tools`: List of tool patterns to enable. Use `"*"` for all tools, or specific names like `["read", "write", "glob"]`
- `tool_approval`: Approval mode for tool calls
  - `ask`: Prompt for approval on each tool call (default)
  - `auto`: Automatically approve all tool calls
  - `deny`: Automatically deny all tool calls
- `tool_allowlist`: List of tool patterns that are always allowed without prompting

You can also override these settings via command-line flags:
```bash
art --tools "*" --tool-approval auto "Your prompt here"
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

### Tool Support

`art` supports tool calls that allow the LLM to interact with your system. Tools include file operations, shell commands, and code execution. Each tool call requires approval (unless configured otherwise).

**Available Tools:**
- `read` - Read file contents
- `write` - Write or create files
- `edit` - Edit files by string replacement
- `glob` - Search for files matching patterns
- `shell` - Execute shell commands
- `python` - Execute Python code

**Basic Usage:**

```bash
# Enable all tools and approve interactively
art --tools "*" "Read the README.md file and summarize it"

# Enable specific tools only
art --tools "read,glob" "Find all Python files and check for TODOs"

# Auto-approve all tool calls (use with caution)
art --tools "*" --tool-approval auto "Search for all .txt files and count lines"

# Never allow tools, even if agent requests them
art --tools "*" --tool-approval deny "What files are in this directory?"
```

**Interactive Approval:**

When `--tool-approval ask` (default), you'll be prompted for each tool call:

```
🛠️  Tool Call: read
   Arguments: {
     "path": "README.md"
   }

Approve this tool call? [Y]es [N]o [A]lways [O]nce:
```

- **Yes** - Approve this call
- **No** - Deny this call
- **Always** - Always allow this tool type
- **Once** - Allow this tool once this session

**Examples:**

```bash
# Read and analyze code
cat src/main.py | art --tools "read,write" "Review this code and write feedback to review.md"

# Search codebase
art --tools "glob,read" "Find all test files and list the first 10 lines of each"

# Edit files
art --tools "edit" "In config.py, change timeout from 30 to 60 seconds"

# Process with shell commands
art --tools "shell" "Count lines of code in src/ directory and show top 5 largest files"
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
  --list-agents       List available agent names
  --list-prompts      List available prompt names
  --print-completion {bash,zsh,fish}
                      Print shell completion script
  --tools TOOLS       Enable tools (comma-separated patterns, e.g., "read,write",
                      or "*" for all)
  --tool-approval {ask,auto,deny}
                      Tool approval mode: ask (interactive), auto (allow all),
                      or deny (disable all) [default: ask]
```

### Shell Completion

Art supports shell completion for Bash, Zsh, and Fish shells with dynamic agent and prompt name completion.

#### Zsh

```bash
# Install completion to zsh site-functions
art --print-completion zsh | sudo tee /usr/local/share/zsh/site-functions/_art

# Or manually add to your zsh configuration
art --print-completion zsh > ~/.zsh/completions/_art
# Then add to ~/.zshrc:
# fpath=(~/.zsh/completions $fpath)
# autoload -U compinit && compinit
```

#### Bash

```bash
# Install system-wide
sudo art --print-completion bash > /etc/bash_completion.d/art

# Or add to your ~/.bashrc or ~/.bash_profile:
art --print-completion bash >> ~/.bash_completion
source ~/.bash_completion
```

#### Fish

```bash
# Install to fish completions directory
art --print-completion fish > ~/.config/fish/completions/art.fish
```

After installation, restart your shell or reload your configuration:

```bash
exec zsh  # or exec bash
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

# Tool settings
tools: ["read", "write", "glob", "edit"]  # List of tools to enable
tool_approval: ask                          # ask, auto, or deny
tool_allowlist: ["read", "glob"]           # Always allow these tools

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
