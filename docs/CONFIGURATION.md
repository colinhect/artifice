# Configuration and Extension Guide

**Version:** 0.1.0
**Last Updated:** 2026-02-12

## Overview

Artifice provides a flexible configuration system allowing users to customize behavior, appearance, and agent integration through a Python configuration file and command-line arguments. This document covers configuration options, extension points, and customization patterns.

---

## Configuration System

### Configuration Sources

Configuration is loaded from three sources in priority order:

1. **Command-line arguments** (highest priority)
2. **User configuration file** (`~/.config/artifice/init.py`)
3. **Built-in defaults** (lowest priority)

### Configuration File Location

**Standard Location:**
```
~/.config/artifice/init.py
```

**XDG Support:**
```
$XDG_CONFIG_HOME/artifice/init.py
```

### Configuration Object

All settings are accessed via the `config` object:

```python
# ~/.config/artifice/init.py

# Agent configuration
config.provider = "anthropic"
config.model = "claude-sonnet-4-5"
config.system_prompt = "You are a helpful coding assistant."
config.prompt_prefix = None

# Display settings
config.banner = False
config.python_markdown = False
config.agent_markdown = True
config.shell_markdown = False

# Behavior
config.auto_send_to_agent = True

# Shell
config.shell_init_script = None

# Sessions
config.save_sessions = True
config.sessions_dir = None  # Uses default: ~/.artifice/sessions/
```

---

## Agent Configuration

### Provider Selection

```python
config.provider = "anthropic"  # or "ollama", "copilot", "simulated"
```

**Available Providers:**

#### Anthropic (Claude)
```python
config.provider = "anthropic"
config.model = "claude-sonnet-4-5"  # or "claude-haiku-4-5", "claude-opus-4-6"
```

**Requirements:**
- `ANTHROPIC_API_KEY` environment variable
- `anthropic` package installed

**Models:**
- `claude-opus-4-6`: Most capable, slowest
- `claude-sonnet-4-5`: Balanced (default)
- `claude-haiku-4-5`: Fastest, least expensive

#### Ollama (Local Models)
```python
config.provider = "ollama"
config.model = "llama3.1"  # or "codellama", "mistral", etc.
config.ollama_host = "http://localhost:11434"  # optional
```

**Requirements:**
- Ollama installed and running
- `ollama` package installed
- Model pulled: `ollama pull llama3.1`

**Models:** Any model supported by Ollama

#### GitHub Copilot
```python
config.provider = "copilot"
config.model = "gpt-4"  # or "gpt-3.5-turbo"
```

**Requirements:**
- GitHub Copilot subscription
- `github-copilot-sdk` package installed

#### Simulated (Testing)
```python
config.provider = "simulated"
```

**Use Cases:**
- Testing UI without API calls
- Development mode
- Offline usage

### Model Selection

```python
config.model = "claude-sonnet-4-5"
```

**Override via CLI:**
```bash
artifice --model claude-opus-4-6
```

### System Prompt

```python
config.system_prompt = """You are a helpful coding assistant.
You provide concise, accurate code examples.
Always explain your reasoning."""
```

**Use Cases:**
- Define agent behavior
- Set domain expertise (e.g., "You are a Python expert")
- Specify output format preferences

**Example:**
```python
config.system_prompt = """You are a Python expert specializing in data science.
Prefer pandas and numpy for data manipulation.
Always include type hints in function signatures.
Explain time/space complexity for algorithms."""
```

### Prompt Prefix

```python
config.prompt_prefix = "Answer concisely."
```

**Effect:** Prefix added to **every** user prompt:
```python
# User enters: "How do I sort a list?"
# Agent receives: "Answer concisely. How do I sort a list?"
```

**Use Cases:**
- Enforce consistent style (e.g., "Be concise")
- Add context (e.g., "Assume Python 3.11+")

### Extended Thinking

```python
config.thinking_budget = 10000  # Token budget for thinking
```

**Supported Providers:** Anthropic (Claude)

**Effect:**
- Agent shows reasoning process in `ThinkingOutputBlock`
- Improves quality of complex responses
- Increases cost and latency

**Recommended Values:**
- `5000`: Light thinking (simple problems)
- `10000`: Medium thinking (moderate complexity)
- `20000`: Deep thinking (complex algorithms, architecture)

**Example:**
```bash
artifice --thinking-budget 10000
```

---

## Display Configuration

### Banner

```python
config.banner = True
```

**Effect:** Show ASCII art banner on startup:
```
┌─┐┬─┐┌┬┐┬┌─┐┬┌─┐┌─┐
├─┤├┬┘ │ │├┤ ││  ├┤
┴ ┴┴└─ ┴ ┴└  ┴└─┘└─┘
```

