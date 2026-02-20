# Artifice Refactoring Plan

## Overview

This document outlines a comprehensive refactoring plan for the Artifice codebase to improve organization, maintainability, and adherence to SOLID principles.

---

## Current Issues

### 1. Mixed Concerns
The main widget (`terminal/widget.py`, 646 lines) handles too many responsibilities:
- UI rendering
- Agent communication
- Code execution
- Keyboard input handling
- State management

### 2. Flat Structure
22 files in the root `artifice/` directory with unclear boundaries between:
- Domain logic
- UI components
- Execution engines
- Utility functions

### 3. Large Classes
- `StreamingFenceDetector` (368 lines): Parsing + UI coordination
- `ArtificeTerminal` (646 lines): Everything related to the terminal

### 4. Tight Coupling
- Direct instantiation instead of dependency injection
- Widget creates its own dependencies internally
- Hard to test in isolation

### 5. Scattered Utilities
Small files with single functions:
- `utils.py` (324 bytes)
- `theme.py` (864 bytes)
- `prompts.py` (1648 bytes)
- `input_mode.py` (1755 bytes)

---

## Proposed Structure

```
src/artifice/
├── __init__.py                    # Public API exports
├── __version__.py                 # Version info
├── app.py                         # Entry point (argparse, main())
│
├── core/                          # Domain layer - business logic
│   ├── __init__.py
│   ├── config.py                  # Configuration management
│   ├── events.py                  # Event types, InputMode
│   ├── history.py                 # Conversation history
│   └── prompts.py                 # System prompt loading
│
├── execution/                     # Code execution layer
│   ├── __init__.py
│   ├── base.py                    # ExecutionResult, ExecutionStatus
│   ├── python.py                  # Python REPL executor
│   ├── shell.py                   # Shell + Tmux executors
│   ├── callbacks.py               # Output callback handlers
│   └── coordinator.py             # Execution orchestration
│
├── agent/                         # LLM integration
│   ├── __init__.py
│   ├── base.py                    # Agent protocol/interface
│   ├── client.py                  # Main Agent class
│   ├── factory.py                 # Agent creation logic
│   ├── simulated.py               # Mock agents for testing
│   ├── tools/                     # Tool system
│   │   ├── __init__.py
│   │   ├── base.py                # ToolDef, ToolCall
│   │   ├── registry.py            # TOOLS registry
│   │   └── executors.py           # Tool implementations
│   └── streaming/                 # Stream handling
│       ├── __init__.py
│       ├── manager.py             # Stream coordination
│       ├── buffer.py              # Chunk buffering
│       └── detector.py            # Code fence detection
│
├── ui/                            # User interface layer
│   ├── __init__.py
│   ├── app.py                     # Textual app (ArtificeApp)
│   ├── theme.py                   # UI themes
│   ├── widget.py                  # Main terminal widget
│   ├── components/                # Reusable UI components
│   │   ├── __init__.py
│   │   ├── blocks/                # Output blocks
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # BaseBlock, mixins
│   │   │   ├── agent.py           # Agent blocks
│   │   │   ├── code.py            # Code blocks
│   │   │   ├── system.py          # System, Thinking blocks
│   │   │   └── tool.py            # Tool call blocks
│   │   ├── output.py              # TerminalOutput container
│   │   ├── input.py               # TerminalInput
│   │   └── status.py              # Status indicators
│   └── controllers/               # UI coordination (NEW)
│       ├── __init__.py
│       ├── agent_coordinator.py   # Agent communication
│       ├── nav_controller.py      # Keyboard navigation
│       └── context_tracker.py     # Context highlighting
│
└── utils/                         # Shared utilities
    ├── __init__.py
    ├── text.py                    # Text processing
    ├── async_helpers.py           # Async utilities
    └── fencing/                   # Code fence parsing
        ├── __init__.py
        ├── parser.py              # Core parsing
        └── state.py               # State machine
```

---

## SOLID Improvements

### 1. Single Responsibility Principle (SRP)

**Before:** `ArtificeTerminal` manages:
- Widget composition
- Agent communication
- Code execution
- Key bindings
- Context tracking
- Stream management

