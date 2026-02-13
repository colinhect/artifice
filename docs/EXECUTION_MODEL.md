# Execution Model

**Version:** 0.1.0
**Last Updated:** 2026-02-12

## Overview

Artifice provides a unified execution environment for Python code and shell commands with persistent state, streaming output, and seamless AI agent integration. This document details the execution model, state management, output handling, and integration patterns.

---

## Execution Modes

### Python REPL

**Executor:** `CodeExecutor` (`src/artifice/execution/python.py`)

**Characteristics:**
- Persistent namespace (variables survive across executions)
- Expression evaluation (last expression value returned)
- Full Python stdlib access
- Textual widget integration

**Namespace:**
```python
self._namespace = {
    "__name__": "__main__",
    "__builtins__": __builtins__
}
```

All code executes in this shared namespace:
```python
# Cell 1
x = 42

# Cell 2
print(x)  # 42 (x persists from cell 1)
```

### Shell Mode

**Executor:** `ShellExecutor` (`src/artifice/execution/shell.py`)

**Characteristics:**
- Persistent Bash process (environment survives)
- Working directory persistence
- Init script support
- Real-time output streaming

**Process:**
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

Shell state persists:
```bash
# Command 1
cd /tmp

# Command 2
pwd  # /tmp (working directory persisted)
```

---

## Execution Flow

### High-Level Flow

```
User Input → Mode Detection → Block Creation → Execution → Output Capture → Status Update
```

### Detailed Flow

#### 1. Input Submission

```python
async def on_terminal_input_submitted(self, event: TerminalInput.Submitted):
    code = event.code
    self.input.clear()

    if event.is_agent_prompt:
        await self._handle_agent_prompt(code)
    elif event.is_shell_command:
        result = await self._execute_code(code, language="bash", ...)
        if self._auto_send_to_agent:
            await self._send_execution_result_to_agent(code, result)
    else:  # Python
        result = await self._execute_code(code, language="python", ...)
        if self._auto_send_to_agent:
            await self._send_execution_result_to_agent(code, result)
```

#### 2. Block Creation

```python
code_input_block = CodeInputBlock(
    code,
    language=language,
    show_loading=True,
    in_context=in_context
)
self.output.append_block(code_input_block)
```

**Visual States:**
- Loading indicator shown immediately
- Status icon empty (unexecuted)
- Code syntax-highlighted

#### 3. Output Callbacks

```python
on_output, on_error, flush = self._make_output_callbacks(
    markdown_enabled=markdown_enabled,
    in_context=in_context
)
```

**Lazy Block Creation:**
```python
def ensure_block():
    if state["block"] is None:
        state["block"] = CodeOutputBlock(...)
        self.output.append_block(state["block"])
    return state["block"]
```

Output block only created if code produces output.

#### 4. Execution

```python
executor = self._shell_executor if language == "bash" else self._executor
result = await executor.execute(code, on_output=on_output, on_error=on_error)
```

Runs in thread pool to avoid blocking event loop.

#### 5. Status Update

```python
code_input_block.update_status(result)
```

**Visual Changes:**
- Loading indicator hidden
- Status icon: `✔` (success) or `✖` (error)
- Icon color: green or red

#### 6. Widget Integration (Python Only)

```python
if language != "bash" and isinstance(result.result_value, Widget):
    widget_block = WidgetOutputBlock(result.result_value)
    self.output.append_block(widget_block)
```

**Example:**
```python
from textual.widgets import DataTable
table = DataTable()
# ... populate table ...
return table  # Auto-mounted in WidgetOutputBlock
```

---

## Python Execution

### Code Compilation

```python
def execute(self, code, on_output=None, on_error=None):
    # Compile with exec mode for statements
    compiled = compile(code, "<input>", "exec")

    # Try expression mode for single expressions
    try:
        expr_compiled = compile(code, "<input>", "eval")
        is_expression = True
    except SyntaxError:
        is_expression = False
```

**Execution Modes:**
- **exec**: Multi-statement code (result = `None`)
- **eval**: Single expression (result = expression value)

### Execution with Output Capture

