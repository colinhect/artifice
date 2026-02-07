"""REPL input component for code entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static, TextArea, Input
from textual import events
from textual_autocomplete import AutoComplete, DropdownItem, TargetState

if TYPE_CHECKING:
    from .history import History


class HistoryAutoComplete(AutoComplete):
    """Custom AutoComplete that applies completion to a TextArea."""

    def __init__(self, terminal_input: TerminalInput, search_input: Input, **kwargs) -> None:
        self._terminal_input = terminal_input
        super().__init__(search_input, **kwargs)

    def apply_completion(self, value: str, state: TargetState) -> None:
        """Apply completion by setting the TextArea text and exiting search mode."""
        self._terminal_input.code = value
        self._terminal_input._exit_search_mode()


class InputTextArea(TextArea):
    """Custom TextArea that handles Enter for submission and history navigation."""

    BINDINGS = [
        Binding("shift+tab", "", "Move to Output", show=True)
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(language="python", **kwargs)

    def set_syntax_highlighting(self, language: str) -> None:
        """Enable or disable Python syntax highlighting."""
        self.language = language

    def _on_key(self, event: events.Key) -> None:
        """Intercept key events before TextArea processes them."""
        # CTRL+R for history search
        if event.key == "ctrl+r":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.HistorySearchRequested())
            return
        # Enter submits the code
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.SubmitRequested())
            return
        # Escape key
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.PythonMode())
            return
        # If input is empty
        if not self.text.strip():
            if event.key == "question_mark":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.AgentMode())
                return
            if event.key == "dollar_sign":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.ShellMode())
                return
            if event.key == "greater_than_sign":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.PythonMode())
                return
        # Let parent handle other keys
        super()._on_key(event)


class TerminalInput(Static):
    """Input component for the Python REPL."""

    BINDINGS = [
        Binding("alt+up", "history_back", "History Back", show=True),
        Binding("alt+down", "history_forward", "History Forward", show=True),
        Binding("ctrl+r", "history_search", "History Search", show=True),
    ]

    DEFAULT_CSS = """
    TerminalInput {
        height: auto;
        max-height: 24;
        padding: 0;
        margin: 0;
        border: none;
    }

    TerminalInput Horizontal {
        height: auto;
        padding: 0;
        margin: 0;
    }

    TerminalInput .prompt {
        width: 2;
        color: $primary;
        padding: 0;
        margin: 0;
    }

    TerminalInput TextArea {
        width: 1fr;
        min-height: 1;
        height: auto;
        max-height: 24;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
        background: transparent;
    }
    
    TerminalInput TextArea:focus {
        border: none !important;
    }

    TerminalInput Input {
        width: 1fr;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
        background: transparent;
    }

    TerminalInput Input:focus {
        border: none !important;
    }
    """

    class SubmitRequested(Message):
        """Internal message from TextArea requesting submission."""
        pass

    class AgentMode(Message):
        pass

    class ShellMode(Message):
        pass

    class PythonMode(Message):
        pass

    class HistoryPrevious(Message):
        """Message requesting previous history item."""
        pass

    class HistoryNext(Message):
        """Message requesting next history item."""
        pass

    class HistorySearchRequested(Message):
        """Message requesting history search interface."""
        pass

    class Submitted(Message):
        """Message sent when code is submitted."""

        def __init__(self, code: str, is_agent_prompt: bool = False, is_shell_command: bool = False) -> None:
            self.code = code
            self.is_agent_prompt = is_agent_prompt
            self.is_shell_command = is_shell_command
            super().__init__()

    def __init__(
        self,
        history: History | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._python_prompt = ">"
        self._ai_prompt = "?"
        self._shell_prompt = "$"
        self.mode = "python"
        self._history = history
        self._search_mode = False
        self._search_input: Input | None = None
        self._autocomplete: HistoryAutoComplete | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(self._python_prompt, classes="prompt", id="prompt-display")
            yield InputTextArea(id="code-input")

    def on_mount(self) -> None:
        """Focus the text area on mount."""
        self.query_one("#code-input", InputTextArea).focus()

    def on_terminal_input_submit_requested(self, event: SubmitRequested) -> None:
        """Handle submission request from TextArea."""
        self.action_submit()

    def on_terminal_input_agent_mode(self, event: AgentMode) -> None:
        """Handle ? key press when input is empty - switch to AI mode."""
        if self.mode != "ai":
            self.mode = "ai"
            self._update_prompt()

    def on_terminal_input_python_mode(self, event: PythonMode) -> None:
        """Handle > key press when input is empty - switch to Python mode."""
        if self.mode != "python":
            self.mode = "python"
            self._update_prompt()

    def on_terminal_input_shell_mode(self, event: ShellMode) -> None:
        """Handle ! key press when input is empty - switch to Shell mode."""
        if self.mode != "shell":
            self.mode = "shell"
            self._update_prompt()

    def _update_prompt(self) -> None:
        """Update the prompt display based on current mode."""
        prompt_widget = self.query_one("#prompt-display", Static)
        text_area = self.query_one("#code-input", InputTextArea)
        
        if self.mode == "ai":
            prompt_widget.update(self._ai_prompt)
            text_area.set_syntax_highlighting(None)
        elif self.mode == "shell":
            prompt_widget.update(self._shell_prompt)
            text_area.set_syntax_highlighting("bash")
        else:
            prompt_widget.update(self._python_prompt)
            text_area.set_syntax_highlighting("python")

    @property
    def code(self) -> str:
        """Get the current code in the input."""
        return self.query_one("#code-input", TextArea).text

    @code.setter
    def code(self, value: str) -> None:
        """Set the code in the input."""
        self.query_one("#code-input", TextArea).text = value

    def clear(self) -> None:
        """Clear the input."""
        self.code = ""

    def action_submit(self) -> None:
        """Submit the current code."""
        code = self.code.strip()
        if code:
            # Add to history before submitting
            if self._history is not None:
                self._history.add(code, self.mode)
                self._history.save()

            # Submit with current mode
            is_ai = self.mode == "ai"
            is_shell = self.mode == "shell"
            self.post_message(self.Submitted(code, is_agent_prompt=is_ai, is_shell_command=is_shell))

    def action_history_back(self) -> None:
        """Navigate to previous history entry."""
        if self._history is None:
            return

        # Get previous entry
        entry = self._history.navigate_back(self.mode, self.code)
        if entry is not None:
            self.code = entry

    def action_history_forward(self) -> None:
        """Navigate to next history entry."""
        if self._history is None:
            return

        # Get next entry
        entry = self._history.navigate_forward(self.mode)
        if entry is not None:
            self.code = entry

    def on_terminal_input_history_search_requested(self, event: HistorySearchRequested) -> None:
        """Handle CTRL+R to enter history search mode."""
        self.action_history_search()

    def action_history_search(self) -> None:
        """Enter history search mode with autocomplete dropdown."""
        if self._history is None:
            return

        if self._search_mode:
            # Already in search mode, exit it
            self._exit_search_mode()
            return

        # Enter search mode
        self._search_mode = True
        
        # Get the text area and horizontal container
        text_area = self.query_one("#code-input", InputTextArea)
        horizontal = self.query_one(Horizontal)
        
        # Hide the text area
        text_area.display = False
        
        # Create search input
        self._search_input = Input(placeholder="Search history (CTRL+R)...", id="history-search-input")
        horizontal.mount(self._search_input)
        
        # Create autocomplete with history items
        def get_history_candidates(state: TargetState) -> list[DropdownItem]:
            """Get filtered history items based on search input."""
            search_text = state.text.lower()
            
            # Get history for current mode
            if self.mode == "ai":
                history_list = self._history._ai_history
            elif self.mode == "shell":
                history_list = self._history._shell_history
            else:
                history_list = self._history._python_history
            
            # Filter and reverse (most recent first)
            filtered = [
                DropdownItem(main=item)
                for item in reversed(history_list)
                if search_text in item.lower()
            ]
            
            return filtered[:50]  # Limit to 50 items
        
        # Mount autocomplete
        self._autocomplete = HistoryAutoComplete(
            terminal_input=self,
            search_input=self._search_input,
            candidates=get_history_candidates
        )
        horizontal.mount(self._autocomplete)
        
        # Focus the search input
        self._search_input.focus()

    def _exit_search_mode(self) -> None:
        """Exit history search mode."""
        if not self._search_mode:
            return
        
        self._search_mode = False
        
        # Remove autocomplete and search input
        if self._autocomplete is not None:
            self._autocomplete.remove()
            self._autocomplete = None
        
        if self._search_input is not None:
            self._search_input.remove()
            self._search_input = None
        
        # Show and focus the text area
        text_area = self.query_one("#code-input", InputTextArea)
        text_area.display = True
        text_area.focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key events for exiting search mode."""
        if self._search_mode and event.key == "escape":
            self._exit_search_mode()
            event.prevent_default()
            event.stop()