**CLI Override:**
```bash
artifice --banner        # Enable
artifice --no-banner     # Disable (if added in future)
```

### Markdown Rendering

Control per-mode markdown rendering:

```python
config.python_markdown = False  # Python output as plain text
config.agent_markdown = True    # Agent output as Markdown
config.shell_markdown = False   # Shell output as plain text
```

**Effect:**
- `True`: Output rendered with Markdown parser (syntax highlighting, tables, etc.)
- `False`: Output shown as plain monospace text

**Runtime Toggle:** `Ctrl+O` toggles current mode's markdown setting

**Per-Block Toggle:** `Ctrl+O` when block highlighted toggles that block

**Recommendations:**
- **Python:** `False` (preserves exact formatting)
- **Agent:** `True` (nicely formatted responses)
- **Shell:** `False` (ANSI escape codes may conflict)

---

## Behavior Configuration

### Auto-Send to Agent

```python
config.auto_send_to_agent = True
```

**Effect:**
- When `True`: Execution results automatically sent to agent
- When `False`: User must manually prompt agent with results

**Workflow with Auto-Send:**
```
1. User: "Generate code to parse JSON"
2. Agent: [Generates code block]
3. User: [Executes code via Enter]
4. Auto-send: Execution result sent to agent
5. Agent: [Responds based on output, e.g., "The code worked!"]
```

**Workflow without Auto-Send:**
```
1. User: "Generate code to parse JSON"
2. Agent: [Generates code block]
3. User: [Executes code via Enter]
4. [No auto-send - user must manually prompt if needed]
```

**Runtime Toggle:** `Ctrl+G` toggles auto-send mode

**Visual Indicator:** Blue left border on input area when enabled

**Recommendations:**
- Enable for collaborative coding sessions
- Disable for batch code execution

---

## Shell Configuration

### Init Script

```python
config.shell_init_script = """
source ~/.bashrc
alias ll='ls -la'
export PATH="/custom/bin:$PATH"
cd ~/projects
"""
```

**Execution:** Run once before first shell command

**Use Cases:**
- Source shell configuration
- Set up environment variables
- Define aliases
- Change working directory
- Load modules (e.g., `module load python`)

**Example: Conda Environment**
```python
config.shell_init_script = """
source ~/miniconda3/etc/profile.d/conda.sh
conda activate myenv
"""
```

**Example: Node.js Version**
```python
config.shell_init_script = """
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
nvm use 18
"""
```

---

## Session Configuration

### Session Saving

```python
config.save_sessions = True
```

**Effect:**
- When `True`: Conversations saved to `~/.artifice/sessions/session_YYYYMMDD_HHMMSS.md`
- When `False`: Sessions not saved (memory-only)

**Session Format:** Markdown file with:
- Timestamp
- Agent configuration
- All blocks (user prompts, agent responses, code, output)

**Use Cases:**
- Review past conversations
- Share session transcripts
- Audit agent interactions

### Sessions Directory

```python
config.sessions_dir = "/custom/path/to/sessions"
```

**Default:** `~/.artifice/sessions/`

**Custom Location:**
```python
config.sessions_dir = "~/Documents/artifice-sessions"
```

**CLI Override:**
```bash
artifice --sessions-dir ~/Documents/artifice-sessions
```

---

## Command-Line Arguments

### Provider and Model

```bash
artifice --provider anthropic --model claude-opus-4-6
```

**Override Config:**
```python
# init.py
config.provider = "ollama"
config.model = "llama3.1"
```

```bash
# CLI overrides init.py
artifice --provider anthropic --model claude-sonnet-4-5
```

### System Prompt

```bash
artifice --system-prompt "You are a Python expert."
```

### Prompt Prefix

```bash
artifice --prompt-prefix "Be concise."
```

### Banner

```bash
artifice --banner
```

### Thinking Budget

```bash
artifice --thinking-budget 10000
```

### Fullscreen Mode

```bash
artifice --fullscreen
```

**Effect:**
- **Normal mode (default):** Inline terminal (output remains after exit)
- **Fullscreen mode:** Clears screen, restores on exit

### Logging

```bash
artifice --logging
```

**Effect:**
- Enables debug logging to `artifice_agent.log`
- Logs agent interactions, API calls, errors

**Log Format:**
```
2026-02-12 14:30:00 - artifice.agent.claude - DEBUG - [ClaudeAgent] Sending prompt: ...
2026-02-12 14:30:01 - artifice.agent.claude - DEBUG - [ClaudeAgent] Received response (1234 chars): ...
```

