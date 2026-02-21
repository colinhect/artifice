"""Input mode configuration for terminal."""

from __future__ import annotations

import enum
from dataclasses import dataclass


@dataclass(frozen=True)
class InputModeConfig:
    """Configuration for a terminal input mode."""

    name: str
    prompt_char: str
    language: str | None


class InputMode(enum.Enum):
    """Available input modes for the terminal."""

    AI = InputModeConfig("ai", ">", None)
    SHELL = InputModeConfig("shell", "$", "bash")
    PYTHON = InputModeConfig("python", "]", "python")

    @classmethod
    def from_name(cls, name: str) -> InputMode:
        """Get mode by name string."""
        for mode in cls:
            if mode.value.name == name:
                return mode
        raise ValueError(f"Unknown mode: {name}")

    @property
    def prompt_char(self) -> str:
        """Get the prompt character for this mode."""
        return self.value.prompt_char

    @property
    def language(self) -> str | None:
        """Get the syntax highlighting language for this mode."""
        return self.value.language

    @property
    def is_ai(self) -> bool:
        """True if this is AI mode."""
        return self == InputMode.AI

    @property
    def is_shell(self) -> bool:
        """True if this is shell mode."""
        return self == InputMode.SHELL

    @property
    def is_python(self) -> bool:
        """True if this is Python mode."""
        return self == InputMode.PYTHON

    def cycle_next(self) -> InputMode:
        """Get the next mode in the cycle (python -> ai -> shell -> python)."""
        if self == InputMode.PYTHON:
            return InputMode.AI
        if self == InputMode.AI:
            return InputMode.SHELL
        return InputMode.PYTHON