**After:** Split into focused coordinators:

```python
class ArtificeTerminal:
    """Main widget delegates to specialized coordinators."""
    
    def __init__(
        self,
        agent_coordinator: AgentCoordinator,
        execution_coordinator: ExecutionCoordinator,
        navigation_controller: NavigationController,
        context_tracker: ContextTracker,
        stream_manager: StreamManager,
    ):
        self._agent = agent_coordinator
        self._executor = execution_coordinator
        self._navigator = navigation_controller
        self._context = context_tracker
        self._stream = stream_manager
```

Each coordinator has one reason to change:
- `AgentCoordinator`: Only changes when agent protocol changes
- `ExecutionCoordinator`: Only changes when execution logic changes
- `NavigationController`: Only changes when keyboard shortcuts change

### 2. Open/Closed Principle

**Before:** Adding new block types requires modifying multiple files.

**After:** Plugin architecture with protocols:

```python
from typing import Protocol

class BlockRenderer(Protocol):
    """Protocol for renderable output blocks."""
    
    def can_render(self, content_type: str) -> bool: ...
    def create_block(self, content: str, **kwargs) -> BaseBlock: ...

class BlockRegistry:
    """Register and lookup block renderers."""
    
    def __init__(self):
        self._renderers: list[BlockRenderer] = []
    
    def register(self, renderer: BlockRenderer) -> None:
        self._renderers.append(renderer)
    
    def create_block(self, content_type: str, content: str) -> BaseBlock:
        for renderer in self._renderers:
            if renderer.can_render(content_type):
                return renderer.create_block(content)
        raise ValueError(f"No renderer for {content_type}")
```

New block types can be added without modifying existing code.

### 3. Liskov Substitution Principle

**Define clear interfaces:**

```python
class AgentProtocol(Protocol):
    """All agents (real and simulated) implement this."""
    
    async def send(
        self, 
        prompt: str, 
        on_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse: ...
    
    def clear(self) -> None: ...
    
    @property
    def has_pending_tool_calls(self) -> bool: ...

class Executor(ABC):
    """Base class for all code executors."""
    
    @abstractmethod
    async def execute(
        self,
        code: str,
        on_output: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> ExecutionResult: ...
    
    @abstractmethod
    def reset(self) -> None: ...

# All implementations are substitutable
class PythonExecutor(Executor): ...
class ShellExecutor(Executor): ...
class TmuxShellExecutor(Executor): ...
```

### 4. Interface Segregation

**Split large interfaces into focused ones:**

```python
# Before: One large interface
class TerminalWidget:
    def handle_agent_response(...): ...
    def handle_code_execution(...): ...
    def handle_navigation(...): ...
    def handle_streaming(...): ...

# After: Role-specific protocols
class StreamHandler(Protocol):
    def on_chunk(self, text: str) -> None: ...
    def on_thinking_chunk(self, text: str) -> None: ...
    def finalize(self) -> None: ...

class ExecutionHandler(Protocol):
    async def execute(self, code: str, language: str) -> ExecutionResult: ...
    def reset(self) -> None: ...

class BlockContainer(Protocol):
    def append_block(self, block: BaseBlock) -> None: ...
    def scroll_end(self, animate: bool = False) -> None: ...
```

### 5. Dependency Inversion

**High-level modules depend on abstractions:**

```python
# Before: Direct dependency
class ArtificeTerminal:
    def __init__(self, app: ArtificeApp):
        self._config = app.config
        self._exec = ExecutionCoordinator(config, ...)  # Direct creation
        self._agent = create_agent(config, ...)        # Direct creation

# After: Dependency injection
class ArtificeTerminal:
    def __init__(
        self,
        config: ConfigProtocol,
        execution_coordinator: ExecutionHandler,
        agent_coordinator: AgentCoordinatorProtocol,
        stream_manager: StreamHandler,
        block_registry: BlockRegistry,
    ):
        self._config = config
        self._exec = execution_coordinator
        self._agent = agent_coordinator
        self._stream = stream_manager
        self._blocks = block_registry

# Factory for wiring
class WidgetFactory:
    def create_terminal(self, config: ArtificeConfig) -> ArtificeTerminal:
        exec_coord = ExecutionCoordinator(config, ...)
        agent_coord = AgentCoordinator(config, ...)
        stream_mgr = StreamManager(...)
        blocks = BlockRegistry()
        blocks.register(CodeBlockRenderer())
        blocks.register(AgentBlockRenderer())
        
        return ArtificeTerminal(
            config=config,
            execution_coordinator=exec_coord,
            agent_coordinator=agent_coord,
            stream_manager=stream_mgr,
            block_registry=blocks,
        )
```

