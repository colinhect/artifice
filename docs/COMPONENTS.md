# Component Design

**Version:** 0.1.0
**Last Updated:** 2026-02-12

## Overview

This document provides detailed design specifications for each major component in the Artifice architecture. Components are organized by layer and responsibility.

---

## Application Layer

### ArtificeApp

**File:** `src/artifice/app.py`

**Responsibility:** Root Textual application managing global concerns.

**Key Features:**
- Theme management (Nord-inspired color scheme)
- Global keyboard bindings
- Configuration loading and precedence
- Inline terminal mode support
- Notification system for warnings/errors

**Configuration Flow:**
1. Load config from `~/.config/artifice/init.py`
2. Override with command-line arguments
3. Pass merged config to `ArtificeTerminal`

**Bindings:**
- `Ctrl+Q`: Quit application
- `F2`: Toggle help footer

---

### ArtificeHeader

**File:** `src/artifice/app.py`

**Responsibility:** Display banner and visual decoration.

**Design:**
- ASCII art banner (optional, controlled by `config.banner`)
- Gradient fade effect using Unicode block characters
- Minimal height impact (collapses when banner disabled)

**Visual Example:**
```
┌─┐┬─┐┌┬┐┬┌─┐┬┌─┐┌─┐
├─┤├┬┘ │ │├┤ ││  ├┤
┴ ┴┴└─ ┴ ┴└  ┴└─┘└─┘
█ █ ▓ ▓ ▒ ▒ ░ ░ · ·
```

---

## Terminal Layer

### ArtificeTerminal

**File:** `src/artifice/terminal.py`

**Responsibility:** Main orchestrator coordinating I/O, execution, and agents.

**Component Composition:**
```
ArtificeTerminal
├─ TerminalOutput (output blocks container)
├─ TerminalInput (multi-mode input)
├─ PinnedOutput (widget display area)
├─ CodeExecutor (Python REPL)
├─ ShellExecutor (Bash shell)
└─ AgentBase (AI agent, optional)
```

**State Variables:**
- `_auto_send_to_agent`: Whether execution results auto-send to agent
- `_context_blocks`: List of blocks in agent context
- `_current_task`: Active async task (for cancellation)
- `_current_detector`: Active streaming fence detector
- `_thinking_block`: Active thinking output block
- `_loading_block`: Initial loading indicator before first chunk
- `_chunk_buffer` / `_thinking_buffer`: Batching buffers for streaming

**Key Methods:**

#### `on_terminal_input_submitted(event)`
Routes submitted input based on mode:
- AI mode → `_handle_agent_prompt()`
- Python mode → `_execute_code(language="python")`
- Shell mode → `_execute_code(language="bash")`

Auto-sends execution results to agent if `_auto_send_to_agent` is enabled.

#### `_stream_agent_response(agent, prompt)`
Orchestrates streaming agent response:
1. Create `StreamingFenceDetector` (deferred start)
2. Create initial loading block
3. Call `agent.send_prompt()` with callbacks
4. Buffer chunks via message passing (`StreamChunk`, `StreamThinkingChunk`)
5. Batch-process chunks on event loop ticks
6. Finalize detector and blocks after streaming completes
7. Auto-highlight last code block

**Why deferred detector start?** Thinking blocks must be created before text blocks to maintain visual order.

#### `_execute_code(code, language, code_input_block, in_context)`
Executes Python or Bash code:
1. Create or reuse `CodeInputBlock`
2. Create buffered output callbacks
3. Call executor with streaming callbacks
4. Update block status on completion
5. Mount Textual widgets if returned by Python code

#### `_make_output_callbacks(markdown_enabled, in_context)`
Factory for creating buffered output callbacks:
- **Lazy block creation**: Block only created on first output
- **Batched flushing**: Output buffered and flushed on next event loop tick
- **Session saving**: Block saved to session on final flush

**Message Handlers:**

