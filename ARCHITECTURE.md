# Artifice Architecture

## Overview

Artifice is a minimal AI agent harness with a terminal interface. It provides a unified way to interact with LLMs (via any-llm) while executing code in Python, shell, or tmux environments.

## Core Principles

1. **Separation of concerns**: Domain logic (agent/execution) is separate from UI
2. **Async throughout**: All I/O operations are async (streaming, execution)
3. **Provider-agnostic**: Uses any-llm for universal LLM support
4. **Streaming-first**: Agent responses stream in real-time with code detection

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ArtificeApp (Entry)                      │
│  - Parses args, loads config                                │
│  - Initializes Textual app with theme                       │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              ArtificeTerminal (UI Layer)                    │
│  - Main widget coordinating all subsystems                  │
│  - Input: TerminalInput with history support                │
│  - Output: TerminalOutput with block-based rendering        │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼───────┐ ┌────▼────┐ ┌───────▼────────┐
│   Agent       │ │Execution│ │   Streaming    │
│   (LLM)       │ │         │ │   Manager      │
├───────────────┤ ├─────────┤ ├────────────────┤
│ Agent         │ │Execution│ │ StreamManager  │
│ manages       │ │Coordinator│ - Buffers      │
│ conversation  │ │         │ │   chunks       │
│ history via   │ │Python   │ │                │
│ any-llm       │ │Executor │ │ FenceDetector  │
│               │ │         │ │   (detects     │
│ Tools         │ │Shell/   │ │   code blocks) │
│ registered    │ │Tmux     │ │                │
│ with schemas  │ │Executors│ │ ChunkBuffer    │
└───────────────┘ └─────────┘ └────────────────┘
```

## Key Components

### 1. Agent Layer (`artifice/agent/`)

- **Agent**: Manages conversation history and LLM calls via any-llm
- **Tool system**: Python/shell tools with OpenAI-style function calling
- **Streaming**: `StreamManager` buffers chunks, detects code fences, and coordinates with UI

### 2. Execution Layer (`artifice/execution/`)

- **ExecutionCoordinator**: Central hub for all code execution
- **CodeExecutor**: Interactive Python REPL with persistent state
- **ShellExecutor**: Direct shell command execution
- **TmuxShellExecutor**: Shell via tmux pane (preserves state/env)

### 3. UI Layer (`artifice/ui/`)

- **ArtificeTerminal**: Main widget composing input/output/history
- **TerminalInput**: Multiline input with mode switching (`>`, `]`, `$`)
- **TerminalOutput**: Block-based output (markdown, code, widgets)
- **Blocks**: `CodeInputBlock`, `CodeOutputBlock`, `ThinkingOutputBlock`

### 4. Core (`artifice/core/`)

- **Config**: YAML-based configuration from `~/.config/artifice/init.yaml`
- **History**: Persistent command history with search
- **Events**: Input modes (AI, Python, Shell)

## Data Flow

```
User Input → ArtificeTerminal ──────> Input Mode?
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
           AI Prompt      Python Code    Shell Command
              │               │               │
              ▼               ▼               ▼
           Agent.send()   Execution       Execution
              │          Coordinator     Coordinator
              │          .execute()      .execute()
              │               │               │
              ▼               ▼               ▼
         Streaming      Python/Shell    Shell/Tmux
         Response      Executor       Executor
              │               │               │
              └───────────────┴───────────────┘
                              │
                              ▼
                    TerminalOutput Blocks
                              │
                              │ (send_user_commands_to_agent?)
                              └───yes──> Agent.send()
```

## Streaming Architecture

The agent streams tokens continuously:

1. **StreamManager** buffers incoming chunks
2. **FenceDetector** detects code fences (```) in the stream
3. When code detected: pause streaming → execute code → resume
4. **ThinkingOutputBlock** displays reasoning content separately

```
LLM Stream → ChunkBuffer → FenceDetector ─┬─> UI (live text)
                                          │
                                          └─> Code detected
                                              → Pause
                                              → Execute
                                              → Resume
```

## Configuration

Configuration is loaded from `~/.config/artifice/init.yaml`:

- **Agent settings**: Model, provider, API key, tools
- **Display**: Markdown rendering toggles per mode
- **Execution**: Tmux target, shell init script
- **Behavior**: Auto-send results to agent

Command-line args override config values.

## Execution Contexts

| Mode | Trigger | Executor | Use Case |
|------|---------|----------|----------|
| AI | `>` | Agent via any-llm | Prompting LLM |
| Python | `]` | CodeExecutor | Interactive Python |
| Shell | `$` | Shell/Tmux | Shell commands |

## Testing

- Unit tests in `tests/` using pytest
- `SimulatedAgent` for testing without LLM calls
- UI changes tested via unit tests (TUI not run directly)

## Dependencies

- **Textual**: TUI framework
- **any-llm**: Universal LLM provider
- **PyYAML**: Configuration parsing

## Design Decisions

1. **Why any-llm?** Single interface for 15+ providers without provider-specific code
2. **Why async?** Streaming requires non-blocking I/O throughout
3. **Why tmux?** Shell state (env, cwd) persists across commands
4. **Why block-based UI?** Enables navigation, re-execution, context tracking
