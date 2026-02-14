"""REPL input component for code entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, TextArea, Input, LoadingIndicator
from textual import events
from textual_autocomplete import AutoComplete, DropdownItem, TargetState

if TYPE_CHECKING:
    from .history import History

class HistoryAutoComplete(AutoComplete):
    """Custom AutoComplete that applies completion to a TextArea."""

    def __init__(self, terminal_input: TerminalInput, search_input: Input, **kwargs) -> None:
        self._terminal_input = terminal_input
        self._truncated_to_full: dict[str, str] = {}  # Map truncated text to full text
        super().__init__(search_input, **kwargs)

    def apply_completion(self, value: str, state: TargetState) -> None:
        """Apply completion by setting the TextArea text and exiting search mode."""
        # Use the original full text if this was a truncated item
        full_text = self._truncated_to_full.get(value, value)
        self._terminal_input.code = full_text
        self._terminal_input._exit_search_mode()


class InputTextArea(TextArea):
    """Custom TextArea that handles Enter for submission and history navigation."""

    BINDINGS = [
        Binding("ctrl+s", "submit_code", "Submit", show=True, priority=True),
        Binding("ctrl+j", "insert_newline", "New Line", show=False, priority=True),
        Binding("ctrl+k", "clear_input", "Clear Input", show=True, priority=True),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(language="python", **kwargs)
        self._focused_placeholder: str = ""
        self._unfocused_placeholder: str = " [cyan]enter[/] to execute    [cyan]ctrl+i[/] return to prompt"

    def action_submit_code(self) -> None:
        """Submit the code."""
        self.post_message(TerminalInput.SubmitRequested())

    def action_insert_newline(self) -> None:
        """Insert a newline."""
        # Insert newline at cursor position
        self.insert("\n")

    def action_clear_input(self) -> None:
        """Clear the input text area."""
        self.text = ""

    def set_syntax_highlighting(self, language: str) -> None:
        """Enable or disable Python syntax highlighting."""
        self.language = language
        self.theme="vscode_dark"

    def set_focused_placeholder(self, text: str) -> None:
        """Set the placeholder text to show when focused."""
        self._focused_placeholder = text
        if self.has_focus:
            pass
            #self.placeholder = str(Text.from_markup(text))

    def on_focus(self) -> None:
        """Update placeholder when gaining focus."""
        pass
        #self.placeholder = str(Text.from_markup(self._focused_placeholder))

    def on_blur(self) -> None:
        """Update placeholder when losing focus."""
        pass
        #self.placeholder = str(Text.from_markup(self._unfocused_placeholder))

    async def _on_key(self, event: events.Key) -> None:
        """Intercept key events before TextArea processes them."""
        # CTRL+R for history search
        if event.key == "ctrl+r":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.HistorySearchRequested())
            return

        # Plain Enter key (modifiers are handled via Bindings)
        if event.key == "enter":
            # Check if text has multiple lines
            line_count = self.document.line_count
            if line_count == 1:
                # Single line: submit the code
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.SubmitRequested())
                return
            # Multi-line: let it fall through to insert newline
        # Insert key - cycle through modes
        if event.key == "insert":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.CycleMode())
            return
        # Escape key
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.SetMode("python"))
            return
        # Up/Down for history navigation when at top/bottom of input
        if event.key == "up":
            # Check if cursor is on the first line
            cursor_row, _ = self.cursor_location
            if cursor_row == 0:
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.HistoryPrevious())
                return
        elif event.key == "down":
            # Check if cursor is on the last line
            cursor_row, _ = self.cursor_location
            line_count = self.document.line_count
            if cursor_row >= line_count - 1:
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.HistoryNext())
                return
        # If input is empty
        if not self.text.strip():
            if event.key == "greater_than_sign":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.SetMode("ai"))
                return
            if event.key == "dollar_sign":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.SetMode("shell"))
                return
            if event.key == "right_square_bracket":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.SetMode("python"))
                return
        # Let parent handle other keys
        await super()._on_key(event)


class TerminalInput(Static):
    """Input component for the Python REPL."""

    BINDINGS = [
        Binding("ctrl+r", "history_search", "History Search", show=True),
    ]

    class SubmitRequested(Message):
        """Internal message from TextArea requesting submission."""
        pass

    class SetMode(Message):
        """Message requesting a mode switch."""
        def __init__(self, mode: str) -> None:
            super().__init__()
            self.mode = mode

    class CycleMode(Message):
        """Message requesting to cycle through modes."""
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

    _MODE_CONFIG = {
        "ai": (">", "ai prompt...       [red]][/] python  [cyan]$[/] shell", None),
        "shell": ("$", "shell command...   [cyan]>[/] ai  [cyan]][/] python", "bash"),
        "python": ("]", "python code...     [cyan]>[/] ai  [cyan]$[/] shell", "python"),
    }

    def __init__(
        self,
        history: History | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.mode = "ai"
        self._history = history
        self._search_mode = False
        self._search_input: Input | None = None
        self._autocomplete: HistoryAutoComplete | None = None
        self._activity_mode = False  # Whether activity indicator is shown
        self.add_class("in-context")

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="prompt-container"):
                yield LoadingIndicator(id="activity-indicator")
                yield Static("]", classes="prompt", id="prompt-display")
            yield InputTextArea(id="code-input")

    def on_mount(self) -> None:
        """Focus the text area on mount."""
        self.query_one("#code-input", InputTextArea).focus()
        # Hide the loading indicator initially
        self.query_one("#activity-indicator", LoadingIndicator).styles.display = "none"
        self._update_prompt()

    def on_terminal_input_submit_requested(self, _: SubmitRequested) -> None:
        """Handle submission request from TextArea."""
        self.action_submit()

    def on_terminal_input_set_mode(self, event: SetMode) -> None:
        """Handle mode switch request."""
        self.set_mode(event.mode)

    def set_mode(self, mode: str) -> None:
        """Switch to the given mode if not already active."""
        if self.mode != mode:
            self.mode = mode
            self._update_prompt()

    def on_terminal_input_cycle_mode(self, _: CycleMode) -> None:
        """Handle Insert key press - cycle through modes while keeping input."""
        # Cycle: python -> ai -> shell -> python
        if self.mode == "python":
            self.mode = "ai"
        elif self.mode == "ai":
            self.mode = "shell"
        else:  # shell
            self.mode = "python"
        self._update_prompt()

    def on_terminal_input_history_previous(self, _: HistoryPrevious) -> None:
        """Handle up arrow key press at top of input - navigate to previous history."""
        self.action_history_back()

    def on_terminal_input_history_next(self, _: HistoryNext) -> None:
        """Handle down arrow key press at bottom of input - navigate to next history."""
        self.action_history_forward()

    def _update_prompt(self) -> None:
        """Update the prompt display based on current mode."""
        prompt_char, placeholder, lang = self._MODE_CONFIG[self.mode]
        prompt_widget = self.query_one("#prompt-display", Static)
        text_area = self.query_one("#code-input", InputTextArea)

        with self.app.batch_update():
            prompt_widget.update(prompt_char)
            text_area.set_focused_placeholder(placeholder)
            text_area.set_syntax_highlighting(lang)

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

    def on_terminal_input_history_search_requested(self, _: HistorySearchRequested) -> None:
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
        self._search_input = Input(placeholder="Search history...", id="history-search-input")
        horizontal.mount(self._search_input)

        # Create autocomplete with history items
        def get_history_candidates(state: TargetState) -> list[DropdownItem]:
            """Get filtered history items based on search input."""
            search_text = state.text.lower()

            if self._history is None:
                return []

            # Get history for current mode
            if self.mode == "ai":
                history_list = self._history._ai_history
            elif self.mode == "shell":
                history_list = self._history._shell_history
            else:
                history_list = self._history._python_history

            # Filter and reverse (most recent first)
            def truncate_multiline(item: str) -> str:
                """Truncate multi-line items to first 3 lines with ... if more exist."""
                lines = item.split('\n')
                if len(lines) > 3:
                    truncated = '\n'.join(lines[:2] + [lines[2] + '...'])
                    # Store mapping from truncated to full
                    if self._autocomplete is not None:
                        self._autocomplete._truncated_to_full[truncated] = item
                    return truncated
                return item

            filtered = [
                DropdownItem(main=truncate_multiline(item))
                for item in reversed(history_list)
                if search_text in item.lower()
            ]

            return filtered[:50]  # Limit to 50 items

        # Mount autocomplete at screen level to avoid clipping
        self._autocomplete = HistoryAutoComplete(
            terminal_input=self,
            search_input=self._search_input,
            candidates=get_history_candidates
        )
        # Mount to screen instead of horizontal container to prevent clipping
        self.screen.mount(self._autocomplete)

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

    def focus_input(self) -> None:
        """Focus the input text area."""
        if not self._search_mode:
            self.query_one("#code-input", InputTextArea).focus()