#### `on_stream_chunk(event)`
Handles text chunks from agent:
1. Start detector on first chunk (removes loading block)
2. Append to `_chunk_buffer`
3. Schedule batch processing if not already scheduled
4. `_process_chunk_buffer()` feeds buffered text to detector

#### `on_stream_thinking_chunk(event)`
Handles thinking chunks:
1. Append to `_thinking_buffer`
2. Schedule batch processing
3. `_process_thinking_buffer()` lazily creates thinking block and appends text

**Why batching?** Reduces render cycles by consolidating multiple chunks into single DOM update.

**Keyboard Bindings:**
- `Ctrl+I`: Focus input
- `Ctrl+L`: Clear output
- `Ctrl+O`: Toggle markdown rendering for current mode
- `Ctrl+C`: Cancel execution
- `Ctrl+G`: Toggle auto-send to agent
- `Ctrl+N`: Clear agent context
- `Alt+Up/Down`: Navigate blocks

---

## I/O Components

### TerminalOutput

**File:** `src/artifice/terminal_output.py`

**Responsibility:** Scrollable container for output blocks with navigation.

**Features:**
- Block highlighting (visual focus)
- Keyboard navigation (up/down, previous/next code)
- Block activation (copy to input)
- Block execution (re-run code)
- Numbered execution (press `1`-`9` to run block #N)
- Markdown toggling per block

**Block Management:**
- `_blocks`: List of all mounted blocks
- `_highlighted_index`: Index of currently highlighted block
- `_next_command_number`: Counter for numbering agent-proposed code blocks

**Navigation Modes:**
1. **Sequential**: Up/Down arrows move through all blocks
2. **Code-only**: Filtered navigation to `CodeInputBlock` only
3. **Numbered**: Direct execution of numbered blocks

**Keyboard Bindings:**
- `Up/Down`: Navigate to previous/next code block
- `End`: Move focus to input
- `Enter`: Execute highlighted code block
- `Ctrl+C`: Copy highlighted block to input
- `Ctrl+O`: Toggle markdown rendering for block
- `Insert`: Cycle language mode (Python ↔ Bash)
- `1`-`9`: Execute code block with that command number

**Block Highlighting:**
- Visual indicator: `highlighted` CSS class on block
- Auto-scroll to keep highlighted block visible
- Highlight persists during focus
- Clear on blur (move focus elsewhere)

**Command Numbering:**
When agent proposes code, blocks are numbered sequentially (1, 2, 3...) for quick execution. Numbers clear when agent sends a new response.

---

### TerminalInput

**File:** `src/artifice/terminal_input.py`

**Responsibility:** Multi-mode input with command history.

**Modes:**
- `python`: Execute Python code
- `shell`: Execute shell commands
- `ai`: Send prompt to AI agent

**Mode Switching:**
Type mode character when input is empty:
- `]` → Python mode
- `$` → Shell mode
- `>` → AI mode
- `Esc` → Return to Python mode

**Visual Indicators:**
- Prompt symbol changes per mode (`]`, `$`, `>`)
- Border highlight when in agent context

**Input Features:**
- Multi-line editing (Ctrl+J for newline)
- Command history (Up/Down when cursor at top/bottom)
- History search (Ctrl+R with autocomplete)
- Auto-complete for history items
- Input clearing (Ctrl+K)

**Submission Logic:**
- Single-line: `Enter` submits
- Multi-line: `Ctrl+S` submits, `Enter` inserts newline

**History Integration:**
Commands saved to `~/.artifice/history` and loaded on startup.

---

### PinnedOutput

**File:** `src/artifice/terminal_output.py`

**Responsibility:** Display area for pinned widget blocks.

**Use Case:**
When Python code returns a Textual widget, it can be "pinned" to remain visible below the input area while scrolling through output.

**Features:**
- Independent scrolling from main output
- Block highlighting and navigation
- Unpin action to remove blocks

**Keyboard Bindings:**
- `Up/Down`: Navigate pinned blocks
- `Ctrl+U`: Unpin highlighted block

**Visibility:**
Container hidden when empty, shown when blocks pinned.

---

## Block Components

### BaseBlock

**File:** `src/artifice/terminal_output.py`

**Responsibility:** Base class for all output blocks.

**Common Features:**
- Margin/padding for consistent spacing
- `in-context` CSS class for agent context highlighting
- Status indicator area (left border)

**CSS Classes:**
- `.in-context`: Blue left border indicating agent context inclusion
- `.highlighted`: Background highlight for navigation focus

---

### CodeInputBlock

**File:** `src/artifice/terminal_output.py:81`

**Responsibility:** Display syntax-highlighted code with execution status.

**Structure:**
```
┌─────────────────────────────┐
│ [⊙] print("hello")          │  ← Loading indicator + status icon
│  ✔  print("hello")          │  ← After execution (success)
│  ✖  1/0                     │  ← After execution (error)
│  1  print("hello")          │  ← Command number (agent-proposed code)
└─────────────────────────────┘
```

**Visual States:**
1. **Unexecuted**: Empty status indicator
2. **Loading**: Spinner indicator (`⊙`)
3. **Success**: Green checkmark (`✔`)
4. **Error**: Red X (`✖`)
5. **Numbered**: Command number for agent-proposed blocks

**Syntax Highlighting:**
- Always syntax-highlighted (even during streaming)
- Uses Textual's `highlight.highlight(code, language=...)`
- Languages: `python`, `bash`

**Streaming Behavior:**
During agent response streaming:
1. Block created with empty code
2. `update_code(text)` called incrementally
3. `finish_streaming()` called on completion

**Why always highlight?** Consistent rendering prevents visual "jumps" during finalization. (See MEMORY.md critical lesson.)

**Code Preservation:**
Original code stored in `_original_code` for re-execution even if display modified.

**Language Cycling:**
User can toggle Python ↔ Bash mode via `Insert` key (updates syntax highlighting).

---

### CodeOutputBlock

**File:** `src/artifice/terminal_output.py:258`

**Responsibility:** Display execution output (stdout/stderr).

**Features:**
- Buffered text accumulation
- Lazy flushing (performance optimization)
- Markdown rendering toggle
- Error styling (red text for stderr)

**Rendering Modes:**
1. **Plain text**: `Static` widget with monospace font
2. **Markdown**: `Markdown` widget with syntax highlighting

**Buffering Strategy:**
```python
append_output(text)  # Accumulates in _full buffer, sets _dirty flag
flush()              # Pushes buffer to widget (Markdown or Static)
```

**Error Handling:**
`append_error(text)` marks block with error styling (red text/border).

**Markdown Toggle:**
Runtime switching between plain and markdown rendering without losing content.

---

### AgentInputBlock

**File:** `src/artifice/terminal_output.py:339`

**Responsibility:** Display user's prompt to AI agent.

**Visual:**
```
> What is the meaning of life?
```

**Status Indicator:**
- `>` symbol in status area
- Styled with `status-pending` class

**Context:**
Always marked as `in-context` (part of agent conversation).

---

### AgentOutputBlock

**File:** `src/artifice/terminal_output.py:370`

**Responsibility:** Display AI agent's prose response.

**Features:**
- Markdown rendering by default
- Streaming support with throttled updates
- Loading indicator during streaming
- Status indicator on completion

**Streaming Throttling:**
```python
_FLUSH_INTERVAL = 0.1  # 100ms minimum between Markdown re-renders
```

**Why throttle?** Markdown parsing is expensive. Throttling prevents UI lag during rapid streaming.

**Flush Strategy:**
1. Check elapsed time since last flush
2. If < 100ms, schedule deferred flush
3. Otherwise, flush immediately
4. Force flush on finalization

**Visual States:**
1. **Streaming**: Loading indicator visible
2. **Finalized**: Loading hidden, content locked

**Finalization:**
`finalize_streaming()` disables throttling and forces final flush, ensuring content is fully rendered.

---

### ThinkingOutputBlock

**File:** `src/artifice/terminal_output.py:469`

**Responsibility:** Display AI agent's extended thinking/reasoning.

**Visual Design:**
- Dimmed text color (60% opacity)
- Blue left border accent
- Plain text rendering (no markdown)
- Status indicator on completion

**Use Case:**
When using extended thinking mode (Claude with thinking budget), thinking content streams separately from regular text and is displayed in a dedicated block.

**Appearance:**
```
│ Let me think about the best approach...
│ First, I'll need to consider...
│ [thinking continues...]
```

**Relationship to AgentOutputBlock:**
- Thinking block appears first (before text)
- Separate streaming path (`on_thinking_chunk` callback)
- Saved to session transcript in `<details>` tag for collapsibility

---

### WidgetOutputBlock

**File:** `src/artifice/terminal_output.py:319`

**Responsibility:** Display arbitrary Textual widgets returned by Python code.

**Use Case:**
```python
from textual.widgets import DataTable
table = DataTable()
# ... populate table ...
return table  # Widget rendered in output
```

**Features:**
- Arbitrary widget embedding
- Pinning support (move to PinnedOutput area)
- Interactive widgets (fully functional)

**Integration:**
When `CodeExecutor` returns a `Widget` instance, `ArtificeTerminal` automatically wraps it in `WidgetOutputBlock`.

---

## Execution Components

### CodeExecutor

**File:** `src/artifice/execution/python.py`

**Responsibility:** Execute Python code in persistent REPL namespace.

**Design:**
- Single global namespace shared across all executions
- Redirected stdout/stderr for capture
- Streaming output via callbacks
- Exception handling with traceback

**Namespace:**
```python
self._namespace = {"__name__": "__main__", "__builtins__": __builtins__}
```

Variables defined in one execution persist to the next (Jupyter-style).

**Execution Flow:**
1. Redirect stdout/stderr to callback wrappers
2. Compile code
3. Execute in namespace
4. Capture result value (last expression)
5. Restore stdout/stderr
6. Return `ExecutionResult`

**Result Value:**
If code is a single expression, its value is returned:
```python
2 + 2  # result_value = 4
```

Multi-statement code returns `None` unless last statement is expression.

**Textual Widget Detection:**
```python
if isinstance(result.result_value, Widget):
    # Wrap in WidgetOutputBlock
```

**Reset:**
`reset()` clears namespace (useful for session cleanup).

---

### ShellExecutor

**File:** `src/artifice/execution/shell.py`

**Responsibility:** Execute shell commands with persistent environment.

**Design:**
- Persistent Bash shell process (stateful)
- Init script support (e.g., source `.bashrc`)
- Real-time output streaming
- Working directory persistence

**Shell Process:**
```python
self._process = subprocess.Popen(
    ["/bin/bash"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=0  # Unbuffered for real-time output
)
```

**Execution Flow:**
1. Send command to shell stdin
2. Stream stdout/stderr via threads
3. Detect command completion marker
4. Return `ExecutionResult`

**Init Script:**
Optional script run on first command (e.g., environment setup):
```python
executor.init_script = "source ~/.bashrc"
```

**Completion Detection:**
Commands wrapped with completion marker:
```bash
echo "START_CMD_12345"; your_command; echo "END_CMD_12345"
```

---

## Agent Components

### AgentBase

**File:** `src/artifice/agent/common.py`

**Responsibility:** Abstract interface for AI agents.

**Interface:**
```python
async def send_prompt(
    self,
    prompt: str,
    on_chunk: Optional[Callable] = None,
    on_thinking_chunk: Optional[Callable] = None,
) -> AgentResponse:
    """Send prompt and stream response via callbacks."""
    ...

def clear_conversation(self):
    """Reset conversation history."""
    ...
```

**Callback Contract:**
- Callbacks invoked from background threads
- Must be thread-safe (use `loop.call_soon_threadsafe()`)
- No return value expected

**AgentResponse:**
```python
@dataclass
class AgentResponse:
    text: str                    # Complete response text
    stop_reason: str | None      # Why generation stopped
    error: str | None            # Error message if failed
    thinking: str | None         # Extended thinking content
```

---

### ClaudeAgent

**File:** `src/artifice/agent/claude.py`

**Responsibility:** Anthropic Claude API integration with streaming.

**Features:**
- Lazy client initialization
- Persistent conversation history
- Extended thinking support
- Streaming via callbacks

**Configuration:**
- API key: `ANTHROPIC_API_KEY` environment variable
- Model: Defaults to `claude-haiku-4-5` (configurable)
- System prompt: Optional persistent instruction
- Thinking budget: Optional token budget for extended thinking

**Conversation History:**
```python
self.messages = [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    ...
]
```

Multi-turn dialogue maintained across interactions.

**Streaming Modes:**

#### Text-only (No Thinking):
```python
with client.messages.stream(...) as stream:
    for text in stream.text_stream:
        on_chunk(text)
```

#### With Extended Thinking:
```python
with client.messages.stream(...) as stream:
    for event in stream:
        if event.delta.type == "thinking_delta":
            on_thinking_chunk(event.delta.thinking)
        elif event.delta.type == "text_delta":
            on_chunk(event.delta.text)
```

**Thread Safety:**
API calls run in thread pool:
```python
await loop.run_in_executor(None, sync_stream)
```

Callbacks use `call_soon_threadsafe()` to post to main event loop.

---

### OllamaAgent

**File:** `src/artifice/agent/ollama.py`

**Responsibility:** Local model integration via Ollama.

**Features:**
- Local model support (no API key required)
- Streaming response
- Persistent conversation
- Optional thinking simulation

**Configuration:**
- Host: `OLLAMA_HOST` environment variable or `http://localhost:11434`
- Model: User-specified (e.g., `llama3.1`, `codellama`)

**Thinking Simulation:**
If `thinking_budget` configured, agent simulates thinking by extracting content between `<think>` tags in response.

---

### SimulatedAgent

**File:** `src/artifice/agent/simulated.py`

**Responsibility:** Testing agent with canned responses.

**Use Cases:**
- Unit testing streaming behavior
- UI development without API calls
- Fence detection testing

**Features:**
- Configurable response delay
- Scenario-based responses
- Simulated streaming (character-by-character)

---

## Streaming Components

### StreamingFenceDetector

**File:** `src/artifice/terminal.py:135`

**Responsibility:** Real-time code fence detection in streaming agent responses.

**Design Philosophy:**
Traditional approach: buffer full response → parse → create blocks

Artifice approach: parse character-by-character → create blocks in real-time

**State Machine:**
```
PROSE ──(```)──> LANG_LINE ──(newline)──> CODE ──(```)──> PROSE
```

**States:**
1. **PROSE**: Processing prose text (Markdown, plain text)
2. **LANG_LINE**: Processing language identifier after opening fence
3. **CODE**: Processing code inside fence

**Fence Detection:**
```
Prose text here...
```python         ← Opening fence detected → create CodeInputBlock
print("hello")
```               ← Closing fence detected → create AgentOutputBlock
More prose...
```

**String Tracking:**
Critical: Ignore fence markers inside string literals:
```python
code = "```python"  # Not a fence!
```

**Character-by-Character Processing:**
```python
def feed(self, text: str):
    for ch in text:
        self._feed_char(ch)  # Update state machine
    self._update_current_block_with_chunk()  # Batch update
```

**Batching Strategy:**
- Accumulate text in `_pending_buffer`
- Flush to `_chunk_buffer` periodically
- Update current block once per `feed()` call

**Block Creation:**
- **Prose blocks**: `AgentOutputBlock` with Markdown rendering
- **Code blocks**: `CodeInputBlock` with syntax highlighting
- Blocks created **during streaming**, not post-processing

**Finalization:**
```python
def finish(self):
    # Handle incomplete fences
    # Flush remaining text
    # Mark blocks complete
    # Remove empty blocks
    # Save to session
```

**Empty Block Cleanup:**
Empty `AgentOutputBlock` instances removed (except first, for status indicator).

---

## Utility Components

### History

**File:** `src/artifice/history.py`

**Responsibility:** Command history management.

**Features:**
- Persistent history file (`~/.artifice/history`)
- Deduplication (consecutive duplicates removed)
- Size limiting (default 1000 entries)
- Thread-safe file writes

**Usage:**
```python
history.add(command)           # Add command
history.get_all()              # Retrieve all
history.search(prefix)         # Search by prefix
history.clear()                # Clear all
```

---

### SessionTranscript

**File:** `src/artifice/session.py`

**Responsibility:** Save conversation transcripts to Markdown files.

**File Location:**
`~/.artifice/sessions/session_YYYYMMDD_HHMMSS.md`

**Format:**
```markdown
# Artifice Session
**Started:** 2026-02-12 14:30:00
**Provider:** anthropic
**Model:** claude-sonnet-4-5

---

## User

[User prompt]

## Thinking

<details>
<summary>Thinking</summary>

[Thinking content]

</details>

## Agent

[Agent response]

### 1 Code

```python
print("hello")
```

### Output

```
hello
```

---

**Ended:** 2026-02-12 15:00:00
```

**Block Serialization:**
Each block type converted to Markdown:
- `AgentInputBlock` → `## User`
- `ThinkingOutputBlock` → `## Thinking` (in collapsible `<details>`)
- `AgentOutputBlock` → `## Agent`
- `CodeInputBlock` → `### {N} Code` (numbered)
- `CodeOutputBlock` → `### Output` (or `### Output (error)`)

**Incremental Writing:**
Blocks appended as they're finalized (not buffered).

---

### Configuration

**File:** `src/artifice/config.py`

**Responsibility:** Load and manage user configuration.

**Configuration Sources:**
1. `~/.config/artifice/init.py` (user config)
2. Command-line arguments (override)
3. Defaults (fallback)

**Config Settings:**
```python
class ArtificeConfig:
    # Agent
    provider: str               # anthropic, ollama, copilot, simulated
    model: str                  # Model identifier
    system_prompt: str          # Agent instructions
    prompt_prefix: str          # Prefix for all prompts
    thinking_budget: int        # Extended thinking tokens

    # Display
    banner: bool                # Show ASCII banner
    python_markdown: bool       # Render Python output as Markdown
    agent_markdown: bool        # Render agent output as Markdown
    shell_markdown: bool        # Render shell output as Markdown

    # Behavior
    auto_send_to_agent: bool    # Auto-send execution results
    shell_init_script: str      # Shell initialization script

    # Sessions
    save_sessions: bool         # Enable session saving
    sessions_dir: str           # Custom session directory
```

**Sandboxed Execution:**
`init.py` runs in restricted namespace:
- No imports (`__import__` disabled)
- No file I/O (`open` disabled)
- No code execution (`eval`, `exec` disabled)
- Basic types and functions only

**Example init.py:**
```python
config.provider = "anthropic"
config.model = "claude-sonnet-4-5"
config.system_prompt = "You are a helpful coding assistant."
config.banner = True
config.auto_send_to_agent = True
```

---

## Design Patterns

### Observer Pattern
- Message passing for cross-component communication
- Custom messages: `StreamChunk`, `StreamThinkingChunk`, `BlockActivated`, etc.
- Textual's message bus handles routing

### Factory Pattern
- Block creation factories in `StreamingFenceDetector`
- Callable factories for testing/mocking

### Strategy Pattern
- Executor interface (Python vs Shell)
- Agent interface (Claude vs Ollama vs Copilot)

### Command Pattern
- Keyboard bindings → action methods
- Reusable actions (e.g., `action_toggle_markdown`)

### Lazy Initialization
- Agent clients created on first use
- Output blocks created on first output

### Buffering Pattern
- Output buffering with lazy flush
- Chunk buffering with batch processing
- Reduces render cycles and improves performance