---

## Environment Variables

### ANTHROPIC_API_KEY

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Required for:** Anthropic provider

### OLLAMA_HOST

```bash
export OLLAMA_HOST="http://localhost:11434"
```

**Default:** `http://localhost:11434`

**Use Cases:**
- Remote Ollama server
- Custom port

### XDG_CONFIG_HOME

```bash
export XDG_CONFIG_HOME="~/.config"
```

**Effect:** Changes config file location to `$XDG_CONFIG_HOME/artifice/init.py`

---

## Extension Points

### Custom Settings

Store arbitrary settings:

```python
config.set("my_custom_setting", "value")
```

Retrieve later:

```python
value = config.get("my_custom_setting", default="fallback")
```

**Use Cases:**
- Store user preferences
- Plugin configuration
- Experimental features

### Custom Agents

Create custom agent by implementing `AgentBase`:

```python
# custom_agent.py
from artifice.agent.common import AgentBase, AgentResponse

class CustomAgent(AgentBase):
    async def send_prompt(self, prompt, on_chunk=None, on_thinking_chunk=None):
        # Call your custom API
        response = await my_api.chat(prompt)

        # Stream chunks
        for chunk in response.stream():
            if on_chunk:
                on_chunk(chunk)

        return AgentResponse(text=response.text)

    def clear_conversation(self):
        # Reset conversation state
        self.messages = []
```

**Integration:**
```python
# init.py
from custom_agent import CustomAgent

# Store reference for later use
config.set("custom_agent_class", CustomAgent)
```

**Activate:**
```python
# In terminal.py (requires code modification)
if config.get("use_custom_agent"):
    AgentClass = config.get("custom_agent_class")
    self._agent = AgentClass(model=model, system_prompt=system_prompt)
```

### Custom Executors

Create custom executor for new languages:

```python
# custom_executor.py
class JavaScriptExecutor:
    def __init__(self):
        self._namespace = {}

    async def execute(self, code, on_output=None, on_error=None):
        # Execute JavaScript via Node.js
        process = await asyncio.create_subprocess_exec(
            "node", "-e", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if on_output:
            on_output(stdout.decode())
        if on_error and stderr:
            on_error(stderr.decode())

        status = ExecutionStatus.SUCCESS if process.returncode == 0 else ExecutionStatus.ERROR

        return ExecutionResult(
            code=code,
            status=status,
            output=stdout.decode(),
            error=stderr.decode()
        )
```

**Integration:** Requires code modification to register executor.

### Custom Themes

Define custom color scheme:

```python
# init.py (requires code modification in app.py)
from textual.theme import Theme

def create_custom_theme():
    return Theme(
        name="custom",
        primary="#FF6B6B",      # Custom primary color
        secondary="#4ECDC4",    # Custom secondary color
        accent="#FFE66D",       # Custom accent color
        # ... other colors
    )

config.set("custom_theme", create_custom_theme())
```

---

## Advanced Patterns

### Environment-Specific Configuration

```python
# init.py
import os

if os.environ.get("ARTIFICE_ENV") == "production":
    config.provider = "anthropic"
    config.model = "claude-opus-4-6"
    config.save_sessions = True
else:
    config.provider = "simulated"
    config.save_sessions = False
```

### Conditional Agent Selection

```python
# init.py
import os

if os.environ.get("ANTHROPIC_API_KEY"):
    config.provider = "anthropic"
    config.model = "claude-sonnet-4-5"
elif os.environ.get("OLLAMA_HOST"):
    config.provider = "ollama"
    config.model = "llama3.1"
else:
    config.provider = "simulated"
```

### Project-Specific Prompts

```python
# init.py
import os

cwd = os.getcwd()

if "my-python-project" in cwd:
    config.system_prompt = """You are a Python expert.
    This project uses pytest, black, and mypy.
    Follow PEP 8 conventions."""

elif "my-web-project" in cwd:
    config.system_prompt = """You are a JavaScript/TypeScript expert.
    This project uses React, TypeScript, and Tailwind CSS.
    Prefer functional components and hooks."""
```

### Dynamic Configuration

```python
# init.py
import datetime

# Use faster model during business hours
hour = datetime.datetime.now().hour
if 9 <= hour <= 17:
    config.model = "claude-haiku-4-5"  # Fast, cheap
else:
    config.model = "claude-sonnet-4-5"  # Balanced
```

---

## Configuration Security

### Sandboxed Execution

The `init.py` file runs in a restricted namespace:

**Allowed:**
- Basic types: `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`, `set`
- Basic functions: `len`, `range`, `enumerate`, `zip`, `print`
- `config` object

