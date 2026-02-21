"""History management for terminal input."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class History:
    """Manages command history for different input modes."""

    MODES = ("python", "ai", "shell")

    def __init__(
        self,
        history_file: str | Path | None = None,
        max_history_size: int = 1000,
    ) -> None:
        """Initialize history manager.

        Args:
            history_file: Path to history file. Defaults to ~/.artifice_history.json
            max_history_size: Maximum number of entries to keep per mode.
        """
        self._histories: dict[str, list[str]] = {mode: [] for mode in self.MODES}
        self._indices: dict[str, int] = {mode: -1 for mode in self.MODES}
        self._current_input: dict[str, str] = {mode: "" for mode in self.MODES}

        if history_file is None:
            self._history_file = Path.home() / ".artifice_history.json"
        else:
            self._history_file = Path(history_file)

        self._max_history_size = max_history_size
        self.load()

    def add(self, entry: str, mode: str) -> None:
        """Add entry to history for the specified mode.

        Args:
            entry: The history entry to add.
            mode: The mode ("python", "ai", or "shell").
        """
        if mode not in self._histories:
            return
        self._histories[mode].append(entry)
        if len(self._histories[mode]) > self._max_history_size:
            self._histories[mode].pop(0)
        self._indices[mode] = -1
        self._current_input[mode] = ""

    def navigate_back(self, mode: str, current_input: str) -> str | None:
        """Navigate to previous history entry.

        Args:
            mode: The mode ("python", "ai", or "shell").
            current_input: Current input text to save if starting navigation.

        Returns:
            The history entry to display, or None if at beginning.
        """
        if mode not in self._histories:
            return None

        history = self._histories[mode]
        if not history:
            return None

        index = self._indices[mode]

        if index == -1:
            self._current_input[mode] = current_input
            index = len(history)

        if index > 0:
            index -= 1
            result = history[index]
        else:
            result = None

        self._indices[mode] = index
        return result

    def navigate_forward(self, mode: str) -> str | None:
        """Navigate to next history entry.

        Args:
            mode: The mode ("python", "ai", or "shell").

        Returns:
            The history entry to display, or the original saved input if at end.
            Returns None if not currently browsing history.
        """
        if mode not in self._histories:
            return None

        history = self._histories[mode]
        index = self._indices[mode]

        if index == -1:
            return None

        if index < len(history) - 1:
            index += 1
            result = history[index]
        else:
            index = -1
            result = self._current_input[mode]
            self._current_input[mode] = ""

        self._indices[mode] = index
        return result

    def get_history(self, mode: str) -> list[str]:
        """Get history entries for the specified mode.

        Args:
            mode: The mode ("python", "ai", or "shell").

        Returns:
            List of history entries for the mode.
        """
        if mode not in self._histories:
            return []
        return self._histories[mode].copy()

    def clear(self) -> None:
        """Clear all history."""
        for mode in self.MODES:
            self._histories[mode].clear()
            self._indices[mode] = -1
            self._current_input[mode] = ""

    def load(self) -> None:
        """Load command history from disk."""
        try:
            if self._history_file.exists():
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for mode in self.MODES:
                            self._histories[mode] = data.get(mode, [])[
                                -self._max_history_size :
                            ]
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to load history from %s: invalid JSON - %s",
                self._history_file,
                e,
            )
            for mode in self.MODES:
                self._histories[mode] = []
        except Exception as e:
            logger.warning("Failed to load history from %s: %s", self._history_file, e)
            for mode in self.MODES:
                self._histories[mode] = []

    def save(self) -> None:
        """Save command history to disk."""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)

            history_to_save = {
                mode: self._histories[mode][-self._max_history_size :]
                for mode in self.MODES
            }

            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(history_to_save, f, indent=2)

            self._history_file.chmod(0o600)
        except OSError as e:
            logger.warning("Failed to save history to %s: %s", self._history_file, e)
        except Exception as e:
            logger.warning("Unexpected error saving history: %s", e)
