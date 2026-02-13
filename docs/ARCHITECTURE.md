# Artifice Architecture

**Version:** 0.1.0
**Last Updated:** 2026-02-12

## Overview

Artifice is a human-in-the-loop agentic AI coding environment built as a Terminal User Interface (TUI) using the [Textual](https://github.com/Textualize/textual) framework. It combines an interactive Python REPL, shell command execution, and AI agent integration in a unified interface.

## Core Principles

1. **Human-in-the-Loop**: AI agents propose code/commands; humans review and approve before execution
2. **Block-Based Architecture**: All I/O organized into navigable, reusable blocks
2. **Conversation Context Indication**: Visualization of what is included in the current conversation context
3. **Real-time Streaming**: Agent responses stream in real-time with live code fence detection
4. **Mode Agnostic**: Seamless switching between Python, shell, and AI prompt modes

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ArtificeApp                              │
│  (Main Textual App - Theme, Layout, Global Bindings)            │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├─── ArtificeHeader (Banner & Visual Decoration)
             │
             ├─── ArtificeTerminal (Primary Widget)
             │    │
             │    ├─── TerminalOutput (Scrollable Block Container)
             │    │    ├─── AgentInputBlock
             │    │    ├─── AgentOutputBlock (Markdown/Plain)
             │    │    ├─── ThinkingOutputBlock (Extended Thinking)
             │    │    ├─── CodeInputBlock (Syntax Highlighted)
             │    │    ├─── CodeOutputBlock (Execution Results)
             │    │    └─── WidgetOutputBlock (Textual Widgets)
             │    │
             │    ├─── TerminalInput (Multi-mode Input)
             │    │    └─── InputTextArea (Code Editor)
             │    │
             │    ├─── PinnedOutput (Widget Display Area)
             │    │
             │    ├─── CodeExecutor (Python REPL)
             │    ├─── ShellExecutor (Bash Shell)
             │    ├─── AgentBase (AI Agent Interface)
             │    │    ├─── ClaudeAgent (Anthropic)
             │    │    ├─── OllamaAgent (Local Models)
             │    │    ├─── CopilotAgent (GitHub Copilot)
             │    │    └─── SimulatedAgent (Testing)
             │    │
             │    └─── StreamingFenceDetector (Real-time Parser)
             │
             └─── Footer (Contextual Help)
```

## Component Layers

### Layer 1: Application Shell
- **ArtificeApp**: Root Textual application
- **ArtificeHeader**: Visual branding and decoration
- **Footer**: Dynamic keyboard shortcuts help

### Layer 2: Terminal Widget
- **ArtificeTerminal**: Main orchestrator
  - Manages all sub-components
  - Coordinates message passing
  - Handles mode state and context

### Layer 3: I/O Components
- **TerminalOutput**: Display and navigation of output blocks
- **TerminalInput**: Multi-mode input with history
- **PinnedOutput**: Persistent widget display area

### Layer 4: Execution Engines
- **CodeExecutor**: Python REPL with persistent namespace
- **ShellExecutor**: Bash shell with init script support
- **AgentBase**: Abstract interface for AI agents
  - Concrete implementations for Claude, Ollama, Copilot

### Layer 5: Data Structures
- **Blocks**: Self-contained UI widgets representing I/O units
  - Input blocks: `CodeInputBlock`, `AgentInputBlock`
  - Output blocks: `CodeOutputBlock`, `AgentOutputBlock`, `ThinkingOutputBlock`
  - Specialized: `WidgetOutputBlock`
- **ExecutionResult**: Captures code execution outcomes
- **AgentResponse**: Captures AI agent responses

## Data Flow

### 1. User Input Flow
```
User Input → TerminalInput → Mode Detection →
  ├─ AI Mode (>)    → AgentInputBlock → AgentBase.send_prompt()
  ├─ Python Mode (]) → CodeInputBlock → CodeExecutor.execute()
  └─ Shell Mode ($)  → CodeInputBlock → ShellExecutor.execute()
```

### 2. Agent Response Flow
```
AgentBase.send_prompt() → Streaming Callback → StreamChunk Message →
  StreamingFenceDetector → Real-time Block Creation →
    ├─ Prose Text → AgentOutputBlock (Markdown)
    └─ Code Fences → CodeInputBlock (Syntax Highlighted)
```

### 3. Code Execution Flow
```
CodeInputBlock → Executor.execute() → Buffered Callbacks →
  CodeOutputBlock → Flush on Complete → Status Update
```

### 4. Agent Context Flow
```
Blocks marked "in-context" → Context Serialization →
  Agent Conversation History → Multi-turn Dialogue