**Denied:**
- `__import__`: No imports allowed
- `open`: No file I/O
- `exec`: No code execution
- `eval`: No expression evaluation
- `compile`: No code compilation

**Rationale:** Prevent accidental or malicious code injection via config file.

### Safe Patterns

**✅ Safe:**
```python
config.provider = "anthropic"
config.model = "claude-sonnet-4-5"
config.system_prompt = "You are helpful."
```

**❌ Unsafe (won't work):**
```python
import requests  # Error: __import__ disabled
open("/etc/passwd")  # Error: open disabled
exec("malicious_code()")  # Error: exec disabled
```

### Environment Variables

**✅ Safe:**
```python
import os  # Error: can't import

# Workaround: Read environment before starting Artifice
# and pass via command-line arguments
```

**Better:**
```bash
export ARTIFICE_PROVIDER="anthropic"
artifice --provider "$ARTIFICE_PROVIDER"
```

---

## Troubleshooting

### Config Not Loading

**Symptom:** Settings in `init.py` ignored

**Solutions:**
1. Check file location: `~/.config/artifice/init.py`
2. Check syntax errors: `python3 ~/.config/artifice/init.py`
3. Enable logging: `artifice --logging` (check `artifice_agent.log`)
4. Override with CLI args to test

### Provider Not Found

**Symptom:** "Unsupported agent" error

**Solutions:**
1. Check provider name: `anthropic`, `ollama`, `copilot`, or `simulated`
2. Ensure package installed: `pip install anthropic` or `pip install ollama`
3. Check API key: `echo $ANTHROPIC_API_KEY`

### Model Not Found

**Symptom:** API error: "model not found"

**Solutions:**
1. Check model name spelling
2. For Ollama: `ollama pull <model-name>`
3. For Anthropic: Use valid model ID (e.g., `claude-sonnet-4-5`)

### Sessions Not Saving

**Symptom:** No files in `~/.artifice/sessions/`

**Solutions:**
1. Check `config.save_sessions = True`
2. Check directory permissions
3. Check custom `sessions_dir` path
4. Enable logging to see errors

---

## Configuration Examples

### Minimal Configuration

```python
# ~/.config/artifice/init.py
config.provider = "anthropic"
config.model = "claude-sonnet-4-5"
```

### Production Configuration

```python
# ~/.config/artifice/init.py

# Agent
config.provider = "anthropic"
config.model = "claude-opus-4-6"
config.system_prompt = """You are an expert software engineer.
Provide production-quality code with error handling.
Include type hints and docstrings.
Consider performance and security."""

# Display
config.banner = True
config.agent_markdown = True
config.python_markdown = False
config.shell_markdown = False

# Behavior
config.auto_send_to_agent = True

# Sessions
config.save_sessions = True
config.sessions_dir = "~/Documents/artifice-sessions"
```

### Development Configuration

```python
# ~/.config/artifice/init.py

# Agent
config.provider = "simulated"

# Display
config.banner = False
config.agent_markdown = True

# Behavior
config.auto_send_to_agent = False

# Sessions
config.save_sessions = False
```

### Data Science Configuration

```python
# ~/.config/artifice/init.py

# Agent
config.provider = "anthropic"
config.model = "claude-sonnet-4-5"
config.system_prompt = """You are a data science expert.
Prefer pandas, numpy, and scikit-learn.
Always include visualizations using matplotlib or seaborn.
Explain statistical methods clearly."""

# Shell init
config.shell_init_script = """
source ~/miniconda3/etc/profile.d/conda.sh
conda activate data-science
"""

# Display
config.python_markdown = False  # Preserve dataframe formatting
config.agent_markdown = True

# Behavior
config.auto_send_to_agent = True
```

---

## Future Configuration Options

### Planned Settings

```python
# Keyboard bindings
config.vim_mode = True

# Editor
config.editor = "vim"  # External editor for multi-line input

# LSP
config.lsp_enabled = True
config.lsp_server = "pyright"

# Plugins
config.plugins = ["custom_plugin"]

# History
config.history_size = 5000
config.history_dedup = True

# Performance
config.lazy_rendering = True
config.batch_size = 100
```

### Plugin System

```python
# init.py
config.plugins = [
    "git_integration",  # Add git commands
    "notebook_export",  # Export as Jupyter notebook
    "code_formatter",   # Auto-format code blocks
]
```

**Plugin Interface:**
```python
class PluginBase:
    def on_load(self, terminal):
        # Initialize plugin
        pass

    def on_block_created(self, block):
        # React to block creation
        pass

    def add_commands(self):
        # Register custom commands
        return {"/format": self.format_code}
```
