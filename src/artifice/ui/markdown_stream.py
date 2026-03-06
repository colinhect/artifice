"""Inline Textual app for streaming markdown output."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.events import Key
from textual.widgets import Markdown, Static

from artifice.agent.runner import run_agent_loop
from artifice.utils.theme import create_artifice_theme

if TYPE_CHECKING:
    from artifice.agent.client import Agent

logger = logging.getLogger(__name__)


class MarkdownStreamApp(App):
    """Inline Textual app for streaming markdown output."""

    CSS = """
    Screen {
        overflow-y: scroll;
    }
    Markdown {
        background: transparent;
        padding: 0;
        margin: 0;
    }
    #exit-hint {
        color: $text-muted;
        text-align: right;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        agent: Agent,
        prompt: str,
        tool_approval: str | None = None,
        tool_allowlist: list[str] | None = None,
        tool_output: bool = False,
    ) -> None:
        super().__init__()
        self._agent = agent
        self._prompt = prompt
        self._tool_approval = tool_approval
        self._tool_allowlist = tool_allowlist
        self._tool_output = tool_output
        self._markdown: Markdown | None = None
        self._stream = None
        self._final_text = ""
        self._streaming_done = False

    def compose(self) -> ComposeResult:
        self._markdown = Markdown("")
        yield self._markdown
        yield Static("", id="exit-hint")

    async def on_mount(self) -> None:
        self.register_theme(create_artifice_theme())
        self.theme = "artifice"
        if self._markdown is not None:
            self._stream = self._markdown.get_stream(self._markdown)
        self.run_worker(self._run_prompt())

    @property
    def final_text(self) -> str:
        return self._final_text

    def on_key(self, event: Key) -> None:
        if self._streaming_done and event.key in ("enter", "escape"):
            self.exit()

    async def _run_prompt(self) -> None:
        def on_chunk(chunk: str) -> None:
            if self._stream is not None:
                asyncio.create_task(self._stream.write(chunk))
            self.screen.scroll_end(animate=False)

        def on_tool_call(text: str) -> None:
            if self._stream is not None:
                asyncio.create_task(self._stream.write(text))
            self.screen.scroll_end(animate=False)

        final_text, _ = await run_agent_loop(
            self._agent,
            self._prompt,
            on_chunk,
            self._tool_approval,
            self._tool_allowlist,
            self._tool_output,
            on_tool_call,
        )
        self._final_text = final_text

        self._streaming_done = True
        self.query_one("#exit-hint", Static).update("Press Enter or Escape to exit")
