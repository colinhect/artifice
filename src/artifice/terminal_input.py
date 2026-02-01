"""REPL input component for code entry."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static, TextArea
from textual import events


class ReplTextArea(TextArea):
    """Custom TextArea that handles Enter for submission and history navigation."""

    def __init__(self, **kwargs) -> None:
        super().__init__(language="python", **kwargs)

    def set_syntax_highlighting(self, language: str) -> None:
        """Enable or disable Python syntax highlighting."""
        self.language = language

    def _on_key(self, event: events.Key) -> None:
        """Intercept key events before TextArea processes them."""
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
            self.post_message(TerminalInput.EscapePressed())
            return
        # If input is empty
        if not self.text.strip():
            if event.key == "question_mark":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.QuestionMarkPressed())
                return
            if event.key == "exclamation_mark":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.ExclamationMarkPressed())
                return
            if event.key == "greater_than_sign":
                event.prevent_default()
                event.stop()
                self.post_message(TerminalInput.GreaterThanSignPressed())
                return
        # Let parent handle other keys
        super()._on_key(event)


class TerminalInput(Static):
    """Input component for the Python REPL."""

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
    """

    BINDINGS = []

    class SubmitRequested(Message):
        """Internal message from TextArea requesting submission."""
        pass

    class EscapePressed(Message):
        """Internal message from TextArea when escape is pressed."""
        pass

    class QuestionMarkPressed(Message):
        """Internal message from TextArea when ? is pressed on empty input."""
        pass

    class ExclamationMarkPressed(Message):
        """Internal message from TextArea when ! is pressed on empty input."""
        pass

    class GreaterThanSignPressed(Message):
        """Internal message from TextArea when > is pressed on empty input."""
        pass

    class HistoryPrevious(Message):
        """Message requesting previous history item."""
        pass

    class HistoryNext(Message):
        """Message requesting next history item."""
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
        prompt: str = ">",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._python_prompt = ">"
        self._ai_prompt = "?"
        self._shell_prompt = "!"
        self.mode = "python"

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(self._python_prompt, classes="prompt", id="prompt-display")
            yield ReplTextArea(id="code-input")

    def on_mount(self) -> None:
        """Focus the text area on mount."""
        self.query_one("#code-input", ReplTextArea).focus()

    def on_terminal_input_submit_requested(self, event: SubmitRequested) -> None:
        """Handle submission request from TextArea."""
        self.action_submit()

    def on_terminal_input_escape_pressed(self, event: EscapePressed) -> None:
        """Handle escape key press - switch to Python mode."""
        if self.mode != "python":
            self.mode = "python"
            self._update_prompt()

    def on_terminal_input_question_mark_pressed(self, event: QuestionMarkPressed) -> None:
        """Handle ? key press when input is empty - switch to AI mode."""
        if self.mode != "ai":
            self.mode = "ai"
            self._update_prompt()

    def on_terminal_input_greater_than_sign_pressed(self, event: GreaterThanSignPressed) -> None:
        """Handle > key press when input is empty - switch to Python mode."""
        if self.mode != "python":
            self.mode = "python"
            self._update_prompt()

    def on_terminal_input_exclamation_mark_pressed(self, event: ExclamationMarkPressed) -> None:
        """Handle ! key press when input is empty - switch to Shell mode."""
        if self.mode != "shell":
            self.mode = "shell"
            self._update_prompt()

    def _update_prompt(self) -> None:
        """Update the prompt display based on current mode."""
        prompt_widget = self.query_one("#prompt-display", Static)
        text_area = self.query_one("#code-input", ReplTextArea)
        
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

    @property
    def is_ai_mode(self) -> bool:
        """Check if currently in AI mode."""
        return self.mode == "ai"

    def clear(self) -> None:
        """Clear the input."""
        self.code = ""

    def action_submit(self) -> None:
        """Submit the current code."""
        code = self.code.strip()
        if code:
            # Submit with current mode
            is_shell = self.mode == "shell"
            self.post_message(self.Submitted(code, is_agent_prompt=self.is_ai_mode, is_shell_command=is_shell))