```python
# Redirect stdout/stderr
old_stdout, old_stderr = sys.stdout, sys.stderr
sys.stdout = OutputCapture(on_output)
sys.stderr = OutputCapture(on_error)

try:
    if is_expression:
        result_value = eval(expr_compiled, self._namespace)
    else:
        exec(compiled, self._namespace)
        result_value = None
except Exception as e:
    # Capture exception and traceback
    result.status = ExecutionStatus.ERROR
    result.exception = e
    on_error(traceback.format_exc())
finally:
    sys.stdout, sys.stderr = old_stdout, old_stderr
```

### Output Capture

```python
class OutputCapture:
    def __init__(self, callback):
        self.callback = callback

    def write(self, text):
        if self.callback:
            self.callback(text)

    def flush(self):
        pass
```

**Streaming:** `print()` calls `write()` → callback invoked immediately.

### Result Value Handling

```python
# Expression: return value
x = 2 + 2  # result_value = None (assignment)
2 + 2      # result_value = 4 (expression)

# Widget detection
if isinstance(result_value, Widget):
    # Mount in WidgetOutputBlock
```

### Namespace Persistence

Variables defined in one execution persist:

```python
# Execution 1
import pandas as pd
df = pd.DataFrame({"a": [1, 2, 3]})

# Execution 2
print(df)  # df still available
```

**Implications:**
- Variables accumulate (can cause memory leaks)
- Imports persist (no need to re-import)
- Functions and classes defined once

**Reset:**
```python
executor.reset()  # Clears namespace
```

---

## Shell Execution

### Process Lifecycle

#### Initialization

```python
def __init__(self):
    self._process = None  # Lazy initialization
    self.init_script = None  # Optional init script
```

#### First Execution

```python
if self._process is None:
    self._start_shell()

    if self.init_script:
        # Run init script (e.g., source ~/.bashrc)
        await self._execute_command(self.init_script)
```

#### Process Creation

```python
def _start_shell(self):
    self._process = subprocess.Popen(
        ["/bin/bash"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0,  # Unbuffered
        env=os.environ.copy()
    )

    # Start output reader threads
    self._start_reader_threads()
```

### Command Execution

#### Command Wrapping

```python
command_id = str(uuid.uuid4())
wrapped = f"""
echo "START_CMD_{command_id}"
{code}
echo "END_CMD_{command_id}"
"""
```

