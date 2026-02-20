"""REPL input component for code entry."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, TextArea, LoadingIndicator
from textual import events
from textual_autocomplete import DropdownItem, TargetState

from ..prompts import list_prompts, load_prompt, fuzzy_match
from ..input_mode import InputMode
from ..search_mode_manager import SearchModeManager

if TYPE_CHECKING:
    from ..history import History


class InputTextArea(TextArea):
    """Custom TextArea that handles Enter for submission and history navigation."""

    BINDINGS = [
        Binding("ctrl+s", "submit_code", "Submit", show=True, priority=True),
        Binding("ctrl+j", "insert_newline", "New Line", show=False, priority=True),
        Binding("ctrl+k", "clear_input", "Clear Input", show=True, priority=True),
        Binding("pageup", "scroll_output_up", "Page Up", show=False),
        Binding("pagedown", "scroll_output_down", "Page Down", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(language="python", **kwargs)

    def action_submit_code(self) -> None:
        """Submit the code."""
        self.post_message(TerminalInput.SubmitRequested())

    def action_insert_newline(self) -> None:
        """Insert a newline."""
        self.insert("\n")

    def action_clear_input(self) -> None:
        """Clear the input text area."""
        self.text = ""

    def action_scroll_output_up(self) -> None:
        """Scroll the output window up by one page."""
        self.screen.query_one("#output").scroll_page_up(animate=True)

    def action_scroll_output_down(self) -> None:
        """Scroll the output window down by one page."""
        self.screen.query_one("#output").scroll_page_down(animate=True)

    def set_syntax_highlighting(self, language: str | None) -> None:
        """Set syntax highlighting language."""
        self.language = language
        self.theme = "vscode_dark"

    async def _on_key(self, event: events.Key) -> None:
        """Intercept key events before TextArea processes them."""
        # Delegate to specific handlers
        if await self._handle_ctrl_r(event):
            return
        if await self._handle_enter(event):
            return
        if await self._handle_insert(event):
            return
        if await self._handle_escape(event):
            return
        if await self._handle_up(event):
            return
        if await self._handle_down(event):
            return
        if await self._handle_empty_input_shortcuts(event):
            return
        if await self._handle_slash(event):
            return

        # Let parent handle other keys
        await super()._on_key(event)

    async def _handle_ctrl_r(self, event: events.Key) -> bool:
        """Handle CTRL+R for history search."""
        if event.key == "ctrl+r":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.HistorySearchRequested())
            return True
        return False

    async def _handle_enter(self, event: events.Key) -> bool:
        """Handle Enter key - submit on single line, insert newline on multi-line."""
        if event.key == "enter":
            line_count = self.document.line_count
            if line_count == 1:
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.SubmitRequested())
                return True
        return False

    async def _handle_insert(self, event: events.Key) -> bool:
        """Handle Insert key - cycle through modes."""
        if event.key == "insert":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.CycleMode())
            return True
        return False

    async def _handle_escape(self, event: events.Key) -> bool:
        """Handle Escape key - return to Python mode."""
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.SetMode(InputMode.PYTHON))
            return True
        return False

    async def _handle_up(self, event: events.Key) -> bool:
        """Handle Up arrow - history navigation when at top of input."""
        if event.key == "up":
            cursor_row, _ = self.cursor_location
            if cursor_row == 0:
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.HistoryPrevious())
                return True
        return False

    async def _handle_down(self, event: events.Key) -> bool:
        """Handle Down arrow - history navigation when at bottom of input."""
        if event.key == "down":
            cursor_row, _ = self.cursor_location
            line_count = self.document.line_count
            if cursor_row >= line_count - 1:
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.HistoryNext())
                return True
        return False

    async def _handle_empty_input_shortcuts(self, event: events.Key) -> bool:
        """Handle mode shortcuts when input is empty."""
        if not self.text.strip():
            shortcuts = {
                "greater_than_sign": InputMode.AI,
                "dollar_sign": InputMode.SHELL,
                "right_square_bracket": InputMode.PYTHON,
            }
            if mode := shortcuts.get(event.key):
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.SetMode(mode))
                return True
        return False

    async def _handle_slash(self, event: events.Key) -> bool:
        """Handle slash on empty input - trigger prompt search."""
        if not self.text.strip() and event.character == "/":
            event.prevent_default()
            event.stop()
            self.post_message(TerminalInput.PromptSearchRequested())
            return True
        return False


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

        def __init__(self, mode: InputMode) -> None:
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

    class PromptSearchRequested(Message):
        """Message requesting prompt template search interface."""

        pass

    class PromptSelected(Message):
        """Message sent when a prompt template is selected via / command."""

        def __init__(self, name: str, path: Path, content: str) -> None:
            self.name = name
            self.path = path
            self.content = content
            super().__init__()

    class Submitted(Message):
        """Message sent when code is submitted."""

        def __init__(
            self,
            code: str,
            is_agent_prompt: bool = False,
            is_shell_command: bool = False,
        ) -> None:
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
        self.mode = InputMode.AI
        self._history = history
        self._search_manager: SearchModeManager | None = None
        self.add_class("in-context")

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="prompt-container"):
                yield LoadingIndicator(id="activity-indicator")
                yield Static("]", classes="prompt", id="prompt-display")
            yield InputTextArea(id="code-input")

    def on_mount(self) -> None:
        """Focus the text area on mount."""
        text_area = self.query_one("#code-input", InputTextArea)
        text_area.focus()
        # Hide the loading indicator initially
        self.query_one("#activity-indicator", LoadingIndicator).styles.display = "none"
        self._update_prompt()
        # Initialize search manager
        self._search_manager = SearchModeManager(
            text_area=text_area,
            horizontal=self.query_one(Horizontal),
            screen=self.screen,
        )

    def on_terminal_input_submit_requested(self, _: SubmitRequested) -> None:
        """Handle submission request from TextArea."""
        self.action_submit()

    def on_terminal_input_set_mode(self, event: SetMode) -> None:
        """Handle mode switch request."""
        self.set_mode(event.mode)

    def set_mode(self, mode: InputMode) -> None:
        """Switch to the given mode if not already active."""
        if self.mode != mode:
            self.mode = mode
            self._update_prompt()

    def on_terminal_input_cycle_mode(self, _: CycleMode) -> None:
        """Handle Insert key press - cycle through modes while keeping input."""
        self.mode = self.mode.cycle_next()
        self._update_prompt()

    def on_terminal_input_history_previous(self, _: HistoryPrevious) -> None:
        """Handle up arrow key press at top of input - navigate to previous history."""
        self.action_history_back()

    def on_terminal_input_history_next(self, _: HistoryNext) -> None:
        """Handle down arrow key press at bottom of input - navigate to next history."""
        self.action_history_forward()

    def _update_prompt(self) -> None:
        """Update the prompt display based on current mode."""
        prompt_widget = self.query_one("#prompt-display", Static)
        text_area = self.query_one("#code-input", InputTextArea)

        with self.app.batch_update():
            prompt_widget.update(self.mode.prompt_char)
            text_area.set_syntax_highlighting(self.mode.language)

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
                self._history.add(code, self.mode.value.name)
                self._history.save()

            # Submit with current mode
            self.post_message(
                self.Submitted(
                    code,
                    is_agent_prompt=self.mode.is_ai,
                    is_shell_command=self.mode.is_shell,
                )
            )

    def action_history_back(self) -> None:
        """Navigate to previous history entry."""
        if self._history is None:
            return

        # Get previous entry
        entry = self._history.navigate_back(self.mode.value.name, self.code)
        if entry is not None:
            self.code = entry

    def action_history_forward(self) -> None:
        """Navigate to next history entry."""
        if self._history is None:
            return

        # Get next entry
        entry = self._history.navigate_forward(self.mode.value.name)
        if entry is not None:
            self.code = entry

    def on_terminal_input_history_search_requested(
        self, _: HistorySearchRequested
    ) -> None:
        """Handle CTRL+R to enter history search mode."""
        self.action_history_search()

    def action_history_search(self) -> None:
        """Enter history search mode with autocomplete dropdown."""
        if self._history is None or self._search_manager is None:
            return

        if self._search_manager.active:
            # Already in search mode, exit it
            self._search_manager.exit_search()
            return

        # Create autocomplete candidates function
        def get_history_candidates(state: TargetState) -> list[DropdownItem]:
            """Get filtered history items based on search input."""
            if self._history is None or self._search_manager is None:
                return []

            search_text = state.text.lower()

            # Get history for current mode
            mode_name = self.mode.value.name
            if mode_name == "ai":
                history_list = self._history._ai_history
            elif mode_name == "shell":
                history_list = self._history._shell_history
            else:
                history_list = self._history._python_history

            # Filter and reverse (most recent first)
            def truncate_multiline(item: str) -> str:
                """Truncate multi-line items to first 3 lines with ... if more exist."""
                lines = item.split("\n")
                if len(lines) > 3:
                    truncated = "\n".join(lines[:2] + [lines[2] + "..."])
                    # Store mapping from truncated to full
                    if self._search_manager:
                        self._search_manager.set_truncation_mapping(truncated, item)
                    return truncated
                return item

            filtered = [
                DropdownItem(main=truncate_multiline(item))
                for item in reversed(history_list)
                if search_text in item.lower()
            ]

            return filtered[:50]  # Limit to 50 items

        # Apply completion function
        def apply_history(value: str) -> None:
            """Apply history selection and exit search."""
            if self._search_manager:
                full_text = self._search_manager.get_full_text(value)
                self.code = full_text
                self._search_manager.exit_search()

        # Enter search mode
        self._search_manager.enter_search(
            placeholder="Search history...",
            candidates_fn=get_history_candidates,
            apply_fn=apply_history,
        )

    def on_terminal_input_prompt_search_requested(
        self, _: PromptSearchRequested
    ) -> None:
        """Handle / key to enter prompt search mode."""
        self._enter_prompt_search_mode()

    def _enter_prompt_search_mode(self) -> None:
        """Enter prompt template search mode with autocomplete dropdown."""
        if self._search_manager is None:
            return

        prompts = list_prompts()
        if not prompts:
            return

        if self._search_manager.active:
            return

        prompt_names = sorted(prompts.keys())

        def get_prompt_candidates(state: TargetState) -> list[DropdownItem]:
            query = state.text.strip()
            if not query:
                return [DropdownItem(main=name) for name in prompt_names]
            return [
                DropdownItem(main=name)
                for name in prompt_names
                if fuzzy_match(query, name)
            ]

        def apply_prompt(value: str) -> None:
            """Load the selected prompt and exit search."""
            prompt = load_prompt(value)
            if prompt is not None:
                (path, text) = prompt
                self.post_message(
                    TerminalInput.PromptSelected(name=value, path=path, content=text.strip())
                )
            if self._search_manager:
                self._search_manager.exit_search()

        # Enter search mode
        self._search_manager.enter_search(
            placeholder="Search prompts...",
            candidates_fn=get_prompt_candidates,
            apply_fn=apply_prompt,
        )

    def on_key(self, event: events.Key) -> None:
        """Handle key events for exiting search mode."""
        if (
            self._search_manager
            and self._search_manager.active
            and event.key == "escape"
        ):
            self._search_manager.exit_search()
            event.prevent_default()
            event.stop()

    def focus_input(self) -> None:
        """Focus the input text area."""
        if not self._search_manager or not self._search_manager.active:
            self.query_one("#code-input", InputTextArea).focus()