```

## Threading Model

### Async Architecture
- **Main Thread**: Textual event loop (asyncio)
- **Executor Threads**: Python/Shell execution runs in thread pool
- **Agent Threads**: API calls run in thread pool, callbacks posted to main loop

### Critical Threading Rules
1. **Never mount widgets in callbacks**: Callbacks from agent streaming run in executor threads where Textual's `active_app` ContextVar is not set
2. **Use messages for cross-thread communication**: `StreamChunk`, `StreamThinkingChunk`
3. **Batch updates**: Use `app.batch_update()` to reduce render cycles
4. **Schedule refreshes**: Use `call_after_refresh()` for layout-dependent operations

## State Management

### Global State
- **Config**: User settings loaded from `~/.config/artifice/init.py`
- **History**: Command history persisted to `~/.artifice/history`
- **Sessions**: Conversation transcripts saved to `~/.artifice/sessions/`

### Terminal State
- **Input Mode**: `python` | `shell` | `ai`
- **Auto-send Mode**: Whether execution results auto-send to agent
- **Context Blocks**: List of blocks included in agent context
- **Current Task**: Active async execution task (for cancellation)

### Block State
- **Execution Status**: `PENDING` | `RUNNING` | `SUCCESS` | `ERROR`
- **Streaming State**: Whether block is currently streaming
- **In-Context Flag**: Whether block is part of agent context

## Configuration System

### Configuration Sources (Priority Order)
1. Command-line arguments (highest priority)
2. `~/.config/artifice/init.py` user configuration
3. Built-in defaults (lowest priority)

### Configuration Categories
- **Agent Settings**: Provider, model, system prompt, thinking budget
- **Display Settings**: Banner, markdown rendering per mode
- **Behavior Settings**: Auto-send to agent, shell init script
- **Session Settings**: Session saving, custom sessions directory

## Extension Points

### 1. Custom Agents
Implement `AgentBase` abstract class:
```python
class CustomAgent(AgentBase):
    async def send_prompt(self, prompt, on_chunk=None, on_thinking_chunk=None):
        # Stream response via callbacks
        ...

    def clear_conversation(self):
        # Reset conversation state
        ...
```

### 2. Custom Executors
Implement executor interface:
```python
class CustomExecutor:
    async def execute(self, code, on_output=None, on_error=None):
        # Execute and stream output
        return ExecutionResult(...)
```

### 3. Custom Blocks
Extend `BaseBlock` for custom display:
```python
class CustomBlock(BaseBlock):
    def compose(self):
        # Define widget structure
        ...
```

### 4. Configuration Extensions
Add custom settings in `init.py`:
```python
config.set('custom_setting', value)
```

## Security Considerations

### Code Execution
- Python code runs in the host process namespace (not sandboxed)
- Shell commands run with user's full permissions
- **Trust model**: User must trust all executed code

### Configuration
- `init.py` runs in restricted namespace (limited builtins)
- No file I/O, imports, or exec in config
- Prevents accidental code injection via config

### Agent Integration
- API keys read from environment variables
- No credentials stored in session files
- Agent responses may contain untrusted content (user must review)

## Performance Characteristics

### Rendering Performance
- **Streaming throttling**: Markdown re-renders throttled to 100ms intervals
- **Batch updates**: Multiple DOM changes batched into single render cycle
- **Lazy loading**: Agent clients instantiated on first use

### Memory Management
- **History limits**: Command history capped at 1000 entries
- **Session persistence**: Blocks written to disk incrementally
- **Block cleanup**: Empty blocks removed during finalization

### Scalability
- **Large outputs**: Buffered output with lazy flush prevents blocking
- **Long conversations**: Agent history grows unbounded (consider truncation)
- **Widget blocks**: Unlimited pinned widgets (user controls cleanup)

## Error Handling Strategy

### User-Facing Errors
- Agent connection failures → Error block with clear message
- Execution errors → Red status indicator + error output
- Config errors → Notification banner with warning

### Internal Errors
- Logging to `artifice_agent.log` when `--logging` enabled
- Exception handling at component boundaries
- Graceful degradation (e.g., missing agent → warning, not crash)

### Recovery Mechanisms
- Ctrl+C cancellation for long-running operations
- Context clearing when agent gets stuck
- Block removal/editing for error correction

## Design Decisions & Rationale

### Why Textual?
- Modern TUI framework with rich widget library
- Async-first architecture matches streaming requirements
- Markdown rendering built-in
- Active development and strong community

### Why Block-Based Architecture?
- Natural unit for navigation (up/down through blocks)
- Enables block reuse (copy code to input, re-execute)
- Clear visual structure for conversation flow
- Supports mixed content types (text, code, widgets)

### Why Streaming Fence Detection?
- Real-time feedback improves UX (see code as it's generated)
- Enables interactive approval (see full code before execution)
- Consistent experience across agent providers
- Avoids post-processing latency

### Why Persistent Namespace?
- REPL-like workflow for iterative development
- Variables persist across cells (Jupyter-style)
- Enables building up complex state interactively
- Matches user mental model of "workspace"

## Future Architectural Considerations

### Planned Enhancements
- VIM keybinding mode for input
- LSP integration for code intelligence
- Multi-language support (JavaScript, TypeScript, etc.)
- Session export/import with full state
- Plugin system for custom commands

### Architectural Constraints
- Must remain terminal-compatible (no GUI dependencies)
- Keep startup time under 500ms
- Support remote/SSH usage
- Maintain single-binary deployment model
