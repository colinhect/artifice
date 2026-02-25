"""Simple command-line interface for artifice."""

from __future__ import annotations

import argparse
import asyncio
import datetime
import importlib.resources
import logging
import shutil
import sys
from pathlib import Path
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


def save_session(
    prompt: str,
    system_prompt: str | None,
    model: str,
    provider: str | None,
    response: str,
) -> Path | None:
    """Save prompt and response to a session markdown file.

    Returns the path to the saved file, or None if saving was disabled.
    """
    sessions_dir = Path.home() / ".artifice" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
    session_file = sessions_dir / f"{timestamp}.md"

    content = f"""# Session: {timestamp}

## Model
- **Provider**: {provider or "default"}
- **Model**: {model}

## System Prompt
{system_prompt or "(none)"}

## User Prompt
{prompt}

## Response
{response}
"""

    session_file.write_text(content, encoding="utf-8")
    return session_file


def install_config() -> None:
    """Install default configuration to ~/.artifice/."""
    from artifice.core.config import get_config_path, get_config_file_path

    config_dir = get_config_path()
    config_file = get_config_file_path()
    prompts_dir = config_dir / "prompts"

    if config_file.exists():
        print(f"Config already exists at {config_file}", file=sys.stderr)
        sys.exit(1)

    config_dir.mkdir(parents=True, exist_ok=True)

    try:
        example_config = importlib.resources.files("artifice.data").joinpath(
            "example.yaml"
        )
        with importlib.resources.as_file(example_config) as example_path:
            shutil.copy(example_path, config_file)
        print(f"Created {config_file}")

        prompts_source = importlib.resources.files("artifice.data.prompts")
        prompts_dir.mkdir(exist_ok=True)
        count = 0
        for prompt_file in prompts_source.iterdir():
            if prompt_file.is_file() and prompt_file.name.endswith(".md"):
                with importlib.resources.as_file(prompt_file) as prompt_path:
                    shutil.copy(prompt_path, prompts_dir / prompt_file.name)
                    count += 1
        print(f"Created {prompts_dir}/ ({count} prompts)")

        print("\nEdit the config file to customize your settings.")
    except Exception as e:
        print(f"Error creating config: {e}", file=sys.stderr)
        sys.exit(1)


async def run_prompt(
    agent: Agent,
    prompt: str,
    tool_approval: str | None = None,
    tool_allowlist: list[str] | None = None,
    tool_output: bool = False,
) -> str:
    """Run a prompt with optional tool support and interactive approval."""

    def on_chunk(chunk: str) -> None:
        print(chunk, end="", flush=True)

    final_text, _ = await run_agent_loop(
        agent, prompt, on_chunk, tool_approval, tool_allowlist, tool_output
    )

    return final_text


def _build_user_message(args: argparse.Namespace) -> str:
    """Build the prompt string from CLI args, stdin, and attached files."""
    prompt = args.prompt or ""

    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()
        if args.prompt and stdin_content.strip():
            prompt = f"{args.prompt}\n\n{stdin_content}"
        elif stdin_content.strip():
            prompt = stdin_content

    if not prompt.strip():
        return prompt

    if args.files:
        file_contents: list[str] = []
        for file_path in args.files:
            path = Path(file_path)
            if not path.is_file():
                print(f"Error: File not found: {file_path}", file=sys.stderr)
                sys.exit(1)
            try:
                content = path.read_text(encoding="utf-8")
                file_contents.append(f"--- {file_path} ---\n{content}")
            except Exception as e:
                print(f"Error reading {file_path}: {e}", file=sys.stderr)
                sys.exit(1)
        if file_contents:
            context = "\n\n".join(file_contents)
            prompt = f"{context}\n\n---\n\n{prompt}"

    return prompt


