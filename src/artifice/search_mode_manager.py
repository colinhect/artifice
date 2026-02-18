"""Search mode management for terminal input."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from textual.containers import Horizontal
from textual.widgets import Input
from textual_autocomplete import AutoComplete, DropdownItem, TargetState

if TYPE_CHECKING:
    from textual.screen import Screen
    from .terminal.input import InputTextArea


class SearchAutoComplete(AutoComplete):
    """Generic AutoComplete with customizable apply logic."""

    def __init__(
        self,
        search_input: Input,
        apply_fn: Callable[[str], None],
        **kwargs,
    ) -> None:
        self._apply_fn = apply_fn
        super().__init__(search_input, **kwargs)

    def apply_completion(self, value: str, state: TargetState) -> None:
        """Apply completion using the provided function."""
        self._apply_fn(value)


class SearchModeManager:
    """Manages search UI lifecycle for history or prompt search."""

    def __init__(
        self,
        text_area: InputTextArea,
        horizontal: Horizontal,
        screen: Screen,
    ):
        self._text_area = text_area
        self._horizontal = horizontal
        self._screen = screen
        self._search_input: Input | None = None
        self._autocomplete: SearchAutoComplete | None = None
        self._active = False
        # For history search - map truncated items to full text
        self._truncated_to_full: dict[str, str] = {}

    @property
    def active(self) -> bool:
        """True if search mode is currently active."""
        return self._active

    def enter_search(
        self,
        placeholder: str,
        candidates_fn: Callable[[TargetState], list[DropdownItem]],
        apply_fn: Callable[[str], None],
    ) -> None:
        """Show search input and autocomplete dropdown."""
        if self._active:
            return

        self._active = True

        # Hide the text area
        self._text_area.display = False

        # Create search input
        self._search_input = Input(placeholder=placeholder)
        self._horizontal.mount(self._search_input)

        # Create autocomplete
        self._autocomplete = SearchAutoComplete(
            search_input=self._search_input,
            apply_fn=apply_fn,
            candidates=candidates_fn,
        )
        # Mount to screen to avoid clipping
        self._screen.mount(self._autocomplete)

        # Focus the search input
        self._search_input.focus()

    def exit_search(self) -> None:
        """Hide search UI and return to text area."""
        if not self._active:
            return

        self._active = False

        # Remove autocomplete and search input
        if self._autocomplete is not None:
            self._autocomplete.remove()
            self._autocomplete = None

        if self._search_input is not None:
            self._search_input.remove()
            self._search_input = None

        # Clear truncation mapping
        self._truncated_to_full.clear()

        # Show and focus the text area
        self._text_area.display = True
        self._text_area.focus()

    def set_truncation_mapping(self, truncated: str, full: str) -> None:
        """Store mapping from truncated text to full text (for history search)."""
        self._truncated_to_full[truncated] = full

    def get_full_text(self, truncated: str) -> str:
        """Get full text from truncated text, or return as-is if not found."""
        return self._truncated_to_full.get(truncated, truncated)