---

## Implementation Phases

### Phase 1: Reorganize (No Behavior Changes)

**Goal:** Restructure files without changing functionality

1. **Create new directory structure**
   ```bash
   mkdir -p src/artifice/{core,execution,agent/tools,agent/streaming,ui/components/blocks,ui/controllers,utils/fencing}
   ```

2. **Move files with re-exports**
   - Move `config.py` → `core/config.py`
   - Move `history.py` → `core/history.py`
   - Move `terminal/` → `ui/`
   - Move `execution/` → `execution/` (reorganize internals)
   - Move agent files → `agent/`
   
3. **Add backward compatibility re-exports**
   ```python
   # In old locations, re-export from new locations
   from artifice.core.config import ArtificeConfig, load_config
   ```

4. **Consolidate small files**
   - Merge `utils.py`, `theme.py` → `utils/` package
   - Merge `input_mode.py` → `core/events.py`

5. **Run tests to verify nothing broke**

### Phase 2: Extract & Simplify

**Goal:** Break down large classes

1. **Extract `AgentCoordinator` from `ArtificeTerminal`**
   - Move all agent-related methods
   - Handle agent prompts, streaming, tool calls
   - ~150 lines extracted

2. **Extract `NavigationController`**
   - Handle all key bindings and navigation
   - Block highlighting, focus management
   - ~50 lines extracted

3. **Simplify `StreamingFenceDetector`**
   - Split into:
     - `FenceParser`: Pure parsing logic (no UI)
     - `BlockFactory`: Creates blocks from parsed content
     - `StreamManager`: Coordinates between parser and UI

4. **Create `BlockRenderer` protocol**
   - Refactor block creation to use registry pattern
   - Each block type registers itself

5. **Run tests after each extraction**

### Phase 3: Dependency Injection

**Goal:** Decouple components

1. **Create `WidgetFactory`**
   - Central place for wiring dependencies
   - Configuration-driven instantiation

2. **Convert `ArtificeTerminal` to receive coordinators**
   - Remove all direct instantiation
   - Inject via constructor

3. **Add `EventBus` for loose coupling**
   ```python
   class EventBus:
       def subscribe(self, event_type: type, handler: Callable) -> None: ...
       def publish(self, event: object) -> None: ...
   ```
   
   Events:
   - `AgentResponseReceived`
   - `CodeBlockDetected`
   - `ExecutionCompleted`
   - `NavigationRequested`

4. **Update `app.py` to use factory**
   ```python
   def main():
       config = load_config()
       factory = WidgetFactory(config)
       terminal = factory.create_terminal()
       app = ArtificeApp(terminal, config)
   ```

5. **Run full test suite**

### Phase 4: Clean Up

**Goal:** Remove legacy code

1. **Remove backward compatibility re-exports**
   - Update all imports to use new paths
   - Delete old location files

2. **Update test imports**
   - Ensure all tests use new module paths

3. **Add comprehensive type hints**
   - All public methods typed
   - Protocol definitions for interfaces

4. **Update documentation**
   - Architecture diagram
   - Module dependency graph
   - Contribution guidelines

5. **Final test run + lint check**

---

## File Migration Map

