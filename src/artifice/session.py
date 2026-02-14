"""Session transcript management for Artifice.

This module handles saving session transcripts as timestamped markdown files
in ~/.artifice/sessions/
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from .config import ArtificeConfig

if TYPE_CHECKING:
    from .terminal_output import BaseBlock


class SessionTranscript:
    """Manages saving session transcripts to markdown files."""

    def __init__(self, sessions_dir: Path, config: ArtificeConfig):
        """Initialize session transcript manager.

        Args:
            sessions_dir: Directory where session files will be saved
        """
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.config = config

        # Generate session filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = self.sessions_dir / f"session_{timestamp}.md"

        # Track if we've written the header
        self._header_written = False

    def _ensure_header(self) -> None:
        """Write session header if not already written."""
        if self._header_written:
            return

        assert self.config.assistants
        assistant = self.config.assistants.get(self.config.assistant)
        assert assistant

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = f"""# Artifice Session
**Started:** {timestamp}
**Assistant:** {self.config.assistant}
Provider:** {assistant["provider"]} ({assistant["model"]})
**System Prompt:** {self.config.system_prompt}

---

"""
        with open(self.session_file, "w") as f:
            f.write(header)

        self._header_written = True

    def append_block(self, block: BaseBlock) -> None:
        """Append a block to the session transcript.

        Args:
            block: The block to append (CodeInputBlock, CodeOutputBlock, etc.)
        """
        self._ensure_header()

        # Import here to avoid circular imports

        markdown = self._block_to_markdown(block)
        if markdown:
            with open(self.session_file, "a") as f:
                f.write(markdown)
                f.write("\n\n")

    def _block_to_markdown(self, block: BaseBlock) -> str:
        """Convert a block to markdown format.

        Args:
            block: The block to convert

        Returns:
            Markdown representation of the block
        """
        from .terminal_output import (
            CodeInputBlock,
            CodeOutputBlock,
            AssistantInputBlock,
            AssistantOutputBlock,
            ThinkingOutputBlock,
        )

        if isinstance(block, AssistantInputBlock):
            prompt = block.get_prompt()
            return f"## User\n\n{prompt}"

        elif isinstance(block, ThinkingOutputBlock):
            content = block._full.strip()
            if content:
                return f"## Thinking\n\n<details>\n<summary>Thinking</summary>\n\n{content}\n\n</details>"
            return ""

        elif isinstance(block, AssistantOutputBlock):
            content = block._full.strip()
            if content:
                return f"## Assistant\n\n{content}"
            return ""

        elif isinstance(block, CodeInputBlock):
            code = block.get_code().strip()
            language = block._language
            return f"### {block._command_number} Code\n\n```{language}\n{code}\n```"

        elif isinstance(block, CodeOutputBlock):
            output = block._full.strip()
            if output:
                # Check if there were errors
                if block._has_error:
                    return f"### Output (error)\n\n```\n{output}\n```"
                else:
                    return f"### Output\n\n```\n{output}\n```"
            return ""

        # Unknown block type - skip
        return ""

    def finalize(self) -> None:
        """Finalize the session transcript (write footer)."""
        if not self._header_written:
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        footer = f"""---

**Ended:** {timestamp}
"""
        with open(self.session_file, "a") as f:
            f.write(footer)
