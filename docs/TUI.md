# Artifice TUI

An experimental terminal interface for interactive sessions with AI agents, Python REPL, and shell execution.

## Starting the TUI

```bash
artifice                    # Inline mode (default)
artifice --fullscreen       # Full-screen mode
artifice my-agent           # Use a specific agent
artifice --tmux main:0.0    # Use tmux for shell execution
```

### Command-Line Options

| Option | Description |
|--------|-------------|
| `[agent]` | Agent name from config |
| `--system-prompt` | Override system prompt |
| `--prompt-prefix` | Prefix for user prompts |
| `--thinking-budget` | Extended thinking token budget |
| `--fullscreen` | Run in full-screen mode |
| `--logging` | Enable logging to `artifice.log` |
| `--tmux TARGET` | Use tmux for shell execution |
| `--tmux-prompt PATTERN` | Regex matching shell prompt |

---

## Input Modes

Switch between three modes using keyboard shortcuts:

| Mode | Key | Prompt | Description |
|------|-----|--------|-------------|
| AI | `>` | `>` | Send prompts to the AI agent |
| Shell | `$` | `$` | Execute shell commands |
| Python | `]` | `]` | Execute Python code |

**Mode Switching:**
- Press `Insert` to cycle through modes
- Press `Esc` to return to Python mode
- Type `>`, `$`, or `]` on empty input to switch modes

---

## Keyboard Shortcuts

### Global

| Key | Action |
|-----|--------|
| `Ctrl+Q` | Quit the application |
| `F2` | Toggle footer/help |
| `Ctrl+C` | Cancel current execution |
| `Ctrl+I` | Focus input |
| `Ctrl+L` | Clear output |
| `Ctrl+O` | Toggle markdown rendering |
| `Ctrl+G` | Toggle agent context mode |
| `Ctrl+N` | Clear agent context |
| `Alt+↑/↓` | Navigate between blocks |
| `PgUp/PgDn` | Scroll output |

### Input

| Key | Action |
|-----|--------|
| `Enter` | Submit (single line) |
| `Ctrl+S` | Submit (always) |
| `Ctrl+J` | Insert newline |
| `Ctrl+K` | Clear input |
| `Ctrl+R` | Search history |
| `↑/↓` | Navigate history (at top/bottom of input) |

### Search Modes

| Key | Action |
|-----|--------|
| `/` (empty input) | Search and load prompts |
| `@` (empty input) | Search and attach files |
| `Esc` | Exit search |

---

## AI Mode Features

### Sending Prompts

Type `>` to enter AI mode, then enter your prompt:

```
> Explain this error message
```

### Slash Commands

In AI mode, commands starting with `/` have special meaning:

| Command | Description |
|---------|-------------|
| `/clear` | Clear agent conversation context |
| `/exit` | Exit the application |
| `/help` | Show available commands |
| `/<name>` | Load prompt from `~/.artifice/prompts/<name>.md` |

### Attaching Files

Type `@` on an empty line to search and attach files to the conversation. The file content is sent to the agent as context.

### Agent Context Mode

Press `Ctrl+G` to toggle agent context mode. When enabled:
- All commands (shell, Python) and their outputs are sent to the agent
- Blocks highlighted with a border are in the agent's context
- Useful for giving the agent awareness of your work

---

## Shell Mode

Execute shell commands directly:

```bash
$ ls -la
$ git status
$ npm test
```

### Tmux Integration

Use `--tmux` to execute commands in an existing tmux pane:

```bash
artifice --tmux main:0.0 --tmux-prompt '^\$ '
```

This allows the agent to see and interact with long-running processes.

---

## Python Mode

Execute Python code in an isolated REPL:

```python
] import pandas as pd
] df = pd.read_csv('data.csv')
] df.head()
```

The Python environment persists across executions within a session.

---

## Blocks and Navigation

Output is organized into blocks that can be navigated and manipulated:

- **Agent blocks**: AI prompts and responses
- **Code blocks**: Shell/Python execution results
- **Tool blocks**: Tool calls with execution status
- **System blocks**: System messages, loaded prompts

Press `Alt+↑/↓` to navigate between blocks. Press `Enter` on a selected block to copy its code to the input.

---

## Configuration

The TUI reads from `~/.artifice/config.yaml`:

```yaml
agent: glm4
banner: true
streaming_fps: 30
send_user_commands_to_agent: true
show_tool_output: true

agents:
  glm4:
    api_key_env: HF_TOKEN
    provider: openai
    model: zai-org/GLM-4.7-Flash:novita
    base_url: https://router.huggingface.co/v1
```

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `banner` | `true` | Show ASCII banner on startup |
| `streaming_fps` | `30` | Streaming update frequency |
| `send_user_commands_to_agent` | `true` | Auto-send commands to agent |
| `show_tool_output` | `true` | Display tool output in TUI |
| `agent_markdown_enabled` | `true` | Render AI output as markdown |
| `shell_markdown_enabled` | `false` | Render shell output as markdown |
| `python_markdown_enabled` | `false` | Render Python output as markdown |

---

## Tips

1. **Use `Ctrl+G`** to let the agent observe your work without manual context sharing
2. **Press `/` on empty input** to quickly load saved prompts
3. **Press `@`** to attach relevant files to the conversation
4. **Navigate with `Alt+↑/↓`** to review and re-execute previous code
5. **Use `--tmux`** for interactive or long-running processes the agent should control
