from __future__ import annotations

import os
from typing import Optional

from .common import AgentBase, AgentResponse

class CopilotAgent(AgentBase):
    """Agent for connecting to GitHub Copilot (placeholder implementation)."""

    def __init__(self, api_key: str | None = None):
        """Initialize Copilot agent.

        Args:
            api_key: GitHub API key. If None, reads from GITHUB_TOKEN env var.
        """
        self.api_key = api_key or os.environ.get("GITHUB_TOKEN")

    async def send_prompt(
        self, prompt: str, on_chunk: Optional[callable] = None
    ) -> AgentResponse:
        """Send a prompt to Copilot.

        Note: This is a placeholder implementation.
        GitHub Copilot doesn't have a public streaming API for chat.

        Args:
            prompt: The prompt text.
            on_chunk: Optional callback for streaming chunks.

        Returns:
            AgentResponse with error message.
        """
        return AgentResponse(
            text="",
            error="GitHub Copilot chat API not yet implemented. Use Claude instead.",
        )