| Current Location | New Location | Notes |
|-----------------|--------------|-------|
| `app.py` | `app.py` | Keep entry point |
| `config.py` | `core/config.py` | Add re-export |
| `history.py` | `core/history.py` | Add re-export |
| `prompts.py` | `core/prompts.py` | Add re-export |
| `input_mode.py` | `core/events.py` | Merge with events |
| `utils.py` | `utils/text.py` | Consolidate |
| `theme.py` | `utils/theme.py` | Consolidate |
| `terminal/widget.py` | `ui/widget.py` | Extract coordinators |
| `terminal/input.py` | `ui/components/input.py` | Move |
| `terminal/output/` | `ui/components/blocks/` | Reorganize |
| `terminal/output/containers.py` | `ui/components/output.py` | Rename |
| `execution/` | `execution/` | Split `common.py` |
| `execution/common.py` | `execution/base.py` | Rename |
| `execution_coordinator.py` | `execution/coordinator.py` | Move |
| `output_callbacks.py` | `execution/callbacks.py` | Rename |
| `agent/agent.py` | `agent/client.py` | Rename |
| `agent/__init__.py` | `agent/factory.py` | Extract factory |
| `agent/tools.py` | `agent/tools/base.py` + `registry.py` | Split |
| `agent/tool_executors.py` | `agent/tools/executors.py` | Move |
| `stream_manager.py` | `agent/streaming/manager.py` | Move |
| `chunk_buffer.py` | `agent/streaming/buffer.py` | Move |
| `fence_detector.py` | `agent/streaming/detector.py` + `utils/fencing/` | Split |
| `block_factory.py` | `ui/components/blocks/factory.py` | Merge into blocks |
| `search_mode_manager.py` | `ui/controllers/search.py` | Move |
| `status_indicator.py` | `ui/components/status.py` | Move |

---

## Testing Strategy

1. **After Phase 1:** Run all tests - should pass with no changes
2. **After Phase 2:** Run all tests - may need to update test imports
3. **After Phase 3:** Run all tests - verify DI works correctly
4. **After Phase 4:** Run all tests + add new tests for extracted classes

### New Test Files to Add

```
tests/
├── unit/
│   ├── core/
│   │   ├── test_config.py
│   │   └── test_history.py
│   ├── execution/
│   │   ├── test_python.py
│   │   ├── test_shell.py
│   │   └── test_coordinator.py
│   ├── agent/
│   │   ├── test_client.py
│   │   ├── test_factory.py
│   │   └── tools/
│   │       └── test_registry.py
│   └── ui/
│       ├── test_widget.py
│       └── components/
│           └── test_blocks.py
├── integration/
│   └── test_end_to_end.py
└── conftest.py
```

---

## Benefits

### Immediate

- **Clear module boundaries**: Know where to find things
- **Reduced cognitive load**: Smaller files, focused responsibilities
- **Better testability**: Components can be tested in isolation

### Long-term

- **Extensibility**: New features fit naturally into structure
- **Maintainability**: Changes are localized to specific modules
- **Onboarding**: New developers understand architecture quickly
- **Refactoring safety**: Clear interfaces prevent breaking changes

---

## Migration Checklist

- [ ] Phase 1: Move all files to new locations
- [ ] Phase 1: Add backward compatibility re-exports
- [ ] Phase 1: Verify all tests pass
- [ ] Phase 2: Extract AgentCoordinator
- [ ] Phase 2: Extract NavigationController
- [ ] Phase 2: Split StreamingFenceDetector
- [ ] Phase 2: Implement BlockRenderer protocol
- [ ] Phase 2: Verify all tests pass
- [ ] Phase 3: Create WidgetFactory
- [ ] Phase 3: Implement EventBus
- [ ] Phase 3: Convert to dependency injection
- [ ] Phase 3: Verify all tests pass
- [ ] Phase 4: Remove re-exports
- [ ] Phase 4: Update test imports
- [ ] Phase 4: Add type hints
- [ ] Phase 4: Final test run
- [ ] Phase 4: Update documentation

---

## Notes

- **Backward compatibility**: Use re-exports during transition
- **Git history**: Use `git mv` to preserve file history
- **Incremental**: Each phase should leave codebase in working state
- **Tests first**: Ensure comprehensive test coverage before refactoring
- **Documentation**: Update AGENTS.md with new structure
