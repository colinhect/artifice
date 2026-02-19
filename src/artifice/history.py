"""History management for terminal input."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class History:
    """Manages command history for different input modes."""

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
        # Separate histories for Python, AI, and Shell modes
        self._python_history: list[str] = []
        self._ai_history: list[str] = []
        self._shell_history: list[str] = []
        self._python_history_index: int = -1  # -1 means not browsing history
        self._ai_history_index: int = -1
        self._shell_history_index: int = -1
        self._current_input: dict[str, str] = {
            "python": "",
            "ai": "",
            "shell": "",
        }  # Store current input per mode when browsing history

        # History persistence configuration
        if history_file is None:
            # Default to ~/.artifice_history.json
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
        if mode == "ai":
            self._ai_history.append(entry)
            if len(self._ai_history) > self._max_history_size:
                self._ai_history.pop(0)
            self._ai_history_index = -1
        elif mode == "shell":
            self._shell_history.append(entry)
            if len(self._shell_history) > self._max_history_size:
                self._shell_history.pop(0)
            self._shell_history_index = -1
        else:
            self._python_history.append(entry)
            if len(self._python_history) > self._max_history_size:
                self._python_history.pop(0)
            self._python_history_index = -1

        self._current_input[mode] = ""

    def _get_history_and_index(self, mode: str) -> tuple[list[str], int]:
        """Get the history list and current index for a mode."""
        if mode == "ai":
            return self._ai_history, self._ai_history_index
        elif mode == "shell":
            return self._shell_history, self._shell_history_index
        return self._python_history, self._python_history_index

    def _set_history_index(self, mode: str, index: int) -> None:
        """Set the history index for a mode."""
        if mode == "ai":
            self._ai_history_index = index
        elif mode == "shell":
            self._shell_history_index = index
        else:
            self._python_history_index = index

    def navigate_back(self, mode: str, current_input: str) -> str | None:
        """Navigate to previous history entry.

        Args:
            mode: The mode ("python", "ai", or "shell").
            current_input: Current input text to save if starting navigation.

        Returns:
            The history entry to display, or None if at beginning.
        """
        history, history_index = self._get_history_and_index(mode)

        if not history:
            return None

        # First time navigating up, save current input
        if history_index == -1:
            self._current_input[mode] = current_input
            history_index = len(history)

        # Move back in history
        if history_index > 0:
            history_index -= 1
            result = history[history_index]
        else:
            result = None

        self._set_history_index(mode, history_index)
        return result

    def navigate_forward(self, mode: str) -> str | None:
        """Navigate to next history entry.

        Args:
            mode: The mode ("python", "ai", or "shell").

        Returns:
            The history entry to display, or the original saved input if at end.
            Returns None if not currently browsing history.
        """
        history, history_index = self._get_history_and_index(mode)

        if history_index == -1:
            return None  # Not browsing history

        # Move forward in history
        if history_index < len(history) - 1:
            history_index += 1
            result = history[history_index]
        else:
            # Reached the end, restore original input
            history_index = -1
            result = self._current_input[mode]
            self._current_input[mode] = ""

        self._set_history_index(mode, history_index)
        return result

    def clear(self) -> None:
        """Clear all history."""
        self._python_history.clear()
        self._ai_history.clear()
        self._shell_history.clear()
        self._python_history_index = -1
        self._ai_history_index = -1
        self._shell_history_index = -1
        self._current_input = {"python": "", "ai": "", "shell": ""}

    def load(self) -> None:
        """Load command history from disk."""
        try:
            if self._history_file.exists():
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._python_history = data.get("python", [])[
                            -self._max_history_size :
                        ]
                        self._ai_history = data.get("ai", [])[-self._max_history_size :]
                        self._shell_history = data.get("shell", [])[
                            -self._max_history_size :
                        ]
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to load history from %s: invalid JSON - %s",
                self._history_file,
                e,
            )
            self._python_history = []
            self._ai_history = []
            self._shell_history = []
        except Exception as e:
            logger.warning("Failed to load history from %s: %s", self._history_file, e)
            self._python_history = []
            self._ai_history = []
            self._shell_history = []

    def save(self) -> None:
        """Save command history to disk."""
        try:
            # Ensure parent directory exists
            self._history_file.parent.mkdir(parents=True, exist_ok=True)

            # Keep only the most recent entries
            history_to_save = {
                "python": self._python_history[-self._max_history_size :],
                "ai": self._ai_history[-self._max_history_size :],
                "shell": self._shell_history[-self._max_history_size :],
            }

            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(history_to_save, f, indent=2)

            # Set restrictive permissions (user read/write only) for security
            self._history_file.chmod(0o600)
        except OSError as e:
            logger.warning("Failed to save history to %s: %s", self._history_file, e)
        except Exception as e:
            logger.warning("Unexpected error saving history: %s", e)
