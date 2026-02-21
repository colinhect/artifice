"""NavigationController - manages keyboard navigation and block highlighting."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artifice.ui.components.blocks.blocks import BaseBlock
    from artifice.ui.components.input import TerminalInput
    from artifice.ui.components.output import TerminalOutput
    from artifice.ui.widget import ArtificeTerminal


class NavigationController:
    """Manages keyboard navigation between input and output blocks.

    This class encapsulates all navigation-related logic from the main terminal
    widget, including:
    - Block highlighting (up/down navigation)
    - Focus management between input and output
    - Keyboard shortcut handling for navigation
    """

    def __init__(
        self,
        input_widget: TerminalInput,
        output_widget: TerminalOutput,
        terminal: ArtificeTerminal,
    ) -> None:
        """Initialize the navigation controller.

        Args:
            input_widget: The terminal input widget
            output_widget: The terminal output widget
            terminal: The main terminal widget (for focus_input)
        """
        self._input = input_widget
        self._output = output_widget
        self._terminal = terminal

    def navigate_up(self) -> None:
        """Navigate up: from input to output, or up through output blocks."""
        from artifice.ui.components.input import InputTextArea

        input_area = self._input.query_one("#code-input", InputTextArea)
        if input_area.has_focus and self._output.has_blocks:
            self._output.focus()
        elif self._output.has_focus:
            self._output.highlight_previous()

    def navigate_down(self) -> None:
        """Navigate down: through output blocks, or from output to input."""
        if self._output.has_focus:
            if not self._output.highlight_next():
                self._terminal.focus_input()

    def scroll_output_up(self) -> None:
        """Scroll the output window up by one page."""
        self._output.scroll_page_up(animate=True)

    def scroll_output_down(self) -> None:
        """Scroll the output window down by one page."""
        self._output.scroll_page_down(animate=True)

    def focus_input(self) -> None:
        """Focus the input text area."""
        self._terminal.focus_input()

    def highlight_block(self, block: BaseBlock) -> None:
        """Highlight a specific block in the output.

        Args:
            block: The block to highlight
        """
        idx = self._output.index_of(block)
        if idx is not None:
            self._output.highlight_block_at(idx)
            self._output.focus()

    def on_stream_paused(self, code_block: BaseBlock | None) -> None:
        """Handle stream pause by highlighting the paused code block.

        Args:
            code_block: The code block that triggered the pause
        """
        if code_block is not None:
            self.highlight_block(code_block)