def main() -> None:
    """Main entry point for the art command."""
    parser = argparse.ArgumentParser(
        prog="art",
        description="Simple LLM prompt tool with tool support. Reads from stdin or argument, outputs to stdout.",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Prompt string (if not provided, reads from stdin)",
    )
    parser.add_argument(
        "-a",
        "--agent",
        default=None,
        help="Agent name from config (uses config default if not specified)",
    )
    parser.add_argument(
        "-p",
        "--prompt-name",
        default=None,
        help="Named prompt from config to use as system prompt",
    )
    parser.add_argument(
        "-s",
        "--system-prompt",
        default=None,
        help="System prompt for the model",
    )
    parser.add_argument(
        "--logging",
        action="store_true",
        help="Enable logging to stderr",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List available agent names",
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="List available prompt names",
    )
    parser.add_argument(
        "--get-current-agent",
        action="store_true",
        help="Print the current agent name and exit",
    )
    parser.add_argument(
        "--tools",
        default=None,
        help="Enable tools (provide comma-separated patterns, e.g., 'read,write', or '*')",
    )
    parser.add_argument(
        "--tool-approval",
        choices=["ask", "auto", "deny"],
        default=None,
        help="Tool approval mode: ask (interactive), auto (allow all), or deny (disable all)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install default configuration to ~/.artifice/",
    )
    parser.add_argument(
        "--add-prompt",
        metavar="FILE",
        help="Add a prompt from FILE to ~/.artifice/prompts/",
    )
    parser.add_argument(
        "--new-prompt",
        metavar="NAME",
        help="Create a new prompt with NAME in ~/.artifice/prompts/ (reads from stdin)",
    )
    parser.add_argument(
        "--no-session",
        action="store_true",
        help="Disable saving session to ~/.artifice/sessions/",
    )
    parser.add_argument(
        "--tool-output",
        action="store_true",
        help="Show tool call output (hidden by default)",
    )
    parser.add_argument(
        "-f",
        "--file",
        action="append",
        dest="files",
        metavar="FILE",
        help="Attach file(s) as context (can be specified multiple times)",
    )
    parser.add_argument(
        "-m",
        "--markdown",
        action="store_true",
        help="Render output as markdown in real-time using Textual",
    )
    args = parser.parse_args()

    if args.install:
        install_config()
        sys.exit(0)

    if args.add_prompt:
        from artifice.core.config import get_config_path

        prompts_dir = get_config_path() / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        source = Path(args.add_prompt)
        if not source.is_file():
            print(f"Error: File not found: {args.add_prompt}", file=sys.stderr)
            sys.exit(1)
        dest = prompts_dir / source.name
        if dest.exists():
            print(f"Error: Prompt already exists: {dest}", file=sys.stderr)
            sys.exit(1)
        shutil.copy(source, dest)
        print(f"Added prompt: {dest}")
        sys.exit(0)

    if args.new_prompt:
        from artifice.core.config import get_config_path

        prompts_dir = get_config_path() / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        name = args.new_prompt
        if not name.endswith(".md"):
            name += ".md"
        dest = prompts_dir / name
        if dest.exists():
            print(f"Error: Prompt already exists: {dest}", file=sys.stderr)
            sys.exit(1)
        if sys.stdin.isatty():
            print(
                f"Enter prompt content for '{args.new_prompt}'. "
                "Press Ctrl-D (or Ctrl-Z on Windows) to save.",
                file=sys.stderr,
            )
        content = sys.stdin.read()
        dest.write_text(content)
        print(f"Created prompt: {dest}")
        sys.exit(0)

    if args.logging:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )

    from artifice.core.config import load_config

    config, config_error = load_config()
    if config_error:
        print(f"Configuration error: {config_error}", file=sys.stderr)
        sys.exit(1)

    if args.list_agents:
        if config.agents:
            for name in config.agents:
                print(name)
        sys.exit(0)

    if args.list_prompts:
        from artifice.core.prompts import list_prompts

        prompts = list_prompts()
        if prompts:
            for name in prompts:
                print(name)
        sys.exit(0)

    if args.get_current_agent:
        agent_name = args.agent or config.agent
        if not agent_name:
            print("Error: No agent configured", file=sys.stderr)
            sys.exit(1)
        print(agent_name)
        sys.exit(0)

    prompt = _build_user_message(args)
    if not prompt.strip():
        sys.exit(0)

    from artifice.agent import Agent, AnyLLMProvider, resolve_agent_config

    try:
        agent_config = resolve_agent_config(config, args.agent)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    system_prompt = args.system_prompt
    if system_prompt is None:
        if args.prompt_name:
            from artifice.core.prompts import load_prompt

            prompt_result = load_prompt(args.prompt_name)
            if not prompt_result:
                print(
                    f"Error: Unknown prompt '{args.prompt_name}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            _, system_prompt = prompt_result
        else:
            system_prompt = agent_config.system_prompt

    tools = None
    if args.tools:
        tools = [pattern.strip() for pattern in args.tools.split(",")]
    elif agent_config.tools:
        tools = agent_config.tools
    elif config.tools:
        tools = config.tools

    tool_approval = args.tool_approval or config.tool_approval
    tool_allowlist = config.tool_allowlist

    provider_instance = AnyLLMProvider(
        model=agent_config.model,
        api_key=agent_config.api_key,
        provider=agent_config.provider,
        base_url=agent_config.base_url,
    )
    agent = Agent(
        provider=provider_instance,
        system_prompt=system_prompt,
        tools=tools,
    )

    try:
        if args.markdown:
            app = MarkdownStreamApp(
                agent=agent,
                prompt=prompt,
                tool_approval=tool_approval,
                tool_allowlist=tool_allowlist,
                tool_output=args.tool_output,
            )
            app.run(inline=True, inline_no_clear=True)
            response = app.final_text
        else:
            response = asyncio.run(
                run_prompt(
                    agent,
                    prompt,
                    tool_approval,
                    tool_allowlist,
                    tool_output=args.tool_output,
                )
            )
            if response and not response.endswith("\n"):
                print()

        if config.save_session and not args.no_session:
            save_session(
                prompt=prompt,
                system_prompt=system_prompt,
                model=agent_config.model,
                provider=agent_config.provider,
                response=response,
            )
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