**Why wrap?** Detects when command completes (bash doesn't provide async API).

#### Streaming Output

```python
def _stdout_reader():
    while True:
        line = process.stdout.readline()
        if not line:
            break

        if line == f"START_CMD_{command_id}":
            # Command started
        elif line == f"END_CMD_{command_id}":
            # Command completed
            break
        else:
            on_output(line)
```

**Real-time:** Output streams as it's produced (no buffering).

#### Error Handling

```python
def _stderr_reader():
    while True:
        line = process.stderr.readline()
        if not line:
            break
        on_error(line)
```

Stderr streamed separately (rendered in red).

### Environment Persistence

```bash
# Command 1
export MY_VAR="hello"
cd /tmp

# Command 2
echo $MY_VAR  # "hello" (env var persisted)
pwd           # /tmp (working dir persisted)
```

**Implications:**
- Shell state accumulates
- Aliases and functions persist
- Environment modifications permanent (within session)

### Init Script

```python
executor.init_script = """
source ~/.bashrc
alias ll='ls -la'
export PATH="/custom/bin:$PATH"
"""
```

**Use Cases:**
- Source shell configuration
- Set up environment
- Define aliases
- Load modules

---

## Output Handling

### Buffered Output

```python
def _make_output_callbacks(self, markdown_enabled, in_context):
    state = {"block": None, "flush_scheduled": False}

    def on_output(text):
        ensure_block().append_output(text)
        _schedule_flush()

    def flush():
        if state["block"]:
            state["block"].flush()
            self.output.scroll_end(animate=False)

    return on_output, on_error, flush
```

**Buffering Strategy:**
1. `append_output()` accumulates text in buffer, sets dirty flag
2. `_schedule_flush()` schedules flush on next event loop tick
3. `flush()` pushes buffer to widget

**Why buffer?** Rapid output (e.g., 1000 lines) batched into fewer renders.

### Markdown Rendering

```python
code_output_block = CodeOutputBlock(render_markdown=markdown_enabled)
```

**Per-Mode Settings:**
```python
self._python_markdown_enabled = config.python_markdown
self._shell_markdown_enabled = config.shell_markdown
self._agent_markdown_enabled = config.agent_markdown
```

**Toggle:**
```python
def action_toggle_mode_markdown(self):
    attr, label = self._MARKDOWN_SETTINGS[self.input.mode]
    setattr(self, attr, not getattr(self, attr))
```

Affects **future** blocks only (existing blocks unchanged).

**Per-Block Toggle:**
User can toggle individual blocks via `Ctrl+O` when highlighted.

### Error Styling

```python
def append_error(self, text):
    self.append_output(text)
    self.mark_failed()

def mark_failed(self):
    if self._output:
        self._output.remove_class("code-output")
        self._output.add_class("error-output")  # Red text
```

**Visual:**
- Red text color
- Red status icon
- Clear distinction from success

---

## Agent Integration

### Auto-Send Mode

```python
self._auto_send_to_agent = config.auto_send_to_agent
```

**When enabled:**
```python
# After execution
if self._auto_send_to_agent:
    await self._send_execution_result_to_agent(code, result)
```

**Visual Indicator:**
Input area shows blue left border when in auto-send mode.

### Execution Context

```python
prompt = f"""Executed:
```
{code}
```

Output:
{result.output}{result.error}
"""
await self._stream_agent_response(self._agent, prompt)
```

**Result Format:**
- Code shown in fence
- Output shown as plain text
- Agent sees both stdout and stderr

### Agent-Proposed Code

```python
# Agent response:
"Here's the code:\n```python\nprint('hello')\n```"

# Creates numbered CodeInputBlock
block = CodeInputBlock(code, language="python", command_number=1)
```

**User Actions:**
1. Navigate to block (Alt+Up/Down)
2. Press `Enter` to execute
3. Or press `1` anywhere to execute block #1

**Approval Model:**
- Code displayed but not executed
- User must explicitly approve (Enter key)
- Can edit code before execution (Ctrl+C to copy to input)

---

## Cancellation

### Cancel Current Task

```python
def action_cancel_execution(self):
    if self._current_task and not self._current_task.done():
        self._current_task.cancel()
```

**Applies to:**
- Python code execution
- Shell command execution
- Agent prompt streaming

### Cancellation Handling

```python
async def _run_cancellable(self, coro, *, finally_callback=None):
    try:
        await coro
    except asyncio.CancelledError:
        block = CodeOutputBlock(render_markdown=False)
        self.output.append_block(block)
        block.append_error("\n[Cancelled]\n")
        block.flush()
        raise
    finally:
        self._current_task = None
        if finally_callback:
            finally_callback()
```

**Visual:**
- `[Cancelled]` message shown in output
- Status icon shows error state
- Cleanup always runs (finally block)

**Limitations:**
- Python code: Cancels at next yield point (may not be immediate)
- Shell commands: Process continues but output ignored
- Agent streaming: Connection closed, partial response shown

---

## Context Management

### Block Context

```python
self._context_blocks = []  # Blocks in agent context
```

**Marking Blocks:**
```python
def _mark_block_in_context(self, block):
    if block not in self._context_blocks:
        self._context_blocks.append(block)
        block.add_class("in-context")
```

**Visual:** Blue left border on blocks.

### Auto-Context Rules

**Always in context:**
- User prompts (`AgentInputBlock`)
- Agent responses (`AgentOutputBlock`)
- Agent-proposed code (`CodeInputBlock` from agent)

**Conditionally in context:**
- User-executed code: Only if auto-send enabled
- Execution output: Only if auto-send enabled

### Context Clearing

```python
def action_clear_agent_context(self):
    if self._agent and hasattr(self._agent, "clear_conversation"):
        self._agent.clear_conversation()

    self._clear_all_context_highlights()

def _clear_all_context_highlights(self):
    for block in self._context_blocks:
        block.remove_class("in-context")
    self._context_blocks.clear()
```

**Effect:**
- Agent conversation history cleared
- Visual highlights removed
- Next prompt starts fresh conversation

---

## Result Structures

### ExecutionResult

```python
@dataclass
class ExecutionResult:
    code: str                    # Original code executed
    status: ExecutionStatus      # PENDING | RUNNING | SUCCESS | ERROR
    output: str                  # Stdout content
    error: str                   # Stderr content
    result_value: Any            # Expression result (Python only)
    exception: Exception | None  # Exception if failed
```

**Usage:**
```python
result = await executor.execute(code)

if result.status == ExecutionStatus.SUCCESS:
    print(f"Output: {result.output}")
    if result.result_value:
        print(f"Result: {result.result_value}")
else:
    print(f"Error: {result.error}")
```

### AgentResponse

```python
@dataclass
class AgentResponse:
    text: str                    # Complete response text
    stop_reason: str | None      # end_turn | max_tokens | ...
    error: str | None            # Error message if failed
    thinking: str | None         # Extended thinking content
```

**Integration:**
```python
response = await agent.send_prompt(prompt)

if response.error:
    # Show error block
else:
    # Response already streamed to blocks
    # Check stop_reason for conversation flow
```

---

## Error Handling

### Python Errors

**Syntax Errors:**
```python
try:
    compiled = compile(code, "<input>", "exec")
except SyntaxError as e:
    result.status = ExecutionStatus.ERROR
    result.exception = e
    on_error(str(e))
```

**Runtime Errors:**
```python
try:
    exec(compiled, self._namespace)
except Exception as e:
    result.status = ExecutionStatus.ERROR
    result.exception = e
    on_error(traceback.format_exc())
```

**Traceback:**
```python
Traceback (most recent call last):
  File "<input>", line 1, in <module>
ZeroDivisionError: division by zero
```

### Shell Errors

**Exit Codes:**
```bash
command ; echo $?  # Exit code in $?
```

Currently not captured (commands always return SUCCESS).

**Future:** Capture exit codes and mark as ERROR if non-zero.

### Agent Errors

**API Errors:**
```python
except Exception as e:
    return AgentResponse(
        text="",
        error=f"Error communicating with agent: {e}"
    )
```

**Display:**
- Error shown in first `AgentOutputBlock`
- Block marked failed (loading → error icon)

---

## Performance Considerations

### Thread Pool Execution

**Python:**
```python
await loop.run_in_executor(None, self._execute_sync, code)
```

**Shell:**
Process runs in separate threads (stdout/stderr readers).

**Why threads?** Avoid blocking event loop during execution.

### Output Buffering

**Problem:** 1000-line output = 1000 render cycles

**Solution:** Batched flushing
```python
def on_output(text):
    block.append_output(text)
    _schedule_flush()  # Flush once per event loop tick
```

**Result:** ~60 renders/sec regardless of output rate.

### Lazy Block Creation

```python
def ensure_block():
    if state["block"] is None:
        state["block"] = CodeOutputBlock(...)
```

**Benefit:** No output block created if code produces no output.

### Session Saving

**Incremental:**
```python
# After each block finalized
self._save_block_to_session(block)
```

**Alternative (rejected):** Batch save on exit
- **Problem:** Lost data if crash

---

## Future Enhancements

### Multi-Language Support

**Planned:**
- JavaScript (Node.js executor)
- TypeScript (tsc + node executor)
- Rust (cargo script executor)

**Design:**
```python
class ExecutorRegistry:
    def get_executor(self, language: str) -> ExecutorBase:
        return self._executors[language]
```

### LSP Integration

**Goal:** Code intelligence (autocomplete, hover, go-to-def) in input area.

**Approach:**
- Run language server in background
- Query on cursor position
- Show completions in autocomplete dropdown

### Session Export/Import

**Export:**
```python
session.export("session.json")  # Full state: namespace, history, blocks
```

**Import:**
```python
session.import_("session.json")  # Restore full state
```

### Execution Replay

**Goal:** Re-run all blocks in sequence.

**Use Case:** Notebook-style execution after app restart.

### Sandboxing

**Current:** Full system access (no sandboxing)

**Future:** Optional sandbox mode:
- Restricted filesystem access
- Network isolation
- Resource limits (CPU, memory)
